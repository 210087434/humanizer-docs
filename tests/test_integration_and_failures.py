"""Integration and failure tests using real Chromium + Mock Clever AI server + LocalBridgeServer."""
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from desktop_app.ws_server import LocalBridgeServer
from tests.mock_clever_server import MockCleverServer
from tests.test_unit import raw_ws_connect, ws_client_recv_json, ws_client_send_json

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CONFIG_JS_PATH = ROOT_DIR / "browser_extension" / "config.example.js"
CONTENT_JS_PATH = ROOT_DIR / "browser_extension" / "content.js"


class ChromiumCDPClient:
    """Minimal RFC 6455 CDP client to drive headless Chromium for integration testing."""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.reader = None
        self.writer = None
        self._msg_id = 0

    async def connect(self):
        import base64
        import os
        import urllib.parse

        parsed = urllib.parse.urlparse(self.ws_url)
        self.reader, self.writer = await asyncio.open_connection(parsed.hostname, parsed.port)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET {parsed.path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.writer.write(req.encode("ascii"))
        await self.writer.drain()
        await self.reader.readuntil(b"\r\n\r\n")

    async def call(self, method: str, params: dict | None = None) -> dict:
        self._msg_id += 1
        target_id = self._msg_id
        await ws_client_send_json(
            self.writer,
            {"id": target_id, "method": method, "params": params or {}},
        )
        while True:
            msg = await ws_client_recv_json(self.reader)
            if msg.get("id") == target_id:
                if "error" in msg:
                    raise RuntimeError(f"CDP Error: {msg['error']}")
                return msg.get("result", {})

    async def evaluate(self, expression: str, await_promise: bool = False):
        res = await self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
        )
        if "exceptionDetails" in res:
            raise RuntimeError(f"JS Exception: {res['exceptionDetails']}")
        return res.get("result", {}).get("value")

    async def close(self):
        if self.writer:
            self.writer.close()


