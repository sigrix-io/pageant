// Drawn over the app's page while a lesson records: a cursor, a spotlight, captions, a chapter
// label and title cards. Loaded with context.add_init_script, so it is in place before the page's
// own scripts run, in every document the page loads; studio.py drives it through window.__demo.
//
// Each document starts with nothing on screen: a click that goes to another page (a link, a form
// post, a server redirect) leaves this one behind with everything it drew. So the studio keeps
// what is on screen (the chapter label, the caption, the title card and where the pointer is) and
// hands it to each page with show(), once from a script of its own that runs as the next document
// starts and again as it loads: a page it has not drawn yet gets all of it at once, without the
// fades, so the page changes under them; a page it has drawn gets what changed, with them. The
// pointer is not drawn until something places it, and it is all built as soon as the page has a
// body, so the first frame of the new page has it.
//
// Built with the CSSOM only (element.style), never a <style> element or a style="" attribute, so
// an app's own CSP (style-src 'self') stays on and the page renders as a person sees it. The title
// card's mark is an address on the page's own origin (Lesson.mark), which that CSP allows too.
//
// A screen held upright, a phone's (camera.PHONE), is laid out for a phone: what is drawn is sized
// for it, the caption sits above the foot of the screen that a vertical video's player covers with
// its own titles, and the pointer is a fingertip rather than an arrow.
(() => {
  if (window.__demo) return;
  const ui = {};
  // What is on screen: what each call below changes, and what is drawn from.
  const shown = { label: null, corner: "top-right", caption: null, card: null, pointer: true, at: null };
  let target = null, pad = 8, drawnHere = false, movedHere = false;
  const UPRIGHT = innerHeight > innerWidth;
  const FONT = "Inter, system-ui, sans-serif";
  // How each part is laid out on a computer's screen, and on a phone's.
  const LOOK = UPRIGHT ? {
    edge: "12px",
    cap: { bottom: "140px", maxWidth: "calc(100vw - 72px)", padding: "10px 16px", borderRadius: "12px",
      font: "600 20px/1.3 " + FONT, textWrap: "balance" },
    chip: { top: "12px", padding: "5px 11px", font: "600 12px/1.2 " + FONT },
    card: { gap: "10px", padding: "0 24px", background: "radial-gradient(520px 900px at 50% 40%, #232842, #0e1018)" },
    logo: { width: "60px", height: "65px", marginBottom: "6px" },
    kicker: { font: "600 12px/1.25 " + FONT },
    title: { font: "700 30px/1.15 " + FONT, maxWidth: "100%" },
    sub: { font: "400 16px/1.45 " + FONT, maxWidth: "100%" },
    points: { gap: "12px", margin: "14px 0 0", font: "500 17px/1.3 " + FONT, maxWidth: "100%" },
    point: { gap: "12px" },
    mark: { width: "28px", height: "28px", font: "700 14px/28px " + FONT },
  } : {
    edge: "18px",
    cap: { bottom: "30px", maxWidth: "1040px", padding: "14px 26px", borderRadius: "14px", font: "500 23px/1.38 " + FONT },
    chip: { top: "12px", padding: "7px 15px", font: "600 15px/1.2 " + FONT },
    card: { gap: "14px", background: "radial-gradient(1200px 600px at 50% 40%, #232842, #0e1018)" },
    logo: { width: "84px", height: "91px", marginBottom: "10px" },
    kicker: { font: "600 18px/1.2 " + FONT },
    title: { font: "700 54px/1.1 " + FONT, maxWidth: "1000px" },
    sub: { font: "400 24px/1.45 " + FONT, maxWidth: "900px" },
    points: { gap: "16px", margin: "18px 0 0", font: "500 29px/1.3 " + FONT, maxWidth: "900px" },
    point: { gap: "18px" },
    mark: { width: "40px", height: "40px", font: "700 19px/40px " + FONT },
  };
  // Where the pointer's point is in what is drawn for it: an arrow's tip, or a fingertip's middle.
  const HOT = UPRIGHT ? [17, 17] : [4, 2];
  // Where the chapter label may sit: a top corner, clear of the captions at the foot of the screen.
  const CORNERS = {
    "top-right": { right: LOOK.edge, left: "auto" },
    "top-left": { left: LOOK.edge, right: "auto" },
  };
  const css = (el, style) => (Object.assign(el.style, style), el);
  const make = (tag, style) => css(document.createElement(tag), style || {});
  const draw = {
    label() {
      css(ui.chip, CORNERS[shown.corner] || CORNERS["top-right"]);
      ui.chip.textContent = shown.label || "";
      ui.chip.style.opacity = shown.label ? "1" : "0";
    },
    caption() {
      if (!shown.caption) { css(ui.cap, { opacity: "0", transform: "translate(-50%, 14px)" }); return; }
      ui.cap.textContent = shown.caption;
      css(ui.cap, { opacity: "1", transform: "translate(-50%, 0)" });
    },
    card() {
      const spec = shown.card;
      if (spec) {
        if (spec.mark) { ui.logo.src = spec.mark; ui.logo.style.display = ""; } else { ui.logo.style.display = "none"; }
        ui.kicker.textContent = spec.kicker || "";
        ui.title.textContent = spec.title || "";
        ui.sub.textContent = spec.sub || "";
        ui.sub.style.display = spec.sub ? "" : "none";
        draw.points(spec.points || [], !!spec.checks);
      }
      ui.card.style.opacity = spec ? "1" : "0";
      draw.pointer();
    },
    // A card's points: a numbered list, or ticked for a recap. A row already drawn stays as it is
    // and a new one fades up into place, so a list the voice reads out appears as it is read.
    points(points, checks) {
      while (ui.points.children.length > points.length) ui.points.lastChild.remove();
      points.forEach((text, index) => {
        let row = ui.points.children[index];
        if (!row) {
          row = make("li", { display: "flex", alignItems: "center", ...LOOK.point });
          row.append(
            make("span", { flex: "none", borderRadius: "50%", background: "#f7c55f", color: "#14161f",
              textAlign: "center", ...LOOK.mark }),
            make("span", {}));
          ui.points.append(row);
          if (!still) {
            row.animate([{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }],
              { duration: 450, easing: "ease-out" });
          }
        }
        row.children[0].textContent = checks ? "✓" : String(index + 1);
        row.children[1].textContent = text;
      });
      ui.points.style.display = points.length ? "flex" : "none";
    },
    pointer() {
      css(ui.cursor, { display: shown.pointer ? "" : "none", opacity: shown.card ? "0" : "1",
        visibility: shown.at ? "visible" : "hidden" });
      if (shown.at) {
        ui.cursor.style.transform = "translate(" + (shown.at[0] - HOT[0]) + "px," + (shown.at[1] - HOT[1]) + "px)";
      }
    },
  };
  // Set while a change is drawn at once, so a card's new points come up with no fade either.
  let still = false;
  // A change drawn at once: what fades in or out is styled once with no transition, then given it back.
  function instantly(change) {
    const fading = [ui.cap, ui.chip, ui.card];
    const fades = fading.map((el) => el.style.transition);
    for (const el of fading) el.style.transition = "none";
    still = true;
    try { change(); } finally { still = false; }
    void ui.root.offsetHeight;
    fading.forEach((el, index) => { el.style.transition = fades[index]; });
  }
  function ensure() {
    if (ui.root) return true;
    if (!document.body) return false;
    ui.root = make("div", { position: "fixed", inset: "0", pointerEvents: "none", zIndex: "2147483000" });
    // What belongs to the screen rather than the page: the caption, the label and the card. The
    // camera draws it into the view it shows (camera(), below), so a zoomed frame shows it as large
    // as the whole screen does; with no camera it is the screen.
    ui.screen = make("div", { position: "absolute", inset: "0", transformOrigin: "0 0" });
    ui.spot = make("div", { position: "fixed", left: "0", top: "0", width: "0", height: "0", borderRadius: "12px",
      border: "3px solid #f5a524", boxShadow: "0 0 0 9999px rgba(12,14,22,0.40), 0 0 22px 3px rgba(245,165,36,0.55)",
      opacity: "0", transition: "left .45s ease, top .45s ease, width .45s ease, height .45s ease, opacity .35s ease" });
    ui.ripple = make("div", { position: "fixed", left: "0", top: "0", width: "40px", height: "40px", marginLeft: "-20px",
      marginTop: "-20px", borderRadius: "50%", border: "3px solid #f5a524", opacity: "0" });
    ui.cap = make("div", { position: "fixed", left: "50%", transform: "translate(-50%, 14px)", width: "max-content",
      background: "rgba(16,18,27,0.93)", color: "#fff", textAlign: "center", boxShadow: "0 12px 32px rgba(0,0,0,.35)",
      opacity: "0", transition: "opacity .35s ease, transform .35s ease", ...LOOK.cap });
    ui.chip = make("div", { position: "fixed", right: LOOK.edge, borderRadius: "999px", background: "rgba(16,18,27,0.88)",
      color: "#f7c55f", opacity: "0", transition: "opacity .35s ease", ...LOOK.chip });
    const NS = "http://www.w3.org/2000/svg";
    const svg = (tag, attributes) => {
      const el = document.createElementNS(NS, tag);
      for (const [name, value] of Object.entries(attributes)) el.setAttribute(name, value);
      return el;
    };
    if (UPRIGHT) {
      // A fingertip: a disc a touch would cover, ringed in white so it shows on a light page and a dark one.
      ui.cursor = svg("svg", { width: "34", height: "34", viewBox: "0 0 34 34" });
      ui.tip = svg("circle", { cx: "17", cy: "17", r: "14", fill: "rgba(20,22,31,0.32)", stroke: "#ffffff",
        "stroke-width": "2.5" });
      css(ui.tip, { transformBox: "fill-box", transformOrigin: "center" });
      ui.cursor.append(ui.tip);
    } else {
      ui.cursor = svg("svg", { width: "30", height: "30", viewBox: "0 0 28 28" });
      ui.cursor.append(svg("path", { d: "M4 2 L4 22 L9.5 17 L13 25 L16.5 23.5 L13 15.7 L20.5 15.7 Z", fill: "#14161f",
        stroke: "#ffffff", "stroke-width": "1.6", "stroke-linejoin": "round" }));
    }
    css(ui.cursor, { position: "fixed", left: "0", top: "0", filter: "drop-shadow(0 2px 3px rgba(0,0,0,.45))" });
    ui.card = make("div", { position: "fixed", inset: "0", display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", color: "#fff", opacity: "0", transition: "opacity .5s ease", textAlign: "center",
      ...LOOK.card });
    ui.logo = make("img", LOOK.logo);
    ui.logo.alt = "";
    ui.logo.style.display = "none";
    ui.kicker = make("div", { letterSpacing: ".14em", textTransform: "uppercase", color: "#f7c55f", ...LOOK.kicker });
    ui.title = make("div", { letterSpacing: "-0.02em", ...LOOK.title });
    ui.sub = make("div", { color: "#c9cee0", ...LOOK.sub });
    ui.points = make("ol", { display: "none", flexDirection: "column", listStyle: "none", padding: "0",
      textAlign: "left", color: "#eef0f8", ...LOOK.points });
    ui.card.append(ui.logo, ui.kicker, ui.title, ui.sub, ui.points);
    // Drawn before it is on the page, so what the page already had shows at once, with no fade.
    draw.label();
    draw.caption();
    draw.card();
    ui.screen.append(ui.cap, ui.chip, ui.card);
    ui.root.append(ui.spot, ui.ripple, ui.screen, ui.cursor);
    document.documentElement.append(ui.root);
    const follow = () => {
      if (target) {
        const r = target.getBoundingClientRect();
        css(ui.spot, { left: r.left - pad + "px", top: r.top - pad + "px", width: r.width + 2 * pad + "px",
          height: r.height + 2 * pad + "px" });
      }
      requestAnimationFrame(follow);
    };
    requestAnimationFrame(follow);
    return true;
  }
  const set = (part, value) => {
    shown[part] = value;
    if (ensure()) draw[part]();
  };
  window.addEventListener("mousemove", (e) => {
    movedHere = true;
    // The page reports whole pixels: a move to where the pointer is already drawn, to within one, keeps
    // the drawn point, so a pointer the studio brought there does not jump the fraction at its end.
    const near = shown.at && Math.abs(e.clientX - shown.at[0]) < 1 && Math.abs(e.clientY - shown.at[1]) < 1;
    if (!near) shown.at = [e.clientX, e.clientY];
    if (ui.root) draw.pointer();
  }, true);
  window.addEventListener("mousedown", (e) => {
    if (!ui.root) return;
    css(ui.ripple, { left: e.clientX + "px", top: e.clientY + "px" });
    ui.ripple.animate([{ opacity: 0.95, transform: "scale(.35)" }, { opacity: 0, transform: "scale(1.5)" }],
      { duration: 520, easing: "ease-out" });
    // A fingertip presses in, as a touch does.
    if (ui.tip) {
      ui.tip.animate([{ transform: "scale(1)" }, { transform: "scale(.72)", offset: 0.35 }, { transform: "scale(1)" }],
        { duration: 380, easing: "ease-out" });
    }
  }, true);
  // A page an app opens with a view transition (CSS @view-transition) takes no clicks until the
  // transition is over: until then the page hit-tests as <html>. The studio waits for it, and skips
  // one that runs long, through the handle the new page is revealed with.
  let transition = null;
  window.addEventListener("pagereveal", (event) => { transition = event.viewTransition || null; });
  window.__demo = {
    ready: ensure,
    transitioning() { return document.documentElement.matches(":active-view-transition"); },
    skipTransition() { if (transition) transition.skipTransition(); },
    // What is on screen, as the studio keeps it: { label, corner, caption, card, at }. On a page the
    // studio has not drawn yet, all of it is drawn at once; on one it has, only what changed is
    // drawn, as the calls below draw it. The pointer is put at `at` until the page sees it move.
    show(screen) {
      const first = !drawnHere;
      drawnHere = true;
      const changed = ["label", "caption", "card"].filter((part) =>
        JSON.stringify(shown[part]) !== JSON.stringify(screen[part] || null));
      for (const part of changed) shown[part] = screen[part] || null;
      if (screen.corner && screen.corner !== shown.corner) {
        shown.corner = screen.corner;
        if (!changed.includes("label")) changed.push("label");
      }
      if (!movedHere && screen.at) shown.at = screen.at;
      if (!ensure()) return;
      const change = () => { for (const part of changed) draw[part](); draw.pointer(); };
      if (first) instantly(change); else change();
    },
    caption(text) { set("caption", text || null); },
    chapter(text) { set("label", text || null); },
    card(spec) { set("card", spec || null); },
    pointer(on) { set("pointer", !!on); },
    // The pointer drawn at (x, y) with no mouse event the page sees: a step on its way somewhere.
    point(x, y) {
      shown.at = [x, y];
      if (ensure()) draw.pointer();
    },
    // The camera: the screen's caption, label and card drawn into the view at (x, y) on the screen,
    // at 1/scale, so a frame showing only that view, scale times larger, shows them as on the whole
    // screen. Returns the page's scroll, which puts the view in the document, or null with no overlay.
    camera(x, y, scale) {
      if (!ensure()) return null;
      ui.screen.style.transform = scale === 1 && !x && !y ? "" : "translate(" + x + "px," + y + "px) scale(" + 1 / scale + ")";
      return [window.scrollX, window.scrollY];
    },
    // The spotlight on el, or taken down for null; whether one was up before.
    spot(el, padding) {
      ensure();
      const was = !!ui.spot && ui.spot.style.opacity === "1";
      pad = padding == null ? 8 : padding;
      if (ui.spot && el && ui.spot.style.opacity !== "1") {
        // Down, it comes up where the element is, rather than sliding there from where it last was
        // (on a page just opened, the screen's corner).
        const r = el.getBoundingClientRect(), moves = ui.spot.style.transition;
        ui.spot.style.transition = "none";
        css(ui.spot, { left: r.left - pad + "px", top: r.top - pad + "px", width: r.width + 2 * pad + "px",
          height: r.height + 2 * pad + "px" });
        void ui.spot.offsetWidth;
        ui.spot.style.transition = moves;
      }
      target = el;
      if (ui.spot) ui.spot.style.opacity = el ? "1" : "0";
      return was;
    },
  };
  if (!ensure()) {
    const watch = new MutationObserver(() => { if (ensure()) watch.disconnect(); });
    watch.observe(document, { childList: true, subtree: true });
    document.addEventListener("DOMContentLoaded", () => { ensure(); watch.disconnect(); });
  }
})();
