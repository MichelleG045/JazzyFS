# JazzyFS

JazzyFS is a research filesystem that makes adaptive prefetching **transparent, measurable, and controllable** — three things no existing filesystem provides today.

Modern filesystems like Linux already do adaptive prefetching: they try to predict what data you will need next and load it in advance. But they do this using hidden internal heuristics. You cannot see what the system is thinking, you cannot tune it without modifying kernel code, and when the workload changes the system reacts slowly because it has no explicit signal to act on.

JazzyFS replaces those hidden heuristics with an **explicit per-decision confidence score** (0.0–1.0) computed on every read. That score drives three contributions:

1. **Confidence decay rate detection** — if confidence drops sharply in a single read, prefetching stops immediately rather than waiting several reads for the heuristic to catch up
2. **Confidence trajectory classification** — the shape of the confidence curve over time classifies the workload type (sequential, random, mixed, phase-change) with no training data
3. **Sonification** — confidence is mapped to musical parameters so an operator can hear when prefetching confidence drops and intervene directly

JazzyFS is implemented as a FUSE filesystem in Python, runs cross-platform on Linux ext4 and macOS APFS, and requires no kernel modification.

---

## Key Results

| Metric | Result |
|--------|--------|
| Workload classification accuracy | 7/7 correct, no training data |
| Phase change detection speed | 1 read (vs 2–3 reads with threshold-only) |
| Confidence threshold | Tunable at runtime via environment variable |
| Platforms | Linux ext4, macOS APFS |

**Trajectory classification results:**

| Workload | Mean Confidence | Std | Classified As | Match |
|----------|----------------|-----|---------------|-------|
| sequential | 0.999 | 0.035 | stable-high | yes |
| random | 0.000 | 0.000 | near-zero | yes |
| phase_change | 0.983 | 0.125 | phase-change | yes |
| python_import | 0.500 | 0.036 | mixed | yes |
| tar_workload | 0.994 | 0.077 | stable-high | yes |
| cache_lookup | 0.000 | 0.000 | near-zero | yes |
| concurrent | 0.000 | 0.000 | near-zero | yes |

---

## Repository Layout

```
source/
  jazzyfs_min.py              — FUSE filesystem implementation
  trajectory_classification.py — classify workload type from confidence curve shape
  decay_rate_analysis.py       — measure phase change reaction speed
  threshold_sweep_analysis.py  — summarize threshold sweep results

Experiments/
  run_all.sh                  — full end-to-end pipeline (9 steps)
  run_experiments.sh          — main experiment runner (all modes, all workloads)
  run_threshold_sweep.sh      — confidence threshold sweep (0.3, 0.5, 0.7, 0.9)
  run_native_timing.sh        — native filesystem timing baseline
  run_jazzyfs_timing.sh       — JazzyFS timing for one mode
  result_summary.py           — aggregate timing and decision logs to CSV
  plot_results.py             — generate thesis figures

workloads/
  synthetic/                  — sequential, random, phase_change, concurrent
  real/                       — tar_workload, python_import, cache_lookup_workload
  setup/setup_test_data.sh    — generate source_data/

results/
  linux/                      — Linux ext4 experiment results
  apfs/                       — macOS APFS experiment results
```

---

## Requirements

- Python 3.10+
- `fusepy`
- macOS: macFUSE — Linux: `libfuse2`
- SoX (`play` command) for sonification

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

bash workloads/setup/setup_test_data.sh
```

---

## Running JazzyFS

Mount in adaptive mode:

```bash
mkdir -p mount
JAZZYFS_MODE=adaptive JAZZYFS_SOUND=0 python3 source/jazzyfs_min.py source_data mount
```

Run a workload in another terminal:

```bash
bash workloads/synthetic/sequential.sh
```

Unmount:

```bash
# Linux
fusermount -u mount

# macOS
diskutil unmount mount
```

---

## Configuration

All behavior is controlled via environment variables — no kernel modification required.

| Variable | Default | Description |
|----------|---------|-------------|
| `JAZZYFS_MODE` | `adaptive` | `none`, `baseline`, or `adaptive` |
| `JAZZYFS_CONFIDENCE_THRESHOLD` | `0.7` | Minimum confidence to issue a prefetch |
| `JAZZYFS_DECAY_THRESHOLD` | `0.25` | Confidence drop that triggers immediate suppression |
| `JAZZYFS_PREFETCH_DEPTH` | `1` | Blocks to read ahead per prefetch |
| `JAZZYFS_SOUND` | `0` | `1` enables sonification |

Example — run with a more conservative threshold:

```bash
JAZZYFS_MODE=adaptive JAZZYFS_CONFIDENCE_THRESHOLD=0.9 JAZZYFS_SOUND=0 \
  python3 source/jazzyfs_min.py source_data mount
```

---

## Reproducing All Results

Run the full pipeline:

```bash
bash Experiments/run_all.sh
```

This runs all experiments, threshold sweep, generates figures, and runs all three analysis scripts. Individual steps:

```bash
bash Experiments/run_experiments.sh              # decision + access logs, all modes
bash Experiments/run_native_timing.sh            # native timing baseline
bash Experiments/run_jazzyfs_timing.sh adaptive  # JazzyFS timing for one mode
bash Experiments/run_threshold_sweep.sh          # threshold sweep at 0.3/0.5/0.7/0.9
python3 Experiments/result_summary.py            # aggregate to CSV
python3 Experiments/plot_results.py              # generate figures
python3 source/threshold_sweep_analysis.py       # threshold sweep summary table
python3 source/trajectory_classification.py      # workload classification results
python3 source/decay_rate_analysis.py            # phase change reaction speed
```

---

## Output Files

| File | Description |
|------|-------------|
| `logs/decisions.csv` | Per-read phase, confidence, decay_rate, prefetch decision |
| `results/{platform}/timing_summary.csv` | Wall-clock timing per workload per mode |
| `results/{platform}/decision_summary.csv` | Prefetch rate and confidence per workload per mode |
| `results/{platform}/trajectory_classification.csv` | Workload classification results |
| `results/{platform}/decay_rate_analysis.csv` | Phase change reaction speed per run |
| `results/{platform}/threshold_sweep/threshold_sweep_summary.csv` | Threshold sweep results |
| `results/{platform}/figures/` | Thesis figures |

---

## Sonification

JazzyFS maps confidence to musical parameters in real time:

- **Scale** — mode determines the musical scale (adaptive → Harmonic Minor)
- **Tempo** — sequential access plays fast, irregular access plays slow
- **Melody direction** — high confidence ascends, low confidence descends

Enable with `JAZZYFS_SOUND=1`. Requires SoX.

---

## Limitations

JazzyFS is a research prototype. FUSE user-space overhead (~334% vs native) means wall-clock timing results reflect the cost of the interception layer, not the prefetching algorithm itself. A kernel-level implementation would eliminate this overhead. The contribution is the mechanism — explicit confidence signals, workload classification, and decay detection — not end-to-end throughput.

---

## MS Thesis

This project is the implementation for Michelle Gurovith's MS thesis at UC Santa Cruz (2026):

> *JazzyFS: Making Filesystem Prefetching Transparent, Reactive, and Controllable Through Explicit Confidence Signals*

Advisor: Scott Brandt, University of California, Santa Cruz.
