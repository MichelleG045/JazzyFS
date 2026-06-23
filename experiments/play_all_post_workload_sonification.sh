#!/usr/bin/env bash
set -euo pipefail

# Run the full post-workload sonification listening test.
# Each test runs the workload, renders a fresh WAV from that run's decision log,
# plays it in the terminal, and refreshes the archive WAVs in:
#   results/apfs/sonification/audio/Post workloads/

REPO="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE_DIR="$REPO/results/apfs/sonification/audio/Post workloads"

MODES=(none baseline adaptive)
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

total=$((${#MODES[@]} * ${#WORKLOADS[@]}))
run=0

echo "[Start] Full post-workload sonification test"
echo "[Output] $ARCHIVE_DIR/"
mkdir -p "$ARCHIVE_DIR"
find "$ARCHIVE_DIR" -maxdepth 1 -type f -name '*.wav' -delete
echo "[Clean] Removed old post-workload archive WAV files."

for mode in "${MODES[@]}"; do
    for workload in "${WORKLOADS[@]}"; do
        run=$((run + 1))
        echo ""
        echo "========================================"
        echo "[$run/$total] workload=$workload mode=$mode"
        echo "========================================"
        OUTPUT_DIR="$ARCHIVE_DIR" bash "$REPO/experiments/play_post_workload_sonification.sh" "$workload" "$mode"
    done
done

echo ""
echo "[Done] Full post-workload sonification test complete."
echo "[Output] $ARCHIVE_DIR/"
