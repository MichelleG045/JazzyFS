#!/usr/bin/env bash
set -euo pipefail

# Collect native Linux page-cache hit/miss samples with cachestat while running
# the same workload scripts used by the JazzyFS experiments.
#
# This script must be run on Linux with bcc-tools installed:
#   sudo apt install bcc-tools
#
# Usage:
#   bash experiments/run_linux_cache_hit_comparison.sh [source_dir] [mount_point]
#
# Output:
#   results/linux/native/linux_cache_hit_miss.csv

SOURCE_DIR="${1:-source_data}"
MOUNT_DIR="${2:-mount}"
OUTDIR="results/linux/native"
RAW_DIR="$OUTDIR/cachestat_raw"
OUTFILE="$OUTDIR/linux_cache_hit_miss.csv"

WORKLOADS=("sequential" "random" "phase_change" "gradual_drift" "seek_suppression" "tar_workload" "python_import" "cache_lookup_workload")
RUNS="${RUNS:-20}"

if [[ "$(uname)" != "Linux" ]]; then
    echo "[ERROR] This script must be run on Linux."
    exit 1
fi

if command -v cachestat >/dev/null 2>&1; then
    CACHESTAT_BIN="$(command -v cachestat)"
elif command -v cachestat-bpfcc >/dev/null 2>&1; then
    CACHESTAT_BIN="$(command -v cachestat-bpfcc)"
elif [[ -x /usr/share/bcc/tools/cachestat ]]; then
    CACHESTAT_BIN="/usr/share/bcc/tools/cachestat"
else
    echo "[ERROR] cachestat not found. Install it with: sudo apt install bcc-tools"
    exit 1
fi

mkdir -p "$OUTDIR" "$RAW_DIR"

_workload_script() {
    local workload=$1
    if [[ -f "workloads/synthetic/${workload}.sh" ]]; then
        echo "workloads/synthetic/${workload}.sh"
    else
        echo "workloads/real/${workload}.sh"
    fi
}

_drop_caches() {
    sync
    echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null
}

_setup_native_symlink() {
    if [[ -L "$MOUNT_DIR" ]]; then
        rm -f "$MOUNT_DIR"
    elif [[ -d "$MOUNT_DIR" ]]; then
        rmdir "$MOUNT_DIR" 2>/dev/null || true
    fi
    ln -s "$(pwd)/$SOURCE_DIR" "$MOUNT_DIR"
}

_teardown_native_symlink() {
    if [[ -L "$MOUNT_DIR" ]]; then
        rm -f "$MOUNT_DIR"
    fi
    mkdir -p "$MOUNT_DIR"
}

_parse_time() {
    echo "$1" | awk '{print $2}' | sed 's/m/:/g' | sed 's/s//g' | awk -F: '{printf "%.4f", $1*60+$2}'
}

_parse_cachestat() {
    local file=$1
    python3 - "$file" <<'PY'
import re
import sys

path = sys.argv[1]
lines = [line.strip() for line in open(path, errors="ignore") if line.strip()]

header = None
data = None
for i, line in enumerate(lines):
    if "HITS" in line and "MISSES" in line:
        header = re.split(r"\s+", line)
        for candidate in lines[i + 1:]:
            if re.search(r"\d", candidate) and "HITS" not in candidate:
                fields = re.split(r"\s+", candidate)
                if len(fields) >= 4:
                    data = fields
                    break
        break

if not header or not data:
    print("0,0,0,0.00")
    sys.exit(0)

def parse_number(raw):
    raw = str(raw).replace("%", "")
    try:
        return float(raw)
    except ValueError:
        return 0.0

idx = {name: pos for pos, name in enumerate(header)}
hits = 0.0
misses = 0.0
dirties = 0.0

for line in lines:
    fields = re.split(r"\s+", line)
    if len(fields) < len(header):
        continue
    if not fields[0].replace(".", "", 1).isdigit():
        continue
    hits += parse_number(fields[idx.get("HITS", 0)])
    misses += parse_number(fields[idx.get("MISSES", 1)])
    dirties += parse_number(fields[idx.get("DIRTIES", 2)])

hit_ratio = hits / (hits + misses) * 100.0 if hits + misses > 0 else 0.0

print(f"{int(hits)},{int(misses)},{int(dirties)},{hit_ratio:.2f}")
PY
}

trap '_teardown_native_symlink' EXIT

echo "workload,run,mode,real_sec,hits,misses,dirties,hit_ratio" > "$OUTFILE"

echo "[cachestat] $CACHESTAT_BIN"
echo "[output]    $OUTFILE"

for workload in "${WORKLOADS[@]}"; do
    echo ""
    echo "=============================="
    echo " Workload: $workload"
    echo "=============================="

    for run in $(seq 1 "$RUNS"); do
        _drop_caches
        _setup_native_symlink

        raw="$RAW_DIR/${workload}_run${run}.txt"
        sudo "$CACHESTAT_BIN" 1 4 > "$raw" 2>&1 &
        cache_pid=$!
        # Give BCC time to compile/install probes and let the first sample pass.
        # Short workloads can finish in milliseconds, so they must run inside a
        # known active sampling window.
        sleep 1.2

        result=$( { time bash "$(_workload_script "$workload")"; } 2>&1 )
        wait "$cache_pid" || true

        _teardown_native_symlink

        real=$(_parse_time "$(echo "$result" | grep real)")
        parsed=$(_parse_cachestat "$raw")
        echo "$workload,$run,native,$real,$parsed" >> "$OUTFILE"
        echo "  [native] $workload run $run: real=${real}s cache=${parsed}"
    done
done

trap - EXIT

echo ""
echo "[DONE] Native Linux cache hit/miss data saved to $OUTFILE"
