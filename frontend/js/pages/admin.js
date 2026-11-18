import { api } from "../api.js";
import { h, notice, link, go, backBar, modal, columnChart, hbars, heatmap, colorOf, fmtDate, fmtDateTime, spinner } from "../ui.js";
import { state, logout } from "../state.js";
import { analysisView } from "./result.js";

const stat = (label, val, cls = "") => h("div", { class: `stat ${cls}` }, h("span", {}, label), h("b", {}, val ?? "—"));
const table = (head, rows, onclick) => h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, head.map((c) => h("th", {}, c)))), h("tbody", {}, rows.map((r) => h("tr", { class: onclick ? "click" : "", onclick: onclick ? () => onclick(r) : null }, r.cells.map((c) => h("td", {}, c)))))));
const recRow = (a, user = true) => ({ id: a.id, cells: [a.code, ...(user ? [a.user?.name] : []), a.uncertain ? `Unclear (${a.predicted_label})` : a.predicted_label, a.confidence + "%", fmtDateTime(a.created_at)] });

export async function dashboard() {
  const s = await api("/admin/stats");
  return h("div", { class: "stack-lg" }, h("div", {}, h("h1", {}, "Dashboard"), h("p", { class: "muted" }, "Overview of AuraCry")),
    h("div", { class: "grid" }, stat("Users", s.total_users), stat("Analyses", s.total_analyses, "alt"), stat("Dataset rows", s.total_dataset, "alt2"), stat("Model macro-F1", s.model_macro_f1 == null ? null : s.model_macro_f1 + "%", "alt3")),
    !s.model_ready ? notice("warn", "No trained model is loaded. Go to Model Performance and click Train.") : null,
    s.model_accuracy != null ? h("div", { class: "honest" }, `Model "${s.model_name}": accuracy ${s.model_accuracy}% vs ${s.majority_baseline}% for always answering the most common cry. Accuracy alone is misleading here; macro-F1 treats all cry types equally.`) : null,
    h("div", { class: "card" }, h("h3", {}, "Recent analyses"), s.recent.length ? table(["ID", "User", "Result", "Confidence", "Date"], s.recent.map((a) => recRow(a)), (r) => go(`/admin/records/${r.id}`)) : h("div", { class: "empty" }, "No analyses yet.")));
}

export async function users() {
  const body = h("div"), q = h("input", { placeholder: "Search name or email", oninput: () => load() });
  const load = async () => { const d = await api("/admin/users?q=" + encodeURIComponent(q.value));
    body.replaceChildren(table(["Name", "Email", "Role", "Status", "Analyses"], d.users.map((u) => ({ id: u.id, cells: [u.name, u.email, u.role, h("span", { class: `pill ${u.status === "ACTIVE" ? "ok" : ""}` }, u.status), u.analysis_count] })), (r) => go(`/admin/users/${r.id}`))); };
  await load(); return h("div", { class: "stack" }, h("h1", {}, "Users"), h("div", { class: "toolbar" }, q), body);
}
export async function userDetails({ id }) {
  const d = await api(`/admin/users/${id}`), u = d.user, box = h("div");
  const act = async (fn) => { try { await fn(); go(`/admin/users/${id}`, true); } catch (e) { box.replaceChildren(notice("err", e.message)); } };
  return h("div", { class: "stack" }, backBar("User details", "/admin/users"), box,
    h("div", { class: "card" }, [["Name", u.name], ["Email", u.email], ["Role", u.role], ["Status", u.status], ["Joined", fmtDate(u.created_at)], ["Analyses", d.analyses.length]].map(([k, v]) => h("div", { class: "kv" }, h("span", {}, k), h("b", {}, v)))),
    u.role === "USER" ? h("div", { class: "row wrap" }, h("button", { class: "btn ghost", onclick: () => act(() => api(`/admin/users/${id}/status`, { method: "PATCH", body: { status: u.status === "ACTIVE" ? "INACTIVE" : "ACTIVE" } })) }, u.status === "ACTIVE" ? "Deactivate" : "Activate"),
      h("button", { class: "btn danger", onclick: () => { if (confirm("Delete this user and all their analyses?")) act(async () => { await api(`/admin/users/${id}`, { method: "DELETE" }); go("/admin/users", true); }); } }, "Delete")) : null,
    h("div", { class: "card" }, h("h3", {}, "Analyses"), d.analyses.length ? table(["ID", "Result", "Confidence", "Date"], d.analyses.map((a) => ({ id: a.id, cells: [a.code, a.predicted_label, a.confidence + "%", fmtDateTime(a.created_at)] })), (r) => go(`/admin/records/${r.id}`)) : h("div", { class: "empty" }, "None.")));
}

