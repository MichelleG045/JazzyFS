#!/usr/bin/env bash
# Sonification test: all workloads × all modes
# Runs each combination, waits for audio playback to finish, then moves on.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
MOUNT="$REPO/mount"
SOURCE="$REPO/source_data"
VENV="$REPO/venv"
LOG_DIR="$REPO/logs"
LOG_ACCESS="$LOG_DIR/access.csv"
LOG_DECISIONS="$LOG_DIR/decisions.csv"
CURRENT_RUN_INDEX=""
CURRENT_RUN_LABEL=""
CURRENT_WORKLOAD=""
CURRENT_MODE=""

MODES=(none baseline adaptive)
WORKLOADS=(
    "synthetic/sequential.sh"
    "synthetic/random.sh"
    "synthetic/phase_change.sh"
    "real/python_import.sh"
    "real/tar_workload.sh"
    "real/cache_lookup_workload.sh"
)

# ---- helpers ----

reset_logs() {
    mkdir -p "$LOG_DIR"
    echo "run_index,run_label,mode,workload,seq,timestamp,path,offset,size" > "$LOG_ACCESS"
    echo "run_index,run_label,mode,workload,timestamp,fs_mode,path,offset,size,phase,confidence,prefetch,prefetch_offset,prefetch_size,prefetch_depth" > "$LOG_DECISIONS"
}

mount_jazzyfs() {
    local mode="$1"
    umount "$MOUNT" 2>/dev/null || true
    sleep 0.5
    JAZZYFS_MODE="$mode" \
        JAZZYFS_SOUND=1 \
        JAZZYFS_RUN_INDEX="$CURRENT_RUN_INDEX" \
        JAZZYFS_RUN_LABEL="$CURRENT_RUN_LABEL" \
        JAZZYFS_WORKLOAD="$CURRENT_WORKLOAD" \
        "$VENV/bin/python3" -u "$REPO/source/jazzyfs_min.py" "$SOURCE" "$MOUNT" \
        > /tmp/jazzyfs_test.log 2>&1 &
    JAZZYFS_PID=$!
    # Wait for mount to become accessible
    local tries=0
    until ls "$MOUNT" > /dev/null 2>&1 && [ "$(ls "$MOUNT" | wc -l)" -gt 0 ]; do
        sleep 0.3
        tries=$((tries + 1))
        if [ "$tries" -gt 30 ]; then
            echo "  [ERROR] Mount timed out"
            return 1
        fi
    done
}

unmount_jazzyfs() {
    umount "$MOUNT" 2>/dev/null || diskutil unmount force "$MOUNT" 2>/dev/null || true
    wait "$JAZZYFS_PID" 2>/dev/null || true
}

wait_for_playback() {
    # Wait for Python to log "Playback complete" (emitted after last note finishes)
    local elapsed=0
    until grep -q "\[JazzyFS\] Playback complete" /tmp/jazzyfs_test.log 2>/dev/null; do
        sleep 1
        elapsed=$((elapsed + 1))
        if [ "$elapsed" -gt 180 ]; then
            echo "  [WARN] Playback timeout — moving on"
            pkill -x play 2>/dev/null || true
            break
        fi
    done
    # Brief pause for the very last note's fade-out to finish
    sleep 0.5
}

# ---- main loop ----

total=$((${#MODES[@]} * ${#WORKLOADS[@]}))
run=0

reset_logs
echo "[Logs] Raw access log: $LOG_ACCESS"
echo "[Logs] Raw decision log: $LOG_DECISIONS"

for mode in "${MODES[@]}"; do
    for workload in "${WORKLOADS[@]}"; do
        run=$((run + 1))
        name=$(basename "$workload" .sh)
        CURRENT_RUN_INDEX="$run"
        CURRENT_WORKLOAD="$name"
        CURRENT_MODE="$mode"
        CURRENT_RUN_LABEL="$(printf '%02d_%s_%s' "$run" "$mode" "$name")"
        echo ""
        echo "════════════════════════════════════════"
        echo "  [$run/$total]  mode=$mode  workload=$name"
        echo "  run_label=$CURRENT_RUN_LABEL"
        echo "════════════════════════════════════════"

        mount_jazzyfs "$mode"
        echo "  [mounted] running workload..."

        (cd "$REPO" && bash "workloads/$workload") 2>/tmp/workload_err.log || true

        # Wait for idle detection (1s) + _analyze_and_play to print labels
        # cache_lookup does 200 random seeks so we wait up to 8s for labels to appear
        label_wait=0
        until grep -q "\[JazzyFS\] Phase pattern" /tmp/jazzyfs_test.log 2>/dev/null || [ "$label_wait" -ge 16 ]; do
            sleep 0.5
            label_wait=$((label_wait + 1))
        done
        echo "  [sonification summary — music starts in ~5s]"
        grep -E "\[JazzyFS\] (Phase pattern|avg_confidence|Root|▶|Starting)" /tmp/jazzyfs_test.log 2>/dev/null | tail -7 | while IFS= read -r line; do
            echo "    $line"
        done || true
        # If still no labels, show raw log tail for debugging
        if ! grep -q "\[JazzyFS\] Phase pattern" /tmp/jazzyfs_test.log 2>/dev/null; then
            echo "  [WARN] No sonification triggered — last log lines:"
            tail -5 /tmp/jazzyfs_test.log 2>/dev/null | while IFS= read -r line; do echo "    $line"; done || true
            [ -s /tmp/workload_err.log ] && echo "  [workload stderr]: $(cat /tmp/workload_err.log)" || true
        fi

        echo "  [waiting for playback to finish...]"
        wait_for_playback
        echo "  [ok] done"

        unmount_jazzyfs
    done
done

echo ""
echo "════════════════════════════════════════"
echo "  All $total sonification tests complete"
echo "════════════════════════════════════════"
