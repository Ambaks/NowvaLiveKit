# Quick Start Guide - Biomechanics Pipeline

Get up and running in 30 minutes with the core pipeline.

---

## Step 1: Environment Setup (5 minutes)

```bash
# Navigate to project
cd /Users/naiahoard/NowvaLiveKit

# Create conda environment
conda create -n biomech python=3.10
conda activate biomech

# Install dependencies
pip install torch torchvision torchaudio
pip install opencv-python numpy scipy pandas matplotlib tqdm

# Install MMPose
pip install openmim
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"

# Verify installation
python -c "import torch; print(f'✓ PyTorch: {torch.__version__}')"
python -c "import cv2; print(f'✓ OpenCV: {cv2.__version__}')"
python -c "import torch; print(f'✓ MPS Available: {torch.backends.mps.is_available()}')"
```

---

## Step 2: Test Basic Pose Estimation (5 minutes)

```bash
cd src/biomechanics/week1_pose

# Run demo (press 'q' to quit)
python minimal_pose_demo.py
```

**What you should see:**
- Webcam feed with skeleton overlay
- FPS counter showing 20+ FPS
- Smooth tracking as you move

**Troubleshooting:**
- Camera not found? Check camera permissions in System Preferences
- Low FPS? Try reducing resolution or using CPU device
- Import errors? Reinstall mmpose: `mim install mmpose`

---

## Step 3: Calibrate Stereo Cameras (10 minutes)

**Prerequisites:**
- 2 USB webcams OR use 1 webcam for testing
- Printed checkerboard (9x6, 25mm squares)
  - Download: https://markhedleyjones.com/projects/calibration-checkerboard-collection

```bash
cd ../week2_stereo

# If you have 2 cameras:
python calibrate_cameras.py 0 2

# If you only have 1 camera (for testing):
python minimal_pose_demo.py  # Use Week 1 demo

# After calibration (if using 2 cameras):
python stereo_triangulation.py 0 2
```

**What you should see:**
- Checkerboard detection with green corners
- After 20 images: calibration results
- 3D reconstruction: hip positions in 3D space

---

## Step 4: Test Inverse Kinematics (5 minutes)

```bash
cd ../week4_ik

# Test with dummy data
python ik_pytorch_simple.py

# If you have stereo cameras calibrated:
# Enter 'y' when prompted to run live demo
```

**What you should see:**
- Joint angles computed from 3D keypoints
- Real-time angle display and visualization bars
- Smooth angle tracking

---

## Step 5: Run Complete Pipeline (5 minutes)

```bash
cd ..

# Single camera mode (no muscle forces)
python complete_pipeline.py --cam0 0 --cam1 0

# Stereo camera mode (if calibrated)
python complete_pipeline.py --cam0 0 --cam1 1
```

**Controls:**
- `q` - Quit
- `s` - Save current data
- `a` - Toggle angle display
- `f` - Toggle force display

**What you should see:**
- Dual camera view (or single if testing)
- Real-time joint angles
- FPS counter
- Muscle forces (if model trained)

---

## What's Next?

### Short Term (Hours)
1. ✅ **Improve calibration** - Capture more checkerboard images from different angles
2. ✅ **Test different poses** - Squats, lunges, walking
3. ✅ **Record data** - Press 's' to save sessions

### Medium Term (Days)
4. **Validate accuracy** - Download OpenCap data and run validation
5. **Tune parameters** - Adjust smoothing, confidence thresholds
6. **Single camera mode** - If you don't have stereo setup

### Long Term (Weeks)
7. **Generate training data** - Use AWS for Moco optimization
8. **Train muscle model** - Get real muscle force predictions
9. **Add features** - Kalman filtering, 3D visualization

---

## Common Issues & Solutions

### "No module named 'mmpose'"
```bash
pip install openmim
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"
```

### "Camera not found" or "Failed to grab frame"
```bash
# List available cameras
python -c "import cv2; [print(f'Camera {i}') for i in range(5) if cv2.VideoCapture(i).isOpened()]"

# On macOS: System Preferences > Security & Privacy > Camera
# Enable access for Terminal/VSCode
```

### "MPS backend not available"
```bash
# Use CPU instead
python complete_pipeline.py --device cpu

# Or set fallback
export PYTORCH_ENABLE_MPS_FALLBACK=1
```

### Low FPS (<15 FPS)
1. Reduce camera resolution in code (640x480 instead of 1280x720)
2. Use CPU device if MPS is slow
3. Close other applications
4. Increase `threshold` in triangulation to process fewer points

### "Checkerboard not detected"
1. Ensure good lighting
2. Print checkerboard on flat, rigid surface
3. Fill entire camera view with checkerboard
4. Try different angles and distances

---

## Testing Without Hardware

### No Camera?
Use video file instead:

```python
# Edit minimal_pose_demo.py
# Replace:
cap = cv2.VideoCapture(0)
# With:
cap = cv2.VideoCapture('path/to/video.mp4')
```

### No Second Camera?
Use the same camera for both views (for testing code):

```bash
python complete_pipeline.py --cam0 0 --cam1 0
```

Note: This won't give accurate 3D reconstruction, but tests the pipeline.

---

## Performance Benchmarks

### Expected Performance (M2 MacBook)
- Week 1 (Pose): 30-60 FPS
- Week 2 (Stereo): 20-30 FPS
- Week 4 (IK): 25-35 FPS
- Complete Pipeline: 20-25 FPS

### Optimization Tips
1. Use lower camera resolution (640x480)
2. Reduce smoothing window size
3. Increase confidence threshold
4. Use MPS device on Apple Silicon
5. Close background apps

---

## Data Collection Tips

### For Best Results
1. **Good Lighting** - Bright, even lighting
2. **Contrast** - Wear clothing that contrasts with background
3. **Camera Placement** - 2-3 meters away, at waist height
4. **Camera Angle** - Perpendicular to movement plane
5. **Calibration** - Recalibrate if cameras move

### Session Recording
```bash
# Save data during session
# Press 's' in complete_pipeline.py

# Data saved to: biomech_data_<timestamp>.npz
# Contains: joint_angles, muscle_forces, points_3d
```

### Loading Saved Data
```python
import numpy as np

data = np.load('biomech_data_1234567890.npz', allow_pickle=True)
joint_angles = data['joint_angles']
muscle_forces = data['muscle_forces']
points_3d = data['points_3d']
```

---

## Next Steps

1. Read [README.md](README.md) for full 8-week roadmap
2. Check individual week folders for detailed docs
3. Join discussions on GitHub for help
4. Share your results and improvements!

---

## Success Checklist

After completing this quick start, you should have:

- [x] ✅ Pose estimation working at 20+ FPS
- [x] ✅ Camera calibration completed (if 2 cameras)
- [x] ✅ 3D reconstruction working (if 2 cameras)
- [x] ✅ Joint angles displayed in real-time
- [x] ✅ Complete pipeline running

**Estimated Time:** 30 minutes (with 2 cameras) or 15 minutes (single camera testing)

**Ready for More?** See [README.md](README.md) for the full 8-week implementation plan.
