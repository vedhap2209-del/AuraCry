// Tiny UI toolkit: h() builds DOM, plus icons, notices, charts, mascot, helpers.
import { LANGS, getLang, setLang } from "./i18n.js";

// Language picker (globe). On change it persists the choice and re-renders the current page.
export function langPicker() {
  const sel = h("select", { class: "lang-select", "aria-label": "Language",
    onchange: (e) => setLang(e.target.value) },
    Object.entries(LANGS).map(([code, name]) => h("option", { value: code, selected: code === getLang() }, name)));
  return h("div", { class: "lang-pick" }, h("span", { class: "svgi", "aria-hidden": "true",
    html: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"/></svg>' }), sel);
}

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else if (k in el && k !== "list") { try { el[k] = v; } catch { el.setAttribute(k, v); } }
    else el.setAttribute(k, v === true ? "" : v);
  }
  const add = (c) => { if (c == null || c === false) return; if (Array.isArray(c)) c.forEach(add); else el.append(c.nodeType ? c : document.createTextNode(String(c))); };
  kids.forEach(add);
  return el;
}
export const svg = (html, size = 22) => h("span", { class: "svgi", html: `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${html}</svg>`, style: { display: "inline-flex" } });
const P = {
  home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>', history: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>', users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  mic: '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"/>', upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5M12 3v12"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>', chart: '<path d="M18 20V10M12 20V4M6 20v-6"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8"/>', logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  menu: '<path d="M3 12h18M3 6h18M3 18h18"/>', grid: '<path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"/>', back: '<path d="M15 18l-6-6 6-6"/>',
  check: '<path d="M20 6L9 17l-5-5"/>', stop: '<rect x="5" y="5" width="14" height="14" rx="2"/>', flask: '<path d="M9 2h6M10 2v6l-6 11a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3L14 8V2"/>', moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
};
export const icon = (n, s = 22) => svg(P[n] || "", s);

export const spinner = () => h("div", { class: "spinner", role: "status", "aria-label": "Loading" });
export const notice = (kind, text) => text ? h("div", { class: `notice ${kind}`, role: kind === "err" ? "alert" : "status" }, text) : null;
export function modal(title, body, onClose) {
  const bg = h("div", { class: "modal-bg", onmousedown: (e) => { if (e.target === bg) close(); } },
    h("div", { class: "modal", role: "dialog", "aria-modal": "true" }, h("div", { class: "row between", style: { marginBottom: "14px" } }, h("h2", {}, title), h("button", { class: "iconbtn", onclick: () => close(), "aria-label": "Close" }, "✕")), body));
  const close = () => { bg.remove(); onClose && onClose(); };
  document.body.append(bg);
  return close;
}
export function backBar(title, to) { return h("div", { class: "topbar" }, h("button", { class: "iconbtn", "aria-label": "Back", onclick: () => (to ? go(to) : history.back()) }, icon("back")), h("h2", {}, title)); }
export const go = (path, replace = false) => window.__go(path, replace);
export const link = (to, props, ...k) => h("a", { href: to, ...props, onclick: (e) => { e.preventDefault(); go(to); } }, ...k);

/* ---- formatting ---- */
export const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "-";
export const fmtDateTime = (iso) => iso ? new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "-";
export const fmtClock = (s) => { s = Math.floor(s); return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
export const COLORS = { hu: "#E98A2B", ti: "#7A62F0", dc: "#2A93CF", bu: "#2FAE80", bp: "#DB4F6A", sc: "#9B59B6", ch: "#1ABC9C", lo: "#E67E9B", dk: "#6B7494" };
export const LABEL2CODE = { Hungry: "hu", Tired: "ti", Discomfort: "dc", "Needs Burping": "bu", "Belly Pain": "bp", Scared: "sc", "Cold / Hot": "ch", Lonely: "lo", Unclear: "dk" };
export const colorOf = (label) => COLORS[LABEL2CODE[label]] || "#6B7494";

/* ---- mascot (same look as the AuraCry landing design; eyes follow the pointer) ---- */
export function mascot(mood = "calm", size = 230) {
  const d = mood === "cry" ? "M10 24 Q30 2 50 24" : mood === "happy" ? "M6 6 Q30 34 54 6" : "M10 8 Q30 26 50 8";
  const eyes = h("div", { class: "mc-eyes" }, h("b", { class: "mc-eye" }), h("b", { class: "mc-eye" }));
  const root = h("div", { class: `mc-stage ${mood === "cry" ? "cry" : ""}`, style: { width: size + "px" }, "aria-hidden": "true" },
    ...[["6%", "22%", "9%", "5s"], ["84%", "14%", "7%", "6s"], ["90%", "60%", "11%", "7s"], ["4%", "70%", "6%", "4.5s"]].map(([x, y, s, dd]) => h("i", { class: "mc-bub", style: { "--x": x, "--y": y, "--s": s, "--d": dd } })),
    h("div", { class: "mc-orb" }, h("i", { class: "mc-ear l" }), h("i", { class: "mc-ear r" }), h("i", { class: "mc-curl" }), h("i", { class: "mc-nose" }), eyes,
      h("i", { class: "mc-cheek l" }), h("i", { class: "mc-cheek r" }), h("span", { html: `<svg class="mc-mth" viewBox="0 0 60 30"><path d="${d}"/></svg>` }), h("i", { class: "mc-tear l" }), h("i", { class: "mc-tear r" })));
  const move = (e) => { if (!root.isConnected) return window.removeEventListener("pointermove", move);
    const r = root.getBoundingClientRect(); const x = (e.clientX - r.left - r.width / 2) / r.width, y = (e.clientY - r.top - r.height / 2) / r.height;
    eyes.style.setProperty("--ex", Math.max(-1, Math.min(1, x * 2)) * 6 + "px"); eyes.style.setProperty("--ey", Math.max(-1, Math.min(1, y * 2)) * 4 + "px"); };
  window.addEventListener("pointermove", move);
  return root;
}

/* ---- charts (hand-written SVG) ---- */
const S = (w, hh, inner, cls = "chart") => h("div", { html: `<svg class="${cls}" viewBox="0 0 ${w} ${hh}">${inner}</svg>` });
export function columnChart(items, color = "#9b8ce8") {
  const W = 340, H = 180, L = 28, B = 26, T = 16, max = Math.max(...items.map((i) => i.count), 1), bw = (W - L) / Math.max(items.length, 1), step = Math.max(1, Math.ceil(items.length / 7));
  let s = `<line x1="${L}" x2="${W}" y1="${H - B}" y2="${H - B}" stroke="#d7d3ee"/><text x="${L - 6}" y="${T + 4}" font-size="10" text-anchor="end" fill="#6b7494">${max}</text><text x="${L - 6}" y="${H - B + 4}" font-size="10" text-anchor="end" fill="#6b7494">0</text>`;
  items.forEach((it, i) => { const hh = ((H - B - T) * it.count) / max; s += `<rect x="${L + i * bw + bw * .18}" y="${H - B - hh}" width="${bw * .64}" height="${hh}" rx="3" fill="${color}"><title>${it.label}: ${it.count}</title></rect>`; if (i % step === 0) s += `<text x="${L + i * bw + bw / 2}" y="${H - 8}" font-size="9.5" text-anchor="middle" fill="#6b7494">${it.label}</text>`; });
  return S(W, H, s);
}
export function hbars(items) {
  const max = Math.max(...items.map((i) => i.value), 0.0001);
  return h("div", {}, items.map((i) => h("div", { class: "hbar" }, h("span", {}, i.label), h("div", { class: "track" }, h("i", { style: { width: (i.value / max) * 100 + "%", background: i.color } })), h("b", { style: { textAlign: "right" } }, i.text ?? i.value))));
}
export function heatmap(matrix, labels, normalize = false) {
  const rs = matrix.map((r) => r.reduce((a, b) => a + b, 0)), mx = Math.max(...matrix.flat(), 1);
  return h("div", { class: "tablewrap", style: { padding: "10px" } }, h("table", { class: "cm" },
    h("thead", {}, h("tr", {}, h("th"), h("th", { colSpan: labels.length }, "Predicted")), h("tr", {}, h("th", { class: "rowh" }, "Actual"), labels.map((l) => h("th", {}, l)))),
    h("tbody", {}, matrix.map((row, a) => h("tr", {}, h("th", { class: "rowh" }, labels[a]), row.map((v, p) => { const sh = normalize ? (rs[a] ? v / rs[a] : 0) : v / mx;
      return h("td", { style: { background: `rgba(122,107,216,${0.07 + sh * 0.93})`, color: sh > .5 ? "#fff" : "#17203d", outline: a === p ? "2px solid #17203d" : "none" }, title: `Actual ${labels[a]} → predicted ${labels[p]}: ${v}` }, normalize ? Math.round(sh * 100) + "%" : v); }))))));
}
export function waveform(env, seconds, units) {
  const W = 600, H = 90, n = env.length || 1; let s = "";
  (units || []).forEach((u) => { s += `<rect x="${(u.start / seconds) * W}" y="0" width="${Math.max(2, ((u.end - u.start) / seconds) * W)}" height="${H}" fill="#9b8ce8" opacity=".22"/>`; });
  env.forEach((v, i) => { const x = (i / n) * W, hh = Math.max(1, v * H * .9); s += `<line x1="${x}" x2="${x}" y1="${H / 2 - hh / 2}" y2="${H / 2 + hh / 2}" stroke="#E0426F" stroke-width="${W / n * .7}"/>`; });
  return h("div", { html: `<svg class="wf" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${s}</svg>` });
}
export function ring(pct, color) {
  const C = 2 * Math.PI * 50;
  return h("div", { class: "ring", html: `<svg viewBox="0 0 120 120" width="120" height="120"><circle cx="60" cy="60" r="50" fill="none" stroke="#eef1f8" stroke-width="11"/><circle cx="60" cy="60" r="50" fill="none" stroke="${color}" stroke-width="11" stroke-linecap="round" stroke-dasharray="${(pct / 100) * C} ${C}" transform="rotate(-90 60 60)"><animate attributeName="stroke-dasharray" from="0 ${C}" to="${(pct / 100) * C} ${C}" dur="1s" fill="freeze"/></circle></svg><b>${pct.toFixed(1)}%</b>` });
}
