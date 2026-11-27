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

  // Jarvis's pointer: find the element he means ("the sign in button") and say where it is on screen.
  function norm(t) { return (t || "").toLowerCase().replace(/\s+/g, " ").trim(); }
  function score(text, want) {
    text = norm(text); if (!text || text.length > 200) return 0;
    if (text === want) return 1;
    if (text.startsWith(want) || text.endsWith(want)) return 0.9 - Math.min(0.3, (text.length - want.length) / 200);
    if (text.includes(want)) return 0.75 - Math.min(0.3, (text.length - want.length) / 300);
    const words = want.split(" ").filter(w => w.length > 2);
    if (!words.length) return 0;
    const hit = words.filter(w => text.includes(w)).length / words.length;
    return hit >= 0.6 ? 0.5 * hit : 0;
  }
  function find(query) {
    const want = norm(query);
    const sel = "a,button,input,select,textarea,label,summary,[role=button],[role=link],[role=tab],[role=menuitem]," +
                "[aria-label],h1,h2,h3,h4,li,td,th,img[alt],p,span";
    let best = null;
    for (const el of document.querySelectorAll(sel)) {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      const text = el.getAttribute("aria-label") || el.innerText || el.value || el.placeholder || el.alt || el.title;
      let s = score(text, want);
      if (!s) continue;
      if (/^(a|button|input|select|textarea|summary)$/i.test(el.tagName) || el.getAttribute("role")) s += 0.1;
      if (!best || s > best.s || (s === best.s && r.width * r.height < best.area)) best = {el, s, area: r.width * r.height};
    }
    if (!best) return {found: false};
    best.el.scrollIntoView({block: "center", inline: "nearest"});
    const r = best.el.getBoundingClientRect();
    return {found: true, x: r.left, y: r.top, w: r.width, h: r.height, label: norm(best.el.innerText || best.el.getAttribute("aria-label") || "").slice(0, 60),
            dpr: devicePixelRatio, screenX, screenY, outerWidth, outerHeight, innerWidth, innerHeight};
  }

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    if (msg.kind === "find") reply(find(msg.query || ""));
    if (msg.kind === "report") { last = ""; report(); }
    if (msg.kind === "html") reply({url: location.href, html: document.documentElement.outerHTML.slice(0, 5000000)});
  });
})();