export async function dataset() {
  const render = async () => {
    const d = await api("/admin/dataset"), err = h("div");
    const card = (title, i, role) => h("div", { class: "card stack" }, h("h3", {}, title), i.empty ? notice("warn", i.exists ? "This file is EMPTY (0 bytes). Upload the real file below." : "File not found.") :
      h("div", {}, h("div", { class: "kv" }, h("span", {}, "Rows"), h("b", {}, i.rows)), h("div", { class: "kv" }, h("span", {}, "Recordings"), h("b", {}, i.recordings)), h("div", { class: "kv" }, h("span", {}, "Synthetic rows"), h("b", {}, i.synthetic_rows)),
        h("div", { class: "mt" }, hbars(Object.entries(i.classes).map(([k, v]) => ({ label: k, value: v, text: v, color: "#9b8ce8" }))))),
      h("label", { class: "btn ghost" }, "Upload CSV ", h("input", { type: "file", accept: ".csv", hidden: true, onchange: async (e) => { const f = e.target.files[0]; if (!f) return; const form = new FormData(); form.append("role", role); form.append("file", f);
        try { await api("/admin/dataset/upload", { method: "POST", form }); await rerender(); } catch (x) { err.replaceChildren(notice("err", x.message)); } } })));
    return h("div", { class: "stack" }, h("h1", {}, "Dataset"), h("p", { class: "muted" }, "Feature CSVs (one row = one cry unit). Codes: hu hungry, dk don't-know, ti tired, bp belly pain, sc scared, dc discomfort, ch cold/hot, bu burping, lo lonely."), err,
      h("div", { class: "grid g2" }, card("Training CSV (balanced_full_dataset_clean.csv)", d.train, "train"), card("Test CSV (test_dataset_clean.csv)", d.test, "test")),
      h("div", { class: "honest" }, "Rare cry types come from only 2–4 recordings each. Rows from the same recording are near-duplicates, so the trainer always splits by recording. More recordings of rare types is the real fix for accuracy."));
  };
  const holder = h("div"); const rerender = async () => holder.replaceChildren(await render()); await rerender(); return holder;
}


