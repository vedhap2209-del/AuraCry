"""Find labelled audio files and split them WITHOUT data leakage."""
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config as C

AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
_UUID = re.compile(r"^[0-9a-fA-F-]{36}$")


@dataclass
class Item:
    path: str
    label: int
    group: str


def infer_class(path: Path):
    """Class from the nearest known parent folder, else from the file-name code."""
    for parent in path.parents:
        cls = C.FOLDER_TO_CLASS.get(parent.name.lower())
        if cls:
            return cls
    code = path.stem.split("-")[-1].lower()
    return C.CODE_TO_CLASS.get(code)


def infer_group(path: Path) -> str:
    """Donate-a-Cry names start with an app-install id. Recordings sharing an id come
    from the same baby/household, so they must never be split across train/test."""
    head = path.stem[:36]
    return head if _UUID.match(head) else path.stem


def discover_files(data_dir):
    items, skipped = [], 0
    for p in sorted(Path(data_dir).rglob("*")):
        if p.suffix.lower() not in AUDIO_EXT:
            continue
        cls = infer_class(p)
        if cls is None:
            skipped += 1
            continue
        items.append(Item(str(p), C.CLASSES.index(cls), infer_group(p)))
    return items, skipped


def make_splits(items, seed=42):
    """Stratified + grouped 64/16/20 train/val/test split."""
    import warnings
    from sklearn.model_selection import StratifiedGroupKFold

    y = np.array([it.label for it in items])
    g = np.array([it.group for it in items])
    idx = np.arange(len(items))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        trainval, test = next(StratifiedGroupKFold(5, shuffle=True, random_state=seed).split(idx, y, g))
        tr, va = next(StratifiedGroupKFold(4, shuffle=True, random_state=seed)
                      .split(trainval, y[trainval], g[trainval]))
    return trainval[tr], trainval[va], test
