# JazzyFS

JazzyFS is a research filesystem that makes adaptive prefetching **transparent, measurable, and controllable** — three things no existing filesystem provides today.

Modern filesystems like Linux already do adaptive prefetching: they try to predict what data you will need next and load it in advance. But they do this using hidden internal heuristics. You cannot see what the system is thinking, you cannot tune it without modifying kernel code, and when the workload changes the system reacts slowly because it has no explicit signal to act on.

JazzyFS replaces those hidden heuristics with explicit per-read signals. The current thesis version focuses on three contributions:

1. **Confidence decay rate detection** — if confidence drops sharply in a single read, prefetching stops immediately rather than waiting several reads for the heuristic to catch up
2. **Seek-distance suppression** — large byte jumps are measured directly and suppress prefetching because speculative sequential reads are unlikely to be useful
3. **Observability through sonification** — seek distance, phase, confidence, and prefetch mode are mapped to musical signals so operators can hear filesystem behavior

JazzyFS is implemented as a FUSE filesystem in Python, runs cross-platform on Linux ext4 and macOS APFS, and requires no kernel modification.

---

## Key Results

| Metric | Result |
|--------|--------|
| Phase change detection speed | 1 read (vs 2–3 reads with threshold-only) |
| Seek suppression threshold | Tunable at runtime via environment variable |
| Platforms | Linux ext4, macOS APFS |

---

## Repository Layout

```
source/
  jazzyfs.py                  — FUSE filesystem implementation

experiments/
  run_all.sh                  — full end-to-end pipeline
  run_experiments.sh          — main experiment runner (all modes, all workloads)
  run_seek_suppression_sweep.sh — seek threshold sweep
  run_timing_interleaved.sh   — native and JazzyFS timing in one interleaved run
  result_summary.py           — aggregate timing and decision logs to CSV
  plot_results.py             — generate thesis figures
  generate_sonification_plots.py — generate sonification music/spectrograms
  decay_rate_analysis.py      — measure phase change reaction speed
  seek_analysis.py            — summarize seek distance and suppression behavior
  test_sonification.sh        — live sonification smoke test

workloads/
  synthetic/                  — sequential, random, phase_change, gradual_drift, seek_suppression
  real/                       — tar_workload, python_import, cache_lookup_workload
  setup/setup_test_data.sh    — generate source_data/

results/
  linux/                      — Linux ext4 experiment results
  apfs/                       — generated on macOS when experiments are run
```

---

## Requirements

- Python 3.10+
- `fusepy`
- macOS: macFUSE — Linux: `libfuse2`
- SoX (`play` command) for sonification/music playback

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
JAZZYFS_MODE=adaptive JAZZYFS_SOUND=0 python3 source/jazzyfs.py source_data mount
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
| `JAZZYFS_SEEK_SUPPRESS_THRESHOLD` | `1048576` | Seek distance in bytes that suppresses adaptive prefetching |
| `JAZZYFS_PREFETCH_DEPTH` | `1` | Blocks to read ahead per prefetch |
| `JAZZYFS_SOUND` | `0` | `1` enables sonification/music playback |

Example — run with a more conservative threshold:

```bash
JAZZYFS_MODE=adaptive JAZZYFS_CONFIDENCE_THRESHOLD=0.9 JAZZYFS_SOUND=0 \
  python3 source/jazzyfs.py source_data mount
```

---

## Reproducing All Results

Run the full pipeline:

```bash
bash experiments/run_all.sh
```

This runs all experiments, the seek-threshold sweep, figures, and claim analysis scripts. Individual steps:

```bash
bash experiments/run_experiments.sh              # decision + access logs, all modes
bash experiments/run_timing_interleaved.sh       # native + JazzyFS timing
bash experiments/run_seek_suppression_sweep.sh   # seek threshold sweep
python3 experiments/result_summary.py            # aggregate to CSV
python3 experiments/plot_results.py              # generate figures
python3 experiments/generate_sonification_plots.py # generate sonification music/spectrograms
python3 experiments/decay_rate_analysis.py       # phase change reaction speed
python3 experiments/seek_analysis.py             # seek suppression results
```

---

## Output Files

| File | Description |
|------|-------------|
| `logs/decisions.csv` | Per-read phase, confidence, decay_rate, seek_delta, prefetch decision |
| `results/{platform}/timing_summary.csv` | Wall-clock timing per workload per mode |
| `results/{platform}/decision_summary.csv` | Prefetch rate and confidence per workload per mode |
| `results/{platform}/decay_rate_analysis.csv` | Phase change reaction speed per run |
| `results/{platform}/seek_analysis.csv` | Seek distance and suppression summary |
| `results/{platform}/seek_suppression_sweep/seek_suppression_sweep.csv` | Seek threshold sweep results |
| `results/{platform}/sonification/` | Generated music and spectrograms for observability |
| `results/{platform}/figures/` | Thesis figures |

---

## Sonification

JazzyFS maps filesystem behavior to music:

- **Seek tone** — non-zero seek distance plays a short musical tone; larger jumps are higher pitched
- **Scale** — mode determines the musical scale (adaptive → Harmonic Minor)
- **Tempo** — sequential access plays fast, irregular access plays slow
- **Melody direction** — high confidence ascends, low confidence descends

Enable with `JAZZYFS_SOUND=1`. Requires SoX.

---

## Limitations

JazzyFS is a research prototype. FUSE user-space overhead means wall-clock timing results reflect the cost of the interception layer, not the prefetching algorithm itself. A kernel-level implementation would eliminate this overhead. The contribution is the mechanism — explicit confidence decay, seek-distance gating, and audible observability — not end-to-end throughput.

---

## MS Thesis

This project is the implementation for Michelle Gurovith's MS thesis at UC Santa Cruz (2026):

> *JazzyFS: Making Filesystem Prefetching Transparent, Reactive, and Controllable Through Explicit Confidence Signals*

Advisor: Scott Brandt, University of California, Santa Cruz.
