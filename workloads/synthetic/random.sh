#!/usr/bin/env bash
set -euo pipefail

# Fixed offsets (deterministic). Each reads 4KB at that position.
# Adjust numbers if your file is smaller; these assume big.txt is at least a few MB.
OFFSETS=(5 120 42 300 17 250 88 190 60 10 275 33 160 210 95)

for o in "${OFFSETS[@]}"; do
  dd if=mount/big.txt of=/dev/null bs=4096 skip="$o" count=1 status=none
done