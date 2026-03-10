import csv
import os
from collections import defaultdict

week8_dir = "results/week8"
output_file = "results/week8/week8_timing_summary.csv"

def read_file(filepath):
    times = defaultdict(list)
    with open(filepath) as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            try:
                val = float(row["real_sec"])
                if val > 0:
                    times[row["workload"]].append(val)
            except ValueError:
                pass
    return times

data = {}
for f in sorted(os.listdir(week8_dir)):
    if not f.endswith(".csv") or f == "week8_timing_summary.csv":
        continue
    filepath = os.path.join(week8_dir, f)
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

with open(output_file, "w", newline="") as out:
    writer = csv.writer(out)
    writer.writerow(["workload", "mode", "avg_real", "min_real", "max_real", "overhead_vs_native"])
    for workload in ["sequential", "random", "phase_change"]:
        native_avg = sum(data["native"][workload]) / len(data["native"][workload])
        for mode in ["native", "none", "baseline", "adaptive"]:
            times = data[mode][workload]
            avg = sum(times) / len(times)
            mn = min(times)
            mx = max(times)
            overhead = "0.0%" if mode == "native" else f"{((avg - native_avg) / native_avg) * 100:+.1f}%"
            writer.writerow([workload, mode, f"{avg:.4f}", f"{mn:.4f}", f"{mx:.4f}", overhead])

print("[OK] Saved to", output_file)
