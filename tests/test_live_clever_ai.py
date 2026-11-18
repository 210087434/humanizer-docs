"""Live selector and DOM verification test against https://cleverhumanizer.ai."""
import json
import sys
import unittest
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


class TestLiveCleverAiDomStructure(unittest.TestCase):
    def test_live_clever_ai_html_matches_extension_selectors(self):
        req = urllib.request.Request(
            "https://cleverhumanizer.ai",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")

        # Verify all critical DOM IDs, classes, and attributes required by browser_extension/content.js
        required_markers = {
            "humanizerPane (#AIHumanizer)": 'id="AIHumanizer"',
            "styleTabsGroup (#humanizeStyleTabs)": 'id="humanizeStyleTabs"',
            "clearStructuredBtn (data-humanize-style='academic')": 'data-humanize-style="academic"',
            "clearStructuredText (Clear & Structured)": "Clear &amp; Structured",
            "removeTextBtn (class='remove-text')": 'class="remove-text"',
            "inputEditor (#quillEditor)": 'id="quillEditor"',
            "humanizeBtn (submitQuill)": "submitQuill",
            "loaderContainer (#loaderContainer)": 'id="loaderContainer"',
            "loaderPercent (#loaderPercent)": 'id="loaderPercent"',
            "loadingText (#loadingText)": 'id="loadingText"',
            "outputEditor (quillOutput)": "quillOutput",
            "outputPlaceholder (class='place')": 'class="place"',
            "resultWordCount (resultWordsNum)": "resultWordsNum",
            "copyTextBtn (copyFromQuillText)": "copyFromQuillText",
            "copyTextAria (aria-label='Copy Text')": 'aria-label="Copy Text"',
            "limitModal (#limitModal)": 'id="limitModal"',
            "unsupportedLangModal (#unsupportedLanguageModal)": 'id="unsupportedLanguageModal"',
        }

        for name, marker in required_markers.items():
            self.assertIn(
                marker,
                html,
                f"Live https://cleverhumanizer.ai HTML is missing expected selector marker: {name} ({marker})",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
