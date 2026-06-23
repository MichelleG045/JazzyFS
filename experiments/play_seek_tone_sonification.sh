#!/usr/bin/env bash
set -euo pipefail

# Run one JazzyFS workload, render a fresh seek-tone WAV from that run's
# decision log, then play the fresh WAV.
#
# Usage:
#   bash experiments/play_seek_tone_sonification.sh [workload] [mode]
#
# Examples:
#   bash experiments/play_seek_tone_sonification.sh random adaptive
#   bash experiments/play_seek_tone_sonification.sh cache_lookup_workload adaptive

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="${SOURCE:-$REPO/source_data}"
MOUNT="${MOUNT:-$REPO/mount}"
PYTHON_BIN="${PYTHON:-$REPO/venv/bin/python}"
LOG_DIR="$REPO/logs"
LOG_ACCESS="$LOG_DIR/access.csv"
LOG_DECISIONS="$LOG_DIR/decisions.csv"
RUN_LOG="/tmp/jazzyfs_seek_tone_sonification.log"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO/results/apfs/sonification/audio/seek_tones}"

WORKLOAD="${1:-random}"
MODE="${2:-adaptive}"

workload_script() {
    local workload="$1"
    if [[ -f "$REPO/workloads/synthetic/${workload}.sh" ]]; then
        echo "$REPO/workloads/synthetic/${workload}.sh"
    elif [[ -f "$REPO/workloads/real/${workload}.sh" ]]; then
        echo "$REPO/workloads/real/${workload}.sh"
    else
        echo "[ERROR] Unknown workload: $workload" >&2
        exit 1
    fi
}

reset_logs() {
    mkdir -p "$LOG_DIR"
    echo "run_index,run_label,mode,workload,seq,timestamp,path,offset,size" > "$LOG_ACCESS"
    echo "run_index,run_label,mode,workload,timestamp,path,offset,size,phase,confidence,decay_rate,seek_delta,prefetch,prefetch_offset,prefetch_size,prefetch_depth,cache_hit,false_negative" > "$LOG_DECISIONS"
}

unmount_jazzyfs() {
    if [[ -d "$MOUNT" ]]; then
        umount "$MOUNT" 2>/dev/null || diskutil unmount "$MOUNT" 2>/dev/null || true
    fi
    if [[ -n "${JAZZYFS_PID:-}" ]]; then
        wait "$JAZZYFS_PID" 2>/dev/null || true
    fi
}

trap unmount_jazzyfs EXIT

cd "$REPO"
SCRIPT="$(workload_script "$WORKLOAD")"
RUN_LABEL="terminal_seek_${MODE}_${WORKLOAD}"
OUT_WAV="$OUTPUT_DIR/${MODE}_${WORKLOAD}_seek_tones.wav"

reset_logs
mkdir -p "$MOUNT" "$OUTPUT_DIR"
unmount_jazzyfs
rm -f "$OUT_WAV"

echo "[JazzyFS] Starting $WORKLOAD in $MODE mode for seek-tone rendering"
echo "[JazzyFS] Audio is off during the workload; a fresh seek-tone WAV will play after the run."

JAZZYFS_MODE="$MODE" \
JAZZYFS_SOUND=0 \
JAZZYFS_SEEK_SOUND=0 \
JAZZYFS_RUN_INDEX=1 \
JAZZYFS_RUN_LABEL="$RUN_LABEL" \
JAZZYFS_WORKLOAD="$WORKLOAD" \
    "$PYTHON_BIN" -u "$REPO/source/jazzyfs.py" "$SOURCE" "$MOUNT" \
    > "$RUN_LOG" 2>&1 &
JAZZYFS_PID=$!

for _ in $(seq 1 40); do
    [[ -e "$MOUNT/big.txt" ]] && break
    sleep 0.25
done

if [[ ! -e "$MOUNT/big.txt" ]]; then
    echo "[ERROR] Mount did not become ready. Last JazzyFS log lines:"
    tail -20 "$RUN_LOG" || true
    exit 1
fi

echo "[Workload] Running $WORKLOAD..."
bash "$SCRIPT"
echo "[Workload] Finished. Rendering fresh seek-tone audio..."

"$PYTHON_BIN" "$REPO/experiments/generate_seek_tone_audio.py" \
    --decisions "$LOG_DECISIONS" \
    --output "$OUT_WAV"

echo "[Play] $OUT_WAV"
if command -v afplay >/dev/null 2>&1; then
    afplay "$OUT_WAV"
elif command -v play >/dev/null 2>&1; then
    play "$OUT_WAV"
else
    echo "[WARN] No terminal audio player found. Open this file manually:"
    echo "$OUT_WAV"
fi
echo "[Done] Fresh seek-tone playback complete."

unmount_jazzyfs
trap - EXIT
