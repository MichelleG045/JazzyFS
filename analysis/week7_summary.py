#!/usr/bin/env python3

import csv
import os
from collections import defaultdict

RESULTS_DIR = "results/week7"
OUTPUT_CSV = "results/week7/week7_summary.csv"

# (workload, mode) → list of (prefetch, confidence)
data = defaultdict(list)

# (workload, mode) → set of run filenames to count actual runs
run_counts = defaultdict(set)

WORKLOADS = ["sequential", "random", "phase_change"]

FIELDNAMES = [
    "timestamp", "mode", "path", "offset", "size",
    "phase", "confidence", "prefetch", "prefetch_offset", "prefetch_size"
]

for workload in WORKLOADS:
    workload_dir = os.path.join(RESULTS_DIR, workload)

    if not os.path.isdir(workload_dir):
        print(f"[WARN] Missing folder: {workload_dir}")
        continue

    for name in os.listdir(workload_dir):
        if not name.endswith("_decisions.csv"):
            continue

        decisions = os.path.join(workload_dir, name)

        with open(decisions, newline="") as f:
            # First line may or may not be a header
            first_line = f.readline()
            f.seek(0)
            if first_line.startswith("timestamp"):
                reader = csv.DictReader(f)
            else:
                reader = csv.DictReader(f, fieldnames=FIELDNAMES)

            for row in reader:
                mode = row["mode"]
                prefetch = int(row["prefetch"])
                confidence = float(row["confidence"])

                data[(workload, mode)].append((prefetch, confidence))
                run_counts[(workload, mode)].add(name)

# Write final summary
os.makedirs(RESULTS_DIR, exist_ok=True)

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow([
        "workload",
        "mode",
        "runs",
        "avg_prefetch_rate",
        "avg_confidence"
    ])

    for (workload, mode), values in sorted(data.items()):
        avg_prefetch = sum(p for p, _ in values) / len(values)
        avg_confidence = sum(c for _, c in values) / len(values)
        runs = len(run_counts[(workload, mode)])

        writer.writerow([
            workload,
            mode,
            runs,
            f"{avg_prefetch:.2f}",
            f"{avg_confidence:.2f}"
        ])

print(f"[OK] Wrote Week 7 summary to {OUTPUT_CSV}")