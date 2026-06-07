# How to Run the Biomechanics Pipeline

Quick reference guide for running the complete implementation.

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Install Dependencies

```bash
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics

# Run automated setup
bash setup.sh
```

### Step 2: Activate Environment

```bash
conda activate biomech
```

### Step 3: Test Basic Pose

```bash
cd week1_pose
python minimal_pose_demo.py
```

**Press 'q' to quit when done**

---

## 📋 Week-by-Week Instructions

### Week 1: Pose Estimation ✅

```bash
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics/week1_pose

# Run the demo
python minimal_pose_demo.py

# Optional: specify camera ID
python minimal_pose_demo.py 0  # Use camera 0
```

**What you'll see:**
- Your webcam feed with skeleton overlay
- FPS counter (should be 20+)
- Green circles on joints
- Yellow lines connecting joints

**Controls:**
- `q` - Quit
- `s` - Save screenshot

---

### Week 2: Stereo Calibration ✅

#### Part A: Calibrate Cameras

```bash
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics/week2_stereo

# Calibrate camera 0 and camera 1
python calibrate_cameras.py 0 1

# Follow on-screen instructions:
# 1. Move checkerboard to different positions
# 2. Press SPACE when checkerboard is detected
# 3. Capture 20 images per camera
# 4. Wait for calibration to complete
```

**What you need:**
- 2 USB webcams
- Printed checkerboard pattern (9x6, 25mm squares)
- Download pattern: https://markhedleyjones.com/projects/calibration-checkerboard-collection

**Output files:**
- `camera_0_calibration.json`
- `camera_1_calibration.json`
- `stereo_calibration.npz`

#### Part B: Test 3D Reconstruction

```bash
# After calibration is complete
python stereo_triangulation.py 0 1
```

**What you'll see:**
- Dual camera view side-by-side
- 3D coordinates printed to console
- Number of reconstructed points

**Controls:**
- `q` - Quit
- `s` - Save current 3D points

---

### Week 3: Validation ✅

```bash
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics/week3_validation

# First, download OpenCap data
python validate_opencap.py
# Follow instructions to download sample data

# After downloading data:
python validate_opencap.py
```

**What you'll get:**
- Validation plots comparing your pipeline to ground truth
- RMSE metrics for each joint
- `validation_results.png` output

---

### Week 4: Inverse Kinematics ✅

```bash
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics/week4_ik

# Test with dummy data
python ik_pytorch_simple.py

# When prompted, type 'y' to run live demo with cameras
```

**What you'll see:**
- Joint angles computed in real-time
- Angle bars showing current values
- Smooth tracking with temporal filtering

---

### Week 6-7: Generate Training Data ⚙️

#### Option A: AWS (Recommended for 500+ trials)

```bash
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics/week6_moco

# Show AWS setup instructions
python generate_moco_dataset.py --aws_setup

# Follow instructions to:
# 1. Launch EC2 instance
# 2. SSH and install OpenSim
# 3. Run generation script on cloud
# 4. Download results
```

#### Option B: Local (If OpenSim installed)

```bash
# Generate small dataset locally
python generate_moco_dataset.py --n_trials 50 --n_processes 4

# Verify dataset
python generate_moco_dataset.py --verify moco_training_data.npz
```

---

### Week 8: Train Muscle Predictor 🧠

```bash
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics/week8_ml

# Train the model (requires moco_training_data.npz from Week 6)
python train_muscle_predictor.py \
  --data ../week6_moco/moco_training_data.npz \
  --epochs 100 \
  --batch_size 32 \
  --device mps

# This will:
# - Load training data
# - Train for 100 epochs (~10-30 minutes)
# - Save best model to muscle_predictor_best.pt
# - Create training_history.png plot
```

**Test trained model:**

```bash
python train_muscle_predictor.py --test muscle_predictor_best.pt
```

---

### Complete Pipeline 🎯

```bash
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics

# Run complete pipeline
python complete_pipeline.py --cam0 0 --cam1 1

# Options:
# --cam0 0 --cam1 0    # Single camera test mode
# --model path.pt      # Custom muscle predictor
# --calibration cal.npz # Custom calibration
```

**What you'll see:**
- Dual camera view
- Real-time joint angles
- Muscle forces (if model trained)
- FPS counter

**Controls:**
- `q` - Quit
- `s` - Save current data (creates biomech_data_*.npz)
- `a` - Toggle angle display
- `f` - Toggle force display

---

## 🔧 Common Workflows

### Workflow 1: Quick Test (No Hardware)

```bash
conda activate biomech
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics/week1_pose
python minimal_pose_demo.py
```

### Workflow 2: Single Camera Mode

```bash
conda activate biomech
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics
python complete_pipeline.py --cam0 0 --cam1 0
```

### Workflow 3: Full Stereo Pipeline

