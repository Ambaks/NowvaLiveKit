#!/bin/bash
# Biomechanics Pipeline Setup Script
# Run this to set up your environment

set -e  # Exit on error

echo "=================================================="
echo "Biomechanics Pipeline Setup"
echo "=================================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if conda is installed
if ! command -v conda &> /dev/null; then
    print_error "Conda not found. Please install Miniconda or Anaconda first."
    echo "Visit: https://docs.conda.io/en/latest/miniconda.html"
    exit 1
fi

print_success "Conda found"

# Check if environment exists
ENV_NAME="biomech"
if conda env list | grep -q "^${ENV_NAME} "; then
    print_warning "Environment '${ENV_NAME}' already exists"
    read -p "Delete and recreate? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        conda env remove -n ${ENV_NAME} -y
        print_success "Removed existing environment"
    else
        print_warning "Using existing environment"
    fi
fi

# Create conda environment
if ! conda env list | grep -q "^${ENV_NAME} "; then
    echo "Creating conda environment..."
    conda create -n ${ENV_NAME} python=3.10 -y
    print_success "Created environment: ${ENV_NAME}"
fi

# Activate environment
echo "Activating environment..."
eval "$(conda shell.bash hook)"
conda activate ${ENV_NAME}

# Install PyTorch
echo ""
echo "Installing PyTorch..."
pip install torch torchvision torchaudio
print_success "PyTorch installed"

# Install core dependencies
echo ""
echo "Installing core dependencies..."
pip install opencv-python numpy scipy pandas matplotlib tqdm
print_success "Core dependencies installed"

# Install MMPose
echo ""
echo "Installing MMPose (this may take a few minutes)..."
pip install openmim
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"
print_success "MMPose installed"

# Install optional dependencies
echo ""
read -p "Install optional dependencies (Jupyter, dev tools)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    pip install jupyter ipykernel pytest black flake8
    print_success "Optional dependencies installed"
fi

# Create necessary directories
echo ""
echo "Creating directories..."
mkdir -p data/opencap_samples
mkdir -p models
mkdir -p calibration_cam0
mkdir -p calibration_cam1
print_success "Directories created"

# Verify installation
echo ""
echo "=================================================="
echo "Verifying Installation"
echo "=================================================="
echo ""

python -c "import torch; print(f'PyTorch: {torch.__version__}')" && print_success "PyTorch OK" || print_error "PyTorch FAILED"
python -c "import cv2; print(f'OpenCV: {cv2.__version__}')" && print_success "OpenCV OK" || print_error "OpenCV FAILED"
python -c "import numpy; print(f'NumPy: {numpy.__version__}')" && print_success "NumPy OK" || print_error "NumPy FAILED"
python -c "import mmpose; print(f'MMPose: {mmpose.__version__}')" && print_success "MMPose OK" || print_error "MMPose FAILED"

# Check MPS availability (Apple Silicon)
if python -c "import torch; exit(0 if torch.backends.mps.is_available() else 1)" 2>/dev/null; then
    print_success "MPS (Apple Silicon GPU) available"
else
    print_warning "MPS not available (will use CPU)"
fi

# Check for cameras
echo ""
echo "Checking for cameras..."
NUM_CAMERAS=$(python -c "import cv2; print(sum([cv2.VideoCapture(i).isOpened() for i in range(5)]))" 2>/dev/null || echo "0")
if [ "$NUM_CAMERAS" -gt 0 ]; then
    print_success "Found ${NUM_CAMERAS} camera(s)"
else
    print_warning "No cameras detected (you can still test with video files)"
fi

# Download RTMPose model files
echo ""
echo "=================================================="
echo "Downloading Model Files"
echo "=================================================="
echo ""

read -p "Download RTMPose pretrained models (~50MB)? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "This will be handled automatically when you run the demo"
    print_success "Models will auto-download on first run"
fi

# Print next steps
echo ""
echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Activate environment:"
echo "   conda activate ${ENV_NAME}"
echo ""
echo "2. Test basic pose estimation:"
echo "   cd week1_pose"
echo "   python minimal_pose_demo.py"
echo ""
echo "3. Follow the Quick Start Guide:"
echo "   cat QUICKSTART.md"
echo ""
echo "4. Read the full README:"
echo "   cat README.md"
echo ""
echo "=================================================="
echo "Hardware Requirements"
echo "=================================================="
echo ""
echo "Minimum (for Week 1-3):"
echo "  • 1x Webcam"
echo "  • M2 MacBook or equivalent"
echo ""
echo "Recommended (for complete pipeline):"
echo "  • 2x USB webcams (Logitech C920 ~\$50 each)"
echo "  • Printed checkerboard pattern"
echo "  • AWS account (for Moco training data)"
echo ""
echo "=================================================="
print_success "Setup completed successfully!"
echo "=================================================="
