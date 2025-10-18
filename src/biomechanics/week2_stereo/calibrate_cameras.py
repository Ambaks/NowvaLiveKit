"""
Week 2: Camera Calibration
Calibrate stereo cameras using checkerboard pattern

Requirements:
- Print checkerboard pattern (9x6, 25mm squares)
- 2x USB cameras (Logitech C920 recommended)

Success Criteria:
- Reprojection error < 1 pixel
- Calibration parameters saved
"""

import cv2
import numpy as np
import glob
import os
import json


class CameraCalibrator:
    """Camera calibration using checkerboard pattern"""

    def __init__(self, checkerboard_size=(8, 6), square_size=0.025):
        """
        Initialize calibrator

        Args:
            checkerboard_size: (width, height) in inner corners
            square_size: Size of checkerboard square in meters

        Note: If you have X×Y squares, use (X, Y) inner corners
              Example: 8 wide × 6 tall squares = (8, 6)
        """
        self.checkerboard_size = checkerboard_size
        self.square_size = square_size

        # Prepare object points (0,0,0), (1,0,0), (2,0,0) ...
        self.objp = np.zeros((checkerboard_size[0] * checkerboard_size[1], 3), np.float32)
        self.objp[:, :2] = np.mgrid[0:checkerboard_size[0], 0:checkerboard_size[1]].T.reshape(-1, 2)
        self.objp *= square_size

        # Termination criteria for corner refinement
        self.criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

    def capture_calibration_images(self, camera_id=0, num_images=20, output_folder='calibration_images'):
        """
        Capture calibration images interactively

        Args:
            camera_id: Camera device ID
            num_images: Number of images to capture
            output_folder: Where to save images
        """
        os.makedirs(output_folder, exist_ok=True)

        cap = cv2.VideoCapture(camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        print(f"\n=== Capturing Calibration Images for Camera {camera_id} ===")
        print(f"Target: {num_images} images")
        print("Press SPACE to capture, Q to quit")
        print("\nTips:")
        print("- Move checkerboard to different positions and angles")
        print("- Fill the entire frame area")
        print("- Include corners, edges, and center positions")
        print("- Tilt the board at various angles\n")

        count = 0
        while count < num_images:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame")
                break

            # Try to find checkerboard
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            ret_corners, corners = cv2.findChessboardCorners(gray, self.checkerboard_size, None)

            # Draw checkerboard if found
            display_frame = frame.copy()
            if ret_corners:
                cv2.drawChessboardCorners(display_frame, self.checkerboard_size, corners, ret_corners)
                status_text = "Checkerboard detected - Press SPACE to capture"
                status_color = (0, 255, 0)
            else:
                status_text = "No checkerboard detected"
                status_color = (0, 0, 255)

            # Display status
            cv2.putText(display_frame, status_text, (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
            cv2.putText(display_frame, f"Captured: {count}/{num_images}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            cv2.imshow('Capture Calibration Images', display_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord(' ') and ret_corners:
                filename = os.path.join(output_folder, f'img_{count:03d}.jpg')
                cv2.imwrite(filename, frame)
                count += 1
                print(f"Captured image {count}/{num_images}")
            elif key == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

        print(f"\nCaptured {count} images to {output_folder}/")
        return count

    def calibrate_from_images(self, image_folder):
        """
        Calibrate camera from saved images

        Args:
            image_folder: Folder containing calibration images

        Returns:
            dict: Calibration parameters
        """
        # Arrays to store object points and image points
        objpoints = []  # 3D points in real world
        imgpoints = []  # 2D points in image plane

        # Load images
        images = glob.glob(os.path.join(image_folder, '*.jpg'))

        if len(images) == 0:
            raise ValueError(f"No images found in {image_folder}")

        print(f"\n=== Calibrating from {len(images)} images ===")

        img_size = None
        for i, fname in enumerate(images):
            img = cv2.imread(fname)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            if img_size is None:
                img_size = gray.shape[::-1]

            # Find checkerboard corners
            ret, corners = cv2.findChessboardCorners(gray, self.checkerboard_size, None)

            if ret:
                objpoints.append(self.objp)

                # Refine corner positions
                corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), self.criteria)
                imgpoints.append(corners2)

                print(f"✓ Image {i+1}/{len(images)}: Checkerboard found")
            else:
                print(f"✗ Image {i+1}/{len(images)}: Checkerboard not found")

        if len(objpoints) < 3:
            raise ValueError("Need at least 3 successful images for calibration")

        print(f"\nCalibrating with {len(objpoints)} images...")

        # Calibrate camera
        ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
            objpoints, imgpoints, img_size, None, None
        )

        print(f"✓ Calibration complete!")
        print(f"  Reprojection error: {ret:.3f} pixels")

        # Calculate individual errors
        mean_error = 0
        for i in range(len(objpoints)):
            imgpoints2, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
            error = cv2.norm(imgpoints[i], imgpoints2, cv2.NORM_L2) / len(imgpoints2)
            mean_error += error

        print(f"  Mean error: {mean_error / len(objpoints):.3f} pixels")

        return {
            'camera_matrix': mtx,
            'dist_coeffs': dist,
            'rvecs': [r.tolist() for r in rvecs],
            'tvecs': [t.tolist() for t in tvecs],
            'image_size': img_size,
            'reprojection_error': ret,
            'mean_error': mean_error / len(objpoints)
        }

    def save_calibration(self, calib_params, filename):
        """Save calibration parameters"""
        # Convert numpy arrays to lists for JSON serialization
        save_params = {
            'camera_matrix': calib_params['camera_matrix'].tolist(),
            'dist_coeffs': calib_params['dist_coeffs'].tolist(),
            'image_size': calib_params['image_size'],
            'reprojection_error': float(calib_params['reprojection_error']),
            'mean_error': float(calib_params['mean_error'])
        }

        with open(filename, 'w') as f:
            json.dump(save_params, f, indent=2)

        # Also save as npz for easy loading
        npz_filename = filename.replace('.json', '.npz')
        np.savez(npz_filename,
                camera_matrix=calib_params['camera_matrix'],
                dist_coeffs=calib_params['dist_coeffs'])

        print(f"Saved calibration to {filename} and {npz_filename}")


def calibrate_stereo_pair(camera_ids=[0, 1], num_images=20):
    """
    Complete calibration workflow for stereo camera pair

    Args:
        camera_ids: List of camera device IDs
        num_images: Number of calibration images per camera
    """
    calibrator = CameraCalibrator()

    results = {}

    for cam_id in camera_ids:
        print(f"\n{'='*60}")
        print(f"CAMERA {cam_id} CALIBRATION")
        print(f"{'='*60}")

        folder = f'calibration_cam{cam_id}'

        # Capture images
        num_captured = calibrator.capture_calibration_images(
            camera_id=cam_id,
            num_images=num_images,
            output_folder=folder
        )

        if num_captured < 10:
            print(f"Warning: Only {num_captured} images captured. Recommend at least 15.")
            response = input("Continue with calibration? (y/n): ")
            if response.lower() != 'y':
                continue

        # Calibrate
        calib_params = calibrator.calibrate_from_images(folder)

        # Save
        calibrator.save_calibration(calib_params, f'camera_{cam_id}_calibration.json')

        results[f'cam{cam_id}'] = calib_params

    # Save combined calibration
    if len(results) == 2:
        combined_file = 'stereo_calibration.npz'
        cam_keys = sorted(results.keys())  # Get actual camera keys
        np.savez(combined_file,
                cam0_matrix=results[cam_keys[0]]['camera_matrix'],
                cam0_dist=results[cam_keys[0]]['dist_coeffs'],
                cam1_matrix=results[cam_keys[1]]['camera_matrix'],
                cam1_dist=results[cam_keys[1]]['dist_coeffs'])

        print(f"\n✓ Stereo calibration saved to {combined_file}")
        print("\n=== Calibration Summary ===")
        for cam_name, params in results.items():
            print(f"{cam_name}: {params['reprojection_error']:.3f} pixels")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2:
        cam_ids = [int(sys.argv[1]), int(sys.argv[2])]
    else:
        cam_ids = [0, 1]

    print("=== Stereo Camera Calibration ===")
    print(f"Camera IDs: {cam_ids}")
    print("\nMake sure you have:")
    print("- Printed checkerboard pattern (9x6, 25mm squares)")
    print("- Both cameras connected and working")

    input("\nPress Enter to start...")

    calibrate_stereo_pair(camera_ids=cam_ids, num_images=20)
