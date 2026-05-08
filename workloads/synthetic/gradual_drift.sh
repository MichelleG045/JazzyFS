#!/usr/bin/env bash
set -euo pipefail

# Gradual drift workload: mostly sequential reads with occasional small skips.
# This creates low, sustained confidence decay rather than one sharp phase
# transition spike. Used as the contrast case for Claim 1.

python3 - <<'PYEOF'
import os

path = "mount/big.txt"
read_size = 4096
skip_every = 8
skip_size = 4096
max_reads = 160

size = os.path.getsize(path)
offset = 0

with open(path, "rb") as f:
    for i in range(max_reads):
        if offset + read_size > size:
            break
        f.seek(offset)
        f.read(read_size)
        offset += read_size
        if i and i % skip_every == 0:
            offset += skip_size
PYEOF
