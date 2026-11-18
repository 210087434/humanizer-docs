"""Windows dashboard for starting and stopping the Humanize Helper service."""
import ctypes
import os
import subprocess
import sys
import tkinter as tk
import time
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

from desktop_app.config import EXTENSION_DIR, LOG_PATH, PID_PATH, STOP_PATH, load_config


def _helper_is_running() -> bool:
    try:
        pid = int(PID_PATH.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return False

    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_ulong(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return False
        process_image = Path(buffer.value).resolve()
        expected_image = Path(sys.executable).resolve()
        if getattr(sys, "frozen", False):
            return process_image.as_posix().casefold() == expected_image.as_posix().casefold()
        return (
            process_image.as_posix().casefold() == expected_image.as_posix().casefold()
            or process_image.name.casefold().startswith("python")
            and expected_image.name.casefold().startswith("python")
        )
    finally:
        kernel32.CloseHandle(handle)


class HumanizeDashboard:
    def __init__(self):
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.title("Humanize Helper Dashboard")
        self.root.geometry("620x470")
        self.root.resizable(False, False)
        self.root.configure(bg="#101713")
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Dashboard.TCombobox",
            fieldbackground="#202d25",
            background="#202d25",
            foreground="#e7f2eb",
            arrowcolor="#b7c9bd",
            bordercolor="#314638",
            lightcolor="#314638",
            darkcolor="#314638",
            padding=(8, 7),
        )
        style.map(
            "Dashboard.TCombobox",
            fieldbackground=[("readonly", "#202d25")],
            foreground=[("readonly", "#e7f2eb")],
            selectbackground=[("readonly", "#202d25")],
            selectforeground=[("readonly", "#e7f2eb")],
        )

        content = tk.Frame(self.root, bg="#101713")
        content.pack(fill=tk.BOTH, expand=True, padx=34, pady=(27, 18))

        tk.Label(
            content,
            text="Humanize Helper",
            bg="#101713",
            fg="#e7f2eb",
            font=("Segoe UI", 23, "bold"),
        ).pack(anchor="w")

        self.status_panel = tk.Frame(
            content,
            bg="#18231d",
            highlightbackground="#2b4033",
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        self.status_panel.pack(fill=tk.X, pady=(24, 27))

        status_row = tk.Frame(self.status_panel, bg="#18231d")
        status_row.pack(fill=tk.X)
        self.status_label = tk.Label(
            status_row,
            text="Checking helper status",
            bg="#18231d",
            fg="#d6b86a",
            font=("Segoe UI", 14, "bold"),
            anchor="w",
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.toggle_button = self._make_button(
            status_row, "Turn on", self.toggle_helper, primary=True
        )
        self.toggle_button.pack(side=tk.RIGHT, padx=(14, 0))

        self.extension_status = tk.Label(
            self.status_panel,
            text="Checking browser extension",
            bg="#18231d",
            fg="#a9bdb0",
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.extension_status.pack(anchor="w", fill=tk.X, pady=(10, 0))

        tk.Label(
            content,
            text="Browser extension",
            bg="#101713",
            fg="#e7f2eb",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            content,
            text="On the extensions page, turn on Developer mode and choose Load unpacked. Select the browser_extension folder; click Reload after updates.",
            wraplength=540,
            justify="left",
            bg="#101713",
            fg="#a9bdb0",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(7, 14))

        browser_row = tk.Frame(content, bg="#101713")
        browser_row.pack(anchor="w", fill=tk.X)
        self.browser = ttk.Combobox(
            browser_row, state="readonly", width=12,
            values=("Chrome", "Edge", "Opera"), style="Dashboard.TCombobox"
        )
        self.browser.current(0)
        self.browser.pack(side="left", padx=(0, 10), ipady=3)
        self._make_button(
            browser_row, "Open extensions", self.open_browser_settings
        ).pack(side="left")
        self._make_button(
            browser_row, "Show extension folder", self.open_extension_folder
        ).pack(side="left", padx=(9, 0))

        tk.Label(
            content,
            text="Developed by Thendo Aubrey Nemafhohoni",
            bg="#101713",
            fg="#73877b",
            font=("Segoe UI", 9),
        ).pack(anchor="w", side="bottom", pady=(18, 0))
        self.refresh_status()

    @staticmethod
    def _make_button(parent, text, command, primary=False):
        background = "#35bd83" if primary else "#26372e"
        foreground = "#092017" if primary else "#e7f2eb"
        hover_background = "#52d39b" if primary else "#33483b"
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=hover_background,
            activeforeground=foreground,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=14,
            pady=9,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            takefocus=False,
        )
        button._base_background = background
        button._hover_background = hover_background
        button.bind("<Enter>", lambda _event: button.configure(bg=button._hover_background))
        button.bind("<Leave>", lambda _event: button.configure(bg=button._base_background))
        return button

    def _extension_connected(self) -> bool:
        token = self.cfg.get("auth_token", "")
        port = self.cfg.get("port")
        if not token or not port:
            return False
        try:
            with urlopen(
                f"http://127.0.0.1:{int(port)}/health?token={token}",
                timeout=0.25,
            ) as response:
                import json

                return bool(json.loads(response.read().decode("utf-8")).get("extensionConnected"))
        except (OSError, ValueError, URLError):
            return False

    def toggle_helper(self):
        if _helper_is_running():
            try:
                STOP_PATH.parent.mkdir(parents=True, exist_ok=True)
                STOP_PATH.write_text("stop", encoding="ascii")
                self.status_label.configure(text="Turning helper off", fg="#d6b86a")
                self.toggle_button.configure(state="disabled")
            except OSError as exc:
                messagebox.showerror("Could not stop Humanize Helper", str(exc), parent=self.root)
        else:
            try:
                STOP_PATH.unlink(missing_ok=True)
                if getattr(sys, "frozen", False):
                    command = [sys.executable, "--helper"]
                    working_directory = Path(sys.executable).resolve().parent
                else:
                    command = [sys.executable, "-m", "desktop_app.app", "--helper"]
                    working_directory = Path(__file__).resolve().parent.parent
                process = subprocess.Popen(command, cwd=str(working_directory))
                self.status_label.configure(text="Starting helper", fg="#d6b86a")
                self.toggle_button.configure(text="Starting", state="disabled")
                self.root.after(500, lambda: self._check_startup(process, time.monotonic() + 10))
            except OSError as exc:
                messagebox.showerror("Could not start Humanize Helper", str(exc), parent=self.root)
        self.root.after(500, self.refresh_status)

    def _check_startup(self, process: subprocess.Popen, deadline: float) -> None:
        if _helper_is_running():
            self.refresh_status()
            return
        if process.poll() is not None or time.monotonic() >= deadline:
            self.refresh_status()
            details = ""
            try:
                details = LOG_PATH.read_text(encoding="utf-8")[-3000:]
            except OSError:
                pass
            message = "Humanize Helper did not start."
            if details:
                message += f"\n\nDetails from helper.log:\n{details}"
            else:
                message += f"\n\nSee {LOG_PATH} for startup details."
            messagebox.showerror("Could not start Humanize Helper", message, parent=self.root)
            return
        self.root.after(500, lambda: self._check_startup(process, deadline))

    def refresh_status(self):
        running = _helper_is_running()
        extension_connected = running and self._extension_connected()
        self.status_label.configure(
            text=("Helper is running" if running else "Helper is off"),
            fg=("#62d49d" if running else "#c1cec5"),
        )
        self.extension_status.configure(
            text=(
                "Browser extension connected"
                if extension_connected
                else "Browser extension not connected. Open your browser’s extensions page to enable or reload it."
                if running
                else "Turn on the helper to check the browser extension."
            ),
            fg=(
                "#62d49d"
                if extension_connected
                else "#d6b86a"
                if running
                else "#91a398"
            ),
        )
        self.toggle_button.configure(
            text=("Turn off" if running else "Turn on"),
            bg=("#26372e" if running else "#35bd83"),
            fg=("#e7f2eb" if running else "#092017"),
            activebackground=("#33483b" if running else "#52d39b"),
            activeforeground=("#e7f2eb" if running else "#092017"),
            state="normal",
        )
        self.toggle_button._base_background = "#26372e" if running else "#35bd83"
        self.toggle_button._hover_background = "#33483b" if running else "#52d39b"
        self.root.after(1000, self.refresh_status)

    def open_browser_settings(self):
        browser_urls = {
            "Chrome": "chrome://extensions",
            "Edge": "edge://extensions",
            "Opera": "opera://extensions",
        }
        try:
            os.startfile(browser_urls[self.browser.get()])
        except (AttributeError, OSError):
            if not webbrowser.open(browser_urls[self.browser.get()]):
                messagebox.showerror("Could not open browser", "Open your browser's extensions page manually.", parent=self.root)

    def open_extension_folder(self):
        if not EXTENSION_DIR.is_dir():
            messagebox.showerror("Extension files missing", f"Could not find:\n{EXTENSION_DIR}", parent=self.root)
            return
        os.startfile(str(EXTENSION_DIR))


def run_dashboard():
    HumanizeDashboard().root.mainloop()
