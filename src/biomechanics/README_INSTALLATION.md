# Biomechanics Module Installation

The main [requirements.txt](../../requirements.txt) in the root directory includes all dependencies needed for the biomechanics module.

## Quick Install

```bash
# From project root
pip install -r requirements.txt

# Install MMPose dependencies
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"
```

## Alternative: Biomechanics-Only Installation

If you only want the biomechanics module without the voice agent:

```bash
# From project root
pip install torch torchvision torchaudio opencv-python numpy scipy pandas matplotlib seaborn tqdm openmim

# Install MMPose
mim install mmengine "mmcv>=2.0.0" "mmdet>=3.0.0" "mmpose>=1.0.0"
```

See [requirements_biomechanics_only.txt](requirements_biomechanics_only.txt) for the minimal set.

## For Complete Setup

Use the root [requirements.txt](../../requirements.txt) which includes everything you need for:
- Voice agent (GPT-4 Realtime API)
- Database & session management
- Pose estimation & biomechanics
- All utilities

Refer to [HOW_TO_RUN.md](../../HOW_TO_RUN.md) for detailed biomechanics pipeline instructions.
