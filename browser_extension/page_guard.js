// Run in the page's MAIN world so Clever AI cannot block background processing with alert().
(function () {
  const nativeAlert = window.alert;
  if (typeof nativeAlert !== "function" || window.__humanizeCopyAlertGuardInstalled) {
    return;
  }

  window.__humanizeCopyAlertGuardInstalled = true;
  window.alert = function (message) {
    if (/copy\s+failed|failed\s+to\s+copy/i.test(String(message || ""))) {
      console.info("[Humanize Helper] Suppressed Clever AI's background clipboard alert.");
      return;
    }
    return nativeAlert.apply(this, arguments);
  };
})();
