#!/usr/bin/env bash
set -euo pipefail

# Creates test data in source_data/ for new workloads.
# Run this once on the server before running experiments.

SOURCE_DIR="${1:-source_data}"
mkdir -p "$SOURCE_DIR"

echo "[1/4] Creating big.txt for sequential/random/phase_change workloads..."
dd if=/dev/urandom bs=1M count=100 of="$SOURCE_DIR/big.txt" status=none
echo "  Created big.txt (100 MB)"

echo "[2/4] Creating SQLite database..."
python3 - <<EOF
import sqlite3, random
conn = sqlite3.connect("$SOURCE_DIR/test.db")
conn.execute("CREATE TABLE IF NOT EXISTS data (id INTEGER PRIMARY KEY, value REAL, label TEXT)")
conn.executemany("INSERT INTO data VALUES (?,?,?)",
    [(i, random.random() * 1000, f"item_{i}") for i in range(10000)])
conn.commit()
conn.close()
print("  Created test.db with 10000 rows")
EOF

echo "[3/4] Creating tar archive..."
mkdir -p /tmp/jazzyfs_archive_src
for i in $(seq 1 100); do
    dd if=/dev/urandom bs=4096 count=4 of="/tmp/jazzyfs_archive_src/file_${i}.bin" status=none
done
tar -cf "$SOURCE_DIR/archive.tar" -C /tmp/jazzyfs_archive_src .
rm -rf /tmp/jazzyfs_archive_src
echo "  Created archive.tar with 100 files (4 x 4KB each)"

echo "[4/4] Creating Python module files..."
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
