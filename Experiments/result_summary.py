#!/usr/bin/env python3

import argparse
import csv
import math
import os
import platform
import statistics
from collections import defaultdict

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--platform", default=None)
_args, _ = _parser.parse_known_args()

PLATFORM = _args.platform or ("apfs" if platform.system() == "Darwin" else "linux")
RESULTS_DIR = f"results/{PLATFORM}"
NATIVE_DIR = os.path.join(RESULTS_DIR, "native")

DECISION_OUTPUT  = os.path.join(RESULTS_DIR, "decision_summary.csv")
TIMING_OUTPUT    = os.path.join(RESULTS_DIR, "timing_summary.csv")

WORKLOADS = [
    "sequential",
    "random",
    "phase_change",
    "tar_workload",
    "python_import",
    "cache_lookup_workload",
    "concurrent",
    "strided",
]


def read_timing_file(filepath):
    times = defaultdict(list)
    with open(filepath, newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            try:
                value = float(row["real_sec"])
            except (ValueError, KeyError):
                continue
            if value > 0:
                times[row["workload"]].append(value)
    return times


def ci95(values):
    n = len(values)
    if n < 2:
        return 0.0
    return 1.96 * statistics.stdev(values) / math.sqrt(n)


def summarize_decisions():
    data = defaultdict(list)
    run_counts = defaultdict(set)

    for workload in WORKLOADS:
        workload_dir = os.path.join(RESULTS_DIR, workload)
        if not os.path.isdir(workload_dir):
            print(f"[WARN] Missing: {workload_dir}")
            continue

        for mode_name in sorted(os.listdir(workload_dir)):
            mode_dir = os.path.join(workload_dir, mode_name)
            if not os.path.isdir(mode_dir):
                continue

            for run_name in sorted(os.listdir(mode_dir)):
                decisions = os.path.join(mode_dir, run_name, "decisions.csv")
                if not os.path.isfile(decisions):
                    continue

                with open(decisions, newline="") as f:
                    reader = csv.DictReader(f)

                    for row in reader:
                        try:
                            mode = row["mode"]
                            prefetch = int(row["prefetch"])
                            confidence = float(row["confidence"])
                        except (ValueError, KeyError):
                            continue

                        data[(workload, mode)].append((prefetch, confidence))
                        run_counts[(workload, mode)].add(run_name)

    with open(DECISION_OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "workload", "mode", "runs",
            "avg_prefetch_rate", "avg_confidence", "std_confidence"
        ])

        for (workload, mode), values in sorted(data.items()):
            avg_prefetch = sum(p for p, _ in values) / len(values)
            confidences = [c for _, c in values]
            avg_confidence = sum(confidences) / len(confidences)
            std_confidence = statistics.stdev(confidences) if len(confidences) > 1 else 0.0
            runs = len(run_counts[(workload, mode)])
            writer.writerow([
                workload, mode, runs,
                f"{avg_prefetch:.2f}", f"{avg_confidence:.4f}", f"{std_confidence:.4f}"
            ])

    print(f"[OK] Saved decision summary to {DECISION_OUTPUT}")


def summarize_timing():
    os.makedirs(NATIVE_DIR, exist_ok=True)

    timing_data = {}
    for filename in sorted(os.listdir(NATIVE_DIR)):
        if not filename.endswith(".csv") or "summary" in filename:
            continue

        filepath = os.path.join(NATIVE_DIR, filename)
        if "native" in filename and "jazzyfs" not in filename:
            mode = "native"
        elif "none" in filename:
            mode = "none"
        elif "baseline" in filename:
            mode = "baseline"
        elif "adaptive" in filename:
            mode = "adaptive"
        else:
            continue

        timing_data[mode] = read_timing_file(filepath)

    with open(TIMING_OUTPUT, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow([
            "workload", "mode", "n",
            "avg_real", "std_real", "ci95_real",
            "min_real", "max_real",
            "overhead_vs_native"
        ])

        for workload in WORKLOADS:
            native_times = timing_data.get("native", {}).get(workload)
            if not native_times:
                continue

            native_avg = sum(native_times) / len(native_times)

            for mode in ["native", "none", "baseline", "adaptive"]:
                times = timing_data.get(mode, {}).get(workload)
                if not times:
                    continue

                n = len(times)
                avg = sum(times) / n
                std = statistics.stdev(times) if n > 1 else 0.0
                ci = ci95(times)
                minimum = min(times)
                maximum = max(times)
                overhead = "0.0%" if mode == "native" else f"{((avg - native_avg) / native_avg) * 100:+.1f}%"

                writer.writerow([
                    workload, mode, n,
                    f"{avg:.4f}", f"{std:.4f}", f"{ci:.4f}",
                    f"{minimum:.4f}", f"{maximum:.4f}", overhead
                ])


    print(f"[OK] Saved timing summary to {TIMING_OUTPUT}")


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print(f"[Platform] {PLATFORM}")
    summarize_decisions()
    summarize_timing()


if __name__ == "__main__":
    main()
