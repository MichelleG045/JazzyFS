#!/usr/bin/env bash
set -euo pipefail

# Creates test data in source_data/ for new workloads.
# Run this once on the server before running experiments.

SOURCE_DIR="${1:-source_data}"
mkdir -p "$SOURCE_DIR"

echo "[1/3] Creating big.txt for sequential/random/phase_change workloads..."
dd if=/dev/urandom bs=1M count=100 of="$SOURCE_DIR/big.txt" status=none
echo "  Created big.txt (100 MB)"

echo "[2/3] Creating tar archive..."
mkdir -p /tmp/jazzyfs_archive_src
for i in $(seq 1 100); do
    dd if=/dev/urandom bs=4096 count=4 of="/tmp/jazzyfs_archive_src/file_${i}.bin" status=none
done
tar -cf "$SOURCE_DIR/archive.tar" -C /tmp/jazzyfs_archive_src .
rm -rf /tmp/jazzyfs_archive_src
echo "  Created archive.tar with 100 files (4 x 4KB each)"

echo "[3/3] Creating Python module files..."
mkdir -p "$SOURCE_DIR/pyfiles"
for i in $(seq 1 200); do
    cat > "$SOURCE_DIR/pyfiles/module_${i}.py" <<PYEOF
import os
import sys

CLASS_CONST = $i

def function_$i(x):
    return x * $i

def helper_$i(data):
    return [function_$i(d) for d in data]
PYEOF
done
echo "  Created 200 Python module files"

echo "[OK] Test data ready in $SOURCE_DIR/"
