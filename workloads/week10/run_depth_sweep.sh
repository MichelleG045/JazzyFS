#!/usr/bin/env bash
set -euo pipefail

# Week 10: Prefetch depth sweep across all 6 workloads. Works on Linux and macOS.
# Auto-detects platform and writes to results/week10/linux/ or results/week10/apfs/.
# Mounts and remounts JazzyFS for each depth so JAZZYFS_PREFETCH_DEPTH takes effect.
# Usage: bash workloads/week10/run_depth_sweep.sh [source_dir] [mount_point]

SOURCE_DIR="${1:-source_data}"
MOUNT_DIR="${2:-mount}"
JAZZYFS="source/jazzyfs_min.py"

if [[ "$(uname)" == "Darwin" ]]; then PLATFORM="apfs"; else PLATFORM="linux"; fi

DEPTHS=(1 2 4 8)
WORKLOADS=("sequential" "random" "phase_change" "sqlite_workload" "tar_workload" "python_import")
JAZZYFS_PID=

_workload_script() {
    local w=$1
    if [[ -f "workloads/synthetic/${w}.sh" ]]; then
        echo "workloads/synthetic/${w}.sh"
    else
        echo "workloads/real/${w}.sh"
    fi
}

_mount() {
    local depth=$1
    mkdir -p "$MOUNT_DIR"
    JAZZYFS_MODE=adaptive JAZZYFS_SOUND=0 JAZZYFS_PREFETCH_DEPTH=$depth \
        python3 "$JAZZYFS" "$SOURCE_DIR" "$MOUNT_DIR" &
    JAZZYFS_PID=$!
    sleep 2
    echo "[JazzyFS] Mounted adaptive depth=$depth (PID=$JAZZYFS_PID)"
}

_unmount() {
    if [[ "$(uname)" == "Darwin" ]]; then
        umount "$MOUNT_DIR" 2>/dev/null || diskutil unmount "$MOUNT_DIR" 2>/dev/null || true
    else
        fusermount -u "$MOUNT_DIR" 2>/dev/null || umount "$MOUNT_DIR" 2>/dev/null || true
    fi
    [[ -n "$JAZZYFS_PID" ]] && wait $JAZZYFS_PID 2>/dev/null || true
    echo "[JazzyFS] Unmounted"
}

trap '_unmount' EXIT

mkdir -p "results/week10/${PLATFORM}/depth"

echo "[Platform] $PLATFORM"

for depth in "${DEPTHS[@]}"; do
    OUTPUT="results/week10/${PLATFORM}/depth/jazzyfs_adaptive_depth${depth}_timing.csv"
    echo "workload,run,real_sec,user_sec,sys_sec" > "$OUTPUT"

    _mount "$depth"

    for workload in "${WORKLOADS[@]}"; do
        echo "  Running $workload..."
        for run in $(seq 1 20); do
            result=$( { time bash "$(_workload_script "$workload")"; } 2>&1 )

            real=$(echo "$result" | grep real | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')
            user=$(echo "$result" | grep user | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')
            sys=$(echo "$result"  | grep sys  | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')

            echo "$workload,$run,$real,$user,$sys" >> "$OUTPUT"
            echo "    Run $run: real=${real}s"

            sleep 2
        done
    done

    _unmount
    JAZZYFS_PID=
    echo "[OK] Depth $depth saved to $OUTPUT"
done

trap - EXIT

echo "[DONE] Week 10 depth sweep complete."
