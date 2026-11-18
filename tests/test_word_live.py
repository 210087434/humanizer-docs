"""Live integration test against Microsoft Word (WINWORD.EXE) using a throwaway document."""
import json
import subprocess
import sys
import tkinter as tk
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from desktop_app.app import ClipboardWatcher
from desktop_app.popup_ui import HumanizePopup
from desktop_app.win32_bridge import (
    VK_C,
    ensure_foreground,
    get_clipboard_text,
    is_word_foreground,
    paste_into_word,
    send_ctrl_shortcut,
    set_clipboard_text,
    undo_in_word,
)


def run_word_ps(script_body: str) -> dict:
    """Execute a short PowerShell COM snippet against the active Word.Application instance."""
    full_script = f"""
$ErrorActionPreference = 'Stop'
try {{
    $word = [Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application')
}} catch {{
    $word = New-Object -ComObject Word.Application
    $word.Visible = $true
}}
{script_body}
"""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", full_script],
        capture_output=True,
        text=True,
        timeout=25,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"PowerShell Word COM error: {proc.stderr}")
    out = proc.stdout.strip().splitlines()
    return json.loads(out[-1]) if out else {}


class TestLiveMicrosoftWordFlow(unittest.TestCase):
    def setUp(self):
        self._saved_clip = get_clipboard_text()

    def tearDown(self):
        # Always close only our throwaway document without saving
        try:
            run_word_ps(
                """
foreach ($d in @($word.Documents)) {
    if ($d.Content.Text -like '*[THROWAWAY_DOC_MARKER]*') {
        $d.Close(0)
    }
}
if ($word.Documents.Count -eq 0) {
    $word.Quit()
}
Write-Output '{ "closed": true }'
"""
            )
        except Exception:
            pass
        if self._saved_clip:
            set_clipboard_text(self._saved_clip)

    def test_word_copy_popup_no_deselect_paste_and_undo(self):
        original_sentence = (
            "In the pilot study, 42 participants recommended clearer instructions (R12)."
        )
        humanized_sentence = (
            "The pilot survey found 42 respondents recommending clearer instructions (R12)."
        )

        watcher = ClipboardWatcher(debounce_sec=0.04)

        # 1. Create throwaway document in Word with Arial 11pt formatting, select target sentence, and copy it
        setup_info = run_word_ps(
            f"""
$doc = $word.Documents.Add()
$word.Visible = $true
$doc.Activate()
$win = $doc.ActiveWindow
$win.WindowState = 0
$range = $doc.Content
$range.Font.Name = 'Arial'
$range.Font.Size = 11
$range.Text = "[THROWAWAY_DOC_MARKER] Lead-in context sentence. {original_sentence} Trailing sentence after selection."

# Find and highlight only the target sentence, then Copy in Word
$sel = $win.Selection
$sel.SetRange(0, 0)
$found = $sel.Find.Execute({json.dumps(original_sentence)})
$sel.Copy()
$hwnd = [int]$win.Hwnd
Write-Output (@{{
    hwnd = $hwnd
    found = [bool]$found
    selectedText = $sel.Text
    fontName = $sel.Font.Name
    fontSize = $sel.Font.Size
}} | ConvertTo-Json -Compress)
"""
        )

        self.assertTrue(setup_info.get("found"), "Failed to highlight target sentence in throwaway Word doc")
        word_hwnd = int(setup_info["hwnd"])
        self.assertEqual(setup_info["selectedText"], original_sentence)

        # 2. Verify Word detection and ClipboardWatcher picking up the Word copy
        is_fg, detected_hwnd = is_word_foreground()
        self.assertTrue(is_fg, "WINWORD.EXE was not detected as active")

        watcher.poll()
        time.sleep(0.06)
        copied = watcher.poll()
        self.assertIsNotNone(copied, "ClipboardWatcher did not detect copy from Word")
        copied_text, captured_hwnd = copied
        self.assertEqual(copied_text.strip(), original_sentence)

        # 3. Show the non-activating popup and verify it DOES NOT steal focus or deselect Word's highlight
        root = tk.Tk()
        try:
            popup = HumanizePopup(
                root=root,
                initial_x=150,
                initial_y=150,
                on_humanize=lambda: None,
                on_paste=lambda: None,
                on_undo=lambda: None,
                on_copy=lambda: True,
                on_position_changed=lambda x, y: None,
            )
            popup.show_copied(copied_text)
            root.update_idletasks()
            root.update()
            popup.show_humanizing("Refining your content...", 45)
            root.update()
            popup.show_humanized(humanized_sentence)
            root.update()

            is_still_fg, _ = is_word_foreground()
            self.assertTrue(is_still_fg, "Popup stole focus from Microsoft Word!")

            sel_check = run_word_ps(
                """
$sel = $word.ActiveWindow.Selection
Write-Output (@{
    selectedText = $sel.Text
    start = $sel.Start
    end = $sel.End
} | ConvertTo-Json -Compress)
"""
            )
            self.assertEqual(
                sel_check["selectedText"],
                original_sentence,
                "Word selection was deselected when popup appeared!",
            )
            self.assertGreater(sel_check["end"] - sel_check["start"], 10)

            # 4. Perform Paste replacement via paste_into_word()
            ok_paste, paste_msg = paste_into_word(word_hwnd, humanized_sentence)
            self.assertTrue(ok_paste, f"paste_into_word failed: {paste_msg}")
            self.assertIn("formatting preserved", paste_msg)

            after_paste = run_word_ps(
                """
$doc = $word.ActiveDocument
Write-Output (@{
    fullText = $doc.Content.Text
    fontName = $doc.Content.Font.Name
    fontSize = $doc.Content.Font.Size
} | ConvertTo-Json -Compress)
"""
            )
            full_text_after_paste = after_paste["fullText"].strip()
            self.assertIn(humanized_sentence, full_text_after_paste)
            self.assertNotIn(original_sentence, full_text_after_paste)
            self.assertEqual(after_paste["fontName"], "Arial", "Font family changed after paste!")
            self.assertEqual(float(after_paste["fontSize"]), 11.0, "Font size changed after paste!")

            # 5. Perform Undo via undo_in_word() (sends Ctrl+Z / Undo) and verify original text is restored
            ok_undo, undo_msg = undo_in_word(word_hwnd, original_sentence)
            self.assertTrue(ok_undo, f"undo_in_word failed: {undo_msg}")

            after_undo = run_word_ps(
                """
$doc = $word.ActiveDocument
Write-Output (@{
    fullText = $doc.Content.Text
} | ConvertTo-Json -Compress)
"""
            )
            full_text_after_undo = after_undo["fullText"].strip()
            self.assertIn(original_sentence, full_text_after_undo)
            self.assertNotIn(humanized_sentence, full_text_after_undo)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
