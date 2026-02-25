#!/usr/bin/env bash
set -euo pipefail

if [ -z "$1" ]; then
    echo "Usage: bash workloads/run_jazzyfs_timing.sh <mode>"
    echo "Example: bash workloads/run_jazzyfs_timing.sh baseline"
    exit 1
fi

MODE=$1
OUTPUT="results/week7/native/jazzyfs_${MODE}_timing.csv"

echo "workload,run,real_sec,user_sec,sys_sec" > "$OUTPUT"

WORKLOADS=("sequential" "random" "phase_change")

for workload in "${WORKLOADS[@]}"; do
    echo "[JazzyFS] Running $MODE $workload..."
    for run in 1 2 3; do
        result=$( { time bash workloads/${workload}.sh; } 2>&1 )

        real=$(echo "$result" | grep real | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')
        user=$(echo "$result" | grep user | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')
        sys=$(echo "$result"  | grep sys  | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')

        echo "$workload,$run,$real,$user,$sys" >> "$OUTPUT"
        echo "  Run $run: real=${real}s user=${user}s sys=${sys}s"

        sleep 3
    done
done

echo "[OK] JazzyFS $MODE timing saved to $OUTPUT"
