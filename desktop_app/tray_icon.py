"""Native Win32 System Tray Icon (Shell_NotifyIconW) with Pause toggle and Quit menu."""
import ctypes
from ctypes import wintypes
import threading
from typing import Callable, Optional

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

IDI_APPLICATION = 32512
TPM_LEFTALIGN = 0x0000
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080
MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MF_GRAYED = 0x0001
MF_CHECKED = 0x0008

ID_TRAY_STATUS = 1001
ID_TRAY_PAUSE = 1002
ID_TRAY_SHOW = 1003
ID_TRAY_QUIT = 1004

if ctypes.sizeof(ctypes.c_void_p) == 8:
    LRESULT = ctypes.c_longlong
else:
    LRESULT = ctypes.c_long

WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.DefWindowProcW.restype = LRESULT


class SystemTrayIcon:
    """Runs a native Windows tray icon with Pause/Resume, Show Popup, and Quit actions."""

    def __init__(
        self,
        on_toggle_pause: Callable[[], bool],
        on_show_popup: Callable[[], None],
        on_quit: Callable[[], None],
        initial_paused: bool = False,
    ):
        self.on_toggle_pause = on_toggle_pause
        self.on_show_popup = on_show_popup
        self.on_quit = on_quit
        self.paused = initial_paused
        self.extension_connected = False
        self._hwnd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._nid: Optional[NOTIFYICONDATAW] = None
        self._wndproc_ref = None
        self._ready = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    def stop(self) -> None:
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)

    def update_status(self, paused: bool, extension_connected: bool) -> None:
        self.paused = paused
        self.extension_connected = extension_connected
        if self._hwnd and self._nid:
            tip = self._build_tooltip()
            self._nid.szTip = tip[:127]
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))

    def _build_tooltip(self) -> str:
        state = "Paused" if self.paused else "Active"
        ext = "Extension Connected" if self.extension_connected else "Extension Waiting"
        return f"Humanize Helper ({state} · {ext})"

    def _run_loop(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        class_name = "HumanizeHelperTrayWndClass"

        def _wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_TRAYICON:
                if lparam == WM_RBUTTONUP:
                    self._show_context_menu(hwnd)
                    return 0
                elif lparam == WM_LBUTTONDBLCLK:
                    self.on_show_popup()
                    return 0
            elif msg == WM_CLOSE:
                if self._nid:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                user32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROC(_wnd_proc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            "HumanizeHelperTrayWindow",
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            hinst,
            None,
        )
        self._hwnd = hwnd

        hicon = user32.LoadIconW(None, ctypes.cast(IDI_APPLICATION, wintypes.LPCWSTR))
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = hicon
        nid.szTip = self._build_tooltip()[:127]
        self._nid = nid

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _show_context_menu(self, hwnd: int) -> None:
        hmenu = user32.CreatePopupMenu()
        if not hmenu:
            return
        try:
            status_label = (
                "Humanize Helper — Paused"
                if self.paused
                else "Humanize Helper — Active"
            )
            ext_label = (
                "Browser Extension: Connected ✓"
                if self.extension_connected
                else "Browser Extension: Disconnected"
            )
            user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED, ID_TRAY_STATUS, status_label)
            user32.AppendMenuW(hmenu, MF_STRING | MF_GRAYED, ID_TRAY_STATUS, ext_label)
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)

            pause_flags = MF_STRING | (MF_CHECKED if self.paused else 0)
            pause_text = "Pause Word Copy Detection"
            user32.AppendMenuW(hmenu, pause_flags, ID_TRAY_PAUSE, pause_text)
            user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_SHOW, "Show Floating Window")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, ID_TRAY_QUIT, "Quit Humanize Helper")

            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(
                hmenu,
                TPM_LEFTALIGN | TPM_RETURNCMD | TPM_NONOTIFY,
                pt.x,
                pt.y,
                0,
                hwnd,
                None,
            )
            if cmd == ID_TRAY_PAUSE:
                self.paused = self.on_toggle_pause()
                self.update_status(self.paused, self.extension_connected)
            elif cmd == ID_TRAY_SHOW:
                self.on_show_popup()
            elif cmd == ID_TRAY_QUIT:
                self.on_quit()
        finally:
            user32.DestroyMenu(hmenu)

