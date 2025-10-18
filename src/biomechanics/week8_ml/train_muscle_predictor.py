"""
Week 8: Train Muscle Force Predictor
Neural network to predict muscle forces from kinematics

Success Criteria:
- Training converges (loss decreases)
- Validation loss < 10% of mean force magnitude
- Model saved and ready for inference
"""

import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import Dataset, DataLoader
import matplotlib.pyplot as plt
import os


class MocoDataset(Dataset):
    """Dataset from Moco trials"""

    def __init__(self, data_file='moco_training_data.npz'):
        """
        Load Moco dataset

        Args:
            data_file: Path to npz file from Week 6
        """
        if not os.path.exists(data_file):
            raise FileNotFoundError(
                f"Dataset not found: {data_file}\n"
                f"Generate it first using week6_moco/generate_moco_dataset.py"
            )

        data = np.load(data_file, allow_pickle=True)

        self.kinematics = data['kinematics']
        self.muscle_forces = data['muscle_forces']

        print(f"Loaded dataset: {data_file}")
        print(f"  Trials: {len(self.kinematics)}")
        print(f"  Kinematics shape: {self.kinematics[0].shape}")
        print(f"  Muscle forces shape: {self.muscle_forces[0].shape}")

    def __len__(self):
        return len(self.kinematics)

    def __getitem__(self, idx):
        return {
            'kinematics': torch.from_numpy(self.kinematics[idx]).float(),
            'muscle_forces': torch.from_numpy(self.muscle_forces[idx]).float()
        }


class MuscleForcePredictor(nn.Module):
    """Feedforward network for muscle force prediction"""

    def __init__(self, n_joints=6, n_muscles=15, hidden_dims=[256, 256, 128]):
        """
        Initialize muscle force predictor

        Args:
            n_joints: Number of joints
            n_muscles: Number of muscles
            hidden_dims: List of hidden layer dimensions
        """
        super().__init__()

        # Input: joint angles, velocities, accelerations
        input_dim = n_joints * 3

        layers = []

        # Input layer
        layers.extend([
            nn.Linear(input_dim, hidden_dims[0]),
            nn.ReLU(),
            nn.BatchNorm1d(hidden_dims[0]),
            nn.Dropout(0.2)
        ])

        # Hidden layers
        for i in range(len(hidden_dims) - 1):
            layers.extend([
                nn.Linear(hidden_dims[i], hidden_dims[i+1]),
                nn.ReLU(),
                nn.BatchNorm1d(hidden_dims[i+1]),
                nn.Dropout(0.2)
            ])

        # Output layer
        layers.extend([
            nn.Linear(hidden_dims[-1], n_muscles),
            nn.Softplus()  # Ensure positive forces
        ])

        self.network = nn.Sequential(*layers)

        # Store dimensions
        self.n_joints = n_joints
        self.n_muscles = n_muscles

    def forward(self, x):
        """
        Forward pass

        Args:
            x: (batch, n_joints*3) kinematics tensor

        Returns:
            (batch, n_muscles) predicted forces
        """
        return self.network(x)


