#!/usr/bin/env bash
set -euo pipefail

# Concurrent reader workload: multiple processes read simultaneously through JazzyFS mount
# Simulates multi-process or multi-threaded access (concurrent irregular access pattern)
# Reads are launched in parallel then waited on — appears as irregular to the phase detector

OFFSETS=(5 120 42 300 17 250 88 190 60 10 333 75 512 200 450 99 600 150 720 380)

for o in "${OFFSETS[@]}"; do
    dd if=mount/big.txt of=/dev/null bs=4096 skip="$o" count=1 status=none &
done

wait
