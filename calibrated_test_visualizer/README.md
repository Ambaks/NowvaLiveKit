# calibrated_test_visualizer/

Multi-camera triangulation test pipeline. Captures synchronized frames from 3 cameras, triangulates 2D poses into 3D via DLT (Direct Linear Transform), runs the full biomechanics pipeline, and generates an interactive HTML dashboard.

## Usage

Run locally (syncs to remote server with GPU, executes there, copies results back):

```bash
./calibrated_test_visualizer/run_test.sh [height_cm] [extra_args]
./calibrated_test_visualizer/run_test.sh 188.5
```

Or run directly on the GPU machine:

```bash
python calibrated_test_visualizer/visualize_triangulated.py --height 188.5
```

## Files

- `visualize_triangulated.py` — main script: captures from 3 cameras, runs triangulation + IK + rep counting, outputs HTML dashboard
- `run_test.sh` — deployment wrapper: syncs code to remote server via SSH/Tailscale, runs headlessly, copies output back, opens in browser

## Output

Results go to `calibrated_test_visualizer/outputs/` — HTML dashboards with 3D skeleton visualization, joint angle plots, and rep-by-rep analysis.
