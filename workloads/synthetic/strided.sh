#!/usr/bin/env bash
set -euo pipefail

# Strided workload: reads 4 KB at alternating stride offsets (+6144, +10240).
#
# Neither stride equals the read size (4096), so one-block lookahead always
# prefetches the wrong offset. JazzyFS stride detection identifies the
# repeating delta pattern after 5 reads and prefetches the correct offset.
#
# Expected results:
#   none mode:     0% prefetch rate (no prefetch issued)
#   baseline mode: 100% prefetch rate, ~0% accuracy (wrong offset every time)
#   adaptive mode: ~100% prefetch rate after warmup, ~100% accuracy

python3 - <<'PYEOF'
import os

path = "mount/big.txt"
stride_a = 6144
stride_b = 10240
read_size = 4096
n_reads   = 200

file_size = os.path.getsize(path)
with open(path, "rb") as f:
    offset = 0
    i = 0
    while i < n_reads and offset + read_size <= file_size:
        f.seek(offset)
        f.read(read_size)
        stride = stride_a if i % 2 == 0 else stride_b
        offset += stride
        i += 1
PYEOF
