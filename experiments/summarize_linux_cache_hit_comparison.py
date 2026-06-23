#!/usr/bin/env python3

import csv
import os
import statistics
from collections import defaultdict

INPUT = "results/linux/native/linux_cache_hit_miss.csv"
OUTPUT = "results/linux/native/linux_cache_hit_miss_summary.csv"


def mean(values):
    return sum(values) / len(values) if values else 0.0


def main():
    if not os.path.exists(INPUT):
        raise SystemExit(f"[ERROR] Missing {INPUT}. Run experiments/run_linux_cache_hit_comparison.sh first.")

    rows = defaultdict(list)
    with open(INPUT, newline="") as fp:
        for row in csv.DictReader(fp):
            workload = row["workload"]
            rows[workload].append({
                "real_sec": float(row["real_sec"]),
                "hits": float(row["hits"]),
                "misses": float(row["misses"]),
                "dirties": float(row["dirties"]),
                "hit_ratio": float(row["hit_ratio"]),
            })

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow([
            "workload",
            "runs",
            "avg_real_sec",
            "avg_hits",
            "avg_misses",
            "avg_dirties",
            "avg_hit_ratio",
            "std_hit_ratio",
        ])

        for workload in sorted(rows):
            values = rows[workload]
            ratios = [v["hit_ratio"] for v in values]
            writer.writerow([
                workload,
                len(values),
                f"{mean([v['real_sec'] for v in values]):.4f}",
                f"{mean([v['hits'] for v in values]):.1f}",
                f"{mean([v['misses'] for v in values]):.1f}",
                f"{mean([v['dirties'] for v in values]):.1f}",
                f"{mean(ratios):.2f}",
                f"{statistics.stdev(ratios) if len(ratios) > 1 else 0.0:.2f}",
            ])

    print(f"[OK] Saved {OUTPUT}")


if __name__ == "__main__":
    main()

