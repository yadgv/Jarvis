// Passes the page in front to Jarvis (http://127.0.0.1:47321) and answers his
// requests for the page's code. Nothing is sent anywhere else.
const JARVIS = "http://127.0.0.1:47321";

// The toolbar icon shows ON (green) while Jarvis is reachable, OFF (grey) when not.
let shown = null;
function badge(on) {
  if (on === shown) return;
  shown = on;
  chrome.action.setBadgeText({text: on ? "ON" : "OFF"});
  chrome.action.setBadgeBackgroundColor({color: on ? "#1a9e4b" : "#777777"});
  chrome.action.setTitle({title: on ? "Jarvis eyes: connected to Jarvis"
                                    : "Jarvis eyes: can't reach Jarvis (is Jarvis running?)"});
}

async function post(path, body) {
  try {
    const r = await fetch(JARVIS + path, {method: "POST", headers: {"Content-Type": "application/json"},
                                          body: JSON.stringify(body)});
    badge(r.ok);
    return r.ok ? await r.json() : {};
  } catch (e) { badge(false); return {}; }   // Jarvis isn't running
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
  return tab;
}

async function sendHtml() {
  const tab = await activeTab();
  if (!tab) return;
  try {
    const res = await chrome.tabs.sendMessage(tab.id, {kind: "html"});
    if (res) await post("/html", res);
  } catch (e) {
    // No content script there (a new tab or a browser page): read it directly.
    try {
      const [r] = await chrome.scripting.executeScript({target: {tabId: tab.id},
        func: () => ({url: location.href, html: document.documentElement.outerHTML})});
      if (r && r.result) await post("/html", r.result);
    } catch (e2) { await post("/html", {url: tab.url || "", html: ""}); }
  }
}

async function handle(want) {
  if (want === "html") await sendHtml();
}

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.kind !== "page" || !sender.tab || !sender.tab.active) return;
  post("/page", msg.page).then(r => r && handle(r.want));
});

// Switching tabs or windows: ask the new tab to report itself.
async function poke() {
  const tab = await activeTab();
  if (tab) chrome.tabs.sendMessage(tab.id, {kind: "report"}).catch(() => {});
}
chrome.tabs.onActivated.addListener(poke);
chrome.windows.onFocusChanged.addListener(poke);

// Wait for Jarvis's requests ("show me the code of this page"). The alarm
// wakes this worker if the browser put it to sleep.
let waiting = false;
async function listen() {
  if (waiting) return;
  waiting = true;
  try {
    for (let i = 0; i < 6; i++) {
      const r = await fetch(JARVIS + "/next", {method: "POST", headers: {"Content-Type": "application/json"},
                                               body: "{}"});
      badge(r.ok);
      if (!r.ok) break;
      const j = await r.json();
      if (j.want) await handle(j.want);
    }
  } catch (e) { badge(false); /* Jarvis isn't running */ }
  waiting = false;
}
chrome.alarms.create("jarvis", {periodInMinutes: 0.5});
chrome.alarms.onAlarm.addListener(() => { listen(); poke(); });
chrome.runtime.onStartup.addListener(listen);
chrome.runtime.onInstalled.addListener(listen);
listen();
