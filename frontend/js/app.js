import { api, ApiError } from "./api.js";
import { h, icon, spinner, notice, link, go, mascot, langPicker } from "./ui.js";
import { t, tErr, getLang, onLangChange } from "./i18n.js";
import * as userPages from "./pages/user.js";
import * as adminPages from "./pages/admin.js";
import { labPage } from "./pages/lab.js";
import * as companionPages from "./pages/companion.js";

import { state, homeFor, refreshUser, logout, setAudio,
  loginIdentify, loginPassword, loginResend, loginVerify, loginPin, resetRequest, resetConfirm } from "./state.js";
/* ---------- theme ---------- */
const applyTheme = (t) => document.documentElement.setAttribute("data-theme", t);
applyTheme(localStorage.getItem("theme") || "light");
const themeBtn = () => h("button", { class: "iconbtn themebtn", "aria-label": "Toggle dark mode", onclick: () => { const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; localStorage.setItem("theme", t); applyTheme(t); } }, icon("moon", 18));

window.addEventListener("auracry-unauth", () => { if (state.user) { state.user = null; go("/login", true); } });

/* ---------- layouts ---------- */
const TABS = [["/user/home", "home", "nav_home"], ["/user/choose", "mic", "Analyze"], ["/user/diary", "file", "Diary"], ["/user/ai", "users", "AI Chat"], ["/user/profile", "user", "nav_profile"]];
function userLayout(page, path) {
  const showNav = TABS.some((tab) => tab[0] === path);
  return h("div", { class: "phone" }, h("div", { class: `page ${showNav ? "" : "nonav"}` }, page),
    showNav ? h("nav", { class: "nav", "aria-label": "Main" }, TABS.map(([to, ic, l]) => link(to, { class: path === to ? "active" : "" }, icon(ic), h("span", {}, t(l))))) : null);
}
const LINKS = [["/admin/dashboard", "grid", "Dashboard"], ["/admin/users", "users", "Users"], ["/admin/dataset", "database", "Dataset"], ["/admin/model", "chart", "Model Performance"],
  ["/admin/lab", "flask", "Pipeline Lab"], ["/admin/records", "history", "Analysis Records"], ["/admin/reports", "file", "Reports"], ["/admin/profile", "user", "Profile / Settings"]];
function adminLayout(page, path) {
  const side = h("aside", { class: "side" }, h("div", { class: "brand" }, "AuraCry"), h("div", { class: "tag" }, "Administrator console"),
    LINKS.map(([to, ic, l]) => link(to, { class: path === to || (to !== "/admin/dashboard" && path.startsWith(to)) ? "active" : "" }, icon(ic, 20), l)), h("div", { class: "sp" }),
    h("a", { href: "#logout", onclick: async (e) => { e.preventDefault(); await logout(); go("/login", true); } }, icon("logout", 20), "Logout"), h("div", { class: "who" }, state.user.name, h("br"), state.user.email));
  const scrim = h("div", { class: "scrim", onclick: () => { side.classList.remove("open"); scrim.remove(); } });
  const menu = h("button", { class: "iconbtn", "aria-label": "Open menu", onclick: () => { side.classList.add("open"); document.querySelector(".admin").append(scrim); } }, icon("menu"));
  return h("div", { class: "admin" }, h("header", { class: "topbar-m" }, menu, h("b", { style: { fontFamily: "var(--font-head)", fontSize: "19px" } }, "AuraCry Admin")), side, h("main", { class: "main" }, page));
}

/* ---------- auth pages ---------- */
export const Logo = (subtitle) => h("div", { class: "logo" }, h("div", { class: "mascot-wrap" }, mascot("calm", 200)), h("h1", {}, "Aura", h("span", {}, "Cry")), h("p", {}, subtitle ?? t("tagline")));
function field(label, props) { return h("label", { class: "field" }, h("span", {}, label), h("input", props)); }

