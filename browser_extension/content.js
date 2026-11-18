// Content script for Clever AI Humanizer (https://cleverhumanizer.ai/*)
(function () {
  function getConfig() {
    return globalThis.HUMANIZE_CONFIG || {};
  }

  function findButtonBySelectorOrText(root, selector, textRegexStr) {
    if (selector) {
      const el = root.querySelector(selector);
      if (el) return el;
    }
    if (textRegexStr) {
      const re = new RegExp(textRegexStr, "i");
      const candidates = root.querySelectorAll("button, [role='button'], .style-tab, .tab");
      for (const btn of candidates) {
        const txt = (btn.innerText || btn.textContent || "").trim();
        const aria = (btn.getAttribute("aria-label") || "").trim();
        const title = (btn.getAttribute("title") || "").trim();
        if (re.test(txt) || re.test(aria) || re.test(title)) {
          return btn;
        }
      }
    }
    return null;
  }

  function checkIsLoggedIn(sel) {
    if (document.body && document.body.dataset.loggedIn === "false") {
      return false;
    }
    if (document.body && document.body.dataset.loggedIn === "true") {
      return true;
    }
    const scripts = document.querySelectorAll("script:not([src])");
    for (const s of scripts) {
      const code = s.textContent || "";
      const m = code.match(/const\s+isLoggedIn\s*=\s*(true|false)/);
      if (m) {
        return m[1] === "true";
      }
    }
    const signInLink = document.querySelector(sel.signInLink || "header a.mb-signin[href*='/login']");
    if (signInLink) {
      return false;
    }
    return true;
  }

  function checkActiveErrorModal(sel) {
    // 1. #limitModal.modal-open
    const limitModal = document.querySelector(sel.limitModal || "#limitModal");
    if (limitModal && (limitModal.classList.contains("modal-open") || limitModal.dataset.open === "true")) {
      const title = (document.querySelector(sel.limitModalTitle || "#limitModalTitle")?.textContent || "").trim();
      const body = (document.querySelector(sel.limitModalBody || "#limitModalBody")?.textContent || "").trim();
      const combined = [title, body].filter(Boolean).join(": ");
      return combined || "Clever AI reported a processing or session limit error.";
    }

    // 2. #signupModal.modal-open
    const signupModal = document.getElementById("signupModal");
    if (signupModal && signupModal.classList.contains("modal-open")) {
      return "Clever AI requires you to sign in at cleverhumanizer.ai to continue.";
    }

    // 3. #unsupportedLanguageModal
    const langModal = document.querySelector(sel.unsupportedLangModal || "#unsupportedLanguageModal");
    if (langModal && !langModal.hidden && langModal.getAttribute("aria-hidden") === "false") {
      const title = (document.querySelector(sel.unsupportedLangTitle || "#unsupportedLanguageTitle")?.textContent || "").trim();
      const body = (document.querySelector(sel.unsupportedLangText || "#unsupportedLanguageText")?.textContent || "").trim();
      return [title, body].filter(Boolean).join(": ") || "Unsupported language in Clever AI.";
    }

    // 4. Security check / Turnstile modal (never bypass or click; report immediately to user)
    const turnstileIframe = document.querySelector("iframe[src*='challenges.cloudflare.com']");
    if (turnstileIframe) {
      const overlay = turnstileIframe.closest("div[style*='position: fixed'], div[style*='position:fixed']");
      if (!overlay || overlay.style.visibility !== "hidden") {
        return "Clever AI requested a security check in your browser. Please open the Clever AI tab in Opera to complete it, then click Retry.";
      }
    }

    // 5. Inline limit message (.limit-msg)
    const inlineLimit = document.querySelector(sel.inlineLimitMsg || ".limit-msg");
    if (inlineLimit && !inlineLimit.hidden && inlineLimit.offsetParent !== null) {
      const txt = (inlineLimit.textContent || "").trim();
      if (txt) return txt;
    }

    // 6. Word count / min length danger banner
    const dangerMsg = document.querySelector(sel.wordCountDanger || ".quillWordCount.danger .info-msg.active");
    if (dangerMsg) {
      const txt = (dangerMsg.textContent || "").trim();
      if (txt) return txt;
    }

    return null;
  }

  function extractCleanOutputText(outputEl) {
    if (!outputEl) return "";
    if (outputEl.querySelector(".place")) return "";

    const clone = outputEl.cloneNode(true);
    clone
      .querySelectorAll(
        ".paraphrase-sentence-variants, .grammar-sent-btn, .grammar-long-sentence, .stream-status, .stream-caret, .place"
      )
      .forEach((el) => el.remove());

    clone
      .querySelectorAll(
        'span[class^="diff-"], mark, .paraphrase-sentence, .paraphrase-change, .paraphrase-frozen, .grammar-sent, .grammar-inline-issue, .grammar-applied'
      )
      .forEach((el) => {
        const parent = el.parentNode;
        if (parent) {
          while (el.firstChild) {
            parent.insertBefore(el.firstChild, el);
          }
          parent.removeChild(el);
        }
      });

    clone.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
    const blocks = clone.querySelectorAll("p, h1, h2, h3, h4, h5, h6, li");
    if (blocks.length > 0) {
      const lines = [];
      blocks.forEach((b) => {
        let t = (b.textContent || b.innerText || "").replace(/\u00a0/g, " ").replace(/[ \t]+\n/g, "\n");
        if (b.tagName === "P" && /^\s*$/.test(t)) {
          lines.push("");
        } else {
          t = t.replace(/\n+$/g, "");
          lines.push(t);
        }
      });
      return lines.join("\n").replace(/\r\n/g, "\n").replace(/[ \t]+\n/g, "\n").trim();
    }
    return (clone.textContent || clone.innerText || "").replace(/\u00a0/g, " ").replace(/\r\n/g, "\n").trim();
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async function pasteTextIntoEditor(inputEditor, text) {
    inputEditor.focus();

    // Attempt 1: Dispatch standard ClipboardEvent('paste')
    try {
      const dt = new DataTransfer();
      dt.setData("text/plain", text);
      const pasteEvt = new ClipboardEvent("paste", {
        bubbles: true,
        cancelable: true,
        clipboardData: dt
      });
      inputEditor.dispatchEvent(pasteEvt);
    } catch (e) {}

    await new Promise((r) => setTimeout(r, 60));

    // Verify editor contents; in background tabs, document.execCommand('insertText') may not fire
    const currentText = (inputEditor.textContent || inputEditor.innerText || "").replace(/\u00a0/g, " ").trim();
    if (!currentText || currentText !== text.trim()) {
      const normalized = String(text).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      const paragraphs = normalized.split("\n");
      inputEditor.innerHTML =
        paragraphs
          .map((line) => "<p>" + (line.trim() === "" ? "<br>" : escapeHtml(line)) + "</p>")
          .join("") || "<p><br></p>";

      inputEditor.dispatchEvent(new Event("input", { bubbles: true }));
      inputEditor.dispatchEvent(new Event("change", { bubbles: true }));
      inputEditor.dispatchEvent(new Event("blur", { bubbles: true }));
    } else {
      inputEditor.dispatchEvent(new Event("input", { bubbles: true }));
      inputEditor.dispatchEvent(new Event("blur", { bubbles: true }));
    }

    await new Promise((r) => setTimeout(r, 200));
  }

  function reportProgress(requestId, status, percent) {
    try {
      if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.sendMessage) {
        chrome.runtime.sendMessage({
          type: "CONTENT_PROGRESS",
          requestId,
          status,
          percent
        });
      }
    } catch (e) {}
  }

  async function runHumanizeFlow(requestId, rawText) {
    const cfg = getConfig();
    const sel = cfg.SELECTORS || {};
    const text = String(rawText || "");

    if (!text.trim()) {
      return {
        ok: false,
        code: "EMPTY_INPUT",
        message: "Copied text is empty. Please highlight and copy text in Word."
      };
    }

    const words = text.trim().split(/\s+/).length;
    const maxWords = cfg.maxWords || 3000;
    if (words > maxWords) {
      return {
        ok: false,
        code: "TEXT_TOO_LONG",
        message: `Text is ${words.toLocaleString()} words, which exceeds Clever AI's ${maxWords.toLocaleString()}-word limit.`
      };
    }

    if (cfg.requireLogin !== false && !checkIsLoggedIn(sel)) {
      return {
        ok: false,
        code: "NOT_LOGGED_IN",
        message: "Not logged in to Clever AI. Please sign in at cleverhumanizer.ai in your browser."
      };
    }

    const pane = document.querySelector(sel.humanizerPane || "#AIHumanizer") || document;
    let inputEditor = document.querySelector(
      sel.inputEditor || "#AIHumanizer #quillEditor .ql-editor"
    );
    let humanizeBtn = findButtonBySelectorOrText(
      pane,
      sel.humanizeBtn || "#AIHumanizer button.submitQuill",
      sel.humanizeBtnTextPattern || "^Humanize(?:\\s+AI)?$"
    );
    let outputEditor = document.querySelector(
      sel.outputEditor || "#AIHumanizer .quillOutput, .ql-editor.quillOutput"
    );
    const copyTextBtn = findButtonBySelectorOrText(
      pane,
      sel.copyTextBtn || ".copyFromQuillText button, button[aria-label='Copy Text']",
      sel.copyTextPattern || "^Copy\\s+Text$"
    );

    if (!inputEditor || !humanizeBtn || !outputEditor) {
      return {
        ok: false,
        code: "LAYOUT_CHANGED",
        message:
          "Clever AI page layout did not match expected selectors (missing editor, Humanize, or result area)."
      };
    }

    // Dismiss any stale error modal before starting
    const limitModal = document.querySelector(sel.limitModal || "#limitModal");
    if (limitModal && limitModal.classList.contains("modal-open")) {
      const dismissBtn = limitModal.querySelector("[data-bs-dismiss], .modal-close");
      if (dismissBtn) dismissBtn.click();
      limitModal.classList.remove("modal-open");
    }

    // Step 4a: Click "Clear & Structured" ("Clear structure") if present
    const clearStructBtn = findButtonBySelectorOrText(
      pane,
      sel.clearStructuredBtn || "#humanizeStyleTabs button[data-humanize-style='academic']",
      sel.clearStructuredTextPattern || "Clear\\s*(?:&|and)?\\s*Structured|Clear\\s+structure"
    );
    if (clearStructBtn && !clearStructBtn.classList.contains("active")) {
      clearStructBtn.click();
      await new Promise((r) => setTimeout(r, 50));
    }

    // Step 4b: If there is existing text in the input area, click "Remove text"
    const existingInput = (inputEditor.textContent || inputEditor.innerText || "").trim();
    if (existingInput.length > 0) {
      const removeBtn = findButtonBySelectorOrText(
        pane,
        sel.removeTextBtn || "#AIHumanizer button.remove-text",
        sel.removeTextPattern || "^Remove\\s+text$"
      );
      if (removeBtn) {
        removeBtn.removeAttribute("disabled");
        removeBtn.click();
        await new Promise((r) => setTimeout(r, 80));
      }
      if ((inputEditor.textContent || inputEditor.innerText || "").trim().length > 0) {
        inputEditor.innerHTML = "<p><br></p>";
        inputEditor.dispatchEvent(new Event("input", { bubbles: true }));
        await new Promise((r) => setTimeout(r, 60));
      }
    }

    // Step 4c: Paste the clipboard text into the input area
    reportProgress(requestId, "Pasting text into Clever AI…", 5);
    await pasteTextIntoEditor(inputEditor, text);

    const modalErrAfterPaste = checkActiveErrorModal(sel);
    if (modalErrAfterPaste) {
      return {
        ok: false,
        code: "CLEVER_AI_INPUT_ERROR",
        message: modalErrAfterPaste
      };
    }

    // Re-query controls because modern editors can replace their DOM after input.
    inputEditor = document.querySelector(sel.inputEditor || "#AIHumanizer #quillEditor .ql-editor");
    humanizeBtn = findButtonBySelectorOrText(
      pane,
      sel.humanizeBtn || "#AIHumanizer button.submitQuill",
      sel.humanizeBtnTextPattern || "^Humanize(?:\\s+AI)?$"
    );
    outputEditor = document.querySelector(
      sel.outputEditor || "#AIHumanizer .quillOutput, .ql-editor.quillOutput"
    );
    if (!inputEditor || !humanizeBtn || !humanizeBtn.isConnected || !outputEditor) {
      return {
        ok: false,
        code: "LAYOUT_CHANGED",
        message: "Clever AI refreshed its editor controls. Please retry the request."
      };
    }

    // Ensure the current Humanize button is enabled before clicking it.
    const enableStart = Date.now();
    while (humanizeBtn.disabled && Date.now() - enableStart < 3000) {
      inputEditor.dispatchEvent(new Event("input", { bubbles: true }));
      inputEditor.dispatchEvent(new Event("blur", { bubbles: true }));
      await new Promise((r) => setTimeout(r, 100));
      humanizeBtn = findButtonBySelectorOrText(
        pane,
        sel.humanizeBtn || "#AIHumanizer button.submitQuill",
        sel.humanizeBtnTextPattern || "^Humanize(?:\\s+AI)?$"
      );
      if (!humanizeBtn || !humanizeBtn.isConnected) {
        return {
          ok: false,
          code: "LAYOUT_CHANGED",
          message: "Clever AI refreshed its Humanize button. Please retry the request."
        };
      }
    }
    if (humanizeBtn.disabled) {
      return {
        ok: false,
        code: "HUMANIZE_BUTTON_DISABLED",
        message: "Clever AI did not enable the Humanize button after receiving the text. Please retry."
      };
    }

    const previousOutputText = extractCleanOutputText(outputEditor);

    // Step 4d: Click "Humanize"
    reportProgress(requestId, "Clicked Humanize AI — waiting for result…", 10);
    humanizeBtn.scrollIntoView({ block: "center" });
    humanizeBtn.click();

    // Step 4e: Wait until Clever AI has actually finished
    const timeoutMs = cfg.humanizeTimeoutMs || 180000;
    const loaderEl = document.querySelector(sel.loaderContainer || "#loaderContainer");
    const loaderPctEl = document.querySelector(sel.loaderPercent || "#loaderPercent");
    const loadingTextEl = document.querySelector(sel.loadingText || "#loadingText");

    const waitResult = await new Promise((resolve) => {
      let sawRunningState = false;
      let resultEventFired = false;
      let settled = false;
      let lastReportedPct = 10;
      let lastKeepAliveTime = Date.now();

      const finish = (outcome) => {
        if (settled) return;
        settled = true;
        observer.disconnect();
        window.removeEventListener("writing-tool:result", onResultEvent);
        window.removeEventListener("upsell:result", onResultEvent);
        clearInterval(checkInterval);
        clearTimeout(timeoutTimer);
        resolve(outcome);
      };

      const onResultEvent = () => {
        resultEventFired = true;
        checkPageState();
      };

      const checkPageState = () => {
        if (settled) return;
        inputEditor = document.querySelector(sel.inputEditor || "#AIHumanizer #quillEditor .ql-editor") || inputEditor;
        humanizeBtn =
          findButtonBySelectorOrText(
            pane,
            sel.humanizeBtn || "#AIHumanizer button.submitQuill",
            sel.humanizeBtnTextPattern || "^Humanize(?:\\s+AI)?$"
          ) || humanizeBtn;
        outputEditor =
          document.querySelector(sel.outputEditor || "#AIHumanizer .quillOutput, .ql-editor.quillOutput") ||
          outputEditor;

        // 1. Check for any Clever AI error modal or security check
        const errText = checkActiveErrorModal(sel);
        if (errText) {
          finish({
            ok: false,
            code: "CLEVER_AI_ERROR",
            message: errText
          });
          return;
        }

        // 2. Check loader visibility and button busy state
        const toolEl = inputEditor.closest(".tool");
        const toolRunning = Boolean(toolEl && toolEl.classList.contains("is-running"));
        const loaderVisible =
          toolRunning ||
          Boolean(
            loaderEl &&
              loaderEl.style.display !== "none" &&
              getComputedStyle(loaderEl).display !== "none"
          );
        const btnBusy =
          humanizeBtn.disabled ||
          humanizeBtn.classList.contains("active-geenration") ||
          humanizeBtn.classList.contains("active-generation");

        if (loaderVisible || btnBusy) {
          sawRunningState = true;
          const rawPct = loaderPctEl ? parseInt(loaderPctEl.textContent || "0", 10) : 0;
          const statusMsg = loadingTextEl
            ? (loadingTextEl.textContent || "").trim()
            : "Refining your content…";
          const now = Date.now();
          if (rawPct > lastReportedPct) {
            lastReportedPct = rawPct;
            lastKeepAliveTime = now;
            reportProgress(
              requestId,
              statusMsg || `Humanizing… (${rawPct}%)`,
              Math.min(99, rawPct)
            );
          } else if (now - lastKeepAliveTime >= 2500) {
            // Keep MV3 service worker awake and advance synthetic progress when tab is in background
            lastKeepAliveTime = now;
            lastReportedPct = Math.min(95, lastReportedPct + 4);
            reportProgress(
              requestId,
              statusMsg || "Refining your content in background…",
              lastReportedPct
            );
          }
          return;
        }

        // 3. Check finished state
        const hasPlaceholder = Boolean(outputEditor.querySelector(sel.outputPlaceholder || ".place"));
        const currentOutput = extractCleanOutputText(outputEditor);
        const copyEnabled =
          !copyTextBtn || (!copyTextBtn.disabled && !copyTextBtn.hasAttribute("disabled"));

        if (
          !loaderVisible &&
          !btnBusy &&
          !hasPlaceholder &&
          copyEnabled &&
          currentOutput.length > 0 &&
          (sawRunningState || resultEventFired || currentOutput !== previousOutputText)
        ) {
          finish({
            ok: true,
            outputText: currentOutput
          });
          return;
        }

        if (!loaderVisible && !btnBusy && (sawRunningState || resultEventFired) && !hasPlaceholder && currentOutput.length === 0) {
          finish({
            ok: true,
            outputText: ""
          });
        }
      };

      const observer = new MutationObserver(() => checkPageState());
      observer.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        characterData: true
      });

      window.addEventListener("writing-tool:result", onResultEvent);
      window.addEventListener("upsell:result", onResultEvent);
      const checkInterval = setInterval(checkPageState, 200);
      const timeoutTimer = setTimeout(() => {
        finish({
          ok: false,
          code: "TIMEOUT",
          message: "Timed out waiting for Clever AI to finish humanizing."
        });
      }, timeoutMs);
    });

    if (!waitResult.ok) {
      return waitResult;
    }

    // Step 4f: Read the result directly instead of using the site's clipboard button.
    const finalResultText = extractCleanOutputText(outputEditor) || waitResult.outputText || "";
    if (!finalResultText.trim()) {
      return {
        ok: false,
        code: "EMPTY_RESULT",
        message: "Clever AI finished, but the humanized result was empty."
      };
    }

    const resultWords = finalResultText.trim().split(/\s+/).length;
    return {
      ok: true,
      text: finalResultText,
      words: resultWords
    };
  }

  // Always update the global function reference so re-injection upgrades logic in place
  globalThis.__runCleverHumanizeFlow = runHumanizeFlow;

  if (!globalThis.__humanizeHelperListenerRegistered) {
    globalThis.__humanizeHelperListenerRegistered = true;
    if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
      chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (!message) return false;
        if (message.type === "PING_CONTENT") {
          sendResponse({ ok: true });
          return false;
        }
        if (message.type === "RUN_CLEVER_HUMANIZE") {
          globalThis
            .__runCleverHumanizeFlow(message.requestId, message.text)
            .then((res) => sendResponse(res))
            .catch((err) =>
              sendResponse({
                ok: false,
                code: "CONTENT_SCRIPT_ERROR",
                message: err && err.message ? err.message : String(err)
              })
            );
          return true;
        }
        return false;
      });
    }
  }
})();
