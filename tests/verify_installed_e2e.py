"""Phase 5 final end-to-end verification of the installed Humanize Helper (Word -> Opera Clever AI -> Word Paste & Undo)."""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from desktop_app.app import ClipboardWatcher
from desktop_app.config import load_config, sync_extension_config
from desktop_app.win32_bridge import (
    get_clipboard_text,
    is_word_foreground,
    paste_into_word,
    set_clipboard_text,
    undo_in_word,
)
from desktop_app.ws_server import LocalBridgeServer
from tests.test_word_live import run_word_ps


async def run_phase5_verification() -> int:
    # 1. Verify Windows Startup shortcut exists
    startup_dir = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    shortcut_path = startup_dir / "HumanizeHelper.lnk"
    if not shortcut_path.exists():
        print(f"FAIL: Startup shortcut missing at {shortcut_path}", flush=True)
        return 1
    print(f"[Phase 5.1] Verified Windows Startup entry exists: {shortcut_path}", flush=True)

    # 2. Load config and start LocalBridgeServer on configured port (54829)
    cfg = load_config()
    sync_extension_config(cfg)
    saved_clip = get_clipboard_text()

    server = LocalBridgeServer(
        host="127.0.0.1",
        port=int(cfg["port"]),
        auth_token=str(cfg["auth_token"]),
        on_progress=lambda req_id, st, pct: print(f"  [Clever AI {pct}%] {st}", flush=True),
    )
    await server.start()
    print(f"[Phase 5.2] WebSocket bridge listening on 127.0.0.1:{server.port}...", flush=True)

    try:
        for _ in range(60):
            if server.has_connected_extension:
                break
            await asyncio.sleep(0.5)
        if not server.has_connected_extension:
            print("FAIL: Opera extension did not connect within 30s.", flush=True)
            return 1
        print("[Phase 5.2] Opera extension connected and authenticated ✓", flush=True)

        # 3. Create throwaway Word document, highlight target sentence, and copy it
        original_sentence = (
            "The main reasons for these task failures were account or login problems (25.3%), "
            "administrative restrictions or holds (20.2%), internet or electricity interruptions "
            "(18.3%), unclear reasons where the portal gave no explanation (15.8%), and server "
            "crashes or freezes during busy times (8.5%)."
        )
        watcher = ClipboardWatcher(debounce_sec=0.04)

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
$range.Text = "[THROWAWAY_DOC_MARKER] Context before. {original_sentence} Context after."
$sel = $win.Selection
$sel.SetRange(0, 0)
$found = $sel.Find.Execute({json.dumps(original_sentence)})
$sel.Copy()
$hwnd = [int]$win.Hwnd
Write-Output (@{{
    hwnd = $hwnd
    found = [bool]$found
    selectedText = $sel.Text
}} | ConvertTo-Json -Compress)
"""
        )
        if not setup_info.get("found"):
            print("FAIL: Could not select text in throwaway Word doc.", flush=True)
            return 1
        word_hwnd = int(setup_info["hwnd"])

        watcher.poll()
        await asyncio.sleep(0.06)
        copied = watcher.poll()
        if not copied or copied[0].strip() != original_sentence:
            print(f"FAIL: ClipboardWatcher did not capture Word copy: {copied}", flush=True)
            return 1
        print("[Phase 5.3] Word highlight & copy detected by ClipboardWatcher ✓", flush=True)

        # 4. Humanize copied text through live Opera extension on https://cleverhumanizer.ai
        print("[Phase 5.4] Sending copied Word text to Clever AI in Opera...", flush=True)
        res = await server.request_humanize(copied[0], timeout_sec=120.0)
        if res.get("type") != "HUMANIZE_RESULT" or not res.get("text", "").strip():
            print(f"FAIL: Live Clever AI humanization failed: {res}", flush=True)
            return 1
        humanized_text = res["text"].strip()
        print(f"[Phase 5.4] Received humanized result ({res.get('words')} words): {humanized_text}", flush=True)

        # 5. Paste humanized result over highlighted selection in Word and verify formatting
        ok_paste, paste_msg = paste_into_word(word_hwnd, humanized_text)
        if not ok_paste:
            print(f"FAIL: paste_into_word failed: {paste_msg}", flush=True)
            return 1

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
        if humanized_text not in after_paste["fullText"] or original_sentence in after_paste["fullText"]:
            print(f"FAIL: Word document text was not replaced properly: {after_paste}", flush=True)
            return 1
        if after_paste["fontName"] != "Arial" or float(after_paste["fontSize"]) != 11.0:
            print(f"FAIL: Formatting changed after paste: {after_paste}", flush=True)
            return 1
        print(f"[Phase 5.5] Verified replacement in Word & Arial 11pt formatting preserved ✓ ({paste_msg})", flush=True)

        # 6. Undo in Word and verify original sentence is restored
        ok_undo, undo_msg = undo_in_word(word_hwnd, original_sentence)
        if not ok_undo:
            print(f"FAIL: undo_in_word failed: {undo_msg}", flush=True)
            return 1

        after_undo = run_word_ps(
            """
$doc = $word.ActiveDocument
Write-Output (@{
    fullText = $doc.Content.Text
} | ConvertTo-Json -Compress)
"""
        )
        if original_sentence not in after_undo["fullText"]:
            print(f"FAIL: Undo did not restore original sentence: {after_undo}", flush=True)
            return 1
        print(f"[Phase 5.6] Verified Undo (Ctrl+Z) restored original text in Word ✓ ({undo_msg})", flush=True)
        print("PHASE 5 FULL END-TO-END VERIFICATION PASSED!", flush=True)
        return 0
    finally:
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
        if saved_clip:
            set_clipboard_text(saved_clip)
        await server.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_phase5_verification()))

