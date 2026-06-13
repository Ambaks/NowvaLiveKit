"""Preview multiple camera feeds side by side."""

from __future__ import annotations

import sys

import cv2


def main() -> None:
    if len(sys.argv) > 1:
        device_ids = [int(x) for x in sys.argv[1:]]
    else:
        device_ids = list(range(10))

    caps: dict[int, cv2.VideoCapture] = {}
    for dev_id in device_ids:
        cap = cv2.VideoCapture(dev_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        if not cap.isOpened():
            print(f"Device {dev_id}: failed to open")
            continue
        ret, frame = cap.read()
        if not ret:
            print(f"Device {dev_id}: opened but no frames")
            cap.release()
            continue
        h, w = frame.shape[:2]
        print(f"Device {dev_id}: {w}x{h}")
        caps[dev_id] = cap

    if not caps:
        print("No cameras available")
        return

    print(f"\nShowing {len(caps)} cameras — press Q to quit")

    while True:
        for dev_id, cap in caps.items():
            ret, frame = cap.read()
            if ret:
                cv2.putText(
                    frame, f"Device {dev_id}", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2,
                )
                cv2.imshow(f"Camera {dev_id}", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    for cap in caps.values():
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
