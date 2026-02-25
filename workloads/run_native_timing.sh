#!/usr/bin/env bash
set -euo pipefail

OUTPUT="results/week7/native/native_timing.csv"
mkdir -p results/week7/native

echo "workload,run,real_sec,user_sec,sys_sec" > "$OUTPUT"

WORKLOADS=("sequential" "random" "phase_change")

for workload in "${WORKLOADS[@]}"; do
    echo "[JazzyFS] Running native $workload..."
    for run in 1 2 3; do
        # Capture time output
        result=$( { time bash workloads/${workload}.sh; } 2>&1 )

        real=$(echo "$result" | grep real | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')
        user=$(echo "$result" | grep user | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')
        sys=$(echo "$result"  | grep sys  | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')

        echo "$workload,$run,$real,$user,$sys" >> "$OUTPUT"
        echo "  Run $run: real=${real}s user=${user}s sys=${sys}s"

        # Wait 3 seconds between runs
        sleep 3
    done
done

echo "[OK] Native timing saved to $OUTPUT"