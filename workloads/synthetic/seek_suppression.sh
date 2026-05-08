#!/usr/bin/env bash
set -euo pipefail

# Seek suppression workload: sequential bursts separated by jumps larger than
# JazzyFS's default 1 MB seek threshold. Used to validate Claim 2.

python3 - <<'PYEOF'
import os

path = "mount/big.txt"
read_size = 4096
burst_reads = 6
seek_jump = 2 * 1024 * 1024
bursts = 12

size = os.path.getsize(path)
offset = 0

with open(path, "rb") as f:
    for _ in range(bursts):
        for _ in range(burst_reads):
            if offset + read_size > size:
                raise SystemExit
            f.seek(offset)
            f.read(read_size)
            offset += read_size
        offset += seek_jump
PYEOF