function loginPage() {
  // ctx carries state across the three factor steps and the reset sub-flow.
  const ctx = { as: "USER", ticket: null, name: "", masked: "", step: "id" };
  const host = h("div", { class: "card stack" });
  const err = () => h("div");
  const showErr = (e, x) => e.append(notice("err", tErr(x.data?.error, x.message, x.data)));
  const stepHint = (n, total, label) => h("div", { class: "muted small", style: { fontWeight: 600, letterSpacing: ".04em" } }, t("step_label", { n, t: total, label }));

  function roleSeg() {
    const seg = h("div", { class: "seg", role: "group" });
    const draw = () => seg.replaceChildren(
      h("button", { type: "button", class: ctx.as === "USER" ? "on" : "", onclick: () => { ctx.as = "USER"; draw(); } }, t("role_user")),
      h("button", { type: "button", class: ctx.as === "ADMIN" ? "on adm" : "", onclick: () => { ctx.as = "ADMIN"; draw(); } }, t("role_admin")));
    draw(); return seg;
  }

  const devNote = (data) => (data?.dev_code ? notice("warn", t("dev_mode_code", { code: data.dev_code })) : null);

  // -------- step 1: identify ----------------------------------------------
  function stepId() {
    const e = err(), email = field(t("f_email_user"), { autocomplete: "username", inputMode: "email", autocapitalize: "none", name: "identifier" });
    const btn = h("button", { class: "btn block lg" }, t("btn_continue"));
    const reg = history.state?.registered ? notice("ok", t("account_created")) : null;
    const form = h("form", { class: "stack", noValidate: true, onsubmit: async (ev) => {
      ev.preventDefault(); e.replaceChildren();
      const i = email.querySelector("input").value.trim();
      if (!i) return e.append(notice("err", t("v_enter_email")));
      btn.disabled = true; btn.textContent = t("checking");
      try { const r = await loginIdentify(i, ctx.as); ctx.ticket = r.ticket; ctx.name = r.name || ""; ctx.ident = i; draw("pw"); }
      catch (x) { showErr(e, x); btn.disabled = false; btn.textContent = t("btn_continue"); }
    } }, reg, h("div", { class: "muted small", style: { fontWeight: 600, letterSpacing: ".04em" } }, t("sign_in")), h("div", {}, h("div", { class: "muted small", style: { fontWeight: 600, marginBottom: "6px" } }, t("login_as")), roleSeg()), e, email, btn,
      h("p", { class: "center small muted" }, t("new_user") + " ", link("/register", {}, t("register")), "  ·  ", h("a", { href: "#reset", onclick: (z) => { z.preventDefault(); draw("reset"); } }, t("forgot_password"))));
    host.replaceChildren(form);
  }

  // -------- step 2: password (factor 1) -----------------------------------
  function stepPw() {
    const e = err(), pw = field(t("f_password"), { type: "password", autocomplete: "current-password", name: "password" });
    const btn = h("button", { class: "btn block lg" }, t("btn_sign_in"));
    const form = h("form", { class: "stack", noValidate: true, onsubmit: async (ev) => {
      ev.preventDefault(); e.replaceChildren();
      const p = pw.querySelector("input").value;
      if (!p) return e.append(notice("err", t("v_enter_password")));
      btn.disabled = true; btn.textContent = t("verifying");
      try { const r = await loginPassword(ctx.ticket, p); ctx.masked = r.masked_email; ctx.last = r; ctx.resendIn = r.resend_in || 30; draw("otp"); }
      catch (x) { showErr(e, x); btn.disabled = false; btn.textContent = t("btn_sign_in"); if (x.status === 410 || x.status === 423) setTimeout(() => draw("id"), 1200); }
    } }, stepHint(1, 3, t("s_password")), ctx.name ? h("p", { class: "muted" }, t("welcome_back_name"), h("b", {}, ctx.name)) : null, e, pw, btn,
      h("p", { class: "center small muted" }, h("a", { href: "#back", onclick: (z) => { z.preventDefault(); draw("id"); } }, t("use_diff_account"))));
    host.replaceChildren(form); setTimeout(() => pw.querySelector("input").focus(), 30);
  }

  // -------- step 3: OTP (factor 2) ----------------------------------------
  function stepOtp() {
    const e = err(), code = field(t("s_email_code"), { inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6, name: "code" });
    const btn = h("button", { class: "btn block lg" }, t("btn_verify_code"));
    const resendBtn = h("button", { type: "button", class: "linklike" }, t("resend_code"));
    let left = ctx.resendIn || 30;
    const tick = () => { if (left > 0) { resendBtn.disabled = true; resendBtn.textContent = t("resend_in", { s: left }); left--; setTimeout(tick, 1000); } else { resendBtn.disabled = false; resendBtn.textContent = t("resend_code"); } };
    tick();
    resendBtn.onclick = async () => { e.replaceChildren(); try { const r = await loginResend(ctx.ticket); ctx.last = r; left = r.resend_in || 30; tick(); e.append(notice("ok", t("new_code_sent"))); const d = devNote(r); if (d) e.append(d); } catch (x) { showErr(e, x); if (x.data?.resend_in) { left = x.data.resend_in; tick(); } } };
    const form = h("form", { class: "stack", noValidate: true, onsubmit: async (ev) => {
      ev.preventDefault(); e.replaceChildren();
      const v = code.querySelector("input").value.trim();
      if (!/^\d{4,6}$/.test(v)) return e.append(notice("err", t("v_code_digits")));
      btn.disabled = true; btn.textContent = t("checking");
      try { const r = await loginVerify(ctx.ticket, v); ctx.pinSet = r.pin_set; draw("pin"); }
      catch (x) { showErr(e, x); btn.disabled = false; btn.textContent = t("btn_verify_code"); if (x.status === 410 || x.status === 429) setTimeout(() => draw("id"), 1400); }
    } }, stepHint(2, 3, t("s_email_code")), h("p", { class: "muted" }, t("code_sent_to"), h("b", {}, ctx.masked || t("your_email")), t("code_expires")),
      devNote(ctx.last), e, code, btn, h("p", { class: "center small" }, resendBtn));
    host.replaceChildren(form); setTimeout(() => code.querySelector("input").focus(), 30);
  }

  // -------- step 4: security PIN (factor 3) -> session --------------------
  function stepPin() {
    const first = !ctx.pinSet;
    const e = err(), pin = field(first ? t("create_pin") : t("s_security_pin"), { type: "password", inputMode: "numeric", autocomplete: "off", maxLength: 6, name: "pin" });
    const confirm = first ? field(t("confirm_pin"), { type: "password", inputMode: "numeric", maxLength: 6 }) : null;
    const btn = h("button", { class: "btn block lg" }, first ? t("btn_set_pin_sign_in") : t("btn_sign_in"));
    const form = h("form", { class: "stack", noValidate: true, onsubmit: async (ev) => {
      ev.preventDefault(); e.replaceChildren();
      const v = pin.querySelector("input").value.trim();
      if (!/^\d{4,6}$/.test(v)) return e.append(notice("err", t("v_pin_digits")));
      if (first && v !== confirm.querySelector("input").value.trim()) return e.append(notice("err", t("v_pins_no_match")));
      btn.disabled = true; btn.textContent = t("signing_in");
      try { const u = await loginPin(ctx.ticket, v); go(homeFor(u), true); }
      catch (x) { showErr(e, x); btn.disabled = false; btn.textContent = first ? t("btn_set_pin_sign_in") : t("btn_sign_in"); if (x.status === 410 || x.status === 429) setTimeout(() => draw("id"), 1400); }
    } }, stepHint(3, 3, t("s_security_pin")),
      h("p", { class: "muted" }, first ? t("pin_setup_note") : t("pin_enter_finish")), e, pin, confirm, btn);
    host.replaceChildren(form); setTimeout(() => pin.querySelector("input").focus(), 30);
  }

  // -------- reset sub-flow -------------------------------------------------
  function stepReset() {
    const e = err(), email = field(t("f_account_email"), { inputMode: "email", autocapitalize: "none" });
    const btn = h("button", { class: "btn block lg" }, t("btn_send_reset"));
    const form = h("form", { class: "stack", noValidate: true, onsubmit: async (ev) => {
      ev.preventDefault(); e.replaceChildren(); const i = email.querySelector("input").value.trim();
      if (!i) return e.append(notice("err", t("v_enter_email")));
      btn.disabled = true;
      try { const r = await resetRequest(i); ctx.ticket = r.ticket; ctx.last = r; if (!r.ticket) { e.append(notice("ok", r.message)); btn.disabled = false; } else draw("reset2"); }
      catch (x) { showErr(e, x); btn.disabled = false; }
    } }, stepHint(1, 2, t("reset_password")), h("p", { class: "muted" }, t("reset_blurb")), e, email, btn,
      h("p", { class: "center small muted" }, h("a", { href: "#back", onclick: (z) => { z.preventDefault(); draw("id"); } }, t("back_to_sign_in"))));
    host.replaceChildren(form);
  }
  function stepReset2() {
    const e = err(), code = field(t("f_reset_code"), { inputMode: "numeric", maxLength: 6 }),
      np = field(t("f_new_password"), { type: "password", autocomplete: "new-password" }), cp = field(t("f_confirm_new_password"), { type: "password", autocomplete: "new-password" });
    const btn = h("button", { class: "btn block lg" }, t("btn_set_new_password"));
    const form = h("form", { class: "stack", noValidate: true, onsubmit: async (ev) => {
      ev.preventDefault(); e.replaceChildren();
      const v = code.querySelector("input").value.trim(), a = np.querySelector("input").value, b = cp.querySelector("input").value;
      if (a.length < 8 || !/\d/.test(a) || !/[A-Za-z]/.test(a)) return e.append(notice("err", t("v_pw_rule")));
      if (a !== b) return e.append(notice("err", t("v_pw_no_match")));
      btn.disabled = true;
      try { await resetConfirm(ctx.ticket, v, a, b); history.replaceState({ registered: true }, ""); draw("id"); }
      catch (x) { showErr(e, x); btn.disabled = false; }
    } }, stepHint(2, 2, t("reset_password")), devNote(ctx.last), e, code, np, cp, btn);
    host.replaceChildren(form);
  }

  const STEPS = { id: stepId, pw: stepPw, otp: stepOtp, pin: stepPin, reset: stepReset, reset2: stepReset2 };
  function draw(step) { ctx.step = step; STEPS[step](); }
  draw("id");
  return h("div", { class: "auth" }, h("div", { class: "auth-card" }, Logo(), host));
}
function registerPage() {
  const err = h("div"), f = {}; const mk = (k, l, t = "text") => (f[k] = field(l, { type: t, name: k }));
  const val = (k) => f[k].querySelector("input").value;
  const btn = h("button", { class: "btn block lg" }, t("btn_create_account"));
  const form = h("form", { class: "card stack", noValidate: true, onsubmit: async (e) => {
    e.preventDefault(); err.replaceChildren();
    const body = { name: val("name"), email: val("email"), password: val("password"), confirm_password: val("confirm_password"), pin: val("pin") };
    if (!body.name.trim() || !body.email.trim() || !body.password || !body.pin) return err.append(notice("err", t("v_fill_all")));
    if (body.password.length < 8 || !/\d/.test(body.password) || !/[A-Za-z]/.test(body.password)) return err.append(notice("err", t("v_pw_rule")));
    if (body.password !== body.confirm_password) return err.append(notice("err", t("v_pw_no_match")));
    if (!/^\d{4,6}$/.test(body.pin.trim())) return err.append(notice("err", t("v_pin_digits")));
    if (body.pin.trim() !== val("confirm_pin").trim()) return err.append(notice("err", t("v_pins_no_match")));
    btn.disabled = true;
    try { await api("/auth/register", { method: "POST", body }); history.replaceState({ registered: true }, ""); go("/login", true); } catch (x) { err.append(notice("err", tErr(x.data?.error, x.message))); btn.disabled = false; }
  } }, err, mk("name", t("f_full_name")), mk("email", t("f_email")), mk("password", t("f_password"), "password"), mk("confirm_password", t("f_confirm_password"), "password"),
    h("p", { class: "muted small", style: { margin: "2px 0 -4px" } }, t("pin_signup_note")),
    mk("pin", t("f_pin"), "password"), mk("confirm_pin", t("confirm_pin"), "password"),
    btn, h("p", { class: "center small muted" }, t("already_registered") + " ", link("/login", {}, t("login"))));
  return h("div", { class: "auth" }, h("div", { class: "auth-card" }, Logo(t("create_account_sub")), form));
}
const accessDenied = () => h("div", { class: "auth" }, h("div", { class: "auth-card center" }, mascot("cry", 160), h("h1", {}, "Access Denied"), h("p", { class: "muted mt" }, "You do not have permission to view this page."), h("div", { class: "mt" }, state.user ? link(homeFor(state.user), { class: "btn" }, "Go to my home") : link("/login", { class: "btn" }, "Back to login"))));
const notFound = () => h("div", { class: "auth" }, h("div", { class: "auth-card center" }, h("h1", {}, "Page not found"), h("div", { class: "mt" }, link("/", { class: "btn" }, "Go home"))));

