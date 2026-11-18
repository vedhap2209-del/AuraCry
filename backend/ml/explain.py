"""Plain-language reasons for a prediction, grounded in the training data.

For every acoustic feature we ask: is this recording's value more typical of the predicted class than of the
runner-up class (Gaussian log-likelihood ratio using per-class mean/std learned from the CSV)?
These are statistical associations in the training rows, not diagnoses."""
import math

INFO = {  # key: (label, unit, decimals)
    "Mean_F0": ("Average pitch", "Hz", 0), "Min_F0": ("Lowest pitch", "Hz", 0), "Max_F0": ("Peak pitch", "Hz", 0),
    "Std_F0": ("Pitch variability", "Hz", 0), "HNR": ("Harmonics-to-noise ratio", "dB", 1), "Duration": ("Cry-unit length", "s", 2),
}
for i in range(1, 14):
    INFO[f"MFCC_{i}"] = (f"Spectral shape (MFCC {i})", "", 1)
GROUP = {k: ("pitch" if "F0" in k else "voice" if k == "HNR" else "timing" if k == "Duration" else "spectrum") for k in INFO}


def _fmt(k, v):
    _, u, d = INFO[k]
    return f"{v:.{d}f}{(' ' + u) if u else ''}"


def _ll(x, m, s, floor):
    s = max(s, floor, 1e-6)
    return -0.5 * ((x - m) / s) ** 2 - math.log(s)


def build(mean_features, profiles, pred_code, runner_code, labels, probs):
    out = {"headline": "", "supporting": [], "conflicting": [], "feature_table": [], "caveats": [], "grounded": False}
    cp = profiles["classes"].get(pred_code, {}); cr = profiles["classes"].get(runner_code, {})
    if not cp or not cr or "Mean_F0" not in cp or "Mean_F0" not in cr:
        out["headline"] = f"Predicted {labels[pred_code]}. There are too few training rows to compare it with the runner-up."
        return out
    out["grounded"] = True
    scored = []
    for k in INFO:
        x = mean_features.get(k)
        if x is None or k not in cp or k not in cr:
            continue
        floor = 0.35 * profiles["global"][k]["std"]
        llr = _ll(x, cp[k]["mean"], cp[k]["std"], floor) - _ll(x, cr[k]["mean"], cr[k]["std"], floor)
        scored.append((llr, k, x))
        out["feature_table"].append({"feature": INFO[k][0], "value": _fmt(k, x),
                                     "typical_pred": f"{cp[k]['p10']:.{INFO[k][2]}f} to {cp[k]['p90']:.{INFO[k][2]}f}",
                                     "typical_runner": f"{cr[k]['p10']:.{INFO[k][2]}f} to {cr[k]['p90']:.{INFO[k][2]}f}"})
    def entry(llr, k, x, supports):
        near, far = (pred_code, runner_code) if supports else (runner_code, pred_code)
        return {"feature": k, "strength": round(abs(llr), 2),
                "text": f"{INFO[k][0]}: {_fmt(k, x)} is closer to typical {labels[near]} cries ({_fmt(k, profiles['classes'][near][k]['mean'])}) "
                        f"than {labels[far]} cries ({_fmt(k, profiles['classes'][far][k]['mean'])})."}
    seen = {}
    for llr, k, x in sorted(scored, key=lambda t: -t[0]):
        g = GROUP[k]
        if llr < 0.3 or len(out["supporting"]) >= 4 or seen.get(g, 0) >= 2:
            continue
        seen[g] = seen.get(g, 0) + 1; out["supporting"].append(entry(llr, k, x, True))
    seen = {}
    for llr, k, x in sorted(scored, key=lambda t: t[0]):
        g = GROUP[k]
        if llr > -0.3 or len(out["conflicting"]) >= 2 or seen.get(g, 0) >= 1:
            continue
        seen[g] = 1; out["conflicting"].append(entry(llr, k, x, False))
    p1, p2 = probs.get(pred_code, 0), probs.get(runner_code, 0)
    out["headline"] = (f"Why {labels[pred_code]}? The model gives it {p1 * 100:.0f}% vs {p2 * 100:.0f}% for {labels[runner_code]}. "
                       f"{len(out['supporting'])} measured properties favour {labels[pred_code]}"
                       + (f", {len(out['conflicting'])} point towards {labels[runner_code]}." if out["conflicting"] else "."))
    n_rec = cp.get("recordings", 0)
    if n_rec < 6:
        out["caveats"].append(f"The reference data for {labels[pred_code]} comes from only {n_rec} recordings - treat with caution.")
    out["caveats"].append("These are statistical patterns from the training recordings, not a medical diagnosis.")
    return out


def drift(vec_names, mean_vec, profiles):
    """Which features of this recording lie outside the range seen in training (microphone / pipeline mismatch warning)."""
    flagged = []
    for k, v in zip(vec_names, mean_vec):
        g = profiles["global"].get(k)
        if not g:
            continue
        z = (v - g["mean"]) / max(g["std"], 1e-9)
        lo, hi = g["p1"], g["p99"]
        span = max(hi - lo, 1e-9)
        if v < lo - 0.25 * span or v > hi + 0.25 * span:
            flagged.append({"feature": k, "value": round(float(v), 2), "z": round(float(z), 1)})
    return flagged
