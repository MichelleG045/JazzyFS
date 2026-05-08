"""
decay_rate_analysis.py

Reads decisions.csv logs from results/{platform}/phase_change/adaptive/run*/
and results/{platform}/gradual_drift/adaptive/run*/. It measures whether
confidence decay produces a sharp single-read spike for abrupt phase changes
but stays low for gradual drift.

    decay detection   -- stops when decay_rate >= JAZZYFS_DECAY_THRESHOLD (0.25)
    threshold only    -- stops when confidence < CONFIDENCE_THRESHOLD (0.7)

For each run, reports:
    - the read index where the phase transition occurs
    - the read index where decay detection triggers
    - the read index where threshold-only detection would trigger
    - reads saved by decay detection vs threshold-only

Outputs a per-run table and a summary row, saved to:
    results/{platform}/decay_rate_analysis.csv
"""

import csv
import platform
import sys
from pathlib import Path

DECAY_THRESHOLD = 0.25
CONFIDENCE_THRESHOLD = 0.7


def analyze_run(csv_path: Path, workload: str) -> dict | None:
    """
    Find the phase transition and measure reaction speed for one run.
    Returns None if the run has no decay_rate column (old log format).
    """
    rows = list(csv.DictReader(open(csv_path, newline="")))
    if not rows or "decay_rate" not in rows[0]:
        return None

    confidences = [float(r["confidence"]) for r in rows]
    decay_rates = [float(r["decay_rate"]) for r in rows]

    # Find the first sharp confidence drop.
    decay_trigger = None
    for i, dr in enumerate(decay_rates):
        if dr >= DECAY_THRESHOLD:
            decay_trigger = i
            break

    if decay_trigger is None:
        max_decay = max(decay_rates) if decay_rates else 0.0
        return {
            "workload": workload,
            "run": csv_path.parent.name,
            "transition_read": "",
            "decay_trigger_read": "",
            "confidence_at_trigger": "",
            "decay_rate_at_trigger": f"{max_decay:.2f}",
            "threshold_trigger_read": "",
            "reads_saved": 0,
        }

    # Simulate threshold-only detection: first read after transition where
    # confidence drops below CONFIDENCE_THRESHOLD.
    threshold_trigger = None
    for i in range(decay_trigger, len(confidences)):
        if confidences[i] < CONFIDENCE_THRESHOLD:
            threshold_trigger = i
            break

    if threshold_trigger is None:
        threshold_trigger = decay_trigger

    reads_saved = threshold_trigger - decay_trigger
    transition_read = decay_trigger - 1  # last sequential read before drop

    return {
        "workload": workload,
        "run": csv_path.parent.name,
        "transition_read": transition_read,
        "decay_trigger_read": decay_trigger,
        "confidence_at_trigger": f"{confidences[decay_trigger]:.2f}",
        "decay_rate_at_trigger": f"{decay_rates[decay_trigger]:.2f}",
        "threshold_trigger_read": threshold_trigger,
        "reads_saved": reads_saved,
    }


def main():
    plat = "apfs" if platform.system() == "Darwin" else "linux"
    results_dir = Path(__file__).parent.parent / "results" / plat
    workloads = ["phase_change", "gradual_drift"]

    if not results_dir.exists():
        print(f"Directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    results = []
    skipped = 0
    for workload in workloads:
        adaptive_dir = results_dir / workload / "adaptive"
        if not adaptive_dir.exists():
            continue
        for run_dir in sorted(d for d in adaptive_dir.iterdir() if d.is_dir()):
            csv_path = run_dir / "decisions.csv"
            if not csv_path.exists():
                continue
            result = analyze_run(csv_path, workload)
            if result is None:
                skipped += 1
                continue
            results.append(result)

    if not results:
        print(
            "No runs with decay_rate column found.\n"
            "Re-run experiments with the updated code first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if skipped > 0:
        print(f"Note: {skipped} runs skipped (old log format, no decay_rate column)")

    headers = [
        "workload", "run", "transition_read", "decay_trigger_read",
        "confidence_at_trigger", "decay_rate_at_trigger",
        "threshold_trigger_read", "reads_saved",
    ]
    col_w = [16, 8, 16, 20, 22, 22, 22, 12]
    sep = "  ".join("-" * w for w in col_w)
    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, col_w))

    print("\nDecay Rate Analysis — Abrupt Phase Change vs Gradual Drift")
    print("=" * len(sep))
    print(header_row)
    print(sep)
    for r in results:
        line = "  ".join(str(r[h]).ljust(w) for h, w in zip(headers, col_w))
        print(line)
    print(sep)

    print(f"\nSummary across {len(results)} runs:")
    for workload in workloads:
        subset = [r for r in results if r["workload"] == workload]
        if not subset:
            continue
        avg_saved = sum(r["reads_saved"] for r in subset) / len(subset)
        avg_decay = sum(float(r["decay_rate_at_trigger"]) for r in subset) / len(subset)
        print(f"  {workload:14s}  runs={len(subset):2d}  avg_decay_spike={avg_decay:.2f}  avg_reads_saved={avg_saved:.1f}")
    print()

    out_path = results_dir / "decay_rate_analysis.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(results)
    print(f"Results saved to: {out_path}")


if __name__ == "__main__":
    main()
