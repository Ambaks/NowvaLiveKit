#!/usr/bin/env python3
"""
Offline Training Script for BiLSTM Rep Counter

Usage:
    python scripts/train_bilstm.py --data data/dataset.npz --epochs 80
    python scripts/train_bilstm.py --data data/dataset.npz --epochs 80 --batch-size 32 --lr 1e-3

Expected dataset format (npz):
    sequences: np.ndarray (N, seq_len, feature_dim)   float32
    labels:    np.ndarray (N, seq_len)                 int64 (0=standing..4=deep)
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

# Allow imports from src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from biomechanics.ml.bilstm_model import BiLSTMRepModel


def parse_args():
    p = argparse.ArgumentParser(description="Train BiLSTM rep counter")
    p.add_argument("--data", required=True, help="Path to dataset.npz")
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--hidden-dim", type=int, default=128)
    p.add_argument("--patience", type=int, default=8, help="Early stopping patience")
    p.add_argument("--val-split", type=float, default=0.15)
    p.add_argument("--output-dir", type=str, default="models")
    p.add_argument("--device", type=str, default="cpu")
    return p.parse_args()


def load_dataset(path: str, val_split: float):
    data = np.load(path)
    sequences = data["sequences"].astype(np.float32)  # (N, seq_len, feat)
    labels = data["labels"].astype(np.int64)           # (N, seq_len)

    num_classes = int(labels.max()) + 1

    n = len(sequences)
    idx = np.random.permutation(n)
    split = int(n * (1 - val_split))

    train_idx, val_idx = idx[:split], idx[split:]

    train_ds = TensorDataset(
        torch.tensor(sequences[train_idx]),
        torch.tensor(labels[train_idx]),
    )
    val_ds = TensorDataset(
        torch.tensor(sequences[val_idx]),
        torch.tensor(labels[val_idx]),
    )
    return train_ds, val_ds, sequences.shape[-1], num_classes


def evaluate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = criterion(logits.reshape(-1, logits.shape[-1]), y.reshape(-1))
            total_loss += loss.item() * x.size(0)

            preds = logits.argmax(dim=-1)
            correct += (preds == y).sum().item()
            total += y.numel()

    avg_loss = total_loss / len(loader.dataset)
    accuracy = correct / total if total > 0 else 0.0
    return avg_loss, accuracy


def per_class_accuracy(model, loader, num_classes, device):
    """Compute per-class accuracy on a data loader."""
    class_correct = np.zeros(num_classes)
    class_total = np.zeros(num_classes)

    model.eval()
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            preds = model(x).argmax(dim=-1)
            for c in range(num_classes):
                mask = (y == c)
                class_total[c] += mask.sum().item()
                class_correct[c] += ((preds == y) & mask).sum().item()

    return class_correct, class_total


def train(args):
    train_ds, val_ds, feature_dim, num_classes = load_dataset(args.data, args.val_split)
    print(f"Train: {len(train_ds)} | Val: {len(val_ds)} | Features: {feature_dim} | Classes: {num_classes}")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size)

    device = torch.device(args.device)
    model = BiLSTMRepModel(
        input_dim=feature_dim,
        hidden_dim=args.hidden_dim,
        num_classes=num_classes,
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    best_val_loss = float("inf")
    patience_counter = 0
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0

        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = criterion(logits.reshape(-1, logits.shape[-1]), y.reshape(-1))

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * x.size(0)

        train_loss = epoch_loss / len(train_ds)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)

        print(
            f"Epoch {epoch:3d}/{args.epochs} | "
            f"Train Loss: {train_loss:.4f} | "
            f"Val Loss: {val_loss:.4f} | "
            f"Val Acc: {val_acc:.4f}"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            checkpoint = {
                "model_state_dict": model.state_dict(),
                "model_config": {
                    "input_dim": feature_dim,
                    "hidden_dim": args.hidden_dim,
                    "num_classes": num_classes,
                },
                "epoch": epoch,
                "val_loss": val_loss,
                "val_acc": val_acc,
            }
            torch.save(checkpoint, output_dir / "bilstm_rep_counter.pt")
            print(f"  -> Saved best model (val_loss={val_loss:.4f})")
        else:
            patience_counter += 1
            if patience_counter >= args.patience:
                print(f"Early stopping at epoch {epoch}")
                break

    # Per-class accuracy report
    print(f"\nTraining complete. Best val loss: {best_val_loss:.4f}")

    # Load best checkpoint for per-class report
    best_ckpt = torch.load(output_dir / "bilstm_rep_counter.pt", map_location=device, weights_only=False)
    model.load_state_dict(best_ckpt["model_state_dict"])

    class_correct, class_total = per_class_accuracy(model, val_loader, num_classes, device)
    class_names = {0: "Standing", 1: "Quarter", 2: "Half", 3: "Parallel", 4: "Deep"}
    print("\nPer-class accuracy (validation):")
    for c in range(num_classes):
        name = class_names.get(c, f"Class {c}")
        if class_total[c] > 0:
            acc = class_correct[c] / class_total[c]
            print(f"  {c} ({name:>9s}): {acc:.4f}  ({int(class_correct[c])}/{int(class_total[c])})")
        else:
            print(f"  {c} ({name:>9s}): N/A (no samples)")

    print(f"\nModel saved to {output_dir / 'bilstm_rep_counter.pt'}")


if __name__ == "__main__":
    train(parse_args())
