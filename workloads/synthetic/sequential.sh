#!/usr/bin/env bash
set -euo pipefail

# Sequential workload: reads entire file from start to finish
# Simulates video streaming, log processing, or full table scan (sequential access pattern)
cat mount/big.txt > /dev/null
