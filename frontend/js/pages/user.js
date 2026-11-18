import { api } from "../api.js";
import { h, icon, notice, link, go, backBar, mascot, colorOf, fmtDate, fmtClock, spinner } from "../ui.js";
import { t, tClass, tErr } from "../i18n.js";
import { state, logout, setAudio } from "../state.js";
import { toWav } from "../wav.js";
import { analysisView } from "./result.js";

export async function home() {
  const d = await api("/dashboard");
  const aiAnswer = h("div");
  const aiInput = h("input", { class: "chat-home-input", placeholder: "Ask AuraCry AI a question…", maxlength: 2000 });
  const aiSend = h("button", { class: "btn", type: "button" }, "Ask");
  aiSend.onclick = async () => { const message = aiInput.value.trim(); if (!message) return; aiAnswer.replaceChildren(notice("info", "AuraCry AI is thinking…")); aiSend.disabled = true; try { const r = await api("/companion/chat", {method:"POST",body:{message}}); aiAnswer.replaceChildren(h("div",{class:"chat-bubble bot"},h("span",{class:"bot-mark"},"🤖"),r.answer)); if (r.memory_suggestion) aiAnswer.append(h("button",{class:"btn ghost block",onclick:()=>go("/user/ai")},"Review and save this memory")); } catch(e) { aiAnswer.replaceChildren(notice("err",e.message)); } finally { aiSend.disabled=false; } };
  aiInput.addEventListener("keydown", e => { if(e.key === "Enter") aiSend.click(); });
  const aiPreview = h("div", { class: "companion-preview card stack" }, h("div", { class: "row", style: {alignItems:"center"} }, h("span", {class:"bot-avatar small"}, "🤖"), h("div", {}, h("b", {}, "AuraCry AI Companion"), h("div", {class:"muted small"}, "Ask a question or tell me a special moment"))),
      h("div",{class:"chat-compose"},aiInput,aiSend), aiAnswer,
      h("div",{class:"row wrap"},h("button", {class:"btn ghost", onclick:()=>go("/user/ai")}, "Open AI Companion"), h("button", {class:"btn ghost", onclick:()=>go("/user/diary")}, "Baby Memory Diary")));
  return h("div", { class: "stack-lg" }, h("div", {}, h("div", { class: "muted" }, t("welcome_back")), h("h1", {}, d.name)),
    h("div", { class: "hero" }, mascot("calm", 230), h("h2", {}, t("understand_every"), h("span", {}, t("cry_word"))),
      h("p", {}, t("home_blurb")),
      h("button", { class: "btn lg", onclick: () => go("/user/choose") }, t("start_analysis")),
      null),
    d.model_ready ? null : notice("warn", t("model_unavailable")),
    aiPreview,
    h("div", { class: "statline" }, h("div", { class: "card" }, h("b", {}, d.analysis_count), h("span", { class: "muted small" }, t("analyses_performed")))),
    h("div", {}, h("div", { class: "row between", style: { marginBottom: "10px" } }, h("h3", {}, t("recent_analyses")), d.recent.length ? link("/user/history", { class: "small" }, t("see_all")) : null),
      d.recent.length ? d.recent.map(item) : h("div", { class: "card empty" }, t("no_analyses_cta"))));
}
const item = (a) => link(`/user/analysis/${a.id}`, { class: "item" }, h("div", { class: "row between" }, h("span", { class: "cat", style: { "--c": colorOf(a.predicted_label) } }, a.uncertain ? t("unclear_x", { x: tClass(a.predicted_label) }) : tClass(a.predicted_label)), h("b", {}, a.confidence + "%")),
  h("div", { class: "muted small", style: { marginTop: "4px" } }, `${a.audio_filename} • ${fmtDate(a.created_at)}`));

const OK = ["wav", "mp3", "m4a", "ogg", "flac", "webm"];
function readDuration(url) { return new Promise((res) => { const a = new Audio(); a.preload = "metadata"; const done = (v) => res(Number.isFinite(v) ? v : null); a.onloadedmetadata = () => done(a.duration); a.onerror = () => done(null); setTimeout(() => done(null), 4000); a.src = url; }); }
async function useBlob(file, source) { const url = URL.createObjectURL(file); const d = await readDuration(url); URL.revokeObjectURL(url); setAudio(file, source, d); go("/user/ready"); }