/* ---------- routes ---------- */
const R = [
  ["/login", { guest: 1, page: loginPage }], ["/register", { guest: 1, page: registerPage }],
  ["/user/home", { role: "USER", page: userPages.home }], ["/user/choose", { role: "USER", page: userPages.choose }], ["/user/record", { role: "USER", page: userPages.record }],
  ["/user/ready", { role: "USER", page: userPages.ready }], ["/user/processing", { role: "USER", page: userPages.processing }], ["/user/result/:id", { role: "USER", page: (p) => userPages.analysis(p, true) }],
  ["/user/analysis/:id", { role: "USER", page: (p) => userPages.analysis(p, false) }], ["/user/history", { role: "USER", page: userPages.history }], ["/user/diary", { role: "USER", page: companionPages.diaryPage }], ["/user/ai", { role: "USER", page: companionPages.companionPage }], ["/user/profile", { role: "USER", page: userPages.profile }],
  ["/admin/dashboard", { role: "ADMIN", page: adminPages.dashboard }], ["/admin/users", { role: "ADMIN", page: adminPages.users }], ["/admin/users/:id", { role: "ADMIN", page: adminPages.userDetails }],
  ["/admin/dataset", { role: "ADMIN", page: adminPages.dataset }], ["/admin/model", { role: "ADMIN", page: adminPages.model }], ["/admin/model/confusion", { role: "ADMIN", page: adminPages.confusion }],
  ["/admin/lab", { role: "ADMIN", page: () => labPage(true) }], ["/admin/records", { role: "ADMIN", page: adminPages.records }], ["/admin/records/:id", { role: "ADMIN", page: adminPages.recordDetails }],
  ["/admin/reports", { role: "ADMIN", page: adminPages.reports }], ["/admin/profile", { role: "ADMIN", page: adminPages.profile }],
].map(([p, o]) => ({ ...o, keys: [...p.matchAll(/:(\w+)/g)].map((m) => m[1]), re: new RegExp("^" + p.replace(/:\w+/g, "([^/]+)") + "/?$") }));

