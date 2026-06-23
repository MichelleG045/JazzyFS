#!/usr/bin/env bash
set -euo pipefail

# Run all adaptive-mode seek-tone sonification tests.
# At startup, old seek-tone WAVs are removed. Each workload then runs fresh,
# renders a new seek-tone WAV from that run's decision log, and plays it.

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$REPO/results/apfs/sonification/audio/seek_tones"
MODE="${MODE:-adaptive}"

WORKLOADS=(
    sequential
    random
    phase_change
    gradual_drift
    seek_suppression
    tar_workload
    python_import
    cache_lookup_workload
)

total=${#WORKLOADS[@]}
run=0

echo "[Start] Full seek-tone sonification test"
echo "[Mode] $MODE"
echo "[Output] $OUT_DIR/"
mkdir -p "$OUT_DIR"
find "$OUT_DIR" -maxdepth 1 -type f -name '*.wav' -delete
echo "[Clean] Removed old seek-tone WAV files."

for workload in "${WORKLOADS[@]}"; do
    run=$((run + 1))
    echo ""
    echo "========================================"
    echo "[$run/$total] workload=$workload mode=$MODE"
    echo "========================================"
    OUTPUT_DIR="$OUT_DIR" bash "$REPO/experiments/play_seek_tone_sonification.sh" "$workload" "$MODE"
done

echo ""
echo "[Done] Full seek-tone sonification test complete."
echo "[Output] $OUT_DIR/"