export function choose() {
  const err = h("div"), input = h("input", { type: "file", accept: ".wav,.mp3,.m4a,.ogg,.flac,audio/*", hidden: true, onchange: async (e) => {
    const f = e.target.files[0]; e.target.value = ""; err.replaceChildren(); if (!f) return;
    const ext = f.name.split(".").pop().toLowerCase();
    if (!OK.includes(ext)) return err.append(notice("err", t("v_unsupported")));
    if (f.size === 0) return err.append(notice("err", t("v_empty")));
    if (f.size > 15 * 1024 * 1024) return err.append(notice("err", t("v_too_large")));
    // Decode the actual file contents before accepting it. A renamed PNG/PDF/etc.
    // will fail here and will never reach the upload/analysis screen.
    let out;
    try {
      const wav = await toWav(f);
      const url = URL.createObjectURL(wav);
      const duration = await readDuration(url);
      URL.revokeObjectURL(url);
      if (!Number.isFinite(duration)) throw new Error("invalid_audio");
      if (duration < 1) throw new Error("too_short");
      if (duration > 60) throw new Error("too_long");
      out = new File([wav], f.name.replace(/\.\w+$/, "") + ".wav", { type: "audio/wav" });
    } catch (x) {
      const messages = {
        invalid_audio: "This file is not a valid audio recording. Please select a genuine WAV, MP3, M4A, OGG or FLAC audio file.",
        too_short: "Audio is too short. Please select a recording of at least 1 second.",
        too_long: "Audio is too long. Please select a recording of 60 seconds or less."
      };
      return err.append(notice("err", messages[x.message] || "This file could not be decoded as audio. Please select a genuine audio recording."));
    }
    await useBlob(out, "upload");
  } });
  const ch = (ic, title, s, fn) => h("button", { class: "choice", onclick: fn }, h("span", { class: "ico" }, icon(ic, 26)), h("div", {}, h("b", {}, title), h("div", { class: "muted small" }, s)));
  return h("div", { class: "stack" }, backBar(t("choose_audio"), "/user/home"), err, input,
    ch("upload", t("upload_audio"), t("upload_formats"), () => input.click()), ch("mic", t("record_cry"), t("use_mic"), () => go("/user/record")),
    h("p", { class: "muted small center" }, t("tip_record")));
}

export function record() {
  let rec, chunks = [], stream, timer, sec = 0, blob = null;
  const err = h("div"), time = h("div", { class: "rec-timer" }, "00:00"), btn = h("button", { class: "rec-btn", "aria-label": "Start recording" }, icon("mic", 34)), out = h("div", { class: "stack mt" });
  const cleanup = () => { clearInterval(timer); stream?.getTracks().forEach((t) => t.stop()); };
  const stop = () => { if (rec && rec.state !== "inactive") rec.stop(); };
  btn.onclick = async () => {
    err.replaceChildren();
    if (rec && rec.state === "recording") return stop();
    if (!navigator.mediaDevices?.getUserMedia) return err.append(notice("err", t("v_rec_https")));
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false } }); } catch { return err.append(notice("err", t("v_mic_blocked"))); }
    chunks = []; sec = 0; blob = null; out.replaceChildren(); rec = new MediaRecorder(stream);
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = async () => { cleanup(); btn.classList.remove("live"); btn.replaceChildren(icon("mic", 34));
      try { blob = await toWav(new Blob(chunks, { type: rec.mimeType })); } catch { return err.append(notice("err", t("v_rec_read"))); }
      if (sec < 1) return err.append(notice("err", t("v_too_short")));
      const url = URL.createObjectURL(blob); out.append(h("audio", { controls: true, src: url }), h("button", { class: "btn block", onclick: () => useBlob(new File([blob], `recording-${Date.now()}.wav`, { type: "audio/wav" }), "record") }, t("use_recording"))); };
    rec.start(); btn.classList.add("live"); btn.replaceChildren(icon("stop", 34));
    timer = setInterval(() => { sec++; time.textContent = fmtClock(sec); if (sec >= 30) stop(); }, 1000);
  };
  const page = h("div", { class: "center stack" }, backBar(t("record_title"), "/user/choose"), err, h("div", { class: "recorder" }, time, btn, h("p", { class: "muted small" }, t("tap_start_stop"))), out);
  new MutationObserver((_, o) => { if (!page.isConnected) { cleanup(); o.disconnect(); } }).observe(document.body, { childList: true, subtree: true });
  return page;
}

export function ready() {
  const a = state.audio; if (!a) { go("/user/choose", true); return h("div"); }
  return h("div", { class: "stack" }, backBar(t("audio_ready"), "/user/choose"), h("div", { class: "card" }, h("div", { class: "row", style: { gap: "10px" } }, h("span", { class: "pill ok" }, a.source === "record" ? t("recorded") : t("uploaded")), h("b", {}, a.name)),
    h("div", { class: "muted small mt" }, a.duration ? t("duration_s", { s: a.duration.toFixed(1) }) : t("duration_unknown")), h("audio", { controls: true, src: a.url, style: { marginTop: "12px" } })),
    h("button", { class: "btn block lg", onclick: () => go("/user/processing") }, t("get_results")), h("button", { class: "btn ghost block", onclick: () => { setAudio(null); go("/user/choose"); } }, t("choose_another")));
}