export async function model() {
  const d = await api("/admin/model/performance");
  const m = d.metrics || {};
  const ml = m.test || {};
  const dlBlock = m.deep_learning || {};
  const dl = dlBlock.test || {};
  const comparisonData = m.comparison || {};
  const selected = ml.accuracy != null ? ml : (m.selected || {});
  const perClass = m.per_class || {};
  const classEntries = Object.entries(perClass).filter(
    ([name, v]) => !["accuracy", "macro avg", "weighted avg"].includes(name.toLowerCase()) &&
      v && typeof v === "object" && Number.isFinite(Number(v.precision))
  );
  const pct = (v) => v == null || !Number.isFinite(Number(v)) ? "—" : (Number(v) * 100).toFixed(1) + "%";

  const logBox = h("pre", { class: "small", style: {
    maxHeight: "220px", overflow: "auto", background: "rgba(0,0,0,.06)",
    padding: "10px", borderRadius: "10px", whiteSpace: "pre-wrap"
  }});
  const btn = h("button", { class: "btn" }, "Train / retrain");
  const msg = h("div");
  const poll = async () => {
    try {
      const s = await api("/admin/model/train-status");
      logBox.textContent = s.log_tail || "";
      btn.disabled = s.running;
      btn.textContent = s.running ? "Training…" : "Train / retrain";
      if (s.running) setTimeout(poll, 2500);
      else if (s.exit_code === 0 && logBox.dataset.was) go("/admin/model", true);
      logBox.dataset.was = s.running ? "1" : "";
    } catch (e) { msg.replaceChildren(notice("err", e.message)); }
  };
  btn.onclick = async () => {
    try {
      await api("/admin/model/retrain", { method: "POST", body: { drop_unclear: true, quick: true } });
      logBox.dataset.was = "1"; poll();
    } catch (e) { msg.replaceChildren(notice("err", e.message)); }
  };
  const train = h("div", { class: "card stack" },
    h("h3", {}, "Training controls"),
    h("p", { class: "muted small" }, "Train / retrain runs the existing tabular ML pipeline. It does not retrain the CNN + BiGRU model."),
    msg, h("div", { class: "row wrap" }, btn,
      h("button", { class: "btn ghost", onclick: async () => {
        const r = await api("/admin/model/reload", { method: "POST" });
        msg.replaceChildren(notice(r.model_ready ? "ok" : "err", r.model_ready ? "Model reloaded." : r.message));
      }}, "Reload model file")
    ), logBox
  );
  const heading = h("div", {}, h("h1", {}, "Model Performance"),
    h("p", { class: "muted" }, "Evaluation values loaded from the project's saved ML and CNN + BiGRU metrics files."));
  if (ml.accuracy == null && !Object.keys(dl).length) {
    return h("div", { class: "stack" }, heading,
      notice("warn", "No saved evaluation metrics were found. Check backend/model/metrics.json and dl_metrics.json."), train);
  }

  const comparisonRows = [];
  const comp = (name, obj) => {
    const v = obj?.recording_level || obj || {};
    if (v.accuracy != null || v.macro_f1 != null) comparisonRows.push({ cells: [h("b", {}, name), pct(v.accuracy), pct(v.balanced_accuracy), pct(v.macro_f1)] });
  };
  Object.entries(comparisonData).forEach(([name, value]) => comp(name, value));
  if (dl.accuracy != null || dl.macro_f1 != null) comp("CNN + BiGRU", dl);
  if (!comparisonRows.length && ml.accuracy != null) comp(m.model_name || "Current ML stack", ml);

  const classTable = classEntries.length ? table(
    ["Cry type", "Precision", "Recall", "F1-score", "Support"],
    classEntries.map(([name, v]) => ({ cells: [
      h("b", { style: { color: colorOf(name) } }, name),
      pct(v.precision), pct(v.recall), pct(v["f1-score"]), v.support ?? "—"
    ]}))
  ) : h("div", { class: "empty" }, "Per-class evaluation values are not present in the saved metrics.");

  const classCounts = m.class_counts || {};
  const trainClips = m.n_train_clips ?? m.n_train ?? m.n_train_units ?? dlBlock.n_train;
  const valClips = m.n_val ?? dlBlock.n_val;
  const testClips = m.n_test_clips ?? m.n_test ?? dlBlock.n_test;
  const trainInfo = [
    ["Training units / clips", trainClips],
    ["Validation clips (CNN + BiGRU)", valClips],
    ["Held-out test clips", testClips],
    ["ML grouped CV macro-F1", m.grouped_cv_macro_f1?.mean == null ? null : pct(m.grouped_cv_macro_f1.mean)],
    ["CNN + BiGRU best validation macro-F1", dlBlock.best_val_macro_f1 == null ? null : pct(dlBlock.best_val_macro_f1)]
  ];

  return h("div", { class: "stack-lg" }, heading,
    h("div", { class: "grid" },
      stat("ML stack accuracy", pct(ml.accuracy)),
      stat("ML stack macro-F1", pct(ml.macro_f1), "alt"),
      stat("CNN + BiGRU accuracy", pct(dl.accuracy), "alt2"),
      stat("CNN + BiGRU macro-F1", pct(dl.macro_f1), "alt3")
    ),
    h("div", { class: "honest" },
      h("b", {}, "Evaluation note. "),
      "These are saved held-out evaluation metrics, not the confidence of an individual uploaded recording. Accuracy can hide poor performance on rare cry types; macro-F1 gives each class equal weight."
    ),
    h("div", { class: "card stack" }, h("h3", {}, "Model comparison"),
      comparisonRows.length ? table(["Model", "Accuracy", "Balanced accuracy", "Macro-F1"], comparisonRows) :
        h("div", { class: "empty" }, "Comparison metrics are not available.")
    ),
    h("div", { class: "grid g2" },
      h("div", { class: "card stack" }, h("h3", {}, "Training dataset class distribution"),
        Object.keys(classCounts).length ? hbars(Object.entries(classCounts).map(([name, count]) => ({
          label: name, value: count, text: count, color: "#9b8ce8"
        }))) : h("div", { class: "empty" }, "Class counts are not present in metrics.")
      ),
      h("div", { class: "card stack" }, h("h3", {}, "Training information"),
        trainInfo.map(([name, value]) => h("div", { class: "kv" },
          h("span", {}, name), h("b", {}, value ?? "—")
        ))
      )
    ),
    h("div", { class: "card stack" }, h("h3", {}, "Per-class ML performance"), classTable,
      h("div", { class: "mt" }, link("/admin/model/confusion", { class: "btn ghost" }, "Open confusion matrix"))
    ),
    train
  );
}

