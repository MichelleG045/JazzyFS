#!/usr/bin/env bash
set -euo pipefail

# Python import workload: reads many small scattered files through JazzyFS mount
# Simulates interpreter startup / developer environment (random access pattern)
find mount/pyfiles/ -name "*.py" | sort | xargs cat > /dev/null
