"""
decay_rate_analysis.py

Reads decisions.csv logs from results/linux/phase_change/adaptive/run*/
and measures how quickly JazzyFS suppresses prefetching after a phase
transition using two mechanisms:

    decay detection   -- stops when decay_rate >= JAZZYFS_DECAY_THRESHOLD (0.25)
    threshold only    -- stops when confidence < CONFIDENCE_THRESHOLD (0.7)

For each run, reports:
    - the read index where the phase transition occurs
    - the read index where decay detection triggers
    - the read index where threshold-only detection would trigger
    - reads saved by decay detection vs threshold-only

Outputs a per-run table and a summary row, saved to:
    results/linux/decay_rate_analysis.csv
"""

import csv
import sys
from pathlib import Path

DECAY_THRESHOLD = 0.25
CONFIDENCE_THRESHOLD = 0.7


def analyze_run(csv_path: Path) -> dict | None:
    """
    Find the phase transition and measure reaction speed for one run.
    Returns None if the run has no decay_rate column (old log format).
    """
    rows = list(csv.DictReader(open(csv_path, newline="")))
    if not rows or "decay_rate" not in rows[0]:
        return None

    confidences = [float(r["confidence"]) for r in rows]
    decay_rates = [float(r["decay_rate"]) for r in rows]
    prefetches = [int(r["prefetch"]) for r in rows]

    # Find the transition: the last read with prefetch=1 followed by a
    # confidence drop. We look for the first read where decay_rate >= threshold.
    decay_trigger = None
    for i, dr in enumerate(decay_rates):
        if dr >= DECAY_THRESHOLD:
            decay_trigger = i
            break

    if decay_trigger is None:
        return None

    # Simulate threshold-only detection: first read after transition where
    # confidence drops below CONFIDENCE_THRESHOLD.
    threshold_trigger = None
    for i in range(decay_trigger, len(confidences)):
        if confidences[i] < CONFIDENCE_THRESHOLD:
            threshold_trigger = i
            break

    if threshold_trigger is None:
        return None

    reads_saved = threshold_trigger - decay_trigger
    transition_read = decay_trigger - 1  # last sequential read before drop

    return {
        "run": csv_path.parent.name,
        "transition_read": transition_read,
        "decay_trigger_read": decay_trigger,
        "confidence_at_trigger": f"{confidences[decay_trigger]:.2f}",
        "decay_rate_at_trigger": f"{decay_rates[decay_trigger]:.2f}",
        "threshold_trigger_read": threshold_trigger,
        "reads_saved": reads_saved,
    }


def main():
    results_dir = Path(__file__).parent.parent / "results" / "linux"
    phase_change_dir = results_dir / "phase_change" / "adaptive"

    if not phase_change_dir.exists():
        print(f"Directory not found: {phase_change_dir}", file=sys.stderr)
        sys.exit(1)

    run_dirs = sorted(d for d in phase_change_dir.iterdir() if d.is_dir())
    if not run_dirs:
        print("No run directories found.", file=sys.stderr)
        sys.exit(1)

    results = []
    skipped = 0
    for run_dir in run_dirs:
        csv_path = run_dir / "decisions.csv"
        if not csv_path.exists():
            continue
        result = analyze_run(csv_path)
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
        "run", "transition_read", "decay_trigger_read",
        "confidence_at_trigger", "decay_rate_at_trigger",
        "threshold_trigger_read", "reads_saved",
    ]
    col_w = [8, 16, 20, 22, 22, 22, 12]
    sep = "  ".join("-" * w for w in col_w)
    header_row = "  ".join(h.ljust(w) for h, w in zip(headers, col_w))

    print("\nDecay Rate Analysis — Phase Change Workload")
    print("=" * len(sep))
    print(header_row)
    print(sep)
    for r in results:
        line = "  ".join(str(r[h]).ljust(w) for h, w in zip(headers, col_w))
        print(line)
    print(sep)

    avg_saved = sum(r["reads_saved"] for r in results) / len(results)
    avg_decay = sum(int(r["decay_trigger_read"]) for r in results) / len(results)
    avg_threshold = sum(int(r["threshold_trigger_read"]) for r in results) / len(results)

    print(f"\nSummary across {len(results)} runs:")
    print(f"  Avg read where decay detection triggers:    {avg_decay:.1f}")
    print(f"  Avg read where threshold detection triggers: {avg_threshold:.1f}")
    print(f"  Avg reads saved by decay detection:         {avg_saved:.1f}\n")

    out_path = results_dir / "decay_rate_analysis.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(results)
    print(f"Results saved to: {out_path}")


if __name__ == "__main__":
    main()
