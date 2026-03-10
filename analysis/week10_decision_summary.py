#!/usr/bin/env python3
import csv
import os
import platform
from collections import defaultdict

# Week 10: Prefetch decision quality. Works on Linux and macOS.
# Auto-detects platform and reads from results/week10/linux/ or results/week10/apfs/.
# Reads access/decisions logs from results/week10/{platform}/{workload}/

PLATFORM    = "apfs" if platform.system() == "Darwin" else "linux"
RESULTS_DIR = f"results/week10/{PLATFORM}"
OUTPUT_CSV  = f"results/week10/{PLATFORM}/week10_decision_summary.csv"

WORKLOADS = ["sequential", "random", "phase_change", "sqlite_workload", "tar_workload", "python_import"]

FIELDNAMES = [
    "timestamp", "mode", "path", "offset", "size",
    "phase", "confidence", "prefetch", "prefetch_offset", "prefetch_size", "prefetch_depth"
]

data       = defaultdict(list)
run_counts = defaultdict(set)

print(f"[Platform] {PLATFORM}")

for workload in WORKLOADS:
    workload_dir = os.path.join(RESULTS_DIR, workload)
    if not os.path.isdir(workload_dir):
        print(f"[WARN] Missing: {workload_dir}")
        continue

    for name in sorted(os.listdir(workload_dir)):
        if not name.startswith(workload):
            continue
        decisions = os.path.join(workload_dir, name, "decisions.csv")
        if not os.path.isfile(decisions):
            continue

        with open(decisions, newline="") as f:
            first = f.readline()
            f.seek(0)
            reader = csv.DictReader(f) if first.startswith("timestamp") else csv.DictReader(f, fieldnames=FIELDNAMES)
            for row in reader:
                try:
                    mode       = row["mode"]
                    prefetch   = int(row["prefetch"])
                    confidence = float(row["confidence"])
                    data[(workload, mode)].append((prefetch, confidence))
                    run_counts[(workload, mode)].add(name)
                except (ValueError, KeyError):
                    pass

os.makedirs(RESULTS_DIR, exist_ok=True)

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["workload", "mode", "runs", "avg_prefetch_rate", "avg_confidence"])

    for (workload, mode), values in sorted(data.items()):
        avg_prefetch   = sum(p for p, _ in values) / len(values)
        avg_confidence = sum(c for _, c in values) / len(values)
        runs           = len(run_counts[(workload, mode)])
        writer.writerow([workload, mode, runs, f"{avg_prefetch:.2f}", f"{avg_confidence:.2f}"])

print(f"[OK] Saved to {OUTPUT_CSV}")
