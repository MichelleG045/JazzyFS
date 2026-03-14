#!/usr/bin/env bash
set -euo pipefail

# Week 10: JazzyFS timing for a given mode. Works on Linux and macOS.
# Auto-detects platform and writes to results/week10/linux/ or results/week10/apfs/.
# Mounts JazzyFS in the specified mode, runs all workloads, then unmounts.
# Usage: bash workloads/week10/run_jazzyfs_timing.sh <mode> [source_dir] [mount_point]
# Example: bash workloads/week10/run_jazzyfs_timing.sh adaptive

if [ -z "${1:-}" ]; then
    echo "Usage: bash workloads/week10/run_jazzyfs_timing.sh <mode> [source_dir] [mount_point]"
    echo "Example: bash workloads/week10/run_jazzyfs_timing.sh adaptive"
    exit 1
fi

MODE=$1
SOURCE_DIR="${2:-source_data}"
MOUNT_DIR="${3:-mount}"
JAZZYFS="source/jazzyfs_min.py"

if [[ "$(uname)" == "Darwin" ]]; then PLATFORM="apfs"; else PLATFORM="linux"; fi

OUTPUT="results/week10/${PLATFORM}/native/jazzyfs_${MODE}_timing.csv"
mkdir -p "results/week10/${PLATFORM}/native"

WORKLOADS=("sequential" "random" "phase_change" "tar_workload" "python_import" "cache_lookup_workload")

_workload_script() {
    local w=$1
    if [[ -f "workloads/synthetic/${w}.sh" ]]; then
        echo "workloads/synthetic/${w}.sh"
    else
        echo "workloads/real/${w}.sh"
    fi
}

_unmount() {
    if [[ "$(uname)" == "Darwin" ]]; then
        umount "$MOUNT_DIR" 2>/dev/null || diskutil unmount "$MOUNT_DIR" 2>/dev/null || true
    else
        fusermount -u "$MOUNT_DIR" 2>/dev/null || umount "$MOUNT_DIR" 2>/dev/null || true
    fi
    wait $JAZZYFS_PID 2>/dev/null || true
}

# Mount JazzyFS in specified mode
mkdir -p "$MOUNT_DIR"
JAZZYFS_MODE=$MODE JAZZYFS_SOUND=0 python3 "$JAZZYFS" "$SOURCE_DIR" "$MOUNT_DIR" &
JAZZYFS_PID=$!
sleep 2
echo "[JazzyFS] Mounted (PID=$JAZZYFS_PID, mode=$MODE)"

trap '_unmount' EXIT

echo "workload,run,real_sec,user_sec,sys_sec" > "$OUTPUT"

for workload in "${WORKLOADS[@]}"; do
    echo "[JazzyFS $MODE] Running $workload..."
    for run in $(seq 1 20); do
        result=$( { time bash "$(_workload_script "$workload")"; } 2>&1 )

        real=$(echo "$result" | grep real | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')
        user=$(echo "$result" | grep user | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')
        sys=$(echo "$result"  | grep sys  | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}')

        echo "$workload,$run,$real,$user,$sys" >> "$OUTPUT"
        echo "  Run $run: real=${real}s"

        sleep 2
    done
done

echo "[Platform] $PLATFORM — JazzyFS $MODE timing saved to $OUTPUT"
