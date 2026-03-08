# Biomechanics Rep Counting Architecture
Location: src/biomechanics/

## Objective
Implement a squat repetition counting system matching the >99% accuracy pipeline:
Pose → Normalized Features → BiLSTM → Smoothing → FSM Counting

---

# 1. System Overview

Pipeline:

1. Pose Estimation (MediaPipe or equivalent)
2. Feature Extraction (angles + normalized distances)
3. Sequence Building (30-frame sliding windows)
4. BiLSTM Temporal Model
5. Probability Smoothing
6. Finite State Machine Rep Counter

---

# 2. Feature Engineering

## 2.1 Normalization Factor (Critical)

Compute distances in this exact order:

1. left_shoulder ↔ left_hip
2. right_shoulder ↔ right_hip
3. left_hip ↔ left_knee
4. right_hip ↔ right_knee

Select:

normalization_factor = first distance > 0  
Fallback = 0.5

All other distances and vertical differences are divided by this value.

This removes:
- Body size differences
- Camera zoom differences
- Scale variance

---

## 2.2 Joint Angles

Compute:
- Left knee angle
- Right knee angle
- Left hip angle
- Right hip angle

Using:

θ = arccos( (u · v) / (||u|| ||v||) )

Angles are inherently scale-invariant.

---

## 2.3 Final Per-Frame Feature Vector

Concatenate:

- 4 joint angles
- Normalized bone lengths
- Normalized vertical displacements
- Optional confidence values

Feature vector shape: (feature_dim,)

---

# 3. Sequence Modeling

## Windowing

Sequence length = 30 frames  
Stride = 5 frames  

Input shape to model:

(batch_size, 30, feature_dim)

---

# 4. BiLSTM Model

Architecture:

- 2-layer BiLSTM
- Hidden size: 128
- Dropout: 0.2
- Output: per-frame squat probability

Loss:
CrossEntropyLoss (frame-wise)

Optimizer:
Adam, lr = 1e-3

Epochs:
60–120 with early stopping

---

# 5. Postprocessing

## 5.1 Exponential Moving Average

p_t = α * p̂_t + (1 - α) * p_{t-1}

α = 0.2

---

## 5.2 Hysteresis Thresholding

Enter squat if prob > 0.6  
Exit squat if prob < 0.4  

Prevents flickering.

---

# 6. Finite State Machine

States:
UP
DOWN

Rep counted when:

UP → DOWN → UP

With constraints:
- Minimum duration: 12 frames
- Knee angle below threshold (e.g., < 90°)

---

# 7. Training Strategy

1. Train offline
2. Save model.pth
3. Load for inference only in production

Use subject-independent train/test splits.

---

# 8. Evaluation Metrics

Frame-level:
- Accuracy
- Precision
- Recall
- F1

Counting-level:
- MAE (|pred - true|)
- Exact count accuracy %

---

# 9. Deployment Notes

- Export to ONNX for production
- Keep pose estimation separate from inference model
- Use identical normalization in training and inference