class TestIntegrationAndFailures(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_http = MockCleverServer()
        cls.mock_http.start()

        cls.tmp_profile = tempfile.mkdtemp(prefix="hh_chromium_test_")
        cls.cdp_port = 59331
        cls.browser_proc = subprocess.Popen(
            [
                EDGE_PATH,
                "--headless=new",
                f"--user-data-dir={cls.tmp_profile}",
                f"--remote-debugging-port={cls.cdp_port}",
                "--no-first-run",
                "--no-default-browser-check",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for CDP endpoint to come up
        deadline = time.time() + 10.0
        cls.page_ws_url = None
        while time.time() < deadline:
            try:
                data = urllib.request.urlopen(
                    f"http://127.0.0.1:{cls.cdp_port}/json/list", timeout=1.0
                ).read()
                targets = json.loads(data.decode("utf-8"))
                for t in targets:
                    if t.get("type") == "page" and "webSocketDebuggerUrl" in t:
                        cls.page_ws_url = t["webSocketDebuggerUrl"]
                        break
                if cls.page_ws_url:
                    break
            except Exception:
                time.sleep(0.15)
        if not cls.page_ws_url:
            raise RuntimeError("Failed to attach to headless Chromium CDP target.")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.browser_proc.terminate()
            cls.browser_proc.wait(timeout=5)
        except Exception:
            pass
        shutil.rmtree(cls.tmp_profile, ignore_errors=True)
        cls.mock_http.stop()

    async def asyncSetUp(self):
        self.token = "integration_secret_token_9876543210"
        self.progress_updates = []
        self.server = LocalBridgeServer(
            host="127.0.0.1",
            port=0,
            auth_token=self.token,
            on_progress=lambda req_id, st, pct: self.progress_updates.append((st, pct)),
        )
        await self.server.start()
        self.cdp = ChromiumCDPClient(self.page_ws_url)
        await self.cdp.connect()
        await self.cdp.call("Page.enable")
        await self.cdp.call("Runtime.enable")

    async def asyncTearDown(self):
        await self.cdp.close()
        await self.server.stop()

    async def _load_mock_page_and_inject_content_script(self, mode: str = "normal"):
        url = f"{self.mock_http.base_url}/?mode={mode}"
        await self.cdp.call("Page.navigate", {"url": url})
        # Wait for document.readyState === 'complete'
        for _ in range(40):
            state = await self.cdp.evaluate("document.readyState")
            if state == "complete":
                break
            await asyncio.sleep(0.05)

        config_js = CONFIG_JS_PATH.read_text(encoding="utf-8")
        content_js = CONTENT_JS_PATH.read_text(encoding="utf-8")
        await self.cdp.evaluate(
            """(() => {
              const nativeAlert = window.alert;
              if (typeof nativeAlert !== "function" || window.__humanizeCopyAlertGuardInstalled) return;
              window.__humanizeCopyAlertGuardInstalled = true;
              window.alert = function (message) {
                if (/copy\\s+failed|failed\\s+to\\s+copy/i.test(String(message || ""))) return;
                return nativeAlert.apply(this, arguments);
              };
            })()"""
        )
        alert_suppressed = await self.cdp.evaluate(
            """(() => {
              alert("Copy failed, your browser may not support copying.");
              return window.__humanizeCopyAlertGuardInstalled === true;
            })()"""
        )
        self.assertTrue(alert_suppressed, "The page's blocking clipboard alert was not suppressed")
        extension_manifest = json.loads(
            (ROOT_DIR / "browser_extension" / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertFalse(
            any("page_guard.js" in script.get("js", []) for script in extension_manifest["content_scripts"]),
            "The extension manifest must not depend on the missing page_guard.js file.",
        )
        background_js = (ROOT_DIR / "browser_extension" / "background.js").read_text(encoding="utf-8")
        self.assertNotIn('files: ["page_guard.js"]', background_js)
        await self.cdp.evaluate(config_js)
        await self.cdp.evaluate("globalThis.__humanizeHelperContentLoaded = false;")
        await self.cdp.evaluate(content_js)

    async def _bridge_ws_to_chromium(self, reader, writer):
        """Relay HUMANIZE_REQUEST from LocalBridgeServer into Chromium's injected content.js."""
        req = await ws_client_recv_json(reader)
        req_id = req["requestId"]
        text = req["text"]

        # Run globalThis.__runCleverHumanizeFlow(req_id, text) inside real Chromium DOM
        js_call = f"globalThis.__runCleverHumanizeFlow({json.dumps(req_id)}, {json.dumps(text)})"
        response = await self.cdp.evaluate(js_call, await_promise=True)

        if response and response.get("ok"):
            await ws_client_send_json(
                writer,
                {
                    "type": "HUMANIZE_RESULT",
                    "requestId": req_id,
                    "text": response["text"],
                    "words": response.get("words", 0),
                    "token": self.token,
                },
            )
        else:
            await ws_client_send_json(
                writer,
                {
                    "type": "HUMANIZE_ERROR",
                    "requestId": req_id,
                    "code": (response or {}).get("code", "CLEVER_AI_ERROR"),
                    "message": (response or {}).get("message", "Unknown failure"),
                    "token": self.token,
                },
            )

    async def test_01_full_end_to_end_mock_clever_ai_flow(self):
        await self._load_mock_page_and_inject_content_script(mode="normal")
        _, reader, writer = await raw_ws_connect(self.server.port, self.token)
        await ws_client_recv_json(reader)  # WELCOME

        sample_input = (
            "In the pilot study, 42 participants recommended clearer instructions (R12).\n"
            "Second paragraph preserving special chars: 24/7, “quotes”, & Español."
        )

        bridge_task = asyncio.create_task(self._bridge_ws_to_chromium(reader, writer))
        result = await self.server.request_humanize(sample_input)
        await bridge_task

        self.assertEqual(result["type"], "HUMANIZE_RESULT", result)
        expected_output = (
            "[Humanized] In the pilot study, 42 participants recommended clearer instructions (R12).\n"
            "[Humanized] Second paragraph preserving special chars: 24/7, “quotes”, & Español."
        )
        self.assertEqual(result["text"], expected_output)

        # Verify every single step of 4a - 4f actually happened inside the DOM
        audit = await self.cdp.evaluate("window.__mockAudit")
        self.assertTrue(audit["clearStructuredClicked"], "Step 4a ('Clear & Structured') was not clicked")
        self.assertEqual(audit["styleSelected"], "academic")
        self.assertTrue(audit["removeTextClicked"], "Step 4b ('Remove text') was not clicked")
        self.assertEqual(audit["pastedText"], sample_input, "Step 4c (paste text) did not match")
        self.assertTrue(audit["humanizeClicked"], "Step 4d ('Humanize AI') was not clicked")
        self.assertFalse(audit["copyTextClicked"], "The site's clipboard button should not be clicked")
        self.assertEqual(
            audit.get("copyClickCount"),
            0,
            "The result should be read directly without triggering a background clipboard alert",
        )

        writer.close()

    async def test_02_failure_extension_disconnected_and_server_down(self):
        # 1. No extension connected at all
        res = await self.server.request_humanize("Some text from Word.")
        self.assertEqual(res["type"], "HUMANIZE_ERROR")
        self.assertEqual(res["code"], "EXTENSION_DISCONNECTED")
        self.assertIn("not connected", res["message"].lower())

        # 2. Extension connects, then abruptly drops mid-request (e.g. browser closed)
        _, reader, writer = await raw_ws_connect(self.server.port, self.token)
        await ws_client_recv_json(reader)

        async def _drop_mid_flight():
            _ = await ws_client_recv_json(reader)
            writer.close()
            await writer.wait_closed()

        drop_task = asyncio.create_task(_drop_mid_flight())
        res_mid = await self.server.request_humanize("Text while browser closes")
        await drop_task
        self.assertEqual(res_mid["type"], "HUMANIZE_ERROR")
        self.assertEqual(res_mid["code"], "EXTENSION_DISCONNECTED")

    async def test_03_failure_not_logged_in(self):
        await self._load_mock_page_and_inject_content_script(mode="not_logged_in")
        _, reader, writer = await raw_ws_connect(self.server.port, self.token)
        await ws_client_recv_json(reader)

        bridge_task = asyncio.create_task(self._bridge_ws_to_chromium(reader, writer))
        res = await self.server.request_humanize("Sample text while signed out.")
        await bridge_task

        self.assertEqual(res["type"], "HUMANIZE_ERROR")
        self.assertEqual(res["code"], "NOT_LOGGED_IN")
        self.assertIn("not logged in", res["message"].lower())
        writer.close()

    async def test_04_failure_clever_ai_error_modal(self):
        await self._load_mock_page_and_inject_content_script(mode="error_modal")
        _, reader, writer = await raw_ws_connect(self.server.port, self.token)
        await ws_client_recv_json(reader)

        bridge_task = asyncio.create_task(self._bridge_ws_to_chromium(reader, writer))
        res = await self.server.request_humanize("Sample text that triggers Clever AI error modal.")
        await bridge_task

        self.assertEqual(res["type"], "HUMANIZE_ERROR")
        self.assertEqual(res["code"], "CLEVER_AI_ERROR")
        self.assertIn("Text Not Ready", res["message"])
        writer.close()

    async def test_05_failure_empty_result_and_broken_layout_and_long_text(self):
        # Empty result
        await self._load_mock_page_and_inject_content_script(mode="empty_result")
        _, reader, writer = await raw_ws_connect(self.server.port, self.token)
        await ws_client_recv_json(reader)

        bridge_task = asyncio.create_task(self._bridge_ws_to_chromium(reader, writer))
        res_empty = await self.server.request_humanize("Sample text returning empty output.")
        await bridge_task
        self.assertEqual(res_empty["type"], "HUMANIZE_ERROR")
        self.assertEqual(res_empty["code"], "EMPTY_RESULT")

        # Broken layout
        await self._load_mock_page_and_inject_content_script(mode="broken_layout")
        bridge_task = asyncio.create_task(self._bridge_ws_to_chromium(reader, writer))
        res_layout = await self.server.request_humanize("Sample text on changed layout.")
        await bridge_task
        self.assertEqual(res_layout["type"], "HUMANIZE_ERROR")
        self.assertEqual(res_layout["code"], "LAYOUT_CHANGED")

        # Exceeding 3,000 words
        await self._load_mock_page_and_inject_content_script(mode="normal")
        bridge_task = asyncio.create_task(self._bridge_ws_to_chromium(reader, writer))
        huge_text = " ".join(["word"] * 3050)
        res_long = await self.server.request_humanize(huge_text)
        await bridge_task
        self.assertEqual(res_long["type"], "HUMANIZE_ERROR")
        self.assertEqual(res_long["code"], "TEXT_TOO_LONG")

        writer.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
