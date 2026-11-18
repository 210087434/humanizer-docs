// Manifest V3 Service Worker for Humanize Helper Bridge
importScripts("config.js");

let ws = null;
let reconnectTimer = null;
let heartbeatTimer = null;
let reconnectAttempts = 0;
let isConnecting = false;
let activeRequestId = null;

function getWsUrl() {
  const cfg = globalThis.HUMANIZE_CONFIG;
  const encodedToken = encodeURIComponent(cfg.authToken);
  return `ws://${cfg.wsHost}:${cfg.wsPort}/ws?token=${encodedToken}`;
}

function sendToDesktop(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(
        JSON.stringify({
          ...payload,
          token: globalThis.HUMANIZE_CONFIG.authToken
        })
      );
      return true;
    } catch (err) {
      return false;
    }
  }
  return false;
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  const delay = Math.min(5000, 1000 * Math.pow(1.5, Math.min(reconnectAttempts, 4)));
  reconnectAttempts += 1;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
  }, delay);
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      sendToDesktop({
        type: "HEARTBEAT",
        timestamp: Date.now()
      });
    } else {
      connectWebSocket();
    }
  }, 15000);
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function connectWebSocket() {
  if (isConnecting || (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING))) {
    return;
  }
  isConnecting = true;
  try {
    const socket = new WebSocket(getWsUrl());
    ws = socket;

    socket.onopen = () => {
      isConnecting = false;
      reconnectAttempts = 0;
      sendToDesktop({
        type: "HELLO",
        version: "1.0.0",
        timestamp: Date.now()
      });
      startHeartbeat();
    };

    socket.onmessage = async (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      if (msg.type === "PING") {
        sendToDesktop({ type: "PONG", timestamp: Date.now() });
        return;
      }
      if (msg.type === "HUMANIZE_REQUEST") {
        await handleHumanizeRequest(msg);
      }
    };

    socket.onclose = () => {
      isConnecting = false;
      ws = null;
      stopHeartbeat();
      scheduleReconnect();
    };

    socket.onerror = () => {
      isConnecting = false;
      try {
        socket.close();
      } catch (e) {}
    };
  } catch (err) {
    isConnecting = false;
    scheduleReconnect();
  }
}

async function waitForTabComplete(tabId, timeoutMs) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (!tab) throw new Error("Clever AI browser tab was closed.");
      if (tab.status === "complete") return tab;
    } catch (err) {
      throw new Error("Clever AI browser tab was closed while loading.");
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("Clever AI page took too long to load. Please check your internet connection.");
}

async function findOrCreateCleverTab(targetBaseUrl, timeoutMs) {
  const parsed = new URL(targetBaseUrl);
  const matchPattern = `${parsed.origin}/*`;
  const tabs = await chrome.tabs.query({ url: matchPattern });

  // Prefer a tab already on the root AI Humanizer page
  let targetTab =
    tabs.find((t) => {
      try {
        const u = new URL(t.url);
        return u.pathname === "/" || u.pathname === "";
      } catch (e) {
        return false;
      }
    }) || tabs[0];

  if (!targetTab) {
    targetTab = await chrome.tabs.create({
      url: targetBaseUrl,
      active: false
    });
  } else {
    const u = new URL(targetTab.url);
    if (u.pathname !== "/" && u.pathname !== "" && !u.pathname.startsWith("/mock")) {
      await chrome.tabs.update(targetTab.id, { url: targetBaseUrl });
    }
  }

  await waitForTabComplete(targetTab.id, timeoutMs);
  return targetTab;
}

async function ensureContentScriptLoaded(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    world: "MAIN",
    func: () => {
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
    }
  });
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["config.js", "content.js"]
  });
}

async function handleHumanizeRequest(msg) {
  const requestId = msg.requestId;
  const text = msg.text || "";
  const cfg = globalThis.HUMANIZE_CONFIG;

  if (activeRequestId) {
    sendToDesktop({
      type: "HUMANIZE_ERROR",
      requestId,
      code: "BUSY",
      message: "Another humanize request is already running in the browser."
    });
    return;
  }

  activeRequestId = requestId;
  try {
    sendToDesktop({
      type: "HUMANIZE_PROGRESS",
      requestId,
      status: "Opening Clever AI in background…",
      percent: 2
    });

    const tab = await findOrCreateCleverTab(cfg.cleverAiUrl, cfg.pageLoadTimeoutMs);
    await ensureContentScriptLoaded(tab.id);

    const response = await chrome.tabs.sendMessage(tab.id, {
      type: "RUN_CLEVER_HUMANIZE",
      requestId,
      text
    });

    if (!response) {
      sendToDesktop({
        type: "HUMANIZE_ERROR",
        requestId,
        code: "NO_RESPONSE",
        message: "Clever AI tab did not respond. Please refresh cleverhumanizer.ai."
      });
    } else if (response.ok) {
      sendToDesktop({
        type: "HUMANIZE_RESULT",
        requestId,
        text: response.text,
        words: response.words || 0
      });
    } else {
      sendToDesktop({
        type: "HUMANIZE_ERROR",
        requestId,
        code: response.code || "CLEVER_AI_ERROR",
        message: response.message || "Clever AI failed to humanize the text."
      });
    }
  } catch (err) {
    sendToDesktop({
      type: "HUMANIZE_ERROR",
      requestId,
      code: "EXTENSION_EXCEPTION",
      message: err && err.message ? err.message : String(err)
    });
  } finally {
    activeRequestId = null;
  }
}

// Listen for progress updates from content.js and relay to desktop
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "CONTENT_PROGRESS") {
    sendToDesktop({
      type: "HUMANIZE_PROGRESS",
      requestId: message.requestId,
      status: message.status,
      percent: message.percent || 0
    });
    sendResponse({ ok: true });
    return false;
  }
  return false;
});

// Keep MV3 service worker alive & reconnected using chrome.alarms
chrome.alarms.create("humanizeHelperKeepAlive", { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "humanizeHelperKeepAlive") {
    connectWebSocket();
  }
});

chrome.runtime.onInstalled.addListener(() => {
  connectWebSocket();
});

chrome.runtime.onStartup.addListener(() => {
  connectWebSocket();
});

connectWebSocket();
