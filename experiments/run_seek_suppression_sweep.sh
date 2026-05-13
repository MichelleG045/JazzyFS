#!/usr/bin/env bash
set -euo pipefail

# Sweep the seek-distance suppression threshold for Claim 2.
# Lower thresholds should suppress more prefetches on seek-heavy workloads.

SOURCE_DIR="${1:-source_data}"
MOUNT_DIR="${2:-mount}"
JAZZYFS="source/jazzyfs.py"
LOG_DECISIONS="logs/decisions.csv"

if [[ "$(uname)" == "Darwin" ]]; then PLATFORM="apfs"; else PLATFORM="linux"; fi

THRESHOLDS=(262144 524288 1048576 2097152)
WORKLOADS=("sequential" "random" "seek_suppression" "cache_lookup_workload")
RUNS=5
OUT_DIR="results/${PLATFORM}/seek_suppression_sweep"
OUT_CSV="${OUT_DIR}/seek_suppression_sweep.csv"
JAZZYFS_PID=

mkdir -p "$OUT_DIR" logs

_workload_script() {
    local w=$1
    if [[ -f "workloads/synthetic/${w}.sh" ]]; then
        echo "workloads/synthetic/${w}.sh"
    else
        echo "workloads/real/${w}.sh"
    fi
}

_reset_decisions() {
    echo "run_index,run_label,mode,workload,timestamp,path,offset,size,phase,confidence,decay_rate,seek_delta,prefetch,prefetch_offset,prefetch_size,prefetch_depth,cache_hit,false_negative" > "$LOG_DECISIONS"
}

_mount_jazzyfs() {
    local threshold=$1
    local workload=$2
    local run=$3
    mkdir -p "$MOUNT_DIR"
    JAZZYFS_MODE=adaptive \
        JAZZYFS_SOUND=0 \
        JAZZYFS_SEEK_SUPPRESS_THRESHOLD="$threshold" \
        JAZZYFS_RUN_INDEX="$run" \
        JAZZYFS_RUN_LABEL="seek_threshold_${threshold}_${workload}_run${run}" \
        JAZZYFS_WORKLOAD="$workload" \
        python3 "$JAZZYFS" "$SOURCE_DIR" "$MOUNT_DIR" &
    JAZZYFS_PID=$!
    sleep 2
}

_unmount_jazzyfs() {
    if [[ "$(uname)" == "Darwin" ]]; then
        umount "$MOUNT_DIR" 2>/dev/null || diskutil unmount "$MOUNT_DIR" 2>/dev/null || true
    else
        fusermount -u "$MOUNT_DIR" 2>/dev/null || umount "$MOUNT_DIR" 2>/dev/null || true
    fi
    [[ -n "$JAZZYFS_PID" ]] && wait "$JAZZYFS_PID" 2>/dev/null || true
}

_summarize_decisions() {
    python3 - "$LOG_DECISIONS" <<'PYEOF'
import csv
import sys

rows = list(csv.DictReader(open(sys.argv[1], newline="")))
if not rows:
    print("0,0,0,0")
    raise SystemExit

prefetch_rate = sum(1 for r in rows if r.get("prefetch") == "1") / len(rows)
suppressed_rate = sum(1 for r in rows if r.get("phase") == "seek-suppressed") / len(rows)
avg_seek = sum(int(r.get("seek_delta") or 0) for r in rows) / len(rows)
max_seek = max(int(r.get("seek_delta") or 0) for r in rows)
print(f"{prefetch_rate:.3f},{suppressed_rate:.3f},{avg_seek:.1f},{max_seek}")
PYEOF
}

trap '_unmount_jazzyfs' EXIT

echo "threshold,workload,run,prefetch_rate,seek_suppressed_rate,avg_seek_delta,max_seek_delta" > "$OUT_CSV"

for threshold in "${THRESHOLDS[@]}"; do
    for workload in "${WORKLOADS[@]}"; do
        for run in $(seq 1 "$RUNS"); do
            _reset_decisions
            _mount_jazzyfs "$threshold" "$workload" "$run"
            bash "$(_workload_script "$workload")"
            summary=$(_summarize_decisions)
            echo "${threshold},${workload},${run},${summary}" >> "$OUT_CSV"
            echo "[seek] threshold=$threshold workload=$workload run=$run $summary"
            _unmount_jazzyfs
            JAZZYFS_PID=
            sleep 1
        done
    done
done

trap - EXIT
echo "[DONE] Seek suppression sweep saved to $OUT_CSV"
