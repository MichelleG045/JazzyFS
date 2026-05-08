"""
seek_analysis.py

Validates Claim 2: seek distance is an actionable prefetch signal.

Reads decisions.csv logs from results/{platform}/{workload}/adaptive/run*/ and
summarizes average seek distance, maximum seek distance, prefetch rate, and the
rate at which JazzyFS explicitly labeled reads as seek-suppressed.
"""

import csv
import platform
import sys
from pathlib import Path


WORKLOADS = [
    "sequential",
    "random",
    "phase_change",
    "gradual_drift",
    "seek_suppression",
    "tar_workload",
    "python_import",
    "cache_lookup_workload",
]


def analyze_workload(workload_dir: Path) -> dict | None:
    adaptive_dir = workload_dir / "adaptive"
    if not adaptive_dir.exists():
        return None

    rows = []
    for run_dir in sorted(d for d in adaptive_dir.iterdir() if d.is_dir()):
        csv_path = run_dir / "decisions.csv"
        if not csv_path.exists():
            continue
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)

    if not rows:
        return None

    seek_values = []
    prefetches = 0
    suppressed = 0
    for row in rows:
        try:
            seek_values.append(int(row.get("seek_delta") or 0))
            prefetches += int(row.get("prefetch") or 0)
            suppressed += 1 if row.get("phase") == "seek-suppressed" else 0
        except ValueError:
            continue

    if not seek_values:
        return None

    n = len(seek_values)
    return {
        "workload": workload_dir.name,
        "reads": n,
        "avg_seek_delta": f"{sum(seek_values) / n:.1f}",
        "max_seek_delta": max(seek_values),
        "prefetch_rate": f"{prefetches / n:.3f}",
        "seek_suppressed_rate": f"{suppressed / n:.3f}",
    }


def main():
    plat = "apfs" if platform.system() == "Darwin" else "linux"
    results_dir = Path(__file__).parent.parent / "results" / plat
    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    rows = []
    for workload in WORKLOADS:
        result = analyze_workload(results_dir / workload)
        if result is not None:
            rows.append(result)

    if not rows:
        print("No adaptive decision logs with seek_delta found.", file=sys.stderr)
        sys.exit(1)

    headers = [
        "workload", "reads", "avg_seek_delta", "max_seek_delta",
        "prefetch_rate", "seek_suppressed_rate",
    ]
    col_w = [26, 8, 16, 15, 14, 22]
    sep = "  ".join("-" * w for w in col_w)
    print("\nSeek Distance Analysis")
    print("=" * len(sep))
    print("  ".join(h.ljust(w) for h, w in zip(headers, col_w)))
    print(sep)
    for row in rows:
        print("  ".join(str(row[h]).ljust(w) for h, w in zip(headers, col_w)))
    print(sep)

    out_path = results_dir / "seek_analysis.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    main()
