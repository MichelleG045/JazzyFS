#!/usr/bin/env bash
set -euo pipefail

# Python source-file scan workload: reads many small .py files through JazzyFS.
# This approximates metadata/source access during interpreter or developer-tool startup.
find mount/pyfiles/ -name "*.py" | sort | xargs cat > /dev/null
