#!/usr/bin/env bash
set -euo pipefail

# Cache lookup workload: simulates a database/cache reading random records by offset
# Real-world analogue: key-value store, LRU cache, or B-tree index lookups
# Access pattern: PURELY IRREGULAR — 200 random seeks across big.txt, no sequential runs

python3 - mount/big.txt <<'PYEOF'
import sys, os, random, time

path = sys.argv[1]
record_size = 4096  # page-aligned — prevents kernel read coalescing
size = os.path.getsize(path)
num_records = size // record_size

random.seed(77)
lookups = random.sample(range(num_records), min(200, num_records))

with open(path, 'rb') as f:
    for rec in lookups:
        f.seek(rec * record_size)
        f.read(record_size)
        time.sleep(0.01)  # small pause so FUSE sees each read as distinct
PYEOF
