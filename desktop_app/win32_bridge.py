"""Win32 API bridge for clipboard, Word foreground detection, non-activating window, and keystrokes."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Tuple

WORD_COM_HELPER_EXE = (
    Path(sys.executable).resolve().parent / "word_com_helper.exe"
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent / "word_com_helper.exe"
)
CREATE_NO_WINDOW = 0x08000000


def call_word_com_helper(cmd: str, stdin_text: str = "") -> Dict[str, Any]:
    """Invoke word_com_helper.exe to inspect/verify Word selection, paste, and formatting."""
    if not WORD_COM_HELPER_EXE.exists():
        return {"ok": False, "error": "HELPER_MISSING"}
    try:
        proc = subprocess.run(
            [str(WORD_COM_HELPER_EXE), cmd],
            input=stdin_text.encode("utf-8") if stdin_text else b"",
            capture_output=True,
            timeout=4.0,
            creationflags=CREATE_NO_WINDOW,
        )
        out = proc.stdout.decode("utf-8", errors="replace").strip()
        if out:
            return json.loads(out.splitlines()[-1])
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": "EMPTY_OUTPUT"}

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Constants
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

GWL_EXSTYLE = -20
GWL_WNDPROC = -4
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_FRAMECHANGED = 0x0020

WM_MOUSEACTIVATE = 0x0021
MA_NOACTIVATE = 3

SW_RESTORE = 9
SW_SHOW = 5

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_V = 0x56
VK_Z = 0x5A
VK_C = 0x43

# Function signatures
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL

user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

if ctypes.sizeof(ctypes.c_void_p) == 8:
    LONG_PTR = ctypes.c_longlong
    GetWindowLongPtrW = user32.GetWindowLongPtrW
    SetWindowLongPtrW = user32.SetWindowLongPtrW
else:
    LONG_PTR = ctypes.c_long
    GetWindowLongPtrW = user32.GetWindowLongW
    SetWindowLongPtrW = user32.SetWindowLongW

GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
GetWindowLongPtrW.restype = LONG_PTR
SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
SetWindowLongPtrW.restype = LONG_PTR

user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL

WNDPROC = ctypes.WINFUNCTYPE(LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.CallWindowProcW.argtypes = [LONG_PTR, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.CallWindowProcW.restype = LONG_PTR


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

# Keep references to subclassed WNDPROCs so GC never collects them
_SUBCLASSED_PROCS = {}


def get_window_process_info(hwnd: Optional[int]) -> Tuple[Optional[str], int]:
    """Return (executable_basename_upper, pid) for a given HWND."""
    if not hwnd:
        return None, 0
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return None, 0
    hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not hproc:
        return None, pid.value
    try:
        buf_len = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(buf_len)):
            exe_name = os.path.basename(buf.value).upper()
            return exe_name, pid.value
    finally:
        kernel32.CloseHandle(hproc)
    return None, pid.value


def get_foreground_process_info() -> Tuple[Optional[int], Optional[str], int]:
    """Return (hwnd, exe_name_upper, pid) of the current foreground window."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, None, 0
    exe_name, pid = get_window_process_info(hwnd)
    return hwnd, exe_name, pid


def is_word_process_name(exe_name: Optional[str]) -> bool:
    """Return True only if the executable name is Microsoft Word (WINWORD.EXE)."""
    if not exe_name:
        return False
    return exe_name.strip().upper() == "WINWORD.EXE"


def is_word_foreground() -> Tuple[bool, Optional[int]]:
    """Return (True, word_hwnd) if Microsoft Word is currently the foreground window."""
    hwnd, exe_name, _ = get_foreground_process_info()
    if is_word_process_name(exe_name):
        return True, hwnd
    # If GetForegroundWindow() returns 0 (e.g. non-interactive desktop station), check Word COM active window
    if not hwnd:
        status = call_word_com_helper("status")
        if status.get("ok") and status.get("hwnd"):
            return True, int(status["hwnd"])
    return False, None


def find_word_window() -> Optional[int]:
    """Find a visible top-level Microsoft Word window if one exists."""
    found_hwnds = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            exe_name, _ = get_window_process_info(hwnd)
            if is_word_process_name(exe_name):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    found_hwnds.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(_callback), 0)
    if found_hwnds:
        return found_hwnds[0]
    status = call_word_com_helper("status")
    if status.get("ok") and status.get("hwnd"):
        return int(status["hwnd"])
    return None


