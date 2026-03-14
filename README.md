# JazzyFS

JazzyFS is a read-only user-space FUSE filesystem for studying predictive prefetching and making filesystem behavior audible. It mounts an existing directory, observes read access patterns, classifies them as sequential or irregular, logs each access and prefetch decision, and can sonify workload structure in real time.

This version of the project centers on [`source/jazzyfs_min.py`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/source/jazzyfs_min.py), the workload scripts in [`workloads/`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads), and the experiment runners in [`Experiments/`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/Experiments).

## What JazzyFS does

- Mounts a source directory as a read-only FUSE filesystem.
- Tracks recent reads in a sliding window.
- Detects workload phase as `sequential` or `irregular`.
- Computes a confidence score from recent read continuity.
- Supports three modes:
  - `none`: no prefetching
  - `baseline`: always prefetch
  - `adaptive`: prefetch only when the access pattern looks sequential with high confidence
- Logs raw reads to `logs/access.csv`.
- Logs prediction and prefetch decisions to `logs/decisions.csv`.
- Optionally turns workload behavior into sound using mode-dependent scales and access-dependent tempo.

## Repository layout

- [`source/jazzyfs_min.py`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/source/jazzyfs_min.py): main FUSE filesystem implementation
- [`workloads/synthetic/`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads/synthetic): synthetic sequential, random, and phase-change workloads
- [`workloads/real/`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads/real): real-ish workloads such as Python imports, tar extraction, and cache lookups
- [`workloads/setup/setup_test_data.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads/setup/setup_test_data.sh): generates `source_data/`
- [`Experiments/test_sonification.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/Experiments/test_sonification.sh): runs the sonification demo across workloads and modes
- [`Experiments/run_experiments.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/Experiments/run_experiments.sh): full experiment runner for week 10
- [`Experiments/run_jazzyfs_timing.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/Experiments/run_jazzyfs_timing.sh): timing runs for one JazzyFS mode
- [`Experiments/run_native_timing.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/Experiments/run_native_timing.sh): native filesystem timing baseline
- [`Experiments/run_depth_sweep.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/Experiments/run_depth_sweep.sh): adaptive prefetch-depth sweep
- [`analysis/`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/analysis): result summarization scripts
- [`results/`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/results): saved experiment outputs and summaries

## Requirements

- Python 3
- `fusepy`
- FUSE support
  - macOS: macFUSE
  - Linux: `libfuse2`
- SoX if you want audio playback from the sonification mode
  - the scripts use the `play` command
## Setup

Create or activate a virtual environment if you want an isolated Python setup:

```bash
python3 -m venv venv
source venv/bin/activate
pip install fusepy
```

Generate the test dataset used by the workloads:

```bash
bash workloads/setup/setup_test_data.sh
```

This creates `source_data/` with:

- `big.txt` for sequential, random, and phase-change tests
- `archive.tar` for tar extraction
- `pyfiles/` with many small Python modules for import-style access

## Running JazzyFS manually

From the repository root:

```bash
mkdir -p mount
JAZZYFS_MODE=adaptive JAZZYFS_SOUND=0 python3 source/jazzyfs_min.py source_data mount
```

In another terminal, run a workload such as:

```bash
bash workloads/synthetic/sequential.sh
```

When you are done, unmount:

```bash
umount mount
```

On macOS, if needed:

```bash
diskutil unmount force mount
```

## Configuration

JazzyFS behavior is controlled with environment variables:

- `JAZZYFS_MODE`: `none`, `baseline`, or `adaptive`
- `JAZZYFS_SOUND`: `1` enables sonification, `0` disables it
- `JAZZYFS_PREFETCH_DEPTH`: number of blocks to read ahead in adaptive mode

Examples:

```bash
JAZZYFS_MODE=none JAZZYFS_SOUND=0 python3 source/jazzyfs_min.py source_data mount
```

```bash
JAZZYFS_MODE=adaptive JAZZYFS_SOUND=1 JAZZYFS_PREFETCH_DEPTH=4 python3 source/jazzyfs_min.py source_data mount
```

## Workloads

Synthetic workloads:

- [`workloads/synthetic/sequential.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads/synthetic/sequential.sh): reads `big.txt` sequentially
- [`workloads/synthetic/random.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads/synthetic/random.sh): deterministic random 4 KB reads
- [`workloads/synthetic/phase_change.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads/synthetic/phase_change.sh): sequential -> random -> sequential

Real-ish workloads:

- [`workloads/real/python_import.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads/real/python_import.sh): many small-file reads through `pyfiles/`
- [`workloads/real/tar_workload.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads/real/tar_workload.sh): archive extraction
- [`workloads/real/cache_lookup_workload.sh`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/workloads/real/cache_lookup_workload.sh): irregular page-aligned reads

## Sonification demo

Run the older sonification test harness with:

```bash
bash Experiments/test_sonification.sh
```

It iterates over modes and workloads, mounts JazzyFS with sound enabled, runs each workload, and prints a short summary including:

- detected phase pattern
- average confidence
- root note and scale
- playback direction and tempo

The musical mapping is:

- mode -> scale
  - `none` -> Major
  - `baseline` -> Natural Minor
  - `adaptive` -> Harmonic Minor
- phase -> tempo
  - `sequential` -> fast
  - `irregular` -> slow
- confidence -> melodic direction
  - higher confidence -> ascending
  - lower confidence -> descending

## Experiment scripts

Run all week-10 experiments:

```bash
bash Experiments/run_experiments.sh
```

Run native baseline timing:

```bash
bash Experiments/run_native_timing.sh
```

Run JazzyFS timing for one mode:

```bash
bash Experiments/run_jazzyfs_timing.sh adaptive
```

Run the adaptive prefetch-depth sweep:

```bash
bash Experiments/run_depth_sweep.sh
```

## Logs and results

During execution, JazzyFS writes:

- [`logs/access.csv`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/logs/access.csv): raw read events
- [`logs/decisions.csv`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/logs/decisions.csv): predicted phase, confidence, and prefetch choice

Experiment outputs are stored under [`results/`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/results), including:

- `results/week4/`
- `results/week7/`
- `results/week9/`
- `results/week10/`

The analysis scripts in [`analysis/`](/Users/michelleg/Projects/UCSC_Code/Masters_Thesis/jazzyfs/analysis) summarize timing and decision logs into CSV tables for reporting.

## Notes

- JazzyFS is read-only. Workloads that require write or lock behavior may not work through the FUSE mount on macOS.
- If `mount/` is still mounted from a previous run, unmount it before cleaning the repo or switching commits.
- Sonification depends on external audio tooling and a working FUSE mount; if mount startup fails, the demo scripts may appear to stall while waiting for playback.
