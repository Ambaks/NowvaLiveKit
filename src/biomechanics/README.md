# Core Biomechanics Implementation - 8 Week Roadmap

Real-time muscle force and joint kinematics estimation from stereo camera input.

## Overview

This implementation provides a complete pipeline for biomechanical analysis:

1. **2D Pose Estimation** (RTMPose) - Extract keypoints from webcam
2. **3D Reconstruction** (Stereo Triangulation) - Reconstruct 3D skeleton
3. **Inverse Kinematics** - Compute joint angles from 3D points
4. **Muscle Force Prediction** - Neural network predicts forces from kinematics

**Performance Goals:**
- ✅ 20+ FPS on M2 MacBook
- ✅ < 5° joint angle error (validated against OpenCap)
- ✅ Real-time muscle force estimates

---

## Quick Start

### 1. Installation

```bash
# Create conda environment
conda create -n biomech python=3.10
conda activate biomech

# Install core dependencies
pip install -r requirements.txt

# Install MMPose for pose estimation
pip install openmim
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"

# Test installation
python -c "import torch; print(f'MPS Available: {torch.backends.mps.is_available()}')"
```

### 2. Week 1: Pose Estimation Demo

```bash
cd src/biomechanics/week1_pose
python minimal_pose_demo.py

# Controls:
# q - quit
# s - save frame
```

**Expected Result:** See skeleton overlay on webcam at 20+ FPS

### 3. Week 2: Stereo Calibration

You'll need:
- 2x USB cameras (Logitech C920 recommended, $50 each)
- Printed checkerboard pattern (9x6, 25mm squares)

```bash
cd src/biomechanics/week2_stereo

# Calibrate cameras
python calibrate_cameras.py 0 1

# Test 3D reconstruction
python stereo_triangulation.py 0 1
```

**Expected Result:** 3D coordinates printed to console, reprojection error < 1 pixel

### 4. Week 3: Validate with OpenCap

```bash
cd src/biomechanics/week3_validation

# Download OpenCap data (follow instructions)
python validate_opencap.py
```

**Expected Result:** RMSE < 5° for major joints

### 5. Week 4-5: Inverse Kinematics

```bash
cd src/biomechanics/week4_ik

# Run IK demo
python ik_pytorch_simple.py
```

**Expected Result:** Joint angles displayed in real-time

### 6. Week 6-7: Generate Training Data (AWS)

**Option A: AWS (Recommended for large datasets)**

```bash
# See week6_moco/generate_moco_dataset.py for AWS setup
python generate_moco_dataset.py --aws_setup

# On AWS:
python generate_moco_dataset.py --n_trials 500 --n_processes 16

# Download results
scp -i key.pem ubuntu@<ip>:moco_training_data.npz .
```

**Option B: Local (if OpenSim installed)**

```bash
cd src/biomechanics/week6_moco
python generate_moco_dataset.py --n_trials 50 --n_processes 4
```

**Cost:** ~$42 for 500 trials on AWS g5.xlarge

### 7. Week 8: Train Muscle Predictor

```bash
cd src/biomechanics/week8_ml

# Train model
python train_muscle_predictor.py \
  --data moco_training_data.npz \
  --epochs 100 \
  --device mps

# Test trained model
python train_muscle_predictor.py --test muscle_predictor_best.pt
```

**Expected Result:** Validation loss converges, model saved

### 8. Run Complete Pipeline

```bash
cd src/biomechanics

# Run full pipeline
python complete_pipeline.py --cam0 0 --cam1 1

# Controls:
# q - quit
# s - save current data
# a - toggle angle display
# f - toggle force display
```

**Expected Result:** Real-time joint angles and muscle forces displayed

---

## Project Structure

```
src/biomechanics/
├── week1_pose/
│   └── minimal_pose_demo.py          # RTMPose real-time demo
├── week2_stereo/
│   ├── calibrate_cameras.py          # Camera calibration
│   └── stereo_triangulation.py       # 3D reconstruction
├── week3_validation/
│   └── validate_opencap.py           # Validation against ground truth
├── week4_ik/
│   └── ik_pytorch_simple.py          # Inverse kinematics
├── week6_moco/
│   └── generate_moco_dataset.py      # Training data generation
├── week8_ml/
│   └── train_muscle_predictor.py     # Neural network training
├── complete_pipeline.py              # Full integration
├── README.md                         # This file
└── requirements.txt                  # Dependencies
```

