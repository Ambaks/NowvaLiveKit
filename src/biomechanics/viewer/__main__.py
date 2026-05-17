"""CLI entry point for the diagnosis comparison viewer.

Usage::

    python -m biomechanics.viewer --diagnosis /path/to/diagnosis_output.json
    python -m biomechanics.viewer.app --diagnosis /path/to/diagnosis_output.json
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Biomechanics Diagnosis Viewer")
    parser.add_argument(
        "--diagnosis",
        required=True,
        help="Path to diagnosis_output_<set_id>.json artifact",
    )
    args = parser.parse_args()

    from .app import launch_diagnosis_viewer

    launch_diagnosis_viewer(args.diagnosis)


if __name__ == "__main__":
    main()