def train_model(
    data_file='moco_training_data.npz',
    epochs=100,
    batch_size=32,
    learning_rate=1e-3,
    device='mps',
    save_path='muscle_predictor_best.pt'
):
    """
    Train muscle force predictor

    Args:
        data_file: Path to training data
        epochs: Number of training epochs
        batch_size: Batch size
        learning_rate: Learning rate
        device: 'mps', 'cuda', or 'cpu'
        save_path: Where to save best model

    Returns:
        Trained model
    """
    print(f"\n{'='*70}")
    print("Training Muscle Force Predictor")
    print(f"{'='*70}\n")

    # Load dataset
    dataset = MocoDataset(data_file)

    # Split train/val
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(
        dataset, [train_size, val_size]
    )

    print(f"Train samples: {train_size}")
    print(f"Val samples: {val_size}\n")

    # Create data loaders
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=0  # Set to 0 for compatibility
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        num_workers=0
    )

    # Infer dimensions from data
    sample_kin = dataset[0]['kinematics']
    sample_forces = dataset[0]['muscle_forces']

    # Flatten if needed
    if len(sample_kin.shape) > 1:
        input_dim = sample_kin.flatten().shape[0]
        n_joints = input_dim // 3  # Assuming angles, velocities, accelerations
    else:
        input_dim = sample_kin.shape[0]
        n_joints = input_dim // 3

    if len(sample_forces.shape) > 1:
        n_muscles = sample_forces.flatten().shape[0]
    else:
        n_muscles = sample_forces.shape[0]

    print(f"Model architecture:")
    print(f"  Input joints: {n_joints}")
    print(f"  Output muscles: {n_muscles}\n")

    # Initialize model
    model = MuscleForcePredictor(n_joints=n_joints, n_muscles=n_muscles).to(device)

    # Optimizer and scheduler
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, epochs)

    # Loss function
    criterion = nn.MSELoss()

    # Training history
    history = {
        'train_loss': [],
        'val_loss': []
    }

    best_val_loss = float('inf')

    print("Starting training...\n")

    for epoch in range(epochs):
        # Train
        model.train()
        train_loss = 0
        n_batches = 0

        for batch in train_loader:
            kinematics = batch['kinematics'].to(device)
            forces = batch['muscle_forces'].to(device)

            # Flatten inputs if needed
            if len(kinematics.shape) > 2:
                kinematics = kinematics.view(kinematics.shape[0], -1)
            if len(forces.shape) > 2:
                forces = forces.view(forces.shape[0], -1)

            optimizer.zero_grad()
            pred_forces = model(kinematics)
            loss = criterion(pred_forces, forces)
            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            n_batches += 1

        avg_train_loss = train_loss / n_batches

        # Validate
        model.eval()
        val_loss = 0
        n_val_batches = 0

        with torch.no_grad():
            for batch in val_loader:
                kinematics = batch['kinematics'].to(device)
                forces = batch['muscle_forces'].to(device)

                # Flatten inputs if needed
                if len(kinematics.shape) > 2:
                    kinematics = kinematics.view(kinematics.shape[0], -1)
                if len(forces.shape) > 2:
                    forces = forces.view(forces.shape[0], -1)

                pred_forces = model(kinematics)
                loss = criterion(pred_forces, forces)
                val_loss += loss.item()
                n_val_batches += 1

        avg_val_loss = val_loss / n_val_batches

        # Update history
        history['train_loss'].append(avg_train_loss)
        history['val_loss'].append(avg_val_loss)

        # Print progress
        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(f"Epoch {epoch+1}/{epochs} - "
                  f"Train Loss: {avg_train_loss:.4f}, "
                  f"Val Loss: {avg_val_loss:.4f}")

        # Save best model
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_loss': best_val_loss,
                'n_joints': n_joints,
                'n_muscles': n_muscles
            }, save_path)

        scheduler.step()

    print(f"\n✓ Training complete!")
    print(f"  Best validation loss: {best_val_loss:.4f}")
    print(f"  Model saved to: {save_path}")

    # Plot training curves
    plot_training_history(history, 'training_history.png')

    return model


def plot_training_history(history, save_path):
    """Plot training and validation loss"""
    plt.figure(figsize=(10, 6))

    plt.plot(history['train_loss'], label='Train Loss', linewidth=2)
    plt.plot(history['val_loss'], label='Validation Loss', linewidth=2)

    plt.xlabel('Epoch', fontsize=12)
    plt.ylabel('Loss (MSE)', fontsize=12)
    plt.title('Training History', fontsize=14, fontweight='bold')
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)

    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"✓ Training plot saved to: {save_path}")
    plt.close()


def load_trained_model(checkpoint_path, device='mps'):
    """
    Load trained model from checkpoint

    Args:
        checkpoint_path: Path to saved checkpoint
        device: Device to load model on

    Returns:
        Loaded model
    """
    checkpoint = torch.load(checkpoint_path, map_location=device)

    model = MuscleForcePredictor(
        n_joints=checkpoint['n_joints'],
        n_muscles=checkpoint['n_muscles']
    ).to(device)

    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()

    print(f"✓ Loaded model from {checkpoint_path}")
    print(f"  Validation loss: {checkpoint['val_loss']:.4f}")
    print(f"  Epoch: {checkpoint['epoch']}")

    return model


def test_inference(model, device='mps'):
    """
    Test model inference with dummy data

    Args:
        model: Trained model
        device: Device
    """
    print("\nTesting inference...")

    # Create dummy input
    n_joints = model.n_joints
    dummy_kinematics = torch.randn(1, n_joints * 3).to(device)

    with torch.no_grad():
        forces = model(dummy_kinematics)

    print(f"Input shape: {dummy_kinematics.shape}")
    print(f"Output shape: {forces.shape}")
    print(f"Predicted forces (N): {forces.cpu().numpy()[0]}")
    print("✓ Inference working correctly")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Train muscle force predictor')
    parser.add_argument('--data', type=str, default='moco_training_data.npz',
                       help='Path to training data')
    parser.add_argument('--epochs', type=int, default=100,
                       help='Number of epochs')
    parser.add_argument('--batch_size', type=int, default=32,
                       help='Batch size')
    parser.add_argument('--lr', type=float, default=1e-3,
                       help='Learning rate')
    parser.add_argument('--device', type=str, default='mps',
                       choices=['mps', 'cuda', 'cpu'],
                       help='Device to train on')
    parser.add_argument('--output', type=str, default='muscle_predictor_best.pt',
                       help='Output model path')
    parser.add_argument('--test', type=str, default=None,
                       help='Test a trained model')

    args = parser.parse_args()

    if args.test:
        # Test mode
        model = load_trained_model(args.test, device=args.device)
        test_inference(model, device=args.device)
    else:
        # Training mode
        model = train_model(
            data_file=args.data,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            device=args.device,
            save_path=args.output
        )

        # Test inference
        test_inference(model, device=args.device)