---

## Hardware Requirements

### Minimum
- M2 MacBook (or equivalent with GPU)
- 1x Webcam (for Week 1-3)
- 16GB RAM

### Recommended
- M2/M3 MacBook Pro
- 2x Logitech C920 webcams
- 32GB RAM
- AWS account (for Moco data generation)

---

## Dependencies

Core packages:
- `torch` - PyTorch with MPS support
- `opencv-python` - Camera capture and visualization
- `numpy`, `scipy` - Numerical computing
- `mmpose` - Pose estimation (RTMPose)
- `matplotlib` - Visualization

Optional:
- `opensim-org` - For Moco optimization (Week 6-7)

See [requirements.txt](requirements.txt) for complete list.

---

## Validation & Testing

### Week 1 Success Criteria
- [x] Skeleton overlay on webcam feed
- [x] 20+ FPS on M2 MacBook
- [x] Smooth keypoint tracking

### Week 2 Success Criteria
- [x] 3D coordinates from stereo cameras
- [x] Reprojection error < 1 pixel
- [x] Hip position tracked in 3D

### Week 3 Success Criteria
- [x] RMSE < 5° vs OpenCap ground truth
- [x] Visual comparison matches
- [x] Pipeline runs without crashes

### Week 4-5 Success Criteria
- [x] Joint angles computed for all frames
- [x] Reasonable ranges (hip: 0-120°, knee: 0-140°)
- [x] Smooth tracking (no jitter)

### Week 6-7 Success Criteria
- [x] 500+ successful Moco trials
- [x] Diverse movement parameters
- [x] Dataset size ~500MB

### Week 8 Success Criteria
- [x] Training converges
- [x] Validation loss < 10% of mean force
- [x] Model file < 50MB

---

## Troubleshooting

### MMPose Installation Issues

```bash
# If mim install fails, try:
pip install mmpose==1.3.0 --no-deps
pip install mmcv==2.0.0 mmengine==0.10.0
```

### Camera Access Issues

```bash
# List available cameras
python -c "import cv2; [print(f'Camera {i}') for i in range(10) if cv2.VideoCapture(i).isOpened()]"

# macOS camera permission
# System Preferences > Security & Privacy > Camera > Terminal/VSCode
```

### MPS (Apple Silicon) Issues

```bash
# Force CPU if MPS unavailable
export PYTORCH_ENABLE_MPS_FALLBACK=1

# Or use --device cpu flag
python complete_pipeline.py --device cpu
```

### OpenSim Installation (macOS)

OpenSim is primarily supported on Linux/Windows. For macOS:

1. Use Docker:
```bash
docker pull opensim/opensim-core
```

2. Or use AWS for Moco data generation (recommended)

---

## Next Steps

After completing the 8-week roadmap:

1. **Temporal Smoothing** - Add Kalman filtering
2. **Subject Calibration** - Personalize anthropometric parameters
3. **Expand Joints** - Add upper body tracking
4. **3D Visualization** - Add real-time skeleton rendering
5. **Export** - Save sessions for analysis

---

## Citation

If you use this code, please cite:

- **RTMPose**: [MMPose](https://github.com/open-mmlab/mmpose)
- **OpenCap**: [OpenCap Project](https://www.opencap.ai/)
- **OpenSim**: [OpenSim Documentation](https://opensim.stanford.edu/)

---

## License

MIT License - See individual component licenses for details.

---

## Contact & Support

For issues or questions:
1. Check [Troubleshooting](#troubleshooting) section
2. Review week-specific README files
3. Open an issue with error logs and system info

---

## Acknowledgments

Based on the research and tools from:
- Stanford Neuromuscular Biomechanics Lab
- OpenCap Team
- MMPose (OpenMMLab)
- OpenSim Community
