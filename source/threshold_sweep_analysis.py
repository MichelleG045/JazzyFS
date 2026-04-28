"""
threshold_sweep_analysis.py

Reads results/{platform}/threshold_sweep/threshold_sweep_results.csv
and produces a summary table showing how prefetch rate, timing, and
confidence change as the confidence threshold varies (0.3, 0.5, 0.7, 0.9).

Outputs:
    results/{platform}/threshold_sweep/threshold_sweep_summary.csv
"""

import csv
import sys
from pathlib import Path
from collections import defaultdict


THRESHOLDS = [0.3, 0.5, 0.7, 0.9]
WORKLOADS = [
    "sequential",
    "random",
    "phase_change",
    "tar_workload",
    "python_import",
    "cache_lookup_workload",
    "concurrent",
]


def load_results(csv_path: Path) -> dict:
    """Load raw sweep results grouped by (threshold, workload)."""
    data = defaultdict(list)
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            key = (float(row["threshold"]), row["workload"])
            data[key].append({
                "wall_time": float(row["wall_time"]),
                "prefetch_rate": float(row["prefetch_rate"]),
                "avg_confidence": float(row["avg_confidence"]),
            })
    return data


def summarize(data: dict) -> list[dict]:
    rows = []
    for threshold in THRESHOLDS:
        for workload in WORKLOADS:
            key = (threshold, workload)
            runs = data.get(key, [])
            if not runs:
                continue
            n = len(runs)
            avg_time = sum(r["wall_time"] for r in runs) / n
            avg_prefetch = sum(r["prefetch_rate"] for r in runs) / n
            avg_conf = sum(r["avg_confidence"] for r in runs) / n
            rows.append({
                "threshold": threshold,
                "workload": workload,
                "runs": n,
                "avg_time": f"{avg_time:.4f}",
                "avg_prefetch_rate": f"{avg_prefetch:.3f}",
                "avg_confidence": f"{avg_conf:.3f}",
            })
    return rows


def main():
    # Auto-detect platform
    import platform as _platform
    plat = "apfs" if _platform.system() == "Darwin" else "linux"
    results_dir = Path(__file__).parent.parent / "results" / plat
    sweep_dir = results_dir / "threshold_sweep"
    in_csv = sweep_dir / "threshold_sweep_results.csv"

    if not in_csv.exists():
        print(
            f"Input file not found: {in_csv}\n"
            "Run Experiments/run_threshold_sweep.sh first.",
            file=sys.stderr,
        )
        sys.exit(1)

    data = load_results(in_csv)
    rows = summarize(data)

    if not rows:
        print("No results found in input file.", file=sys.stderr)
        sys.exit(1)

    headers = ["threshold", "workload", "runs", "avg_time", "avg_prefetch_rate", "avg_confidence"]
    col_w   = [10, 26, 6, 10, 18, 15]
    sep = "  ".join("-" * w for w in col_w)
    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, col_w))

    print("\nConfidence Threshold Sweep Summary")
    print("=" * len(sep))
    print(header_row)
    print(sep)

    prev_threshold = None
    for r in rows:
        if r["threshold"] != prev_threshold and prev_threshold is not None:
            print(sep)
        prev_threshold = r["threshold"]
        line = "  ".join(str(r[h]).ljust(w) for h, w in zip(headers, col_w))
        print(line)
    print(sep)

    out_csv = sweep_dir / "threshold_sweep_summary.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nResults saved to: {out_csv}")


if __name__ == "__main__":
    main()