export async function confusion() {
  const response = await api("/admin/model/performance");
  const m = response.metrics || {};
  const matrix = m.confusion_matrix || [];
  const labels = m.labels || m.classes || [];
  if (!matrix.length || !labels.length || matrix.length !== labels.length ||
      matrix.some((row) => !Array.isArray(row) || row.length !== labels.length)) {
    return h("div", { class: "stack" }, backBar("Confusion matrix", "/admin/model"),
      notice("warn", "A compatible confusion matrix is not available in the saved ML metrics."));
  }
  let norm = false;
  const holder = h("div");
  const draw = () => holder.replaceChildren(heatmap(matrix, labels, norm));
  draw();
  return h("div", { class: "stack" }, backBar("Confusion matrix", "/admin/model"),
    h("div", { class: "tabs" },
      h("button", { class: "on", onclick: (e) => {
        norm = false; e.target.className = "on"; e.target.nextSibling.className = ""; draw();
      }}, "Counts"),
      h("button", { onclick: (e) => {
        norm = true; e.target.className = "on"; e.target.previousSibling.className = ""; draw();
      }}, "Row %")
    ), holder,
    h("p", { class: "muted small" }, "Rows represent the actual cry type. Columns represent the predicted cry type. Results are from the held-out test set.")
  );
}

export async function records() {
  const body = h("div"), q = h("input", { placeholder: "Search ID, user or file", oninput: () => load() }), cat = h("select", { onchange: () => load() }, h("option", { value: "" }, "All categories"), ["hu", "ti", "dc", "bu", "bp", "sc", "ch", "lo"].map((c) => h("option", { value: c }, { hu: "Hungry", ti: "Tired", dc: "Discomfort", bu: "Needs Burping", bp: "Belly Pain", sc: "Scared", ch: "Cold / Hot", lo: "Lonely" }[c])));
  const load = async () => { const d = await api(`/admin/analyses?q=${encodeURIComponent(q.value)}&category=${cat.value}`); body.replaceChildren(d.analyses.length ? table(["ID", "User", "Result", "Confidence", "Date"], d.analyses.map((a) => recRow(a)), (r) => go(`/admin/records/${r.id}`)) : h("div", { class: "card empty" }, "No records match.")); };
  await load(); return h("div", { class: "stack" }, h("h1", {}, "Analysis Records"), h("div", { class: "toolbar" }, q, cat), body);
}
export async function recordDetails({ id }) { const d = await api(`/admin/analyses/${id}`); return h("div", { class: "stack" }, backBar("Record details", "/admin/records"), analysisView(d.analysis, { admin: true })); }

export async function reports() {
  const d = await api("/admin/reports"); let tab = "daily"; const holder = h("div"), tabs = h("div", { class: "tabs" });
  const draw = () => { tabs.replaceChildren(...["daily", "weekly", "monthly"].map((t) => h("button", { class: tab === t ? "on" : "", onclick: () => { tab = t; draw(); } }, t[0].toUpperCase() + t.slice(1)))); holder.replaceChildren(columnChart(d[tab])); }; draw();
  return h("div", { class: "stack-lg" }, h("h1", {}, "Reports"), h("div", { class: "grid" }, stat("Total analyses", d.total_analyses), stat("Users", d.total_users, "alt"), stat("Avg confidence", d.avg_confidence == null ? null : d.avg_confidence + "%", "alt2")),
    h("div", { class: "card" }, h("h3", {}, "Cry type distribution"), d.distribution.length ? hbars(d.distribution.map((x) => ({ label: x.label, value: x.count, text: x.count, color: colorOf(x.label) }))) : h("div", { class: "empty" }, "No analyses yet.")),
    h("div", { class: "card" }, h("h3", {}, "Analyses over time"), tabs, holder));
}
export function profile() {
  const u = state.user, pe = h("div"), pp = h("div"), inp = (n, l, v, t = "text") => h("label", { class: "field" }, h("span", {}, l), h("input", { name: n, type: t, value: v || "" }));
  const f1 = h("form", { class: "card stack", onsubmit: async (e) => { e.preventDefault(); pe.replaceChildren(); try { state.user = (await api("/account/profile", { method: "PUT", body: { name: f1.elements.name.value, email: f1.elements.email.value } })).user; pe.append(notice("ok", "Profile updated.")); } catch (x) { pe.append(notice("err", x.message)); } } }, h("h3", {}, "Admin profile"), pe, inp("name", "Name", u.name), inp("email", "Email", u.email), h("button", { class: "btn block" }, "Save"));
  const f2 = h("form", { class: "card stack", onsubmit: async (e) => { e.preventDefault(); pp.replaceChildren(); try { await api("/account/password", { method: "POST", body: { current_password: f2.elements.c.value, new_password: f2.elements.n.value, confirm_password: f2.elements.m.value } }); f2.reset(); pp.append(notice("ok", "Password changed.")); } catch (x) { pp.append(notice("err", x.message)); } } }, h("h3", {}, "Change password"), pp, inp("c", "Current password", "", "password"), inp("n", "New password", "", "password"), inp("m", "Confirm", "", "password"), h("button", { class: "btn block" }, "Change password"));
  return h("div", { class: "stack", style: { maxWidth: "520px" } }, h("h1", {}, "Profile / Settings"), f1, f2);
}
