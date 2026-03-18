#!/usr/bin/env bash
set -euo pipefail

# Full experiment runner — works on Linux (ext4) and macOS (APFS).
# Auto-detects platform and writes to results/linux/ or results/apfs/.
# Produces: results/{platform}/{workload}/{workload}_{mode}_run{n}/access.csv + decisions.csv
#
# Usage: bash Experiments/run_experiments.sh [source_dir] [mount_point]
# Example: bash Experiments/run_experiments.sh source_data mount
#
# Prerequisites:
#   1. Run workloads/setup/setup_test_data.sh first to create source_data/
#   2. Install fusepy: pip3 install fusepy
#   3. macOS: macFUSE must be installed. Linux: libfuse2 must be installed.

SOURCE_DIR="${1:-source_data}"
MOUNT_DIR="${2:-mount}"
JAZZYFS="source/jazzyfs_min.py"
LOG_ACCESS="logs/access.csv"
LOG_DECISIONS="logs/decisions.csv"

if [[ "$(uname)" == "Darwin" ]]; then PLATFORM="apfs"; else PLATFORM="linux"; fi

MODES=("none" "baseline" "adaptive")
WORKLOADS=("sequential" "random" "phase_change" "tar_workload" "python_import" "cache_lookup_workload")
RUNS=20
JAZZYFS_PID=

mkdir -p logs

_workload_script() {
    local w=$1
    if [[ -f "workloads/synthetic/${w}.sh" ]]; then
        echo "workloads/synthetic/${w}.sh"
    else
        echo "workloads/real/${w}.sh"
    fi
}

_reset_logs() {
    echo "run_index,run_label,mode,workload,seq,timestamp,path,offset,size" > "$LOG_ACCESS"
    echo "run_index,run_label,mode,workload,timestamp,path,offset,size,phase,confidence,prefetch,prefetch_offset,prefetch_size,prefetch_depth" > "$LOG_DECISIONS"
}

_mount_jazzyfs() {
    local mode=$1
    local run_index=$2
    local workload=$3
    local run_label=$4
    mkdir -p "$MOUNT_DIR"
    JAZZYFS_MODE="$mode" \
        JAZZYFS_SOUND=0 \
        JAZZYFS_RUN_INDEX="$run_index" \
        JAZZYFS_RUN_LABEL="$run_label" \
        JAZZYFS_WORKLOAD="$workload" \
        python3 "$JAZZYFS" "$SOURCE_DIR" "$MOUNT_DIR" &
    JAZZYFS_PID=$!
    sleep 2
    echo "[JazzyFS] Mounted (PID=$JAZZYFS_PID, mode=$mode)"
}

_unmount_jazzyfs() {
    if [[ "$(uname)" == "Darwin" ]]; then
        umount "$MOUNT_DIR" 2>/dev/null || diskutil unmount "$MOUNT_DIR" 2>/dev/null || true
    else
        fusermount -u "$MOUNT_DIR" 2>/dev/null || umount "$MOUNT_DIR" 2>/dev/null || true
    fi
    [[ -n "$JAZZYFS_PID" ]] && wait "$JAZZYFS_PID" 2>/dev/null || true
    echo "[JazzyFS] Unmounted"
}

trap '_unmount_jazzyfs' EXIT

echo "[Platform] $PLATFORM"

run_index=0

for mode in "${MODES[@]}"; do
    echo ""
    echo "=============================="
    echo " Mode: $mode"
    echo "=============================="

    for workload in "${WORKLOADS[@]}"; do
        for run in $(seq 1 $RUNS); do
            run_index=$((run_index + 1))
            run_label="$(printf '%03d_%s_%s_run%02d' "$run_index" "$mode" "$workload" "$run")"
            OUT_DIR="results/${PLATFORM}/${workload}/${mode}/run${run}"
            mkdir -p "$OUT_DIR"

            _reset_logs
            _mount_jazzyfs "$mode" "$run_index" "$workload" "$run_label"

            echo "  [$mode] $workload run $run (label=$run_label)..."
            bash "$(_workload_script "$workload")"

            cp "$LOG_ACCESS"    "$OUT_DIR/access.csv"
            cp "$LOG_DECISIONS" "$OUT_DIR/decisions.csv"
            echo "    Saved to $OUT_DIR"

            _unmount_jazzyfs
            JAZZYFS_PID=
            sleep 1
        done
    done
done

trap - EXIT

echo ""
echo "[DONE] Experiments complete."
echo "Results in results/${PLATFORM}/"
