"""
BiLSTM Repetition Counting Model

2-layer bidirectional LSTM that outputs per-frame depth class logits.
Pure PyTorch — no dependency on the rest of the biomechanics package.
"""

import torch
import torch.nn as nn


class BiLSTMRepModel(nn.Module):
    """
    Bidirectional LSTM for per-frame squat depth classification.

    Architecture:
        Input  (batch, seq_len, input_dim)
        → 2-layer BiLSTM (hidden=128)
        → FC 256→64 → ReLU → Dropout → FC 64→num_classes
        Output (batch, seq_len, num_classes)  per-frame logits
    """

    def __init__(
        self,
        input_dim: int = 14,
        hidden_dim: int = 128,
        num_layers: int = 2,
        num_classes: int = 5,
        dropout: float = 0.2,
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.classifier = nn.Sequential(
            nn.Linear(hidden_dim * 2, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, input_dim)

        Returns:
            (batch, seq_len, num_classes) raw logits
        """
        lstm_out, _ = self.lstm(x)           # (batch, seq, hidden*2)
        logits = self.classifier(lstm_out)   # (batch, seq, num_classes)
        return logits

    @classmethod
    def from_checkpoint(cls, path: str, device: str = "cpu", **kwargs) -> "BiLSTMRepModel":
        """
        Load a trained model from a checkpoint file.

        The checkpoint should contain either a raw state_dict or a dict with
        a ``model_state_dict`` key plus optional ``model_config``.
        """
        checkpoint = torch.load(path, map_location=device, weights_only=False)

        if isinstance(checkpoint, dict) and "model_config" in checkpoint:
            config = dict(checkpoint["model_config"])
            # Infer num_classes from state dict if not in config (backward compat)
            if "num_classes" not in config:
                state = checkpoint.get("model_state_dict", checkpoint)
                if "classifier.3.weight" in state:
                    config["num_classes"] = state["classifier.3.weight"].shape[0]
            model = cls(**config)
        else:
            model = cls(**kwargs)

        state = checkpoint.get("model_state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
        model.load_state_dict(state)
        model.to(device)
        model.eval()
        return model
