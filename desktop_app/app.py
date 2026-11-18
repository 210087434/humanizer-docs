"""Main entrypoint and controller for Humanize Helper desktop app."""
import asyncio
import ctypes
import os
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from typing import Callable, Optional, Tuple

# Ensure parent directory is in sys.path when launched directly
ROOT_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from desktop_app.config import LOG_PATH, PID_PATH, STOP_PATH, load_config, save_config, sync_extension_config
from desktop_app.popup_ui import HumanizePopup
from desktop_app.tray_icon import SystemTrayIcon
from desktop_app.win32_bridge import (
    get_clipboard_sequence_number,
    get_clipboard_text,
    is_word_foreground,
    paste_into_word,
    set_clipboard_text,
    undo_in_word,
)
from desktop_app.ws_server import LocalBridgeServer


class ClipboardWatcher:
    """
    Lightweight clipboard state detector that only triggers when:
    1. Watcher is not paused
    2. Clipboard sequence number changed (and wasn't written by our own Paste action)
    3. Current foreground process is Microsoft Word (WINWORD.EXE)
    4. Clipboard text is non-empty
    """

    def __init__(
        self,
        seq_fn: Callable[[], int] = get_clipboard_sequence_number,
        text_fn: Callable[[], str] = get_clipboard_text,
        word_fg_fn: Callable[[], Tuple[bool, Optional[int]]] = is_word_foreground,
        debounce_sec: float = 0.08,
    ):
        self.seq_fn = seq_fn
        self.text_fn = text_fn
        self.word_fg_fn = word_fg_fn
        self.debounce_sec = debounce_sec

        self.last_seq = self.seq_fn()
        self.ignored_seq: Optional[int] = None
        self.paused = False
        self._pending_seq: Optional[int] = None
        self._pending_time: float = 0.0
        self._pending_hwnd: Optional[int] = None

    def mark_self_clipboard_write(self) -> None:
        self.ignored_seq = self.seq_fn()
        self.last_seq = self.ignored_seq

    def poll(self) -> Optional[Tuple[str, int]]:
        """
        Poll once. Returns (copied_text, word_hwnd) when a valid Word copy completes,
        or None otherwise.
        """
        cur_seq = self.seq_fn()
        if cur_seq != self.last_seq:
            self.last_seq = cur_seq
            if self.paused or cur_seq == self.ignored_seq:
                self._pending_seq = None
                return None

            is_word, hwnd = self.word_fg_fn()
            if not is_word:
                self._pending_seq = None
                return None

            self._pending_seq = cur_seq
            self._pending_time = time.monotonic()
            self._pending_hwnd = hwnd
            return None

        if self._pending_seq is not None:
            if (time.monotonic() - self._pending_time) >= self.debounce_sec:
                self._pending_seq = None
                text = self.text_fn()
                if text and text.strip():
                    return text, (self._pending_hwnd or 0)
        return None


