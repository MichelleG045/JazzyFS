#!/usr/bin/env bash
set -euo pipefail

# Confidence threshold sweep for JazzyFS adaptive prefetching.
# Runs all workloads in adaptive mode at four confidence threshold values
# (0.3, 0.5, 0.7, 0.9) and records timing and prefetch rate at each threshold.
#
# Usage: bash Experiments/run_threshold_sweep.sh [source_dir] [mount_point]
# Output: results/{platform}/threshold_sweep/threshold_sweep_results.csv

SOURCE_DIR="${1:-source_data}"
MOUNT_DIR="${2:-mount}"
JAZZYFS="source/jazzyfs_min.py"
LOG_DECISIONS="logs/decisions.csv"

if [[ "$(uname)" == "Darwin" ]]; then PLATFORM="apfs"; else PLATFORM="linux"; fi

THRESHOLDS=(0.3 0.5 0.7 0.9)
WORKLOADS=("sequential" "random" "phase_change" "tar_workload" "python_import" "cache_lookup_workload" "concurrent")
RUNS=5
OUT_DIR="results/${PLATFORM}/threshold_sweep"
OUT_CSV="${OUT_DIR}/threshold_sweep_results.csv"

mkdir -p "$OUT_DIR" logs

JAZZYFS_PID=

_workload_script() {
    local w=$1
    if [[ -f "workloads/synthetic/${w}.sh" ]]; then
        echo "workloads/synthetic/${w}.sh"
    else
        echo "workloads/real/${w}.sh"
    fi
}

_mount_jazzyfs() {
    local threshold=$1
    mkdir -p "$MOUNT_DIR"
    JAZZYFS_MODE="adaptive" \
        JAZZYFS_SOUND=0 \
        JAZZYFS_CONFIDENCE_THRESHOLD="$threshold" \
        JAZZYFS_RUN_INDEX="0" \
        JAZZYFS_RUN_LABEL="threshold_sweep" \
        JAZZYFS_WORKLOAD="sweep" \
        python3 "$JAZZYFS" "$SOURCE_DIR" "$MOUNT_DIR" &
    JAZZYFS_PID=$!
    sleep 2
}

_unmount_jazzyfs() {
    if [[ "$(uname)" == "Darwin" ]]; then
        umount "$MOUNT_DIR" 2>/dev/null || diskutil unmount "$MOUNT_DIR" 2>/dev/null || true
    else
        fusermount -u "$MOUNT_DIR" 2>/dev/null || umount "$MOUNT_DIR" 2>/dev/null || true
    fi
    [[ -n "$JAZZYFS_PID" ]] && wait "$JAZZYFS_PID" 2>/dev/null || true
}

_reset_decisions() {
    echo "run_index,run_label,mode,workload,timestamp,path,offset,size,phase,confidence,decay_rate,prefetch,prefetch_offset,prefetch_size,prefetch_depth" > "$LOG_DECISIONS"
}

_prefetch_rate() {
    python3 -c "
import csv, sys
rows = list(csv.DictReader(open('$LOG_DECISIONS')))
if not rows:
    print('0.000')
    sys.exit(0)
rate = sum(1 for r in rows if r.get('prefetch','0') == '1') / len(rows)
print(f'{rate:.3f}')
"
}

_avg_confidence() {
    python3 -c "
import csv, sys
rows = list(csv.DictReader(open('$LOG_DECISIONS')))
if not rows:
    print('0.000')
    sys.exit(0)
vals = [float(r['confidence']) for r in rows if r.get('confidence','')]
print(f'{sum(vals)/len(vals):.3f}' if vals else '0.000')
"
}

trap '_unmount_jazzyfs' EXIT

echo "[Platform] $PLATFORM"
echo "[Output]   $OUT_CSV"
echo ""

# Write CSV header
echo "threshold,workload,run,wall_time,prefetch_rate,avg_confidence" > "$OUT_CSV"

for threshold in "${THRESHOLDS[@]}"; do
    echo "=============================="
    echo " Threshold: $threshold"
    echo "=============================="

    for workload in "${WORKLOADS[@]}"; do
        for run in $(seq 1 $RUNS); do

            _reset_decisions
            _mount_jazzyfs "$threshold"

            start=$(python3 -c "import time; print(time.time())")
            bash "$(_workload_script "$workload")"
            end=$(python3 -c "import time; print(time.time())")

            wall_time=$(python3 -c "print(f'{${end} - ${start}:.4f}')" 2>/dev/null || \
                python3 -c "print(round($end - $start, 4))")
            prefetch_rate=$(_prefetch_rate)
            avg_conf=$(_avg_confidence)

            echo "  [t=$threshold] $workload run $run  time=${wall_time}s  prefetch=${prefetch_rate}  conf=${avg_conf}"
            echo "${threshold},${workload},${run},${wall_time},${prefetch_rate},${avg_conf}" >> "$OUT_CSV"

            _unmount_jazzyfs
            JAZZYFS_PID=
            sleep 1
        done
    done
done

trap - EXIT

echo ""
echo "[DONE] Threshold sweep complete."
echo "Results saved to: $OUT_CSV"
