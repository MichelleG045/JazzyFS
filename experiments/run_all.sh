#!/usr/bin/env bash
set -euo pipefail

# Full end-to-end JazzyFS experiment pipeline.
# Runs all experiments, generates summaries, and produces thesis figures.
# Usage: bash experiments/run_all.sh [source_dir] [mount_point]
#
# Prerequisites:
#   1. bash workloads/setup/setup_test_data.sh
#   2. pip install fusepy matplotlib numpy

SOURCE_DIR="${1:-source_data}"
MOUNT_DIR="${2:-mount}"

echo "========================================"
echo "  JazzyFS Full Experiment Pipeline"
echo "========================================"
echo ""

echo "[1/5] Main experiments (access + decision logs)..."
bash experiments/run_experiments.sh "$SOURCE_DIR" "$MOUNT_DIR"

echo ""
echo "[2/5] Interleaved timing baseline + JazzyFS modes..."
bash experiments/run_timing_interleaved.sh "$SOURCE_DIR" "$MOUNT_DIR"

echo ""
echo "[3/5] Seek suppression threshold sweep..."
bash experiments/run_seek_suppression_sweep.sh "$SOURCE_DIR" "$MOUNT_DIR"

echo ""
echo "[4/5] Summarizing results and generating figures..."
python3 experiments/result_summary.py
python3 experiments/plot_results.py
python3 experiments/generate_sonification_plots.py

echo ""
echo "[5/5] Running claim analyses..."
python3 experiments/decay_rate_analysis.py
python3 experiments/seek_analysis.py

echo ""
echo "========================================"
echo "  Pipeline complete."
if [[ "$(uname)" == "Darwin" ]]; then
    echo "  Results in results/apfs/"
else
    echo "  Results in results/linux/"
fi
echo "========================================"
