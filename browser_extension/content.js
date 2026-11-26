// Reads the page you're looking at and hands it to the extension's background
// worker, which passes it to Jarvis on this PC. Runs only while the tab is visible.
(() => {
  const MAX_TEXT = 300000;
  let last = "", timer = null;

  function readable() {
    const main = document.querySelector("article, main, [role=main]") || document.body;
    let text = (main && main.innerText) || "";
    if (main !== document.body && text.length < 500) text = document.body.innerText || text;
    return text.replace(/\n{3,}/g, "\n\n").slice(0, MAX_TEXT);
  }

  function report() {
    if (document.visibilityState !== "visible") return;
    const page = {
      url: location.href, title: document.title, text: readable(),
      selection: String(window.getSelection() || "").slice(0, 20000),
    };
    const key = page.url + "|" + page.title + "|" + page.text.length + "|" + page.selection.length;
    if (key === last) return;
    last = key;
    try { chrome.runtime.sendMessage({kind: "page", page}); } catch (e) { /* extension reloaded */ }
  }
  const soon = (ms) => { clearTimeout(timer); timer = setTimeout(report, ms); };

  report();
  document.addEventListener("visibilitychange", () => soon(100));
  document.addEventListener("selectionchange", () => soon(800));
  addEventListener("focus", () => soon(100));
  new MutationObserver(() => soon(3000)).observe(document.documentElement, {childList: true, subtree: true, characterData: true});

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    if (msg.kind === "report") { last = ""; report(); }
    if (msg.kind === "html") reply({url: location.href, html: document.documentElement.outerHTML.slice(0, 5000000)});
  });
})();
