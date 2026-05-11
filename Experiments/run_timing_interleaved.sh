#!/usr/bin/env bash
set -euo pipefail

# Interleaved timing experiment — matches run_experiments.sh loop order and cache policy.
# Loop: workload → run → mode (native, none, baseline, adaptive)
# Cache is dropped before every run. JazzyFS is mounted/unmounted fresh per run.
# Outputs: results/{platform}/native/{mode}_timing_interleaved.csv
#
# Usage: bash Experiments/run_timing_interleaved.sh [source_dir] [mount_point]

SOURCE_DIR="${1:-source_data}"
MOUNT_DIR="${2:-mount}"
JAZZYFS="source/jazzyfs_min.py"

if [[ "$(uname)" == "Darwin" ]]; then PLATFORM="apfs"; else PLATFORM="linux"; fi

OUTDIR="results/${PLATFORM}/native"
mkdir -p "$OUTDIR"

WORKLOADS=("sequential" "random" "phase_change" "gradual_drift" "seek_suppression" "tar_workload" "python_import" "cache_lookup_workload")
MODES=("none" "baseline" "adaptive")
RUNS=20
JAZZYFS_PID=

_workload_script() {
    local w=$1
    if [[ -f "workloads/synthetic/${w}.sh" ]]; then
        echo "workloads/synthetic/${w}.sh"
    else
        echo "workloads/real/${w}.sh"
    fi
}

_drop_caches() {
    sync
    if [[ -w /proc/sys/vm/drop_caches ]]; then
        echo 3 > /proc/sys/vm/drop_caches
    elif command -v sudo &>/dev/null; then
        echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null 2>&1 || true
    fi
}

_mount_jazzyfs() {
    local mode=$1
    mkdir -p "$MOUNT_DIR"
    JAZZYFS_MODE="$mode" JAZZYFS_SOUND=0 \
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
    JAZZYFS_PID=
}

_parse_time() {
    echo "$1" | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}'
}

trap '_unmount_jazzyfs' EXIT

# Write headers
echo "workload,run,mode,real_sec,user_sec,sys_sec" > "$OUTDIR/timing_interleaved.csv"

# Mirror native timing with the same interleaved loop so comparisons are fair.
# Native uses a symlink so workload scripts read source_data directly.
SYMLINKED=0
_setup_native_symlink() {
    if [[ ! -e "$MOUNT_DIR" ]] || [[ -d "$MOUNT_DIR" && -z "$(ls -A "$MOUNT_DIR" 2>/dev/null)" ]]; then
        [[ -d "$MOUNT_DIR" ]] && rmdir "$MOUNT_DIR" 2>/dev/null || true
        ln -s "$(pwd)/$SOURCE_DIR" "$MOUNT_DIR"
        SYMLINKED=1
    fi
}
_teardown_native_symlink() {
    if [[ "$SYMLINKED" == "1" ]]; then
        rm -f "$MOUNT_DIR"
        mkdir -p "$MOUNT_DIR"
        SYMLINKED=0
    fi
}

echo "[Platform] $PLATFORM"
echo "[Output]   $OUTDIR/timing_interleaved.csv"

for workload in "${WORKLOADS[@]}"; do
    echo ""
    echo "=============================="
    echo " Workload: $workload"
    echo "=============================="

    for run in $(seq 1 $RUNS); do

        # --- native ---
        _drop_caches
        _setup_native_symlink
        result=$( { time bash "$(_workload_script "$workload")"; } 2>&1 )
        _teardown_native_symlink
        real=$(_parse_time "$(echo "$result" | grep real)")
        user=$(_parse_time "$(echo "$result" | grep user)")
        sys=$(_parse_time  "$(echo "$result" | grep sys)")
        echo "$workload,$run,native,$real,$user,$sys" >> "$OUTDIR/timing_interleaved.csv"

        # --- FUSE modes ---
        for mode in "${MODES[@]}"; do
            _drop_caches
            _mount_jazzyfs "$mode"
            result=$( { time bash "$(_workload_script "$workload")"; } 2>&1 )
            _unmount_jazzyfs
            real=$(_parse_time "$(echo "$result" | grep real)")
            user=$(_parse_time "$(echo "$result" | grep user)")
            sys=$(_parse_time  "$(echo "$result" | grep sys)")
            echo "$workload,$run,$mode,$real,$user,$sys" >> "$OUTDIR/timing_interleaved.csv"
            echo "  [$mode] $workload run $run: real=${real}s"
            sleep 1
        done

    done
done

trap - EXIT

echo ""
echo "[DONE] Timing complete. Results in $OUTDIR/timing_interleaved.csv"
