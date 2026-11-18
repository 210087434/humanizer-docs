"""Frameless, draggable, always-on-top, non-activating popup UI for Humanize Helper."""
import tkinter as tk
from typing import Callable, Optional
from desktop_app.win32_bridge import (
    apply_noactivate_style,
    make_preview,
    user32,
    HWND_TOPMOST,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOACTIVATE,
    SWP_SHOWWINDOW,
)

class HumanizePopup:
    """
    Small floating, non-activating popup window.
    Uses WS_EX_NOACTIVATE + WM_MOUSEACTIVATE so clicking it never steals focus
    or deselects highlighted text in Microsoft Word.
    """

    def __init__(
        self,
        root: tk.Tk,
        initial_x: Optional[int],
        initial_y: Optional[int],
        on_humanize: Callable[[], None],
        on_paste: Callable[[], None],
        on_undo: Callable[[], None],
        on_copy: Callable[[], bool],
        on_position_changed: Callable[[int, int], None],
    ):
        self.root = root
        self.on_humanize = on_humanize
        self.on_paste = on_paste
        self.on_undo = on_undo
        self.on_copy = on_copy
        self.on_position_changed = on_position_changed

        self.root.title("HumanizeHelperFloatingWindow")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#111a15")

        self.width = 360
        self.height = 160
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = initial_x if initial_x is not None else max(20, screen_w - self.width - 36)
        y = initial_y if initial_y is not None else max(40, screen_h - self.height - 96)
        self.x = max(0, min(x, screen_w - self.width))
        self.y = max(0, min(y, screen_h - self.height))
        self.root.geometry(f"{self.width}x{self.height}+{self.x}+{self.y}")

        self._drag_offset_x = 0
        self._drag_offset_y = 0
        self.state = "HIDDEN"
        self._hwnd: Optional[int] = None

        self._build_widgets()
        self.root.update_idletasks()
        self._apply_win32_noactivate()
        self.show_ready(extension_connected=False)

    def _apply_win32_noactivate(self) -> None:
        try:
            frame_id = self.root.wm_frame()
            hwnd = int(frame_id, 16) if isinstance(frame_id, str) and frame_id.startswith("0x") else self.root.winfo_id()
        except Exception:
            hwnd = self.root.winfo_id()
        self._hwnd = hwnd
        apply_noactivate_style(hwnd)

    def _build_widgets(self) -> None:
        self.container = tk.Frame(
            self.root,
            bg="#111a15",
            highlightbackground="#2b4938",
            highlightthickness=1,
            bd=0,
        )
        self.container.pack(fill=tk.BOTH, expand=True)

        self.title_bar = tk.Frame(self.container, bg="#19271f", height=34, cursor="fleur")
        self.title_bar.pack(fill=tk.X, side=tk.TOP)
        self.title_bar.pack_propagate(False)

        self.status_label = tk.Label(
            self.title_bar,
            text="Humanize Helper",
            fg="#eaf6ef",
            bg="#19271f",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(14, 4))

        self.close_btn = tk.Label(
            self.title_bar,
            text="Close",
            fg="#a9bdb0",
            bg="#19271f",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            cursor="hand2",
        )
        self.close_btn.pack(side=tk.RIGHT, fill=tk.Y)
        self.close_btn.bind("<ButtonRelease-1>", lambda e: self.hide())
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.configure(fg="#ffffff", bg="#7b3b37"))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.configure(fg="#a9bdb0", bg="#19271f"))

        for w in (self.title_bar, self.status_label):
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_motion)
            w.bind("<ButtonRelease-1>", self._on_drag_end)

        self.body = tk.Frame(self.container, bg="#111a15", padx=14, pady=10)
        self.body.pack(fill=tk.BOTH, expand=True)

        self.preview_label = tk.Label(
            self.body,
            text="",
            fg="#d4e2d9",
            bg="#111a15",
            font=("Segoe UI", 10),
            justify=tk.LEFT,
            anchor="nw",
            wraplength=332,
        )
        self.preview_label.pack(fill=tk.BOTH, expand=True)

        self.footer = tk.Frame(self.container, bg="#111a15", padx=14, pady=9)
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)

        self.meta_label = tk.Label(
            self.footer,
            text="",
            fg="#91a99a",
            bg="#111a15",
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.meta_label.pack(side=tk.LEFT)

        self.action_btn = tk.Label(
            self.footer,
            text="Humanize",
            fg="#092017",
            bg="#35bd83",
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=7,
            cursor="hand2",
        )
        self.action_btn.pack(side=tk.RIGHT)
        self.action_btn.bind("<ButtonRelease-1>", self._on_primary_click)
        self.action_btn._base_background = "#35bd83"
        self.action_btn._hover_background = "#52d39b"
        self.action_btn.bind(
            "<Enter>", lambda e: self.action_btn.configure(bg=self.action_btn._hover_background)
        )
        self.action_btn.bind(
            "<Leave>", lambda e: self.action_btn.configure(bg=self.action_btn._base_background)
        )

        self.copy_btn = tk.Label(
            self.footer,
            text="Copy",
            fg="#e7f2eb",
            bg="#26372e",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7,
            cursor="hand2",
        )
        self.copy_btn.bind("<ButtonRelease-1>", self._on_copy_click)
        self.copy_btn.bind("<Enter>", lambda e: self.copy_btn.configure(bg="#33483b"))
        self.copy_btn.bind("<Leave>", lambda e: self.copy_btn.configure(bg="#26372e"))

        self.secondary_btn = tk.Label(
            self.footer,
            text="Undo",
            fg="#e7f2eb",
            bg="#26372e",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7,
            cursor="hand2",
        )
        self.secondary_btn.bind("<ButtonRelease-1>", lambda e: self.on_undo())
        self.secondary_btn.bind("<Enter>", lambda e: self.secondary_btn.configure(bg="#33483b"))
        self.secondary_btn.bind("<Leave>", lambda e: self.secondary_btn.configure(bg="#26372e"))

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_offset_x = event.x_root - self.root.winfo_x()
        self._drag_offset_y = event.y_root - self.root.winfo_y()

    def _on_drag_motion(self, event: tk.Event) -> None:
        new_x = event.x_root - self._drag_offset_x
        new_y = event.y_root - self._drag_offset_y
        self.x = new_x
        self.y = new_y
        self.root.geometry(f"+{new_x}+{new_y}")

    def _on_drag_end(self, event: tk.Event) -> None:
        self.on_position_changed(self.x, self.y)

    def _on_primary_click(self, event: tk.Event) -> None:
        if self.state in ("COPIED", "ERROR"):
            self.on_humanize()
        elif self.state == "HUMANIZED":
            self.on_paste()
        elif self.state == "PASTED":
            self.on_undo()

    def _on_copy_click(self, event: tk.Event) -> None:
        if self.state != "HUMANIZED":
            return

        if self.on_copy():
            self.status_label.configure(text="Copied to clipboard")
            self.copy_btn.configure(text="Copied", fg="#72d6a9")
        else:
            self.status_label.configure(text="Clipboard copy failed")
            self.copy_btn.configure(text="Retry copy", fg="#f7baba")
        self.root.after(1600, self._reset_copy_feedback)

    def _reset_copy_feedback(self) -> None:
        if self.state == "HUMANIZED":
            self.status_label.configure(text="Humanized text ready")
            self.copy_btn.configure(text="Copy", fg="#e7f2eb", bg="#26372e")

    def _set_action(self, text: str, background: str, foreground: str, cursor: str) -> None:
        self.action_btn.configure(text=text, bg=background, fg=foreground, cursor=cursor)
        self.action_btn._base_background = background
        self.action_btn._hover_background = (
            "#52d39b" if background == "#35bd83" else "#33483b"
        )

    def show_without_focus(self) -> None:
        self.root.deiconify()
        if self._hwnd:
            apply_noactivate_style(self._hwnd)
            user32.SetWindowPos(
                self._hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )

    def hide(self) -> None:
        self.state = "HIDDEN"
        self.root.withdraw()

    def show_ready(self, extension_connected: bool = False) -> None:
        self.state = "READY"
        self.status_label.configure(text="Humanize Helper")
        self.preview_label.configure(
            text="Copy text in Word. Humanize it in your browser, then paste it back.",
            fg="#d4e2d9",
        )
        ext_txt = "Extension connected" if extension_connected else "Waiting for browser extension"
        self.meta_label.configure(text=ext_txt)
        self.copy_btn.pack_forget()
        self.secondary_btn.pack_forget()
        self._set_action("Waiting for copy", "#26372e", "#a9bdb0", "arrow")
        self.action_btn.pack(side=tk.RIGHT)
        self.show_without_focus()

    def show_copied(self, text: str) -> None:
        self.state = "COPIED"
        words = len(text.split())
        preview = make_preview(text, 80)
        self.status_label.configure(text="Text copied in Word")
        self.preview_label.configure(text=f"“{preview}”", fg="#d4e2d9")
        self.meta_label.configure(text=f"{words} word{'s' if words != 1 else ''}")
        self.copy_btn.pack_forget()
        self.secondary_btn.pack_forget()
        self._set_action("Humanize", "#35bd83", "#092017", "hand2")
        self.action_btn.pack(side=tk.RIGHT)
        self.show_without_focus()

    def show_humanizing(self, detail: str = "Humanizing…", percent: int = 0) -> None:
        self.state = "HUMANIZING"
        label_text = f"Humanizing ({percent}%)" if percent > 0 else "Humanizing"
        self.status_label.configure(text=label_text)
        self.preview_label.configure(
            text=detail or "Working in the background. You can keep using Word.",
            fg="#b9d1c3",
        )
        self.meta_label.configure(text="Working in background…")
        self.copy_btn.pack_forget()
        self.secondary_btn.pack_forget()
        self._set_action("Working", "#26372e", "#a9bdb0", "watch")
        self.action_btn.pack(side=tk.RIGHT)
        self.show_without_focus()

    def show_humanized(self, result_text: str) -> None:
        self.state = "HUMANIZED"
        words = len(result_text.split())
        preview = make_preview(result_text, 80)
        self.status_label.configure(text="Humanized text ready")
        self.preview_label.configure(text=f"“{preview}”", fg="#eaf6ef")
        self.meta_label.configure(text=f"{words} words ready")
        self.secondary_btn.pack_forget()
        self._set_action("Paste", "#35bd83", "#092017", "hand2")
        self.action_btn.pack(side=tk.RIGHT)
        self.copy_btn.configure(text="Copy", fg="#e7f2eb", bg="#26372e")
        self.copy_btn.pack(side=tk.RIGHT, padx=(0, 8))
        self.show_without_focus()

    def show_pasted(self, message: str = "Replaced highlighted text in Word.") -> None:
        self.state = "PASTED"
        self.status_label.configure(text="Pasted into Word")
        self.preview_label.configure(text=message, fg="#d4e2d9")
        self.meta_label.configure(text="Original text saved")
        self.copy_btn.pack_forget()
        self.secondary_btn.pack_forget()
        self._set_action("Undo", "#26372e", "#e7f2eb", "hand2")
        self.action_btn.pack(side=tk.RIGHT)
        self.show_without_focus()

    def show_error(self, error_message: str) -> None:
        self.state = "ERROR"
        self.status_label.configure(text="Could not humanize text")
        self.preview_label.configure(text=error_message, fg="#f0aaa3")
        self.meta_label.configure(text="Original selection unchanged")
        self.copy_btn.pack_forget()
        self.secondary_btn.pack_forget()
        self._set_action("Try again", "#35bd83", "#092017", "hand2")
        self.action_btn.pack(side=tk.RIGHT)
        self.show_without_focus()