def get_clipboard_sequence_number() -> int:
    return int(user32.GetClipboardSequenceNumber())


def get_clipboard_text(retries: int = 8, delay_sec: float = 0.03) -> str:
    """Read plain Unicode text from the Windows clipboard safely."""
    for _ in range(retries):
        if user32.OpenClipboard(None):
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    text = ctypes.wstring_at(ptr)
                    return text or ""
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        time.sleep(delay_sec)
    return ""


def set_clipboard_text(text: str, retries: int = 8, delay_sec: float = 0.03) -> bool:
    """Write plain Unicode text to the Windows clipboard, normalizing line endings to CRLF for Word."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    encoded = normalized.encode("utf-16-le") + b"\x00\x00"
    byte_count = len(encoded)

    for _ in range(retries):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                hmem = kernel32.GlobalAlloc(GMEM_MOVEABLE, byte_count)
                if not hmem:
                    return False
                ptr = kernel32.GlobalLock(hmem)
                if not ptr:
                    kernel32.GlobalFree(hmem)
                    return False
                try:
                    ctypes.memmove(ptr, encoded, byte_count)
                finally:
                    kernel32.GlobalUnlock(hmem)
                if not user32.SetClipboardData(CF_UNICODETEXT, hmem):
                    kernel32.GlobalFree(hmem)
                    return False
                return True
            finally:
                user32.CloseClipboard()
        time.sleep(delay_sec)
    return False


def apply_noactivate_style(hwnd: int) -> None:
    """Make a window frameless-friendly, always-on-top, toolwindow, and strictly non-activating."""
    ex_style = GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    new_style = ex_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
    SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new_style)
    user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        0,
        0,
        0,
        0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )

    # Subclass WM_MOUSEACTIVATE to return MA_NOACTIVATE so clicking buttons never steals focus from Word
    if hwnd not in _SUBCLASSED_PROCS:
        orig_proc = GetWindowLongPtrW(hwnd, GWL_WNDPROC)

        def _wnd_proc(h, msg, wparam, lparam):
            if msg == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE
            return user32.CallWindowProcW(orig_proc, h, msg, wparam, lparam)

        c_proc = WNDPROC(_wnd_proc)
        _SUBCLASSED_PROCS[hwnd] = (c_proc, orig_proc)
        SetWindowLongPtrW(hwnd, GWL_WNDPROC, ctypes.cast(c_proc, ctypes.c_void_p).value)


def ensure_foreground(target_hwnd: int, timeout_sec: float = 1.5) -> bool:
    """Ensure target_hwnd is the active foreground window on Windows 10/11."""
    if not target_hwnd or not user32.IsWindow(target_hwnd):
        return False
    if user32.GetForegroundWindow() == target_hwnd:
        return True

    if user32.IsIconic(target_hwnd):
        user32.ShowWindow(target_hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(target_hwnd, SW_SHOW)

    # Windows 10/11 ForegroundLockTimeout bypass: send a neutral Control keyup event
    # before SetForegroundWindow / SwitchToThisWindow so Windows permits foreground activation
    # without triggering Microsoft Word's Alt Ribbon KeyTips.
    ctrl_input = (INPUT * 1)()
    ctrl_input[0].type = INPUT_KEYBOARD
    ctrl_input[0].union.ki = KEYBDINPUT(wVk=VK_CONTROL, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    user32.SendInput(1, ctrl_input, ctypes.sizeof(INPUT))

    fg_hwnd = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
    cur_tid = kernel32.GetCurrentThreadId()
    target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)

    attached_fg = False
    attached_target = False
    try:
        if fg_tid and fg_tid != cur_tid:
            attached_fg = bool(user32.AttachThreadInput(cur_tid, fg_tid, True))
        if target_tid and target_tid != cur_tid:
            attached_target = bool(user32.AttachThreadInput(cur_tid, target_tid, True))

        user32.BringWindowToTop(target_hwnd)
        user32.SetForegroundWindow(target_hwnd)
        try:
            user32.SwitchToThisWindow(target_hwnd, True)
        except Exception:
            pass
    finally:
        if attached_fg:
            user32.AttachThreadInput(cur_tid, fg_tid, False)
        if attached_target:
            user32.AttachThreadInput(cur_tid, target_tid, False)

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if user32.GetForegroundWindow() == target_hwnd:
            return True
        user32.SendInput(1, ctrl_input, ctypes.sizeof(INPUT))
        user32.SetForegroundWindow(target_hwnd)
        try:
            user32.SwitchToThisWindow(target_hwnd, True)
        except Exception:
            pass
        time.sleep(0.04)
    return user32.GetForegroundWindow() == target_hwnd


def send_ctrl_shortcut(vk_code: int) -> bool:
    """Send Ctrl+<Key> via Win32 SendInput."""
    inputs = (INPUT * 4)()
    # Ctrl down
    inputs[0].type = INPUT_KEYBOARD
    inputs[0].union.ki = KEYBDINPUT(wVk=VK_CONTROL, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
    # Key down
    inputs[1].type = INPUT_KEYBOARD
    inputs[1].union.ki = KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
    # Key up
    inputs[2].type = INPUT_KEYBOARD
    inputs[2].union.ki = KEYBDINPUT(wVk=vk_code, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    # Ctrl up
    inputs[3].type = INPUT_KEYBOARD
    inputs[3].union.ki = KEYBDINPUT(wVk=VK_CONTROL, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)

    sent = user32.SendInput(4, inputs, ctypes.sizeof(INPUT))
    return sent == 4


def paste_into_word(word_hwnd: Optional[int], humanized_text: str) -> Tuple[bool, str]:
    """
    Put humanized_text on clipboard, ensure Word is foreground, send Ctrl+V,
    and verify replacement succeeded (with Word COM verification & formatting check).
    Returns (success, message).
    """
    if not humanized_text or not humanized_text.strip():
        return False, "Cannot paste empty humanized text."

    target_hwnd = word_hwnd if (word_hwnd and user32.IsWindow(word_hwnd)) else find_word_window()
    if not target_hwnd:
        return False, "Microsoft Word window was not found. Please keep your Word document open."

    if not set_clipboard_text(humanized_text):
        return False, "Failed to place humanized text onto the system clipboard."

    clip_verify = get_clipboard_text()
    if clip_verify.replace("\r\n", "\n").strip() != humanized_text.replace("\r\n", "\n").strip():
        return False, "Clipboard verification failed before pasting."

    fg_ok = ensure_foreground(target_hwnd)
    if fg_ok:
        time.sleep(0.04)
        send_ctrl_shortcut(VK_V)
        time.sleep(0.10)

    # Verify replacement (and perform plain-text paste via Word COM if Ctrl+V did not reach Word)
    com_res = call_word_com_helper("verify_or_paste", stdin_text=humanized_text)
    if com_res.get("ok"):
        if com_res.get("formattingWarning"):
            bf = com_res.get("beforeFont")
            af = com_res.get("afterFont")
            bs = com_res.get("beforeSize")
            as_ = com_res.get("afterSize")
            return (
                True,
                f"Replaced text in Word (Note: formatting changed from {bf} {bs}pt to {af} {as_}pt).",
            )
        return True, "Replaced highlighted text in Word (formatting preserved)."

    if not fg_ok:
        return False, "Could not bring Microsoft Word to the foreground to paste safely."

    return True, "Replaced highlighted text in Word."


def undo_in_word(word_hwnd: Optional[int], original_text: str = "") -> Tuple[bool, str]:
    """Ensure Word is foreground, send Ctrl+Z to undo the last paste, and verify restoration."""
    target_hwnd = word_hwnd if (word_hwnd and user32.IsWindow(word_hwnd)) else find_word_window()
    if not target_hwnd:
        return False, "Microsoft Word window was not found."

    fg_ok = ensure_foreground(target_hwnd)
    if fg_ok:
        time.sleep(0.04)
        send_ctrl_shortcut(VK_Z)
        time.sleep(0.08)

    com_res = call_word_com_helper("verify_or_undo", stdin_text=original_text)
    if com_res.get("ok") and com_res.get("restored"):
        return True, "Undid replacement in Word (original text restored)."

    if not fg_ok:
        return False, "Could not bring Microsoft Word to the foreground for Undo."

    return True, "Undid replacement in Word (Ctrl+Z)."


def make_preview(text: str, max_len: int = 80) -> str:
    """Create a clean single-line ~80-char preview of copied text."""
    single_line = " ".join(text.strip().split())
    if len(single_line) <= max_len:
        return single_line
    return single_line[: max_len - 1].rstrip() + "…"
