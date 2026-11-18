import random

import librosa
import numpy as np
import torch
from torch.utils.data import Dataset

from . import config as C
from .audio_utils import best_window, fix_length, logmel


class CryDataset(Dataset):
    """Holds pre-loaded, pre-normalised waveforms (loaded once, not every epoch).

    train=True : random 3 s crop + noise / mild pitch shift / mild time stretch
                 + SpecAugment (frequency & time masking)
    train=False: deterministic loudest 3 s window (what inference uses)
    """

    def __init__(self, waves, labels, train=False):
        self.waves = waves
        self.labels = list(labels)
        self.train = train
        self.n = int(C.SR * C.DURATION)

    def __len__(self):
        return len(self.waves)

    def best_wave(self, i):
        return best_window(self.waves[i])

    # -- augmentation -------------------------------------------------------
    def _crop(self, y):
        if len(y) <= self.n:
            return fix_length(y, self.n)
        s = random.randint(0, len(y) - self.n)
        return y[s:s + self.n]

    def _augment_wave(self, y):
        if random.random() < 0.5:                       # background noise, SNR 10-35 dB
            snr = random.uniform(10, 35)
            p = float(np.mean(y ** 2)) + 1e-9
            y = y + np.random.randn(len(y)).astype(np.float32) * np.sqrt(p / (10 ** (snr / 10)))
        if random.random() < 0.3:                       # small pitch shift (pitch carries class info!)
            y = librosa.effects.pitch_shift(y, sr=C.SR, n_steps=random.uniform(-0.5, 0.5))
        if random.random() < 0.3:                       # mild tempo change
            y = librosa.effects.time_stretch(y, rate=random.uniform(0.92, 1.08))
        y = fix_length(y, self.n)
        peak = float(np.abs(y).max())
        return y / peak * 0.95 if peak > 1e-6 else y

    @staticmethod
    def _spec_augment(S):
        S = S.copy()
        n_mels, T = S.shape
        for _ in range(random.randint(1, 2)):
            w = random.randint(4, 16)
            f0 = random.randint(0, max(n_mels - w, 0))
            S[f0:f0 + w, :] = 0.0
        for _ in range(random.randint(1, 2)):
            w = random.randint(6, 24)
            t0 = random.randint(0, max(T - w, 0))
            S[:, t0:t0 + w] = 0.0
        return S

    def __getitem__(self, i):
        y = self.waves[i]
        if self.train:
            y = self._augment_wave(self._crop(y))
            S = self._spec_augment(logmel(y))
        else:
            S = logmel(best_window(y))
        return torch.from_numpy(S).unsqueeze(0), torch.tensor(self.labels[i], dtype=torch.long)
