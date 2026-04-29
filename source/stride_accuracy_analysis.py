"""
stride_accuracy_analysis.py

Reads decisions.csv logs from results/linux/strided/{mode}/run*/
and measures prefetch accuracy for each mode:

    accuracy = prefetches where prefetch_offset == next_read_offset
               -------------------------------------------------------
               total prefetches issued

For the strided workload (+6144, +10240 alternating deltas):
  - none:     no prefetches issued (accuracy undefined, rate = 0%)
  - baseline: always prefetches at offset+4096 (wrong every time, ~0% accuracy)
  - adaptive: after 5-read warmup, stride detection predicts correct offset (~100% accuracy)

This is the key result: adaptive mode achieves correct prefetch accuracy on a
pattern class that neither Linux readahead nor simple one-block lookahead can handle.

Outputs a per-mode table and saves results to:
    results/linux/stride_accuracy_analysis.csv
"""

import csv
import sys
from pathlib import Path


def analyze_mode(mode_dir: Path) -> dict | None:
    """
    Compute prefetch accuracy across all runs for one mode.
    Accuracy is measured by comparing each prefetch_offset in decisions.csv
    against the offset of the immediately following read.
    """
    total_prefetches = 0
    correct_prefetches = 0
    total_reads = 0

    run_dirs = sorted(d for d in mode_dir.iterdir() if d.is_dir())
    if not run_dirs:
        return None

    for run_dir in run_dirs:
        csv_path = run_dir / "decisions.csv"
        if not csv_path.exists():
            continue

        rows = list(csv.DictReader(open(csv_path, newline="")))
        total_reads += len(rows)

        for i, row in enumerate(rows):
            if int(row.get("prefetch", 0)) != 1:
                continue
            total_prefetches += 1

            if i + 1 >= len(rows):
                continue
            try:
                next_offset = int(rows[i + 1]["offset"])
                pred_offset = int(row["prefetch_offset"])
            except (ValueError, KeyError):
                continue

            if next_offset == pred_offset:
                correct_prefetches += 1

    if total_prefetches == 0:
        accuracy = 0.0
    else:
        accuracy = correct_prefetches / total_prefetches

    prefetch_rate = total_prefetches / max(1, total_reads)

    return {
        "mode": mode_dir.name,
        "runs": len(run_dirs),
        "total_reads": total_reads,
        "total_prefetches": total_prefetches,
        "correct_prefetches": correct_prefetches,
        "prefetch_rate": f"{prefetch_rate:.2f}",
        "prefetch_accuracy": f"{accuracy:.2f}",
    }


def main():
    results_dir = Path(__file__).parent.parent / "results" / "linux"
    strided_dir = results_dir / "strided"

    if not strided_dir.exists():
        print(f"Directory not found: {strided_dir}", file=sys.stderr)
        print("Run the strided workload experiments first.", file=sys.stderr)
        sys.exit(1)

    mode_dirs = sorted(d for d in strided_dir.iterdir() if d.is_dir())
    if not mode_dirs:
        print("No mode directories found.", file=sys.stderr)
        sys.exit(1)

    results = []
    for mode_dir in mode_dirs:
        result = analyze_mode(mode_dir)
        if result is not None:
            results.append(result)

    if not results:
        print("No data found.", file=sys.stderr)
        sys.exit(1)

    headers = [
        "mode", "runs", "total_reads", "total_prefetches",
        "correct_prefetches", "prefetch_rate", "prefetch_accuracy",
    ]
    col_w = [10, 5, 12, 18, 18, 14, 18]
    sep = "  ".join("-" * w for w in col_w)
    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, col_w))

    print("\nStride Accuracy Analysis — Strided Workload (+6144, +10240)")
    print("=" * len(sep))
    print(header_row)
    print(sep)
    for r in results:
        line = "  ".join(str(r[h]).ljust(w) for h, w in zip(headers, col_w))
        print(line)
    print(sep)

    print("\nKey result:")
    for r in results:
        print(f"  {r['mode']:10s}  prefetch_rate={r['prefetch_rate']}  accuracy={r['prefetch_accuracy']}")
    print()

    out_path = results_dir / "stride_accuracy_analysis.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(results)
    print(f"Results saved to: {out_path}")


if __name__ == "__main__":
    main()
