#!/usr/bin/env bash
set -euo pipefail

# Phase 1: sequential
cat mount/big.txt > /dev/null

# Phase 2: random-ish deterministic offsets
OFFSETS=(5 120 42 300 17 250 88 190 60 10)
for o in "${OFFSETS[@]}"; do
  dd if=mount/big.txt of=/dev/null bs=4096 skip="$o" count=1 status=none
done

# Phase 3: sequential again
cat mount/big.txt > /dev/null