import { api } from "../api.js";
import { h, notice, spinner, colorOf, mascot } from "../ui.js";
import { toWav } from "../wav.js";
import { traceView } from "./result.js";

// Pipeline Lab: runs the REAL models on a real dataset row or on audio you give it, and draws every stage's real output.
export async function labPage(admin) {
  const s = (await api("/lab/samples")).samples;
  const out = h("div", { class: "mt" }), err = h("div");
  const show = async (p) => {
    err.replaceChildren(); out.replaceChildren(h("div", { style: { display: "grid", placeItems: "center", padding: "20px" } }, spinner()));
    try { const r = (await p).result; out.replaceChildren(...[traceView(r), r.source === "dataset_row" ? h("div", { class: "honest mt" }, `The label stored in the dataset for this row is “${r.true_label}”. ${r.true_label === r.label ? "The pipeline agrees." : "The pipeline disagrees, which is expected: on new recordings these models are only slightly better than guessing the most common cry (see Model Performance)."}`) : null].filter(Boolean)); out.scrollIntoView({ behavior: "smooth" }); }
    catch (e) { out.replaceChildren(); err.append(notice("err", e.message)); }
  };
  const file = h("input", { type: "file", accept: "audio/*,.wav", hidden: true, onchange: async (e) => {
    const f = e.target.files[0]; e.target.value = ""; if (!f) return;
    let b;
    try {
      b = new File([await toWav(f)], "demo.wav", { type: "audio/wav" });
    } catch {
      err.replaceChildren(notice("err", "This file is not a valid audio recording. Please select a genuine audio file."));
      return;
    }
    const form = new FormData(); form.append("audio", b, b.name); show(api("/lab/run", { method: "POST", form })); } });
  return h("div", { class: "stack" }, h("div", { class: "row", style: { gap: "12px" } }, mascot("happy", 90), h("div", {}, h("h1", {}, "Pipeline Lab"), h("p", { class: "muted small" }, "Watch the real two-branch pipeline: audio → validate → preprocess, then an ML branch (19 features → Random Forest → AdaBoost → Logistic Regression) and a DL branch (spectrogram → CNN + BiGRU) run in parallel and are fused into one answer."))),
    h("div", { class: "card stack" }, h("h3", {}, "A. Your own audio (runs both branches + fusion)"), h("p", { class: "muted small" }, "Nothing is saved from the Lab."), h("button", { class: "btn", onclick: () => file.click() }, "Choose an audio file"), file),
    h("div", { class: "card stack" }, h("h3", {}, "B. A real row from the dataset (ML branch only)"), h("p", { class: "muted small" }, "Pick a measured cry unit to see each ML stage score it. The CNN branch needs audio, so use option A to see the full fusion."),
      h("div", { class: "sample-grid" }, s.map((x) => h("button", { class: "sample", onclick: () => show(api("/lab/run", { method: "POST", body: { row: x.id } })) }, h("b", { style: { color: colorOf(x.true_label) } }, x.true_label), h("div", { class: "muted small" }, `${x.duration}s · ${x.mean_f0} Hz`))))),
    err, out);
}
