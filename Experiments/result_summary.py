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
    "gradual_drift",
    "seek_suppression",
    "tar_workload",
    "python_import",
    "cache_lookup_workload",
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
                    rows = list(csv.DictReader(f))

                prev_fn = False
                for row in rows:
                    try:
                        mode = row["mode"]
                        prefetch = int(row["prefetch"])
                        confidence = float(row["confidence"])
                        seek_delta = int(row.get("seek_delta") or 0)
                        seek_suppressed = 1 if row.get("phase") == "seek-suppressed" else 0
                        cache_hit = int(row.get("cache_hit") or 0)
                        is_fn = row.get("false_negative") == "1"
                        chain_start_fn = 1 if (is_fn and not prev_fn) else 0
                        false_negative = 1 if is_fn else 0
                    except (ValueError, KeyError):
                        prev_fn = False
                        continue

                    data[(workload, mode)].append((
                        prefetch, confidence, seek_delta, seek_suppressed,
                        cache_hit, false_negative, chain_start_fn,
                    ))
                    run_counts[(workload, mode)].add(run_name)
                    prev_fn = is_fn

    with open(DECISION_OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "workload", "mode", "runs",
            "avg_prefetch_rate", "avg_confidence", "std_confidence",
            "avg_seek_delta", "seek_suppressed_rate",
            "cache_hit_rate", "false_negative_rate", "chain_start_fn_rate",
        ])

        for (workload, mode), values in sorted(data.items()):
            n = len(values)
            avg_prefetch         = sum(v[0] for v in values) / n
            confidences          = [v[1] for v in values]
            avg_confidence       = sum(confidences) / n
            std_confidence       = statistics.stdev(confidences) if n > 1 else 0.0
            avg_seek_delta       = sum(v[2] for v in values) / n
            seek_suppressed_rate = sum(v[3] for v in values) / n
            cache_hit_rate       = sum(v[4] for v in values) / n
            false_negative_rate  = sum(v[5] for v in values) / n
            chain_start_fn_rate  = sum(v[6] for v in values) / n
            runs = len(run_counts[(workload, mode)])
            writer.writerow([
                workload, mode, runs,
                f"{avg_prefetch:.4f}", f"{avg_confidence:.4f}", f"{std_confidence:.4f}",
                f"{avg_seek_delta:.1f}", f"{seek_suppressed_rate:.4f}",
                f"{cache_hit_rate:.4f}", f"{false_negative_rate:.4f}", f"{chain_start_fn_rate:.4f}",
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
