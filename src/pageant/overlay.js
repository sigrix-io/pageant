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
(() => {
  if (window.__demo) return;
  const ui = {};
  // What is on screen: what each call below changes, and what is drawn from.
  const shown = { label: null, corner: "top-right", caption: null, card: null, pointer: true, at: null };
  let target = null, pad = 8, drawnHere = false, movedHere = false;
  // Where the chapter label may sit: a top corner, clear of the captions at the foot of the screen.
  const CORNERS = {
    "top-right": { right: "18px", left: "auto" },
    "top-left": { left: "18px", right: "auto" },
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
      }
      ui.card.style.opacity = spec ? "1" : "0";
      draw.pointer();
    },
    pointer() {
      css(ui.cursor, { display: shown.pointer ? "" : "none", opacity: shown.card ? "0" : "1",
        visibility: shown.at ? "visible" : "hidden" });
      if (shown.at) ui.cursor.style.transform = "translate(" + (shown.at[0] - 4) + "px," + (shown.at[1] - 2) + "px)";
    },
  };
  // A change drawn at once: what fades in or out is styled once with no transition, then given it back.
  function instantly(change) {
    const fading = [ui.cap, ui.chip, ui.card];
    const fades = fading.map((el) => el.style.transition);
    for (const el of fading) el.style.transition = "none";
    change();
    void ui.root.offsetHeight;
    fading.forEach((el, index) => { el.style.transition = fades[index]; });
  }
  function ensure() {
    if (ui.root) return true;
    if (!document.body) return false;
    ui.root = make("div", { position: "fixed", inset: "0", pointerEvents: "none", zIndex: "2147483000" });
    ui.spot = make("div", { position: "fixed", left: "0", top: "0", width: "0", height: "0", borderRadius: "12px",
      border: "3px solid #f5a524", boxShadow: "0 0 0 9999px rgba(12,14,22,0.40), 0 0 22px 3px rgba(245,165,36,0.55)",
      opacity: "0", transition: "left .45s ease, top .45s ease, width .45s ease, height .45s ease, opacity .35s ease" });
    ui.ripple = make("div", { position: "fixed", left: "0", top: "0", width: "40px", height: "40px", marginLeft: "-20px",
      marginTop: "-20px", borderRadius: "50%", border: "3px solid #f5a524", opacity: "0" });
    ui.cap = make("div", { position: "fixed", left: "50%", bottom: "30px", transform: "translate(-50%, 14px)",
      maxWidth: "1040px", width: "max-content", padding: "14px 26px", borderRadius: "14px", background: "rgba(16,18,27,0.93)",
      color: "#fff", font: "500 23px/1.38 Inter, system-ui, sans-serif", textAlign: "center",
      boxShadow: "0 12px 32px rgba(0,0,0,.35)", opacity: "0", transition: "opacity .35s ease, transform .35s ease" });
    ui.chip = make("div", { position: "fixed", right: "18px", top: "12px", padding: "7px 15px", borderRadius: "999px",
      background: "rgba(16,18,27,0.88)", color: "#f7c55f", font: "600 15px/1.2 Inter, system-ui, sans-serif",
      opacity: "0", transition: "opacity .35s ease" });
    const NS = "http://www.w3.org/2000/svg";
    ui.cursor = document.createElementNS(NS, "svg");
    ui.cursor.setAttribute("width", "30");
    ui.cursor.setAttribute("height", "30");
    ui.cursor.setAttribute("viewBox", "0 0 28 28");
    css(ui.cursor, { position: "fixed", left: "0", top: "0", filter: "drop-shadow(0 2px 3px rgba(0,0,0,.45))" });
    const arrow = document.createElementNS(NS, "path");
    arrow.setAttribute("d", "M4 2 L4 22 L9.5 17 L13 25 L16.5 23.5 L13 15.7 L20.5 15.7 Z");
    arrow.setAttribute("fill", "#14161f");
    arrow.setAttribute("stroke", "#ffffff");
    arrow.setAttribute("stroke-width", "1.6");
    arrow.setAttribute("stroke-linejoin", "round");
    ui.cursor.append(arrow);
    ui.card = make("div", { position: "fixed", inset: "0", display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", gap: "14px", background: "radial-gradient(1200px 600px at 50% 40%, #232842, #0e1018)",
      color: "#fff", opacity: "0", transition: "opacity .5s ease", textAlign: "center" });
    ui.logo = make("img", { width: "84px", height: "91px", marginBottom: "10px" });
    ui.logo.alt = "";
    ui.logo.style.display = "none";
    ui.kicker = make("div", { font: "600 18px/1.2 Inter, system-ui, sans-serif", letterSpacing: ".14em",
      textTransform: "uppercase", color: "#f7c55f" });
    ui.title = make("div", { font: "700 54px/1.1 Inter, system-ui, sans-serif", letterSpacing: "-0.02em", maxWidth: "1000px" });
    ui.sub = make("div", { font: "400 24px/1.45 Inter, system-ui, sans-serif", color: "#c9cee0", maxWidth: "900px" });
    ui.card.append(ui.logo, ui.kicker, ui.title, ui.sub);
    // Drawn before it is on the page, so what the page already had shows at once, with no fade.
    draw.label();
    draw.caption();
    draw.card();
    ui.root.append(ui.spot, ui.ripple, ui.cap, ui.chip, ui.card, ui.cursor);
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
    shown.at = [e.clientX, e.clientY];
    if (ui.root) draw.pointer();
  }, true);
  window.addEventListener("mousedown", (e) => {
    if (!ui.root) return;
    css(ui.ripple, { left: e.clientX + "px", top: e.clientY + "px" });
    ui.ripple.animate([{ opacity: 0.95, transform: "scale(.35)" }, { opacity: 0, transform: "scale(1.5)" }],
      { duration: 520, easing: "ease-out" });
  }, true);
  window.__demo = {
    ready: ensure,
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
