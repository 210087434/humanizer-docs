"""Unit tests for Humanize Helper: clipboard, Word detection, auth token, protocol, reconnect, and non-activating UI."""
import asyncio
import base64
import json
import os
import sys
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from desktop_app.app import ClipboardWatcher
from desktop_app.config import load_config
from desktop_app import dashboard
from desktop_app.popup_ui import HumanizePopup
from desktop_app.win32_bridge import (
    GWL_EXSTYLE,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    GetWindowLongPtrW,
    get_clipboard_text,
    is_word_process_name,
    make_preview,
    set_clipboard_text,
)
from desktop_app.ws_server import LocalBridgeServer


async def raw_ws_connect(port: int, token: str | None):
    """Helper to open a raw RFC 6455 client connection to 127.0.0.1:port."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    path = f"/ws?token={token}" if token is not None else "/ws"
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    writer.write(req.encode("ascii"))
    await writer.drain()
    status_line = await reader.readline()
    headers = await reader.readuntil(b"\r\n\r\n")
    return status_line.decode("latin-1").strip(), reader, writer


async def ws_client_send_json(writer: asyncio.StreamWriter, obj: dict):
    import struct

    payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    mask_key = b"\x12\x34\x56\x78"
    header = bytearray([0x81])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask_key)
    masked = bytearray(length)
    for i in range(length):
        masked[i] = payload[i] ^ mask_key[i % 4]
    writer.write(bytes(header) + bytes(masked))
    await writer.drain()


async def ws_client_recv_json(reader: asyncio.StreamReader) -> dict:
    import struct

    b1, b2 = await reader.readexactly(2)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]
    data = await reader.readexactly(length)
    return json.loads(data.decode("utf-8"))


class TestClipboardAndWordDetection(unittest.TestCase):
    def setUp(self):
        self._saved_clip = get_clipboard_text()

    def tearDown(self):
        if self._saved_clip:
            set_clipboard_text(self._saved_clip)

    def test_clipboard_roundtrip_special_chars_and_paragraphs(self):
        sample = (
            "First paragraph with statistics (42%, n = 18) — “quoted text”.\n\n"
            "Second paragraph with non-Latin & accents: Español, Português, Venda, 中文, 🚀."
        )
        ok = set_clipboard_text(sample)
        self.assertTrue(ok)
        read_back = get_clipboard_text().replace("\r\n", "\n")
        self.assertEqual(read_back, sample)

    def test_preview_formatting(self):
        long_text = "The pilot survey recorded 42 responses and practical recommendations (R12), including clearer instructions and shorter wait times."
        preview = make_preview(long_text, max_len=80)
        self.assertLessEqual(len(preview), 80)
        self.assertTrue(preview.endswith("…"))

    def test_word_process_detection_strict(self):
        self.assertTrue(is_word_process_name("WINWORD.EXE"))
        self.assertTrue(is_word_process_name("winword.exe"))
        self.assertFalse(is_word_process_name("opera.exe"))
        self.assertFalse(is_word_process_name("notepad.exe"))
        self.assertFalse(is_word_process_name("wordpad.exe"))
        self.assertFalse(is_word_process_name(None))
        self.assertFalse(is_word_process_name(""))

    def test_clipboard_watcher_ignores_non_word_and_debounces_rapid_copies(self):
        seq = [10]
        clip_text = ["Initial"]
        fg_state = [(False, 999)]  # Not Word initially

        watcher = ClipboardWatcher(
            seq_fn=lambda: seq[0],
            text_fn=lambda: clip_text[0],
            word_fg_fn=lambda: fg_state[0],
            debounce_sec=0.04,
        )

        # 1. Copy from browser (not Word) -> must be ignored
        seq[0] = 11
        clip_text[0] = "Copied from Opera"
        self.assertIsNone(watcher.poll())
        time.sleep(0.06)
        self.assertIsNone(watcher.poll())

        # 2. Switch foreground to Word (WINWORD.EXE) and simulate 3 rapid copies
        fg_state[0] = (True, 12345)
        seq[0] = 12
        clip_text[0] = "Copy 1"
        self.assertIsNone(watcher.poll())

        seq[0] = 13
        clip_text[0] = "Copy 2"
        self.assertIsNone(watcher.poll())

        seq[0] = 14
        clip_text[0] = "Final rapid copy from Word"
        self.assertIsNone(watcher.poll())

        time.sleep(0.06)
        result = watcher.poll()
        self.assertEqual(result, ("Final rapid copy from Word", 12345))

        # 3. Self clipboard write during Paste must be ignored
        seq[0] = 15
        clip_text[0] = "Humanized replacement text"
        watcher.mark_self_clipboard_write()
        self.assertIsNone(watcher.poll())
        time.sleep(0.06)
        self.assertIsNone(watcher.poll())

        # 4. Empty clipboard in Word must be ignored
        seq[0] = 16
        clip_text[0] = "   \n  "
        self.assertIsNone(watcher.poll())
        time.sleep(0.06)
        self.assertIsNone(watcher.poll())


class TestNonActivatingPopupWindow(unittest.TestCase):
    def test_popup_has_noactivate_and_toolwindow_exstyles(self):
        root = tk.Tk()
        try:
            popup = HumanizePopup(
                root=root,
                initial_x=120,
                initial_y=140,
                on_humanize=lambda: None,
                on_paste=lambda: None,
                on_undo=lambda: None,
                on_copy=lambda: True,
                on_position_changed=lambda x, y: None,
            )
            popup.show_copied("Sample highlighted sentence from Word.")
            root.update_idletasks()
            root.update()

            ex_style = GetWindowLongPtrW(popup._hwnd, GWL_EXSTYLE)
            self.assertTrue(bool(ex_style & WS_EX_NOACTIVATE), "Missing WS_EX_NOACTIVATE")
            self.assertTrue(bool(ex_style & WS_EX_TOOLWINDOW), "Missing WS_EX_TOOLWINDOW")
            self.assertTrue(bool(ex_style & WS_EX_TOPMOST), "Missing WS_EX_TOPMOST")
            popup.show_humanized("Complete humanized result.")
            root.update_idletasks()
            self.assertTrue(popup.copy_btn.winfo_manager(), "Copy button should be visible with humanized results")
            popup._on_copy_click(None)
            self.assertEqual(popup.copy_btn.cget("text"), "Copied")
            self.assertEqual(popup.status_label.cget("text"), "Copied to clipboard")
            self.assertFalse(hasattr(popup, "dot_label"), "Popup status should not use a decorative dot")
        finally:
            root.destroy()


class TestHumanizeDashboard(unittest.TestCase):
    def test_running_status_requires_a_valid_helper_process_marker(self):
        if sys.platform != "win32":
            self.skipTest("The installed helper dashboard is Windows-only.")

        with tempfile.TemporaryDirectory() as temp_dir:
            marker = Path(temp_dir) / "helper.pid"
            previous_path = dashboard.PID_PATH
            dashboard.PID_PATH = marker
            try:
                marker.write_text(str(os.getpid()), encoding="ascii")
                self.assertTrue(dashboard._helper_is_running())
                marker.write_text("not-a-process-id", encoding="ascii")
                self.assertFalse(dashboard._helper_is_running())
            finally:
                dashboard.PID_PATH = previous_path


class TestWebSocketProtocolAuthAndReconnect(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.token = "test_secret_token_0123456789abcdef"
        self.progress_events = []
        self.server = LocalBridgeServer(
            host="127.0.0.1",
            port=0,  # Ephemeral port for unit test
            auth_token=self.token,
            on_progress=lambda req_id, st, pct: self.progress_events.append((st, pct)),
        )
        await self.server.start()
        self.port = self.server.port

    async def asyncTearDown(self):
        await self.server.stop()

    async def test_rejects_missing_or_wrong_token(self):
        status_missing, _, w1 = await raw_ws_connect(self.port, None)
        w1.close()
        self.assertIn("403 Forbidden", status_missing)

        status_wrong, _, w2 = await raw_ws_connect(self.port, "wrong_token_value")
        w2.close()
        self.assertIn("403 Forbidden", status_wrong)
        self.assertFalse(self.server.has_connected_extension)

    async def test_accepts_valid_token_and_completes_request_cycle(self):
        status_ok, reader, writer = await raw_ws_connect(self.port, self.token)
        self.assertIn("101 Switching Protocols", status_ok)

        welcome = await ws_client_recv_json(reader)
        self.assertEqual(welcome["type"], "WELCOME")
        self.assertTrue(self.server.has_connected_extension)

        # Simulate extension client task responding to HUMANIZE_REQUEST
        async def _mock_extension():
            req = await ws_client_recv_json(reader)
            self.assertEqual(req["type"], "HUMANIZE_REQUEST")
            req_id = req["requestId"]
            await ws_client_send_json(
                writer,
                {
                    "type": "HUMANIZE_PROGRESS",
                    "requestId": req_id,
                    "status": "Refining your content…",
                    "percent": 42,
                    "token": self.token,
                },
            )
            await asyncio.sleep(0.05)
            await ws_client_send_json(
                writer,
                {
                    "type": "HUMANIZE_RESULT",
                    "requestId": req_id,
                    "text": "Humanized paragraph one.\n\nHumanized paragraph two.",
                    "words": 6,
                    "token": self.token,
                },
            )

        ext_task = asyncio.create_task(_mock_extension())
        result = await self.server.request_humanize("Original paragraph one.\n\nOriginal paragraph two.")
        await ext_task

        self.assertEqual(result["type"], "HUMANIZE_RESULT")
        self.assertEqual(result["text"], "Humanized paragraph one.\n\nHumanized paragraph two.")
        self.assertEqual(self.progress_events, [("Refining your content…", 42)])

        writer.close()

    async def test_reconnect_and_busy_guard(self):
        # Connect first client, then close it, then connect second client (simulating MV3 service worker wake)
        _, r1, w1 = await raw_ws_connect(self.port, self.token)
        await ws_client_recv_json(r1)
        w1.close()
        await asyncio.sleep(0.05)

        _, r2, w2 = await raw_ws_connect(self.port, self.token)
        await ws_client_recv_json(r2)
        self.assertTrue(self.server.has_connected_extension)

        # Start a slow request and verify a second concurrent request returns BUSY immediately
        async def _slow_extension():
            req = await ws_client_recv_json(r2)
            await asyncio.sleep(0.25)
            await ws_client_send_json(
                w2,
                {
                    "type": "HUMANIZE_RESULT",
                    "requestId": req["requestId"],
                    "text": "Completed first request.",
                    "words": 3,
                    "token": self.token,
                },
            )

        ext_task = asyncio.create_task(_slow_extension())
        first_task = asyncio.create_task(self.server.request_humanize("First input text"))
        await asyncio.sleep(0.05)

        second_res = await self.server.request_humanize("Second concurrent click")
        self.assertEqual(second_res["type"], "HUMANIZE_ERROR")
        self.assertEqual(second_res["code"], "BUSY")

        first_res = await first_task
        await ext_task
        self.assertEqual(first_res["type"], "HUMANIZE_RESULT")
        w2.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