let token = 0;
async function render(path, replace) {
  const my = ++token;
  if (path === "/" || path === "") path = state.user ? homeFor(state.user) : "/login";
  if (path === "/user" || path === "/user/") path = "/user/home";
  if (path === "/admin" || path === "/admin/") path = "/admin/dashboard";
  const cur = location.pathname + location.search;
  if (replace) history.replaceState(history.state, "", path); else if (path !== cur) history.pushState(null, "", path);
  const base = path.split("?")[0];
  let m = null, route = null;
  for (const r of R) { m = r.re.exec(base); if (m) { route = r; break; } }
  const mount = (n) => { if (my === token) root.replaceChildren(h("div", { class: "topbar-lang" }, langPicker(), themeBtn()), n); window.scrollTo(0, 0); };
  if (!route) return mount(notFound());
  if (route.guest && state.user) return render(homeFor(state.user), true);
  if (route.role) {
    if (!state.user) return render("/login", true);
    if (state.user.role !== route.role) return mount(accessDenied());
  }
  const params = Object.fromEntries(route.keys.map((k, i) => [k, m[i + 1]]));
  const wrap = (n) => (route.role === "USER" ? userLayout(n, base) : route.role === "ADMIN" ? adminLayout(n, base) : n);
  mount(wrap(h("div", { style: { display: "grid", placeItems: "center", minHeight: "40vh" } }, spinner())));
  try { const page = await route.page(params); if (my === token) mount(wrap(page)); }
  catch (e) { if (my === token) mount(wrap(notice("err", e.message || "Something went wrong."))); }
}
window.__go = (p, replace = false) => render(p, replace);
window.addEventListener("popstate", () => render(location.pathname + location.search, true));
document.documentElement.lang = getLang(); document.body.setAttribute("data-lang", getLang());
onLangChange(() => render(location.pathname + location.search, true));   // re-render the page in the new language
document.addEventListener("click", (e) => { const a = e.target.closest("a[data-spa]"); if (a) { e.preventDefault(); go(a.getAttribute("href")); } });

await refreshUser();
render(location.pathname, true);