```bash
conda activate biomech
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics

# 1. Calibrate (once)
cd week2_stereo
python calibrate_cameras.py 0 1

# 2. Run complete pipeline
cd ..
python complete_pipeline.py --cam0 0 --cam1 1
```

### Workflow 4: Record Session

```bash
conda activate biomech
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics
python complete_pipeline.py --cam0 0 --cam1 1

# During session:
# - Press 's' to save data
# - Files saved as biomech_data_<timestamp>.npz
```

### Workflow 5: Analyze Saved Data

```python
# In Python or Jupyter
import numpy as np
import matplotlib.pyplot as plt

# Load saved session
data = np.load('biomech_data_1234567890.npz', allow_pickle=True)

# Extract data
joint_angles = data['joint_angles'].item()
muscle_forces = data['muscle_forces']
points_3d = data['points_3d']

# Plot knee angle over time
plt.plot(joint_angles['knee_angle_l'])
plt.xlabel('Frame')
plt.ylabel('Knee Angle (degrees)')
plt.show()
```

---

## 📦 Installation Commands Reference

### Full Installation

```bash
# Create environment
conda create -n biomech python=3.10
conda activate biomech

# Install dependencies
pip install torch torchvision torchaudio
pip install opencv-python numpy scipy pandas matplotlib tqdm
pip install openmim
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"

# Optional: Jupyter
pip install jupyter ipykernel
```

### Minimal Installation (Testing Only)

```bash
conda create -n biomech python=3.10
conda activate biomech
pip install torch opencv-python numpy
```

---

## 🐛 Troubleshooting

### Camera Not Found

```bash
# List available cameras
python -c "import cv2; [print(f'Camera {i}') for i in range(5) if cv2.VideoCapture(i).isOpened()]"

# macOS: Grant camera permission
# System Preferences > Security & Privacy > Camera > Terminal
```

### Import Errors

```bash
# Verify installation
python -c "import torch; print('PyTorch:', torch.__version__)"
python -c "import cv2; print('OpenCV:', cv2.__version__)"
python -c "import mmpose; print('MMPose:', mmpose.__version__)"

# Reinstall if needed
pip uninstall mmpose mmcv mmengine
mim install mmengine "mmcv>=2.0.0" "mmpose>=1.0.0"
```

### Low FPS

```bash
# Try CPU device
python minimal_pose_demo.py  # Edit code to use device='cpu'

# Or reduce camera resolution
# Edit code: cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
```

---

## 📁 File Structure Reference

```
/Users/naiahoard/NowvaLiveKit/src/biomechanics/
├── setup.sh                   # Run this first
├── requirements.txt           # Dependencies
├── complete_pipeline.py       # Main pipeline
│
├── week1_pose/
│   └── minimal_pose_demo.py   # Start here
│
├── week2_stereo/
│   ├── calibrate_cameras.py   # Step 1: Calibrate
│   └── stereo_triangulation.py # Step 2: Test 3D
│
├── week3_validation/
│   └── validate_opencap.py    # Validation
│
├── week4_ik/
│   └── ik_pytorch_simple.py   # IK solver
│
├── week6_moco/
│   └── generate_moco_dataset.py # Training data
│
└── week8_ml/
    └── train_muscle_predictor.py # Train model
```

---

## ⏱️ Time Estimates

| Task | Time | Dependencies |
|------|------|--------------|
| Setup environment | 10 min | Internet |
| Week 1 demo | 2 min | Webcam |
| Calibrate cameras | 15 min | 2 cameras, checkerboard |
| 3D reconstruction | 5 min | Calibration done |
| IK testing | 5 min | Stereo working |
| Generate 50 trials | 2-4 hours | OpenSim installed |
| Train model | 20 min | Training data ready |
| Complete pipeline | 2 min | All above done |

**Total to complete pipeline:** 3-5 hours (with hardware)

---

## 🎯 Success Checklist

After running everything, you should have:

- [x] ✅ Pose estimation working (Week 1)
- [x] ✅ Cameras calibrated (Week 2)
- [x] ✅ 3D reconstruction working (Week 2)
- [x] ✅ Joint angles computed (Week 4)
- [x] ✅ Training data generated (Week 6) - Optional
- [x] ✅ Model trained (Week 8) - Optional
- [x] ✅ Complete pipeline running

**Minimum for testing:** Just Week 1 ✅
**Full stereo system:** Weeks 1-4 ✅
**With muscle forces:** Weeks 1-8 ✅

---

## 📞 Getting Help

1. Check error message carefully
2. Verify environment: `conda activate biomech`
3. Test imports individually
4. Check camera access permissions
5. Review [INSTALLATION.md](src/biomechanics/INSTALLATION.md)
6. See [README.md](src/biomechanics/README.md) for details

---

**Ready to start? Run:**

```bash
cd /Users/naiahoard/NowvaLiveKit/src/biomechanics
bash setup.sh
```

Then follow the prompts! 🚀
