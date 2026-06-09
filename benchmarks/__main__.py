"""Entry point: python -m benchmarks"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for biomechanics/agent imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from benchmarks.config import parse_args
from benchmarks.regression import detect_regressions, load_baseline
from benchmarks.report import generate_html_report, load_all_reports, write_json_report
from benchmarks.runner import BenchmarkRunner


def main() -> None:
    config = parse_args()
    runner = BenchmarkRunner(config)
    report = runner.run_all()

    # JSON output
    json_path = write_json_report(report, config.output_dir)
    if not config.json_only:
        print(f"  JSON report: {json_path}")

    # Regression detection
    baseline = load_baseline(config.baseline_path, config.output_dir)
    regressions = detect_regressions(report, baseline) if baseline else None

    # HTML report
    if not config.no_html:
        historical = load_all_reports(config.output_dir)
        html_path = generate_html_report(report, historical, regressions, config.output_dir)
        if not config.json_only:
            print(f"  HTML report: {html_path}")

    # Console summary
    runner.print_summary(report, regressions)

    # Exit code
    sys.exit(1 if any(r.status == "fail" for r in report.components.values()) else 0)


if __name__ == "__main__":
    main()