class HumanizeHelperApp:
    """Coordinates the popup UI, clipboard watcher, WebSocket bridge, and system tray."""

    def __init__(self):
        self.cfg = load_config()
        sync_extension_config(self.cfg)

        self.original_text: str = ""
        self.humanized_text: str = ""
        self.last_word_hwnd: Optional[int] = None

        self.root = tk.Tk()
        self.watcher = ClipboardWatcher()
        self.watcher.paused = bool(self.cfg.get("paused", False))

        self.popup = HumanizePopup(
            root=self.root,
            initial_x=self.cfg.get("popup_x"),
            initial_y=self.cfg.get("popup_y"),
            on_humanize=self._on_click_humanize,
            on_paste=self._on_click_paste,
            on_undo=self._on_click_undo,
            on_copy=self._on_click_copy,
            on_position_changed=self._on_popup_moved,
        )

        self.loop = asyncio.new_event_loop()
        self.ws_server = LocalBridgeServer(
            host="127.0.0.1",
            port=int(self.cfg["port"]),
            auth_token=str(self.cfg["auth_token"]),
            on_progress=self._on_ws_progress,
            on_result=self._on_ws_result,
            on_error=self._on_ws_error,
            on_connection_change=self._on_ws_connection_change,
        )

        self.tray = SystemTrayIcon(
            on_toggle_pause=self._toggle_pause,
            on_show_popup=lambda: self.root.after(0, self.popup.show_without_focus),
            on_quit=lambda: self.root.after(0, self.shutdown),
            initial_paused=self.watcher.paused,
        )

    def _start_async_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self.ws_server.start())
            PID_PATH.parent.mkdir(parents=True, exist_ok=True)
            PID_PATH.write_text(str(os.getpid()), encoding="ascii")
        except Exception:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as log_file:
                log_file.write(
                    f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Could not start local bridge:\n"
                    f"{traceback.format_exc()}\n"
                )
            self.root.after(0, self._on_server_start_failed)
            return
        self.loop.run_forever()

    def _on_server_start_failed(self) -> None:
        messagebox.showerror(
            "Humanize Helper could not start",
            f"The local bridge could not start.\n\nDetails: {LOG_PATH}",
            parent=self.root,
        )
        self.shutdown()

    def _on_popup_moved(self, x: int, y: int) -> None:
        self.cfg["popup_x"] = x
        self.cfg["popup_y"] = y
        save_config(self.cfg)

    def _toggle_pause(self) -> bool:
        self.watcher.paused = not self.watcher.paused
        self.cfg["paused"] = self.watcher.paused
        save_config(self.cfg)
        return self.watcher.paused

    def _on_ws_connection_change(self, connected: bool) -> None:
        self.tray.update_status(self.watcher.paused, connected)
        if self.popup.state == "READY":
            self.root.after(0, lambda: self.popup.show_ready(extension_connected=connected))

    def _on_ws_progress(self, req_id: str, status: str, percent: int) -> None:
        self.root.after(0, lambda: self.popup.show_humanizing(status, percent))

    def _on_ws_result(self, req_id: str, text: str, words: int) -> None:
        self.humanized_text = text
        set_clipboard_text(text)
        self.watcher.mark_self_clipboard_write()
        self.root.after(0, lambda: self.popup.show_humanized(text))

    def _on_ws_error(self, req_id: str, code: str, message: str) -> None:
        self.root.after(0, lambda: self.popup.show_error(message))

    def _on_click_humanize(self) -> None:
        if self.ws_server.is_busy:
            return
        if not self.original_text or not self.original_text.strip():
            self.popup.show_error("No copied text to humanize. Please highlight and copy text in Word.")
            return

        words = len(self.original_text.split())
        if words > 3000:
            self.popup.show_error(
                f"Selection is {words:,} words, exceeding Clever AI's 3,000-word limit per request."
            )
            return

        self.popup.show_humanizing("Sending text to Clever AI in background…", 0)

        async def _dispatch():
            res = await self.ws_server.request_humanize(
                self.original_text,
                timeout_sec=float(self.cfg.get("humanize_timeout_sec", 180)),
            )
            if res.get("type") == "HUMANIZE_ERROR":
                msg = res.get("message", "Humanize failed.")
                self.root.after(0, lambda: self.popup.show_error(msg))

        asyncio.run_coroutine_threadsafe(_dispatch(), self.loop)

    def _on_click_paste(self) -> None:
        if not self.humanized_text:
            self.popup.show_error("No humanized result available to paste.")
            return

        # Pre-set clipboard and mark as self-write so ClipboardWatcher ignores it
        set_clipboard_text(self.humanized_text)
        self.watcher.mark_self_clipboard_write()

        ok, msg = paste_into_word(self.last_word_hwnd, self.humanized_text)
        self.watcher.mark_self_clipboard_write()

        if ok:
            self.popup.show_pasted(msg)
        else:
            self.popup.show_error(msg)

    def _on_click_copy(self) -> bool:
        if not self.humanized_text:
            return False

        if not set_clipboard_text(self.humanized_text):
            return False

        self.watcher.mark_self_clipboard_write()
        return True

    def _on_click_undo(self) -> None:
        ok, msg = undo_in_word(self.last_word_hwnd, self.original_text)
        if self.original_text:
            set_clipboard_text(self.original_text)
            self.watcher.mark_self_clipboard_write()
        if ok:
            self.popup.show_copied(self.original_text)
        else:
            self.popup.show_error(msg)

    def _poll_clipboard_tick(self) -> None:
        if STOP_PATH.exists():
            STOP_PATH.unlink()
            self.shutdown()
            return

        res = self.watcher.poll()
        if res is not None:
            copied_text, word_hwnd = res
            self.original_text = copied_text
            self.humanized_text = ""
            if word_hwnd:
                self.last_word_hwnd = word_hwnd
            # Only overwrite popup if not mid-humanization, or if user copied new text
            if not self.ws_server.is_busy:
                self.popup.show_copied(copied_text)
        self.root.after(120, self._poll_clipboard_tick)

    def run(self) -> None:
        PID_PATH.parent.mkdir(parents=True, exist_ok=True)
        STOP_PATH.unlink(missing_ok=True)
        PID_PATH.unlink(missing_ok=True)
        ws_thread = threading.Thread(target=self._start_async_loop, daemon=True)
        ws_thread.start()
        self.tray.start()
        self.root.after(150, self._poll_clipboard_tick)
        try:
            self.root.mainloop()
        finally:
            try:
                if PID_PATH.read_text(encoding="ascii").strip() == str(os.getpid()):
                    PID_PATH.unlink()
            except FileNotFoundError:
                pass

    def shutdown(self) -> None:
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            fut = asyncio.run_coroutine_threadsafe(self.ws_server.stop(), self.loop)
            fut.result(timeout=2.0)
            self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception:
            pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass


def main() -> None:
    if "--dashboard" in sys.argv:
        from desktop_app.dashboard import run_dashboard

        run_dashboard()
        return
    if "--prepare-extension" in sys.argv:
        load_config()
        return

    # Single-instance mutex check; if already running, bring existing window to visible state
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    _mutex = kernel32.CreateMutexW(None, False, "Local\\HumanizeHelperSingleInstanceMutex")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        existing_hwnd = user32.FindWindowW(None, "HumanizeHelperFloatingWindow")
        if existing_hwnd:
            user32.ShowWindow(existing_hwnd, 5)  # SW_SHOW
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(
                f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Another Humanize Helper instance is already running.\n"
            )
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(
                None,
                "Another Humanize Helper instance is already running. Close the older helper from its system-tray menu, then try again.",
                "Humanize Helper",
                0x30,
            )
        return

    try:
        app = HumanizeHelperApp()
        app.run()
    except Exception as exc:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(
                f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Helper startup failed:\n"
                f"{traceback.format_exc()}\n"
            )
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(
                None,
                f"Humanize Helper could not start.\n\n{exc}\n\nDetails: {LOG_PATH}",
                "Humanize Helper",
                0x10,
            )


if __name__ == "__main__":
    main()
