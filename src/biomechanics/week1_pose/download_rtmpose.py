"""
Download RTMPose model and config files
Run this once to set up RTMPose-M
"""

import os
import urllib.request
from pathlib import Path

def download_file(url, dest_path):
    """Download file with progress"""
    print(f"Downloading {dest_path.name}...")

    def progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(downloaded / total_size * 100, 100)
        print(f"\r  Progress: {percent:.1f}%", end='')

    urllib.request.urlretrieve(url, dest_path, reporthook=progress)
    print()  # New line after progress

def main():
    # Create models directory
    models_dir = Path(__file__).parent / 'models'
    models_dir.mkdir(exist_ok=True)

    print("="*60)
    print("RTMPose-M Model Download")
    print("="*60)
    print()

    # RTMPose-M config and checkpoint
    files = {
        'config': {
            'url': 'https://raw.githubusercontent.com/open-mmlab/mmpose/main/projects/rtmpose/rtmpose/body_2d_keypoint/rtmpose-m_8xb256-420e_coco-256x192.py',
            'path': models_dir / 'rtmpose-m_8xb256-420e_coco-256x192.py'
        },
        'checkpoint': {
            'url': 'https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.pth',
            'path': models_dir / 'rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.pth'
        }
    }

    # Download files
    for name, info in files.items():
        if info['path'].exists():
            print(f"✓ {name.capitalize()} already exists: {info['path'].name}")
        else:
            download_file(info['url'], info['path'])
            print(f"✓ Downloaded {name}: {info['path'].name}")

    print()
    print("="*60)
    print("✓ RTMPose-M setup complete!")
    print("="*60)
    print()
    print("Model files saved to:")
    print(f"  {models_dir}/")
    print()
    print("You can now run:")
    print("  python minimal_pose_demo.py")
    print()

if __name__ == "__main__":
    main()
