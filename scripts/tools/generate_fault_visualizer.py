#!/usr/bin/env python3
"""
Generate an interactive 3D fault visualizer HTML page.

Creates a self-contained HTML file with Three.js that lets users:
- View a COCO-17 stick figure performing squats
- Inject forward lean and knee valgus faults via sliders
- Adjust body proportions (height, limb ratios)
- Export validated fault parameters as JSON for data generation

Usage:
    python scripts/generate_fault_visualizer.py [--output fault_visualizer.html]
"""

import argparse
import webbrowser
from pathlib import Path


def generate_html() -> str:
    html_path = Path(__file__).resolve().parent.parent / "fault_visualizer.html"
    return html_path.read_text()


def main():
    p = argparse.ArgumentParser(description="Generate fault visualizer HTML")
    p.add_argument("--output", type=str, default="fault_visualizer.html")
    p.add_argument("--no-open", action="store_true", help="Don't auto-open in browser")
    args = p.parse_args()

    html = generate_html()
    out = Path(args.output)
    out.write_text(html)
    print(f"Saved: {out}")

    if not args.no_open:
        webbrowser.open(f"file://{out.resolve()}")


if __name__ == "__main__":
    main()
