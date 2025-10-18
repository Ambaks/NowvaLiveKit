"""
Camera Identification and Testing Tool
"""

import cv2
import sys
import numpy as np


def detect_cameras(max_cameras=5):
    """Detect all available cameras"""
    print("="*60)
    print("Checking available cameras...")
    print("="*60)
    print()

    available = []

    for i in range(max_cameras):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            # Get camera properties
            width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            fps = cap.get(cv2.CAP_PROP_FPS)
            backend = cap.getBackendName()

            print(f"✓ Camera Index {i}:")
            print(f"    Resolution: {int(width)}x{int(height)}")
            print(f"    FPS: {fps}")
            print(f"    Backend: {backend}")

            # Try to read a frame to verify it's working
            ret, frame = cap.read()
            if ret:
                print(f"    Status: ✓ Working (frame captured)")
                available.append(i)
            else:
                print(f"    Status: ✗ Opens but cannot read frames")

            cap.release()
            print()

    print("="*60)
    print(f"Found {len(available)} working camera(s): {available}")
    print("="*60)
    print()

    if len(available) >= 2:
        print("✓ You have 2+ cameras for stereo vision!")
        print()
        print("Next steps:")
        print(f"  python identify_cameras.py test {available[0]}")
        print(f"  python identify_cameras.py compare {available[0]} {available[1]}")
        print(f"  python calibrate_cameras.py {available[0]} {available[1]}")
    elif len(available) == 1:
        print("⚠ Only 1 camera found")
        print("For stereo vision, you need 2 cameras")
        print()
        print("Test your camera:")
        print(f"  python identify_cameras.py test {available[0]}")

    return available


def test_camera(camera_id):
    """Test a specific camera with live preview"""
    print(f"Testing camera {camera_id}...")
    print("Press 'q' to quit")
    print()

    cap = cv2.VideoCapture(camera_id)

    if not cap.isOpened():
        print(f"✗ Cannot open camera {camera_id}")
        return

    print(f"✓ Camera {camera_id} opened")

    import time
    frame_count = 0
    start_time = time.time()

    while True:
        ret, frame = cap.read()

        if not ret:
            print("Failed to read frame")
            break

        # Calculate FPS
        frame_count += 1
        if frame_count % 30 == 0:
            elapsed = time.time() - start_time
            fps = 30 / elapsed
            start_time = time.time()

            # Display info
            cv2.putText(frame, f"Camera {camera_id} - FPS: {fps:.1f}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.putText(frame, "Press 'q' to quit", (10, 60),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow(f'Camera {camera_id} Test', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print(f"Camera {camera_id} test completed")


def compare_cameras(cam_ids):
    """Show multiple cameras side-by-side"""
    print(f"Comparing cameras: {cam_ids}")
    print("Press 'q' to quit")
    print()

    # Open all cameras
    caps = []
    for cam_id in cam_ids:
        cap = cv2.VideoCapture(cam_id)
        if cap.isOpened():
            caps.append((cam_id, cap))
            print(f"✓ Camera {cam_id} opened")
        else:
            print(f"✗ Cannot open camera {cam_id}")

    if len(caps) == 0:
        print("No cameras available")
        return

    print()
    print("Displaying cameras side-by-side...")

    while True:
        frames = []

        for cam_id, cap in caps:
            ret, frame = cap.read()
            if ret:
                # Resize for comparison
                frame = cv2.resize(frame, (640, 480))

                # Add label
                cv2.putText(frame, f"Camera {cam_id}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                frames.append(frame)

        if len(frames) == 0:
            break

        # Combine frames
        if len(frames) == 1:
            combined = frames[0]
        else:
            combined = np.hstack(frames)

        cv2.imshow('Camera Comparison', combined)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Cleanup
    for cam_id, cap in caps:
        cap.release()

    cv2.destroyAllWindows()
    print("Comparison completed")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "test":
            if len(sys.argv) > 2:
                camera_id = int(sys.argv[2])
                test_camera(camera_id)
            else:
                print("Usage: python identify_cameras.py test <camera_id>")
                print("Example: python identify_cameras.py test 0")

        elif command == "compare":
            if len(sys.argv) > 2:
                cam_ids = [int(x) for x in sys.argv[2:]]
                compare_cameras(cam_ids)
            else:
                print("Usage: python identify_cameras.py compare <cam1> <cam2> ...")
                print("Example: python identify_cameras.py compare 0 1")

        else:
            print("Unknown command. Available commands:")
            print("  python identify_cameras.py              # Detect all cameras")
            print("  python identify_cameras.py test 0       # Test camera 0")
            print("  python identify_cameras.py compare 0 1  # Compare cameras 0 and 1")

    else:
        # Default: detect all cameras
        detect_cameras()
