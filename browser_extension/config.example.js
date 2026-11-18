// Safe development fixture. The desktop app generates config.js with a per-user token.
const HUMANIZE_CONFIG = {
  wsHost: "127.0.0.1",
  wsPort: 54829,
  authToken: "LOCAL_DEVELOPMENT_TOKEN_NOT_FOR_PRODUCTION",
  cleverAiUrl: "https://cleverhumanizer.ai",
  requireLogin: true,
  pageLoadTimeoutMs: 30000,
  humanizeTimeoutMs: 180000,
  maxWords: 3000,
  minWords: 5,
  SELECTORS: {
    humanizerPane: "#AIHumanizer, form#quillForm",
    styleTabsGroup: "#humanizeStyleTabs, [aria-label='Choose the Writing style']",
    clearStructuredBtn: "#humanizeStyleTabs button[data-humanize-style='academic']",
    clearStructuredTextPattern: "Clear\\s*(?:&|and)?\\s*Structured|Clear\\s+structure",
    removeTextBtn: "#AIHumanizer button.remove-text, button.remove-text",
    removeTextPattern: "^Remove\\s+text$",
    inputEditor: "#AIHumanizer #quillEditor .ql-editor, #quillEditor .ql-editor, .original-block .ql-editor[contenteditable='true']",
    originalWordCount: "#AIHumanizer .originalWordsNum, .originalWordsNum",
    humanizeBtn: "#AIHumanizer button.submitQuill, button.submitQuill",
    humanizeBtnTextPattern: "^Humanize(?:\\s+AI)?$",
    loaderContainer: "#loaderContainer",
    loaderPercent: "#loaderPercent",
    loadingText: "#loadingText",
    outputEditor: "#AIHumanizer .quillOutput, .humanResult .quillOutput, .ql-editor.quillOutput",
    outputPlaceholder: ".place",
    resultWordCount: "#outputWordCount .resultWordsNum, .resultWordsNum",
    copyTextBtn: ".copyFromQuillText button, button[aria-label='Copy Text'], button[title='Copy Text']",
    copyTextPattern: "^Copy\\s+Text$",
    signInLink: "header a.mb-signin[href*='/login'], header a[href$='/login']",
    limitModal: "#limitModal",
    limitModalTitle: "#limitModalTitle",
    limitModalBody: "#limitModalBody",
    unsupportedLangModal: "#unsupportedLanguageModal",
    unsupportedLangTitle: "#unsupportedLanguageTitle",
    unsupportedLangText: "#unsupportedLanguageText",
    inlineLimitMsg: ".limit-msg",
    wordCountDanger: ".quillWordCount.danger .info-msg.active"
  }
};

if (typeof globalThis !== "undefined") {
  globalThis.HUMANIZE_CONFIG = HUMANIZE_CONFIG;
}
