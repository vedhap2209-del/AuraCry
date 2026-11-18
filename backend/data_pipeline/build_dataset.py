"""Build the unified AuraCry dataset: manifest, exclusions, subject-wise splits, training-only augmentation.

    python -m data_pipeline.build_dataset --dac ../data/sources/donateacry-corpus --esc50 ../data/sources/ESC-50 \
        [--dbl ../data/sources/InfantCry-DBL] --out ../data

Rules this script enforces (see DATASET_REPORT.md):
* Only real recordings enter validation/test. Augmented clips exist only in train and keep their parent's subject + fold.
* Splits are by subject (Donate-a-Cry app install), so one family's recordings never sit on both sides.
* Nothing is relabelled to improve scores; every excluded file is listed with its reason.
"""
import argparse, csv, hashlib, json, re, subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from data_pipeline import labels as L

SR = 16000
DAC_RX = re.compile(r"^(?P<uuid>[0-9A-Fa-f-]{36})-(?P<ts>\d+)-(?P<ver>[\d.]+)-(?P<g>[mf])-(?P<age>\d{2})-(?P<r>[a-z]{2})$")
DAC_URL = "https://github.com/gveres/donateacry-corpus"
ESC_URL = "https://github.com/karolpiczak/ESC-50"
DBL_URL = "https://data.mendeley.com/datasets/x493z8nmwc/1"
FIELDS = ["sample_id", "task", "source_dataset", "source_url", "license", "source_file", "original_label", "label",
          "subject_id", "gender", "age_band", "recorded_unix", "platform", "orig_codec", "orig_sr", "audio_path",
          "duration_s", "pcm_sha1", "is_synthetic", "is_augmented", "augmentation", "parent_id", "split", "cv_fold", "notes"]


