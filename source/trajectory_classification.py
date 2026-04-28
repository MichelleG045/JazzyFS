"""
trajectory_classification.py

Reads decisions.csv logs from results/linux/{workload}/adaptive/run*/
and classifies the shape of each workload's confidence curve using
three statistics: mean, standard deviation, and fraction near zero.

Classification rules (training-free, threshold-based):

    near-zero     -- mean < 0.15
                     random or unpredictable access pattern

    mixed         -- 0.15 <= mean <= 0.75
                     interleaved sequential and non-sequential access

    stable-high   -- mean > 0.75 AND std < 0.10
                     sustained sequential access, low variability

    phase-change  -- mean > 0.75 AND std >= 0.10
                     mostly sequential but a confidence dip occurred,
                     indicating a workload phase transition

Compares each classification against the ground-truth workload label
and prints a match/mismatch table plus a CSV summary.
"""

import csv
import sys
from pathlib import Path


# Ground truth: expected trajectory shape per workload.
# Derived from known workload construction, not from the data.
#
#   tar_workload:         tar reads sequentially through the archive -> stable-high
#   concurrent:           reads from many offsets simultaneously -> near-zero
#   cache_lookup_workload: random key lookups -> near-zero
#   python_import:        mixes sequential .py reads with random .pyc seeks -> mixed
GROUND_TRUTH = {
    "sequential": "stable-high",
    "random": "near-zero",
    "phase_change": "phase-change",
    "tar_workload": "stable-high",
    "concurrent": "near-zero",
    "python_import": "mixed",
    "cache_lookup_workload": "near-zero",
}

NEAR_ZERO_MAX = 0.15
MID_RANGE_MAX = 0.75
LOW_STD_MAX = 0.10


def load_confidence_values(workload_dir: Path) -> list[float]:
    """Return all confidence values from adaptive-mode runs for one workload."""
    values = []
    adaptive_dir = workload_dir / "adaptive"
    if not adaptive_dir.exists():
        return values
    for run_dir in sorted(adaptive_dir.iterdir()):
        csv_path = run_dir / "decisions.csv"
        if not csv_path.exists():
            continue
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    values.append(float(row["confidence"]))
                except (KeyError, ValueError):
                    continue
    return values


def classify_trajectory(values: list[float]) -> tuple[str, float, float]:
    """
    Classify the shape of a confidence curve.

    Returns (label, mean, std).

    Rules:
        near-zero:    mean < 0.15
        mixed:        0.15 <= mean <= 0.75
        stable-high:  mean > 0.75 and std < 0.10
        phase-change: mean > 0.75 and std >= 0.10
    """
    if not values:
        return "unknown", 0.0, 0.0

    n = len(values)
    mean = sum(values) / n
    std = (sum((v - mean) ** 2 for v in values) / n) ** 0.5

    if mean < NEAR_ZERO_MAX:
        label = "near-zero"
    elif mean <= MID_RANGE_MAX:
        label = "mixed"
    elif std < LOW_STD_MAX:
        label = "stable-high"
    else:
        label = "phase-change"

    return label, mean, std


def main():
    results_dir = Path(__file__).parent.parent / "results" / "linux"
    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    workload_dirs = sorted(
        d for d in results_dir.iterdir()
        if d.is_dir() and (d / "adaptive").exists()
    )

    if not workload_dirs:
        print("No adaptive-mode results found.", file=sys.stderr)
        sys.exit(1)

    rows = []
    for workload_dir in workload_dirs:
        workload = workload_dir.name
        values = load_confidence_values(workload_dir)
        if not values:
            continue
        label, mean, std = classify_trajectory(values)
        expected = GROUND_TRUTH.get(workload, "unknown")
        match = "yes" if label == expected else "no"
        rows.append({
            "workload": workload,
            "reads": len(values),
            "mean": f"{mean:.3f}",
            "std": f"{std:.3f}",
            "classified_as": label,
            "ground_truth": expected,
            "match": match,
        })

    headers = ["workload", "reads", "mean", "std", "classified_as", "ground_truth", "match"]
    col_w   = [26,          7,       6,      6,     14,              14,              6]
    sep = "  ".join("-" * w for w in col_w)
    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, col_w))

    print("\nConfidence Trajectory Classification Results")
    print("=" * len(sep))
    print(header_row)
    print(sep)
    for r in rows:
        line = "  ".join(str(r[h]).ljust(w) for h, w in zip(headers, col_w))
        print(line)
    print(sep)

    matched = sum(1 for r in rows if r["match"] == "yes")
    print(f"\n{matched}/{len(rows)} workloads classified correctly\n")

    out_path = results_dir / "trajectory_classification.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Results saved to: {out_path}")


if __name__ == "__main__":
    main()
