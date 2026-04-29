#!/usr/bin/env bash
set -euo pipefail

# Full end-to-end JazzyFS experiment pipeline.
# Runs all experiments, generates summaries, and produces thesis figures.
# Usage: bash Experiments/run_all.sh [source_dir] [mount_point]
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

echo "[1/9] Main experiments (access + decision logs)..."
bash Experiments/run_experiments.sh "$SOURCE_DIR" "$MOUNT_DIR"

echo ""
echo "[2/9] Native timing baseline..."
bash Experiments/run_native_timing.sh "$SOURCE_DIR" "$MOUNT_DIR"

echo ""
echo "[3/9] JazzyFS timing — mode: none..."
bash Experiments/run_jazzyfs_timing.sh none "$SOURCE_DIR" "$MOUNT_DIR"

echo ""
echo "[4/9] JazzyFS timing — mode: baseline..."
bash Experiments/run_jazzyfs_timing.sh baseline "$SOURCE_DIR" "$MOUNT_DIR"

echo ""
echo "[5/9] JazzyFS timing — mode: adaptive..."
bash Experiments/run_jazzyfs_timing.sh adaptive "$SOURCE_DIR" "$MOUNT_DIR"

echo ""
echo "[6/9] Confidence threshold sweep..."
bash Experiments/run_threshold_sweep.sh "$SOURCE_DIR" "$MOUNT_DIR"

echo ""
echo "[7/9] Summarizing results and generating figures..."
python3 Experiments/result_summary.py
python3 Experiments/plot_results.py

echo ""
echo "[8/9] Threshold sweep analysis..."
python3 source/threshold_sweep_analysis.py

echo ""
echo "[9/9] Trajectory classification, decay rate, and stride accuracy analysis..."
python3 source/trajectory_classification.py
python3 source/decay_rate_analysis.py
python3 source/stride_accuracy_analysis.py

echo ""
echo "========================================"
echo "  Pipeline complete."
if [[ "$(uname)" == "Darwin" ]]; then
    echo "  Results in results/apfs/"
else
    echo "  Results in results/linux/"
fi
echo "========================================"