def decode(src, dst):
    """Any input -> 16 kHz mono 16-bit WAV via ffmpeg. Returns (duration, orig_codec, orig_sr) or None."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name,sample_rate",
                         "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout.strip().split(",")
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", str(SR), "-sample_fmt", "s16", str(dst)],
                       capture_output=True)
    if r.returncode or not dst.exists():
        return None
    y, _ = sf.read(dst, dtype="int16")
    if len(y) < SR * 0.3:
        return None
    return len(y) / SR, (pr[0] if pr and pr[0] else ""), (int(pr[1]) if len(pr) > 1 and pr[1].isdigit() else "")


def pcm_sha1(path):
    y, _ = sf.read(path, dtype="int16")
    return hashlib.sha1(y.tobytes()).hexdigest()


def row(**kw):
    r = {k: "" for k in FIELDS}
    r.update(is_synthetic=0, is_augmented=0)
    r.update(kw)
    return r


# ---------------------------------------------------------------- sources
def load_donateacry(repo, out):
    repo = Path(repo)
    curated = {p.stem: p.parent.name for p in (repo / "donateacry_corpus_cleaned_and_updated_data").rglob("*.wav")}
    raw = sorted(repo.glob("donateacry-*-bucket/*"))
    kept, excluded, seen = [], [], {}
    for p in raw:
        m = DAC_RX.match(p.stem)
        base = dict(task="cry_reason", source_dataset="donateacry", source_url=DAC_URL, license="ODbL-1.0 / DbCL-1.0",
                    source_file=str(p.relative_to(repo)), platform="ios" if p.suffix == ".caf" else "android")
        if not m:
            excluded.append(row(**base, notes="filename does not follow the Donate-a-Cry tag convention")); continue
        base.update(original_label=m["r"], subject_id="dac:" + m["uuid"].lower(), gender=m["g"], age_band=m["age"],
                    recorded_unix=m["ts"][:10])
        if p.stem not in curated:
            why = ("label not used (lonely/scared/don't-know)" if L.DONATEACRY_TAG.get(m["r"]) is None
                   else "rejected by the Donate-a-Cry curators after listening (non-cry, noise, adult imitation, etc.)")
            excluded.append(row(**base, label=L.DONATEACRY_TAG.get(m["r"]) or "", notes=why)); continue
        sid = "dac_" + hashlib.sha1(p.stem.encode()).hexdigest()[:12]
        dst = out / "audio" / "donateacry" / f"{sid}.wav"
        d = decode(p, dst)
        if d is None:
            excluded.append(row(**base, notes="audio could not be decoded or is shorter than 0.3 s")); continue
        h = pcm_sha1(dst)
        if h in seen:
            dst.unlink(); excluded.append(row(**base, notes=f"exact duplicate of {seen[h]}")); continue
        seen[h] = sid
        lab = L.DONATEACRY_FOLDER[curated[p.stem]]
        note = "label from curated folder" + ("" if L.DONATEACRY_TAG.get(m["r"]) == lab else f" (uploader tag '{m['r']}' merged)")
        kept.append(row(**base, sample_id=sid, label=lab, audio_path=str(dst.relative_to(out)), duration_s=round(d[0], 3),
                        orig_codec=d[1], orig_sr=d[2], pcm_sha1=h, notes=note))
    return kept, excluded


def load_dbl(root, out, known_hashes):
    """InfantCry-DBL (Mendeley, CC BY 4.0). Folder name is the authoritative label (per the dataset card).
    A committed audit list (cross_source_conflicts.csv) names Tier 2 clips that are the SAME audio as a curated
    Donate-a-Cry clip but carry a different label; those are dropped (Donate-a-Cry's curated label is kept instead)."""
    root = Path(root)
    kept, excluded = [], []
    qfile = Path(__file__).with_name("cross_source_conflicts.csv")
    quarantine = {}
    if qfile.exists():
        with open(qfile, newline="") as f:
            for r in csv.DictReader(f):
                quarantine[Path(r["dbl_file"]).name] = r["dac_curated_label"]
    meta = {}
    for mf in root.rglob("metadata.csv"):
        with open(mf, newline="", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                key = Path(r.get("file_name") or r.get("filename") or r.get("path") or "").name
                if key:
                    meta[key] = r
    # Tier 1 first: Tier 2 turned out to contain byte-identical copies of Tier 1 clips, and those must stay train-only.
    files = [p for p in root.rglob("*") if p.suffix.lower() in (".wav", ".mp3", ".m4a", ".flac", ".ogg")]
    files.sort(key=lambda p: (0 if p.name.lower().startswith("dunstan") else 1, str(p)))
    by_id = {}
    for p in files:
        folder = next((part.lower() for part in reversed(p.parts[:-1]) if part.lower() in L.DUNSTAN), None)
        md = meta.get(p.name, {})
        src_note = (md.get("source") or "").strip()
        tier = str(md.get("tier") or ("1" if p.name.lower().startswith("dunstan") else "2"))
        # Tier 2 filenames are <ID>_<sex>_<class>.wav; the README says to keep each ID in one split.
        # Tier 1 (instructional videos) has no infant identity at all -> it is never put in validation/test.
        sub = f"dbl_t1:{p.name}" if tier == "1" else "dbl:" + p.name.split("_")[0]
        base = dict(task="cry_reason", source_dataset="infantcry_dbl_t" + tier, source_url=DBL_URL, license="CC-BY-4.0",
                    source_file=str(p.relative_to(root)), original_label=folder or "", subject_id=sub,
                    gender=(md.get("gender") or "").lower())
        if folder is None:
            excluded.append(row(**base, notes="not inside a Dunstan category folder")); continue
        if p.name in quarantine:
            excluded.append(row(**base, notes=f"same audio as a curated Donate-a-Cry '{quarantine[p.name]}' clip but "
                                f"labelled '{folder}' here: dropped, Donate-a-Cry label kept")); continue
        if "cryceleb" in src_note.lower():
            base["license"] = "CC-BY-4.0 (derived from CryCeleb2023, source licence CC-BY-NC-ND-4.0)"
        sid = "dbl_" + hashlib.sha1(str(p.relative_to(root)).encode()).hexdigest()[:12]
        dst = out / "audio" / "infantcry_dbl" / f"{sid}.wav"
        d = decode(p, dst)
        if d is None:
            excluded.append(row(**base, notes="audio could not be decoded or is shorter than 0.3 s")); continue
        h = pcm_sha1(dst)
        if h in known_hashes:
            dst.unlink()
            first = by_id.get(known_hashes[h])
            if first is not None and first["label"] != L.DUNSTAN[folder]:
                kept.remove(first); first["notes"] = "identical audio is labelled differently elsewhere in the corpus"
                excluded.append(first); by_id.pop(first["sample_id"])
                excluded.append(row(**base, notes=f"identical audio to {known_hashes[h]} but a different label")); continue
            excluded.append(row(**base, notes=f"exact duplicate of {known_hashes[h]}" +
                                (" (a Tier 1 studio clip re-used in Tier 2)" if first is not None and first.get("_forced") else "")))
            continue
        known_hashes[h] = sid
        if tier == "1":
            base["notes_extra"] = "Tier 1 (studio, instructional video, no infant id): training only, never evaluated"
            base["forced_split"] = "train"
        notes = (f"tier {tier}, source={src_note or 'n/a'}; label from Dunstan category folder (annotator judgement of the "
                 "sound, not a confirmed cause); Dunstan categories are not scientifically validated")
        kept.append(row(**{k: v for k, v in base.items() if k not in ("notes_extra", "forced_split")},
                        _forced=base.get("forced_split", ""), sample_id=sid, label=L.DUNSTAN[folder],
                        audio_path=str(dst.relative_to(out)), duration_s=round(d[0], 3), orig_codec=d[1], orig_sr=d[2],
                        pcm_sha1=h, notes=notes + ("; " + base["notes_extra"] if "notes_extra" in base else "")))
        by_id[sid] = kept[-1]
    return kept, excluded


def load_esc50(repo, out):
    """Side task only (cry vs not-cry). ESC-50 has no cry-reason labels, so it never enters the reason classifier."""
    repo = Path(repo)
    rows = []
    with open(repo / "meta" / "esc50.csv", newline="") as f:
        for r in csv.DictReader(f):
            cry = r["category"] == "crying_baby"
            rows.append(row(sample_id="esc_" + Path(r["filename"]).stem, task="cry_detection", source_dataset="esc50",
                            source_url=ESC_URL, license="CC-BY-NC-3.0 (clips from freesound.org)", source_file="audio/" + r["filename"],
                            original_label=r["category"], label="cry" if cry else "not_cry", subject_id="esc:" + r["src_file"],
                            audio_path=str((repo / "audio" / r["filename"]).resolve()), duration_s=5.0, orig_sr=44100,
                            cv_fold=int(r["fold"]) - 1, split="train" if r["fold"] in "123" else ("val" if r["fold"] == "4" else "test"),
                            notes="ESC-50 official fold kept"))
    return rows


# ---------------------------------------------------------------- near-duplicates
def merge_near_duplicates(rows, out, thr=0.995):
    """Clips that sound almost identical (re-encodes, re-uploads, overlapping segments) must share a split.
    Fingerprint = mean+std of a 4 kHz band-limited log-mel; pairs above `thr` cosine get one subject id (union-find)."""
    import librosa
    V = []
    for r in rows:
        y, _ = sf.read(out / r["audio_path"], dtype="float32")
        S = librosa.power_to_db(librosa.feature.melspectrogram(y=y, sr=SR, n_mels=48, fmax=4000) + 1e-10)
        v = np.concatenate([S.mean(1), S.std(1)]); v = v - v.mean(); V.append(v / (np.linalg.norm(v) + 1e-9))
    V = np.array(V); C = V @ V.T; np.fill_diagonal(C, 0)
    # Union-find over SUBJECTS (not clips): a near-duplicate pair merges the two clips' whole subject groups, so clips that
    # share a real id stay together and a merged group can never collide with an unrelated clip that already has that id.
    subs = sorted({r["subject_id"] for r in rows})
    idx = {s: k for k, s in enumerate(subs)}
    parent = list(range(len(subs)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    pairs = np.argwhere(np.triu(C > thr))
    for i, j in pairs:
        parent[find(idx[rows[i]["subject_id"]])] = find(idx[rows[j]["subject_id"]])
    comp = {}                                   # component root -> member subject ids
    for s, k in idx.items():
        comp.setdefault(find(k), []).append(s)
    canon, forced_comp = {}, {}
    for members in comp.values():
        rep = "grp:" + hashlib.sha1("|".join(sorted(members)).encode()).hexdigest()[:12] if len(members) > 1 else members[0]
        for s in members:
            canon[s] = rep
    forced_sub = {r["subject_id"] for r in rows if r.get("_forced") == "train"}
    forced_reps = {canon[s] for s in forced_sub}
    merged = 0
    for r in rows:
        new = canon[r["subject_id"]]
        if new != r["subject_id"]:
            r["notes"] += f"; near-duplicate cluster {new}"; merged += 1
            r["subject_id"] = new
        if new in forced_reps:
            r["_forced"] = "train"              # a studio Tier-1 clip anywhere in the cluster -> whole cluster is train-only
    cross = sum(1 for i, j in pairs if rows[i]["source_dataset"][:5] != rows[j]["source_dataset"][:5])
    return dict(pairs=int(len(pairs)), clips_regrouped=merged, cross_source_pairs=int(cross),
                clusters_merged=sum(len(m) > 1 for m in comp.values()))


# ---------------------------------------------------------------- splits
def assign_splits(rows, n_folds=5, seed=42):
    """Subject-wise stratified folds. fold 0 = test, fold 1 = validation, folds 2-4 = train. Every class must appear in
    test and validation; seeds are tried in order and the first one that satisfies that is used (recorded in the report)."""
    from sklearn.model_selection import StratifiedGroupKFold
    forced = [r for r in rows if r.get("_forced") == "train"]
    for r in forced:
        r["split"], r["cv_fold"] = "train", -1          # -1 = training data in every cross-validation fold
    rows = [r for r in rows if r.get("_forced") != "train"]
    y = np.array([r["label"] for r in rows]); g = np.array([r["subject_id"] for r in rows])
    for s in range(seed, seed + 200):
        folds = np.empty(len(rows), int)
        for k, (_, te) in enumerate(StratifiedGroupKFold(n_folds, shuffle=True, random_state=s).split(np.zeros(len(y)), y, g)):
            folds[te] = k
        if all(set(y[folds == k]) == set(L.CLASSES) for k in (0, 1)):
            break
    else:
        raise RuntimeError("could not find a split with every class in test and validation")
    for r, k in zip(rows, folds):
        r["cv_fold"] = int(k); r["split"] = "test" if k == 0 else ("val" if k == 1 else "train")
    return s


# ---------------------------------------------------------------- augmentation (train only)
def augment(rows, out, max_per_original=8, seed=7):
    """Bring minority classes towards the majority with label-preserving audio transforms.
    Capped at `max_per_original` copies per real clip: copying 5 clips 50 times teaches the model those 5 clips, not the class.
    The rest of the imbalance is left to class weights at training time."""
    import librosa
    rng = np.random.default_rng(seed)
    train = [r for r in rows if r["split"] == "train" and r["task"] == "cry_reason"]
    by = {c: [r for r in train if r["label"] == c] for c in L.CLASSES}
    target = max(len(v) for v in by.values())
    recipes = [("pitch", +1.0), ("pitch", -1.0), ("stretch", 0.9), ("stretch", 1.1), ("noise", 20.0), ("pitch", +2.0),
               ("pitch", -2.0), ("noise", 15.0), ("gain", -6.0), ("stretch", 0.95)]
    aug = []
    for c, items in by.items():
        if not items:
            continue
        need = min(target - len(items), max_per_original * len(items))
        for i in range(max(need, 0)):
            parent = items[i % len(items)]
            kind, val = recipes[(i // len(items)) % len(recipes)]
            y, _ = sf.read(out / parent["audio_path"], dtype="float32")
            if kind == "pitch":
                z = librosa.effects.pitch_shift(y, sr=SR, n_steps=val)
            elif kind == "stretch":
                z = librosa.effects.time_stretch(y, rate=val)
            elif kind == "noise":
                p = np.mean(y ** 2) + 1e-12
                z = y + rng.normal(0, np.sqrt(p / 10 ** (val / 10)), len(y)).astype("float32")
            else:
                z = y * 10 ** (val / 20)
            z = np.clip(z, -1, 1)
            sid = f"{parent['sample_id']}_aug{i // len(items):02d}"
            dst = out / "audio" / "augmented" / f"{sid}.wav"
            dst.parent.mkdir(parents=True, exist_ok=True)
            sf.write(dst, z, SR, subtype="PCM_16")
            aug.append({**parent, "sample_id": sid, "audio_path": str(dst.relative_to(out)), "duration_s": round(len(z) / SR, 3),
                        "pcm_sha1": "", "is_synthetic": 1, "is_augmented": 1, "augmentation": f"{kind}:{val}",
                        "parent_id": parent["sample_id"], "notes": "augmented copy of a training recording; never used for validation/test"})
    return aug


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dac", required=True); ap.add_argument("--esc50"); ap.add_argument("--dbl"); ap.add_argument("--out", required=True)
    ap.add_argument("--no_augment", action="store_true")
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    kept, excl = load_donateacry(a.dac, out)
    known = {r["pcm_sha1"]: r["sample_id"] for r in kept}
    if a.dbl:
        k2, e2 = load_dbl(a.dbl, out, known); kept += k2; excl += e2
    dup = merge_near_duplicates(kept, out)
    seed = assign_splits(kept)
    aug = [] if a.no_augment else augment(kept, out)
    write(out / "manifest.csv", kept + aug)
    write(out / "excluded.csv", excl)
    if a.esc50:
        write(out / "manifest_cry_detection.csv", load_esc50(a.esc50, out))
    info = {"classes": L.CLASSES, "split_seed": seed, "n_real": len(kept), "n_augmented": len(aug), "n_excluded": len(excl), "near_duplicates": dup,
            "sources": sorted({r["source_dataset"] for r in kept})}
    (out / "build_info.json").write_text(json.dumps(info, indent=2))
    print(json.dumps(info))


if __name__ == "__main__":
    main()
