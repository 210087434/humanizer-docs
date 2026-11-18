"""Mock Clever AI HTTP server that faithfully mimics https://cleverhumanizer.ai DOM and state transitions."""
import http.server
import json
import socketserver
import threading
import urllib.parse


MOCK_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Mock Clever AI Humanizer</title>
  <script>
    const isLoggedIn = __IS_LOGGED_IN__;
    window.IS_LOGGED_IN = isLoggedIn;
    window.__mockAudit = {
      clearStructuredClicked: false,
      removeTextClicked: false,
      pastedText: "",
      humanizeClicked: false,
      copyTextClicked: false,
      styleSelected: "casual"
    };
  </script>
</head>
<body data-logged-in="__IS_LOGGED_IN__">
  __HEADER_HTML__
  <main id="content">
    <form id="quillForm" data-form-type="humanize" onsubmit="return false;">
      <div class="fields form-glass in bg-full" id="AIHumanizer">
        <div class="tool-controls">
          <div id="humanizeToolbar" class="rewrite-toolbar">
            <span class="label">Writing Style</span>
            <div class="style-tabs" id="humanizeStyleTabs" role="group" aria-label="Choose the Writing style">
              <button type="button" class="style-tab active" data-humanize-style="casual">Normal</button>
              <button type="button" class="style-tab" data-humanize-style="academic">Clear &amp; Structured</button>
            </div>
          </div>
          <input type="hidden" name="humanize_style" id="humanizeStyle" value="casual">
        </div>

        <div class="form-floating w-50 original-block">
          <div class="output-header original-header">
            Original text
            <button class="remove-text active" type="button">Remove text</button>
          </div>
          <div class="input-zone">
            <div id="quillEditor" class="form-control quill-editor-container" data-editor-type="humanize">
              <div class="ql-editor" contenteditable="true"><p>Stale previous text that must be removed first.</p></div>
            </div>
            <div class="custom-placeholder hidden">Paste your text here</div>
          </div>
          <div class="quillFooter">
            <p class="limit-msg" hidden>This request exceeds the available processing capacity for today.</p>
            <div class="outstyle">
              <div class="foot-left">
                <div class="quillWordCount">
                  <div class="info-messages">
                    <div class="info-msg textMaxLengthBlock">Maximum allowed <strong>3,000 words</strong>.</div>
                  </div>
                  Words: <span class="originalWordsNum">8</span> / <span class="originalWordsLimit">3,000</span>
                </div>
              </div>
              <button class="downloadLink submitQuill" type="button">Humanize AI</button>
            </div>
          </div>
        </div>

        <div class="form-floating w-50 humanResult human-result-plain">
          <div id="loaderContainer" style="display: none;" class="loader-overlay generation">
            <div class="progress-wrap">
              <p id="loadingText" class="pstatus" aria-live="polite">Refining your content...</p>
              <div class="progress-container pbar">
                <div class="progress-bar" id="minuteProgress"></div>
              </div>
              <div class="pmeta">
                <span class="ppct" id="loaderPercent">0%</span>
              </div>
            </div>
          </div>
          <div class="output-header">
            <span class="output-title">Result text</span>
          </div>
          <div class="text-box form-control ql-editor quillOutput">
            <p class="place">New text will appear here</p>
          </div>
          <div class="output-footer">
            <div id="outputWordCount">
              <span class="rw-line">Result words: <span class="resultWordsNum">0</span></span>
            </div>
            <div class="btns d-flex">
              <div class="copyBtn copyFromQuillText">
                <button disabled="disabled" type="button" class="btn-close" data-target="text" aria-label="Copy Text" title="Copy Text">Copy Text</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </form>
  </main>

  <div class="modal fade" id="limitModal" role="dialog" hidden aria-hidden="true">
    <div class="modal-dialog" role="document">
      <div class="modal-content">
        <div class="modal-body">
          <div class="mtitle" id="limitModalTitle"></div>
          <div class="modal-list" id="limitModalBody"></div>
          <button class="greenBtn" data-bs-dismiss="modal" aria-label="Close">OK</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    (function() {
      const mode = __MODE_JSON__;
      const styleTabs = document.getElementById("humanizeStyleTabs");
      const styleInput = document.getElementById("humanizeStyle");
      const removeBtn = document.querySelector(".remove-text");
      const editor = document.querySelector("#quillEditor .ql-editor");
      const submitBtn = document.querySelector(".submitQuill");
      const loader = document.getElementById("loaderContainer");
      const loaderPct = document.getElementById("loaderPercent");
      const loadingText = document.getElementById("loadingText");
      const output = document.querySelector(".quillOutput");
      const resultWords = document.querySelector(".resultWordsNum");
      const copyBtn = document.querySelector(".copyFromQuillText button");
      const origWords = document.querySelector(".originalWordsNum");

      styleTabs.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-humanize-style]");
        if (!btn) return;
        styleTabs.querySelectorAll("[data-humanize-style]").forEach(b => b.classList.toggle("active", b === btn));
        styleInput.value = btn.dataset.humanizeStyle;
        if (btn.dataset.humanizeStyle === "academic") {
          window.__mockAudit.clearStructuredClicked = true;
          window.__mockAudit.styleSelected = "academic";
        }
      });

      removeBtn.addEventListener("click", () => {
        window.__mockAudit.removeTextClicked = true;
        editor.innerHTML = "<p><br></p>";
        origWords.textContent = "0";
        submitBtn.disabled = true;
      });

      function extractEditorLines() {
        const ps = editor.querySelectorAll("p");
        if (ps.length > 0) {
          return Array.from(ps).map(p => (p.innerText || p.textContent || "").replace(/\\n+$/g, "")).join("\\n").trim();
        }
        return (editor.innerText || editor.textContent || "").trim();
      }

      function updateEditorState() {
        const txt = extractEditorLines();
        window.__mockAudit.pastedText = txt;
        const words = txt ? txt.split(/\\s+/).length : 0;
        origWords.textContent = String(words);
        submitBtn.disabled = words === 0;
      }

      editor.addEventListener("paste", (e) => {
        e.preventDefault();
        const plain = (e.clipboardData && e.clipboardData.getData("text/plain")) || "";
        if (plain) {
          const lines = plain.replace(/\\r\\n/g, "\\n").split("\\n");
          editor.innerHTML = lines.map(l => "<p>" + (l.trim() ? l : "<br>") + "</p>").join("");
          updateEditorState();
        }
      });

      editor.addEventListener("input", updateEditorState);

      submitBtn.addEventListener("click", () => {
        window.__mockAudit.humanizeClicked = true;
        const srcText = extractEditorLines();
        submitBtn.disabled = true;
        submitBtn.classList.add("active-geenration");
        copyBtn.setAttribute("disabled", "disabled");
        loader.style.display = "block";
        loaderPct.textContent = "17%";
        loadingText.textContent = "Refining your content...";

        setTimeout(() => {
          loaderPct.textContent = "62%";
          loadingText.textContent = "Optimizing tone and readability...";
        }, 100);

        setTimeout(() => {
          loader.style.display = "none";
          submitBtn.disabled = false;
          submitBtn.classList.remove("active-geenration");

          if (mode === "error_modal") {
            const modal = document.getElementById("limitModal");
            document.getElementById("limitModalTitle").textContent = "Text Not Ready";
            document.getElementById("limitModalBody").textContent = "The text didn’t come through this time. Let’s give it another try.";
            modal.hidden = false;
            modal.classList.add("modal-open");
            return;
          }

          if (mode === "empty_result") {
            output.innerHTML = "";
            resultWords.textContent = "0";
            copyBtn.removeAttribute("disabled");
            window.dispatchEvent(new CustomEvent("writing-tool:result", { detail: {} }));
            return;
          }

          const paras = srcText.replace(/\\r\\n/g, "\\n").split("\\n");
          output.innerHTML = paras.map((p) => {
            if (!p.trim()) return "<p><br></p>";
            return "<p><span class=\\"diff-add\\">[Humanized]</span> " + p + "</p>";
          }).join("");

          const outWords = (output.innerText || output.textContent || "").trim().split(/\\s+/).length;
          resultWords.textContent = String(outWords);
          copyBtn.removeAttribute("disabled");
          window.dispatchEvent(new CustomEvent("writing-tool:result", { detail: {} }));
        }, 250);
      });

      window.__mockAudit.copyClickCount = 0;

      // Capture-phase audit records that Copy Text button was clicked
      copyBtn.addEventListener("click", () => {
        window.__mockAudit.copyTextClicked = true;
        window.__mockAudit.copyClickCount = (window.__mockAudit.copyClickCount || 0) + 1;
      }, true);

      // Bubble-phase listener mimics real Clever AI's unfocused copy failure alert
      copyBtn.addEventListener("click", (e) => {
        if (!e.isTrusted) {
          alert("Copy failed, your browser may not support copying.");
        }
      });
    })();
  </script>
</body>
</html>
"""


def build_mock_clever_html(mode: str = "normal") -> str:
    is_logged_in = "false" if mode == "not_logged_in" else "true"
    header_html = (
        '<header><a href="/login" class="border-link mb-signin">Sign in</a></header>'
        if mode == "not_logged_in"
        else '<header><div class="user-avatar">A</div></header>'
    )

    if mode == "broken_layout":
        return (
            f"<!DOCTYPE html><html><head><title>Broken Layout</title>"
            f"<script>const isLoggedIn = {is_logged_in};</script>"
            f"</head><body>{header_html}<main><div>Completely changed DOM without editors</div></main></body></html>"
        )

    return (
        MOCK_TEMPLATE.replace("__IS_LOGGED_IN__", is_logged_in)
        .replace("__HEADER_HTML__", header_html)
        .replace("__MODE_JSON__", json.dumps(mode))
    )


class MockCleverHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        mode = params.get("mode", ["normal"])[0]
        body = build_mock_clever_html(mode=mode).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


class MockCleverServer:
    def __init__(self):
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), MockCleverHandler)
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
