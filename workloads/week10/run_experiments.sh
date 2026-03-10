#!/usr/bin/env bash
set -euo pipefail

# Week 10: Full experiment runner — works on Linux (ext4) and macOS (APFS).
# Auto-detects platform and writes to results/week10/linux/ or results/week10/apfs/.
# Produces: results/week10/{platform}/{workload}/{workload}_{mode}_run{n}/access.csv + decisions.csv
#
# Usage: bash workloads/week10/run_experiments.sh [source_dir] [mount_point]
# Example: bash workloads/week10/run_experiments.sh source_data mount
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
WORKLOADS=("sequential" "random" "phase_change" "sqlite_workload" "tar_workload" "python_import")
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
    echo "seq,timestamp,path,offset,size" > "$LOG_ACCESS"
    echo "timestamp,mode,path,offset,size,phase,confidence,prefetch,prefetch_offset,prefetch_size,prefetch_depth" > "$LOG_DECISIONS"
}

_mount_jazzyfs() {
    local mode=$1
    mkdir -p "$MOUNT_DIR"
    JAZZYFS_MODE=$mode JAZZYFS_SOUND=0 python3 "$JAZZYFS" "$SOURCE_DIR" "$MOUNT_DIR" &
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
    [[ -n "$JAZZYFS_PID" ]] && wait $JAZZYFS_PID 2>/dev/null || true
    echo "[JazzyFS] Unmounted"
}

trap '_unmount_jazzyfs' EXIT

echo "[Platform] $PLATFORM"

for mode in "${MODES[@]}"; do
    echo ""
    echo "=============================="
    echo " Mode: $mode"
    echo "=============================="

    _mount_jazzyfs "$mode"

    for workload in "${WORKLOADS[@]}"; do
        for run in $(seq 1 $RUNS); do
            OUT_DIR="results/week10/${PLATFORM}/${workload}/${workload}_${mode}_run${run}"
            mkdir -p "$OUT_DIR"

            _reset_logs

            echo "  [$mode] $workload run $run..."
            bash "$(_workload_script "$workload")"

            cp "$LOG_ACCESS"    "$OUT_DIR/access.csv"
            cp "$LOG_DECISIONS" "$OUT_DIR/decisions.csv"
            echo "    Saved to $OUT_DIR"

            sleep 2
        done
    done

    _unmount_jazzyfs
    JAZZYFS_PID=
done

trap - EXIT

echo ""
echo "[DONE] Week 10 experiments complete."
echo "Results in results/week10/${PLATFORM}/"
