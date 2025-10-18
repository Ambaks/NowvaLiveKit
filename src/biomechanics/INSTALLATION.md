# Installation Guide

Complete installation instructions for the Biomechanics Pipeline.

---

## Prerequisites

- macOS 12+ (for Apple Silicon MPS support) OR Linux/Windows
- Python 3.10
- Conda or Miniconda
- 16GB+ RAM recommended
- Webcam (2x cameras for full stereo pipeline)

---

## Method 1: Automated Setup (Recommended)

```bash
cd src/biomechanics

# Run setup script
bash setup.sh

# Follow prompts
```

The script will:
1. Create conda environment
2. Install all dependencies
3. Verify installation
4. Create necessary directories

---

## Method 2: Manual Installation

### Step 1: Create Environment

```bash
# Create conda environment
conda create -n biomech python=3.10
conda activate biomech
```

### Step 2: Install PyTorch

**For Apple Silicon (M1/M2/M3):**
```bash
pip install torch torchvision torchaudio
```

**For NVIDIA GPU:**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**For CPU only:**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### Step 3: Install Core Dependencies

```bash
pip install opencv-python numpy scipy pandas matplotlib tqdm
```

### Step 4: Install MMPose

```bash
pip install openmim
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"
```

### Step 5: (Optional) Install OpenSim

**For Linux:**
```bash
conda install -c opensim-org opensim
```

**For macOS/Windows:**
Use AWS EC2 for Moco data generation (see Week 6 docs)

### Step 6: Verify Installation

```bash
# Test imports
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import cv2; print(f'OpenCV: {cv2.__version__}')"
python -c "import mmpose; print(f'MMPose: {mmpose.__version__}')"

# Check GPU availability
python -c "import torch; print(f'MPS: {torch.backends.mps.is_available()}')"
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

---

## Troubleshooting Installation

### MMPose Installation Fails

**Error:** `No matching distribution found for mmpose`

**Solution:**
```bash
# Install specific version
pip install mmpose==1.3.0 mmcv==2.0.0 mmengine==0.10.0

# Or try without dependencies
pip install mmpose --no-deps
pip install mmcv mmengine mmdet
```

### PyTorch MPS Not Available

**Error:** `MPS backend not available`

**Check:**
```bash
# Verify macOS version
sw_vers  # Should be 12.3+

# Check PyTorch version
python -c "import torch; print(torch.__version__)"  # Should be 2.0+
```

**Solution:**
```bash
# Reinstall PyTorch
pip uninstall torch torchvision torchaudio
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cpu
```

### OpenCV Camera Access Issues

**macOS:**
```bash
# Grant camera permission
# System Preferences > Security & Privacy > Camera
# Enable for Terminal or VSCode
```

**Linux:**
```bash
# Add user to video group
sudo usermod -a -G video $USER
# Logout and login again
```

### CUDA Out of Memory

**Solution:**
```bash
# Reduce batch size in training scripts
python train_muscle_predictor.py --batch_size 16  # Instead of 32

# Or use CPU
python train_muscle_predictor.py --device cpu
```

---

## Platform-Specific Instructions

### macOS (Apple Silicon)

```bash
# Recommended setup
conda create -n biomech python=3.10
conda activate biomech

pip install torch torchvision torchaudio
pip install opencv-python numpy scipy pandas matplotlib tqdm
pip install openmim
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"

# Verify MPS
python -c "import torch; print(torch.backends.mps.is_available())"
```

### Linux (NVIDIA GPU)

```bash
# With CUDA 11.8
conda create -n biomech python=3.10
conda activate biomech

pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install opencv-python numpy scipy pandas matplotlib tqdm
pip install openmim
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"

# Install OpenSim (optional)
conda install -c opensim-org opensim

# Verify CUDA
python -c "import torch; print(torch.cuda.is_available())"
```

### Windows

```bash
# Use WSL2 recommended, or native Windows:
conda create -n biomech python=3.10
conda activate biomech

pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install opencv-python numpy scipy pandas matplotlib tqdm
pip install openmim
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"
```

---

## Optional Dependencies

### Jupyter Notebook Support

```bash
pip install jupyter ipykernel
python -m ipykernel install --user --name biomech --display-name "Biomech"
```

### Development Tools

```bash
pip install pytest black flake8 mypy
```

### 3D Visualization (Future)

```bash
pip install plotly dash open3d
```

---

## Verifying Hardware Access

### Check Cameras

```bash
python -c "
import cv2
cameras = [i for i in range(10) if cv2.VideoCapture(i).isOpened()]
print(f'Available cameras: {cameras}')
"
```

### Check GPU Memory

```bash
# Apple Silicon
python -c "
import torch
if torch.backends.mps.is_available():
    print('MPS available')
    # Test allocation
    x = torch.randn(1000, 1000, device='mps')
    print('MPS working correctly')
"

# NVIDIA
python -c "
import torch
if torch.cuda.is_available():
    print(f'CUDA devices: {torch.cuda.device_count()}')
    print(f'Current device: {torch.cuda.get_device_name(0)}')
    print(f'Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')
"
```

---

## Post-Installation Testing

### Quick Test

```bash
cd src/biomechanics/week1_pose
python minimal_pose_demo.py
```

**Expected:** Webcam window with skeleton overlay at 20+ FPS

### Full Pipeline Test

```bash
cd src/biomechanics
python complete_pipeline.py --cam0 0 --cam1 0  # Single camera test
```

**Expected:** Pipeline runs without errors

---

## Uninstallation

```bash
# Remove conda environment
conda deactivate
conda env remove -n biomech

# Remove downloaded models (optional)
rm -rf ~/.cache/torch
rm -rf ~/.cache/mmpose
```

---

## Disk Space Requirements

- Base installation: ~3GB
- MMPose models (auto-downloaded): ~50MB
- Moco training data (optional): ~500MB
- Trained models (optional): ~50MB

**Total:** ~4GB (without optional components)

---

## Network Requirements

Downloads during installation:
- PyTorch: ~2GB
- MMPose dependencies: ~500MB
- Model weights (on first run): ~50MB

**Total download:** ~2.5GB

---

## Next Steps

After successful installation:

1. **Test basic pose** - See [QUICKSTART.md](QUICKSTART.md)
2. **Calibrate cameras** - Week 2 guide
3. **Run full pipeline** - [README.md](README.md)

---

## Getting Help

If you encounter issues:

1. Check [Troubleshooting](#troubleshooting-installation) section above
2. Verify all dependencies: `pip list`
3. Check Python version: `python --version` (should be 3.10)
4. Test imports individually
5. Open an issue with:
   - Error message
   - OS and Python version
   - Output of `pip list`
   - Steps to reproduce

---

## Minimum Working Installation

If you just want to test the core pipeline without all features:

```bash
# Minimal install
pip install torch opencv-python numpy

# Test basic pose (without MMPose)
# Will use a simplified pose estimator
```

This allows you to explore the code structure without full dependency installation.
