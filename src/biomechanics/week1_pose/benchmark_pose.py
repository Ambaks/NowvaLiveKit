"""
Benchmark RTMPose performance
Identify bottlenecks
"""

import cv2
import torch
import numpy as np
import time
from pathlib import Path

# Apply torch.load patch
_original_torch_load = torch.load
def _patched_torch_load(*args, **kwargs):
    kwargs.setdefault('weights_only', False)
    return _original_torch_load(*args, **kwargs)
torch.load = _patched_torch_load

from mmpose.apis import inference_topdown, init_model


def benchmark():
    print("="*60)
    print("RTMPose Performance Benchmark")
    print("="*60)
    print()

    # Check device
    print("Device Information:")
    print(f"  MPS available: {torch.backends.mps.is_available()}")
    print(f"  MPS built: {torch.backends.mps.is_built()}")
    if torch.backends.mps.is_available():
        print(f"  ✓ Using Apple Silicon GPU (MPS)")
    else:
        print(f"  ⚠ MPS not available, using CPU")
    print()

    # Load model
    models_dir = Path(__file__).parent / 'models'
    config = models_dir / 'rtmpose-m_8xb256-420e_coco-256x192.py'
    checkpoint = models_dir / 'rtmpose-m_simcc-body7_pt-body7_420e-256x192-e48f03d0_20230504.pth'

    device = 'mps' if torch.backends.mps.is_available() else 'cpu'

    print(f"Loading model on {device}...")
    start = time.time()
    model = init_model(str(config), str(checkpoint), device=device)
    load_time = time.time() - start
    print(f"✓ Model loaded in {load_time:.2f}s")
    print()

    # Create test image
    test_resolutions = [
        (640, 480),
        (1280, 720),
        (1920, 1080)
    ]

    for width, height in test_resolutions:
        print(f"Testing resolution: {width}x{height}")

        # Create dummy frame
        frame = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
        bbox = np.array([[0, 0, width, height]])

        # Warmup
        for _ in range(3):
            _ = inference_topdown(model, frame, bbox)

        # Benchmark
        times = []
        n_runs = 20

        for _ in range(n_runs):
            start = time.time()
            _ = inference_topdown(model, frame, bbox)
            times.append(time.time() - start)

        avg_time = np.mean(times)
        fps = 1.0 / avg_time

        print(f"  Average inference time: {avg_time*1000:.1f}ms")
        print(f"  FPS: {fps:.1f}")
        print()

    # Camera capture test
    print("Testing with actual camera:")
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("  ⚠ Camera not available")
        return

    # Test different camera resolutions
    for width, height in [(640, 480), (1280, 720)]:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"  Camera set to: {width}x{height} (actual: {actual_w}x{actual_h})")

        times = []
        capture_times = []
        inference_times = []

        for i in range(30):
            # Measure capture time
            t0 = time.time()
            ret, frame = cap.read()
            t1 = time.time()

            if not ret:
                break

            capture_times.append(t1 - t0)

            # Measure inference time
            bbox = np.array([[0, 0, frame.shape[1], frame.shape[0]]])
            t2 = time.time()
            _ = inference_topdown(model, frame, bbox)
            t3 = time.time()

            inference_times.append(t3 - t2)
            times.append(t3 - t0)

        avg_total = np.mean(times)
        avg_capture = np.mean(capture_times)
        avg_inference = np.mean(inference_times)

        print(f"    Capture time: {avg_capture*1000:.1f}ms")
        print(f"    Inference time: {avg_inference*1000:.1f}ms")
        print(f"    Total time: {avg_total*1000:.1f}ms")
        print(f"    FPS: {1.0/avg_total:.1f}")
        print()

    cap.release()

    print("="*60)
    print("Recommendations:")
    print("="*60)

    if fps < 25:
        print("⚠ Low FPS detected. Try:")
        print("  1. Reduce camera resolution to 640x480")
        print("  2. Use RTMPose-S (smaller model)")
        print("  3. Check if MPS is actually being used")
        print("  4. Close other applications")
    else:
        print("✓ Performance looks good!")


if __name__ == "__main__":
    benchmark()
