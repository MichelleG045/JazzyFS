#!/usr/bin/env bash
set -euo pipefail

# Week 10: Native timing — no JazzyFS, direct filesystem. Works on Linux and macOS.
# Auto-detects platform and writes to results/week10/linux/ or results/week10/apfs/.
# Usage: bash workloads/week10/run_native_timing.sh [source_dir] [mount_point]

SOURCE_DIR="${1:-source_data}"
MOUNT_DIR="${2:-mount}"

if [[ "$(uname)" == "Darwin" ]]; then PLATFORM="apfs"; else PLATFORM="linux"; fi

OUTPUT="results/week10/${PLATFORM}/native/native_timing.csv"
mkdir -p "results/week10/${PLATFORM}/native"

# Workload scripts read from mount/. For native timing, symlink mount → source_data
# so they access files directly without going through JazzyFS.
# mount/ may exist as an empty dir (FUSE mount point) — remove it first if so.
SYMLINKED=0
if [[ ! -e "$MOUNT_DIR" ]] || [[ -d "$MOUNT_DIR" && -z "$(ls -A "$MOUNT_DIR" 2>/dev/null)" ]]; then
    [[ -d "$MOUNT_DIR" ]] && rmdir "$MOUNT_DIR" 2>/dev/null || true
    ln -s "$(pwd)/$SOURCE_DIR" "$MOUNT_DIR"
    SYMLINKED=1
fi

# Clean up symlink on exit (even if a workload fails)
trap '[[ "$SYMLINKED" == "1" ]] && rm -f "$MOUNT_DIR" && mkdir -p "$MOUNT_DIR"' EXIT

echo "workload,run,real_sec,user_sec,sys_sec" > "$OUTPUT"

WORKLOADS=("sequential" "random" "phase_change" "sqlite_workload" "tar_workload" "python_import")

_workload_script() {
    local w=$1
    if [[ -f "workloads/synthetic/${w}.sh" ]]; then
        echo "workloads/synthetic/${w}.sh"
    else
        echo "workloads/real/${w}.sh"
    fi
}

for workload in "${WORKLOADS[@]}"; do
    echo "[Native] Running $workload..."
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

echo "[Platform] $PLATFORM — saved to $OUTPUT"
