#!/usr/bin/env python3
import csv
import os
import platform
from collections import defaultdict

# Week 10: Timing + depth sweep summary. Works on Linux and macOS.
# Auto-detects platform and reads from results/week10/linux/ or results/week10/apfs/.
# Reads native/JazzyFS timing from results/week10/{platform}/native/
# Reads depth sweep timing from results/week10/{platform}/depth/

PLATFORM         = "apfs" if platform.system() == "Darwin" else "linux"
native_dir       = f"results/week10/{PLATFORM}/native"
depth_dir        = f"results/week10/{PLATFORM}/depth"
output_file      = f"results/week10/{PLATFORM}/week10_timing_summary.csv"

WORKLOADS = ["sequential", "random", "phase_change", "sqlite_workload", "tar_workload", "python_import"]
DEPTHS    = [1, 2, 4, 8]

def read_file(filepath):
    times = defaultdict(list)
    with open(filepath) as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            try:
                val = float(row["real_sec"])
                if val > 0:
                    times[row["workload"]].append(val)
            except (ValueError, KeyError):
                pass
    return times

os.makedirs(native_dir, exist_ok=True)
os.makedirs(depth_dir,  exist_ok=True)

print(f"[Platform] {PLATFORM}")

# Load native + JazzyFS mode timing
data = {}
for f in sorted(os.listdir(native_dir)):
    if not f.endswith(".csv") or "summary" in f:
        continue
    filepath = os.path.join(native_dir, f)
    if "native" in f and "jazzyfs" not in f:
        mode = "native"
    elif "none" in f:
        mode = "none"
    elif "baseline" in f:
        mode = "baseline"
    elif "adaptive" in f:
        mode = "adaptive"
    else:
        continue
    data[mode] = read_file(filepath)

# Load depth sweep timing
depth_data = {}
for d in DEPTHS:
    path = os.path.join(depth_dir, f"jazzyfs_adaptive_depth{d}_timing.csv")
    if os.path.exists(path):
        depth_data[d] = read_file(path)

with open(output_file, "w", newline="") as out:
    writer = csv.writer(out)
    writer.writerow(["workload", "mode", "avg_real", "min_real", "max_real", "overhead_vs_native"])

    for workload in WORKLOADS:
        if "native" not in data or workload not in data["native"]:
            continue
        native_avg = sum(data["native"][workload]) / len(data["native"][workload])

        # Standard modes
        for mode in ["native", "none", "baseline", "adaptive"]:
            if mode not in data or workload not in data[mode]:
                continue
            times    = data[mode][workload]
            avg      = sum(times) / len(times)
            mn       = min(times)
            mx       = max(times)
            overhead = "0.0%" if mode == "native" else f"{((avg - native_avg) / native_avg) * 100:+.1f}%"
            writer.writerow([workload, mode, f"{avg:.4f}", f"{mn:.4f}", f"{mx:.4f}", overhead])

        # Depth sweep rows
        for d in DEPTHS:
            if d not in depth_data or workload not in depth_data[d]:
                continue
            times    = depth_data[d][workload]
            avg      = sum(times) / len(times)
            mn       = min(times)
            mx       = max(times)
            overhead = f"{((avg - native_avg) / native_avg) * 100:+.1f}%"
            writer.writerow([workload, f"adaptive_depth{d}", f"{avg:.4f}", f"{mn:.4f}", f"{mx:.4f}", overhead])

print(f"[OK] Saved to {output_file}")