export function processing() {
  const a = state.audio; if (!a) { go("/user/choose", true); return h("div"); }
  const title = h("h1", {}, t("analyzing")), sub = h("p", { class: "muted", style: { marginTop: "6px" } }, t("running_pipeline")), list = h("ul", { class: "steps" }), errBox = h("div", { class: "stack mt-lg", style: { textAlign: "left" } });
  const pending = h("li", { class: "now" }, h("span", { class: "dot" }), t("uploading_waiting"));
  list.append(pending);
  const form = new FormData(); form.append("audio", a.file, a.name);
  api("/analyses", { method: "POST", form }).then(async (d) => {
    const trace = d.analysis.result.trace; list.replaceChildren(); sub.textContent = t("replaying_steps");
    for (const step of trace) { const li = h("li", { class: "now" }, h("span", { class: "dot" }), h("div", {}, h("b", {}, `${step.title}`), h("span", { class: "muted small" }, `  ${step.ms} ms`), h("div", { class: "muted small" }, step.detail))); list.append(li); await new Promise((r) => setTimeout(r, 420)); li.className = "done"; li.querySelector(".dot").replaceChildren(icon("check", 14)); }
    await new Promise((r) => setTimeout(r, 400)); setAudio(null); go(`/user/result/${d.analysis.id}`, true);
  }).catch((e) => { title.textContent = t("analysis_failed"); sub.textContent = ""; list.replaceChildren(); errBox.append(notice("err", tErr(e.data?.error, e.message)), h("button", { class: "btn block", onclick: () => go("/user/choose") }, t("choose_another"))); });
  return h("div", { class: "center", style: { paddingTop: "24px" } }, h("div", { class: "eq", "aria-hidden": "true" }, Array.from({ length: 11 }, (_, i) => h("i", { style: { animationDelay: `${i * 0.09}s` } }))), title, sub,
    h("div", { class: "card mt-lg", style: { textAlign: "left" } }, list), errBox);
}

export async function analysis({ id }, fresh) {
  const d = await api(`/analyses/${id}`);
  return h("div", { class: "stack" }, backBar(fresh ? t("result_title") : t("analysis_details"), fresh ? "/user/home" : "/user/history"), analysisView(d.analysis));
}

export async function history() {
  const d = await api("/analyses");
  return h("div", { class: "stack" }, h("h1", {}, t("nav_history")), d.analyses.length ? d.analyses.map(item) : h("div", { class: "card empty" }, t("no_analyses_cta")));
}

export function profile() {
  const u = state.user, pe = h("div"), pp = h("div");
  const inp = (n, l, v, t = "text") => h("label", { class: "field" }, h("span", {}, l), h("input", { name: n, type: t, value: v || "" }));
  const g = (f, n) => f.elements[n].value;
  const f1 = h("form", { class: "card stack", onsubmit: async (e) => { e.preventDefault(); pe.replaceChildren(); try { const r = await api("/account/profile", { method: "PUT", body: { name: g(f1, "name"), email: g(f1, "email") } }); state.user = r.user; pe.append(notice("ok", t("profile_updated"))); } catch (x) { pe.append(notice("err", tErr(x.data?.error, x.message))); } } },
    h("h3", {}, t("edit_profile")), pe, inp("name", t("f_name"), u.name), inp("email", t("f_email"), u.email), h("button", { class: "btn block" }, t("save")));
  const f2 = h("form", { class: "card stack", onsubmit: async (e) => { e.preventDefault(); pp.replaceChildren(); try { await api("/account/password", { method: "POST", body: { current_password: g(f2, "c"), new_password: g(f2, "n"), confirm_password: g(f2, "m") } }); f2.reset(); pp.append(notice("ok", t("password_changed"))); } catch (x) { pp.append(notice("err", tErr(x.data?.error, x.message))); } } },
    h("h3", {}, t("change_password")), pp, inp("c", t("f_current_password"), "", "password"), inp("n", t("f_new_password"), "", "password"), inp("m", t("f_confirm_new"), "", "password"), h("button", { class: "btn block" }, t("change_password")));
  return h("div", { class: "stack" }, h("h1", {}, t("profile_title")), f1, f2, h("button", { class: "btn danger block", onclick: async () => { await logout(); go("/login", true); } }, t("logout")),
    h("p", { class: "muted small center" }, t("experimental_note")));
}
