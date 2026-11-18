import torch
import torch.nn as nn


class CryCNNGRUModel(nn.Module):
    """CNN (spectral patterns) -> BiGRU (temporal evolution) -> attention pooling.

    Changes vs. the original:
      * attention pooling over ALL time steps (the old code used only the last GRU
        step, which for the backward direction has seen just one frame)
      * a linear projection before the GRU (2048 -> 128 inputs) so the model is far
        smaller, which matters with a few hundred training clips
      * features()/classify() split so Grad-CAM can be computed for explanations
      * the attention weights are returned so we can say WHICH moments mattered
    """

    def __init__(self, num_classes=5, n_mels=128, proj_dim=128, gru_hidden=96, dropout=0.4):
        super().__init__()
        assert n_mels % 8 == 0, "n_mels must be divisible by 8"

        def block(cin, cout, pool):
            return nn.Sequential(
                nn.Conv2d(cin, cout, 3, padding=1, bias=False),
                nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                nn.Dropout2d(0.1), nn.MaxPool2d(pool))

        self.block1 = block(1, 32, 2)
        self.block2 = block(32, 64, 2)
        self.block3 = block(64, 128, (2, 1))
        self.freq_out = n_mels // 8
        self.proj = nn.Sequential(nn.Linear(128 * self.freq_out, proj_dim), nn.ReLU(inplace=True), nn.Dropout(dropout))
        self.gru = nn.GRU(proj_dim, gru_hidden, batch_first=True, bidirectional=True)
        self.attn = nn.Sequential(nn.Linear(2 * gru_hidden, 64), nn.Tanh(), nn.Linear(64, 1))
        self.head = nn.Sequential(
            nn.Dropout(dropout), nn.Linear(2 * gru_hidden, 64), nn.ReLU(inplace=True),
            nn.Dropout(dropout), nn.Linear(64, num_classes))

    def features(self, x):
        """x: (B, 1, n_mels, T) -> (B, 128, n_mels/8, T/4)"""
        return self.block3(self.block2(self.block1(x)))

    def classify(self, feat, return_attention=False):
        b, c, h, w = feat.shape
        seq = feat.permute(0, 3, 1, 2).reshape(b, w, c * h)
        out, _ = self.gru(self.proj(seq))
        a = torch.softmax(self.attn(out).squeeze(-1), dim=1)          # (B, w)
        logits = self.head((out * a.unsqueeze(-1)).sum(dim=1))
        return (logits, a) if return_attention else logits

    def forward(self, x, return_attention=False):
        return self.classify(self.features(x), return_attention)


DEFAULT_ARCH = dict(num_classes=5, n_mels=128, proj_dim=128, gru_hidden=96, dropout=0.4)
