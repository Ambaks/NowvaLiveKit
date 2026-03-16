"""Quick test: generate interactive HTML dashboard from existing output data.

Usage:
    python test_dashboard.py [path/to/set1_plot_data.json]

Defaults to output/set_20260310_171600/set1_plot_data.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from biomechanics.analysis.rep_segmenter import segment_set
from biomechanics.viz.html_dashboard import generate_set_dashboard, generate_session_dashboard


def main():
    data_path = sys.argv[1] if len(sys.argv) > 1 else "output/set_20260310_171600/set1_plot_data.json"
    data_path = Path(data_path)

    if not data_path.exists():
        print(f"File not found: {data_path}")
        sys.exit(1)

    with open(data_path) as f:
        plot_data = json.load(f)

    out_dir = str(data_path.parent)
    set_number = plot_data.get("set_number", 1)

    print(f"Loaded {len(plot_data['timestamps'])} frames from {data_path}")

    # Run segmentation
    seg_result = segment_set(plot_data)
    print(f"Segmented {seg_result['total_reps']} reps")

    # Generate per-set dashboard
    generate_set_dashboard(plot_data, seg_result, out_dir, set_number, auto_open=True)

    # Also generate session dashboard (single-set session)
    session_info = {"exercise": "Barbell Back Squat", "target_sets": 1, "target_reps": 6}
    generate_session_dashboard([plot_data], session_info, out_dir, auto_open=False)

    print("Done!")


if __name__ == "__main__":
    main()
