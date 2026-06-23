# JazzyFS

JazzyFS is a read-only FUSE filesystem prototype for studying adaptive file
prefetching and filesystem observability. It was built for the MS thesis
*JazzyFS: Adaptive File Prefetching with Runtime Suppression Signals and
Sonification*.

The prototype records per-read runtime signals such as phase, confidence,
confidence decay, seek distance, prefetch decisions, cache-hit feedback, and
false negatives. It also includes sonification tools that turn workload
behavior into post-workload musical summaries and seek-tone audio.

JazzyFS is a research prototype, not a replacement for native Linux/ext4. The
thesis performance and decision results are collected on Linux/ext4. The
macOS/APFS runs are used for sonification outputs and do not make APFS
performance claims.

## Contributions

The thesis version focuses on:

1. A FUSE-based filesystem prototype for studying adaptive prefetching.
2. Confidence and confidence-decay signals for workload phase behavior.
3. Seek-distance suppression for large offset jumps.
4. Linux/ext4 experiments across eight workloads and three prefetching modes.
5. Native Linux page-cache hit/miss comparison using `cachestat-bpfcc`.
6. Sonification outputs for observing filesystem access behavior.

## Repository Layout

```text
source/
  jazzyfs.py                         FUSE filesystem implementation

workloads/
  synthetic/                         sequential, random, phase_change,
                                     gradual_drift, seek_suppression
  real/                              tar_workload, python_import,
                                     cache_lookup_workload
  setup/setup_test_data.sh           creates source_data/

experiments/
  run_experiments.sh                 runs JazzyFS modes and saves logs
  run_timing_interleaved.sh          native Linux/ext4 and JazzyFS timing
  run_linux_cache_hit_comparison.sh  native Linux page-cache hit/miss data
  summarize_linux_cache_hit_comparison.py
  result_summary.py                  aggregates timing and decision logs
  plot_results.py                    creates thesis performance figures
  generate_sonification_plots.py     creates post-workload audio and plots
  generate_seek_tone_audio.py        creates seek-tone WAV files from logs
  plot_seek_sonification.py          creates the seek-tone figure
  play_post_workload_sonification.sh runs one workload and refreshes one
                                     post-workload WAV
  play_all_post_workload_sonification.sh
  play_seek_tone_sonification.sh     runs one workload and refreshes one
                                     seek-tone WAV
  play_all_seek_tone_sonification.sh

results/
  linux/                             Linux/ext4 results used for claims
  apfs/                              macOS/APFS sonification outputs

thesis/
  thesis.tex                         thesis source
  references.bib                     bibliography
```

## Requirements

- Python 3.10+
- `fusepy`
- `matplotlib`
- `numpy`
- macOS: macFUSE
- Linux: FUSE support such as `libfuse2`
- SoX `play` command for live terminal sonification playback
- Linux cache comparison: `bpfcc-tools` / `cachestat-bpfcc` on Ubuntu

Install Python dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create test data:

```bash
bash workloads/setup/setup_test_data.sh
```

## Running JazzyFS

Mount in adaptive mode:

```bash
mkdir -p mount
JAZZYFS_MODE=adaptive JAZZYFS_SOUND=0 python3 source/jazzyfs.py source_data mount
```

Run a workload from another terminal:

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

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `JAZZYFS_MODE` | `adaptive` | `none`, `baseline`, or `adaptive` |
| `JAZZYFS_CONFIDENCE_THRESHOLD` | `0.7` | Minimum confidence for adaptive prefetching |
| `JAZZYFS_DECAY_THRESHOLD` | `0.25` | Confidence drop that suppresses prefetching |
| `JAZZYFS_SEEK_SUPPRESS_THRESHOLD` | `1048576` | Seek distance in bytes that suppresses adaptive prefetching |
| `JAZZYFS_PREFETCH_DEPTH` | `1` | Number of blocks to read ahead per prefetch |
| `JAZZYFS_SOUND` | `0` | `1` enables sonification playback |
| `JAZZYFS_SEEK_SOUND` | `1` | `0` disables live seek tones while keeping other sound behavior available |

Example:

```bash
JAZZYFS_MODE=adaptive JAZZYFS_CONFIDENCE_THRESHOLD=0.9 JAZZYFS_SOUND=0 \
  python3 source/jazzyfs.py source_data mount
```

## Reproducing Results

Run the main JazzyFS workload experiments:

```bash
RUNS=20 PYTHON=venv/bin/python bash experiments/run_experiments.sh source_data mount
python3 experiments/result_summary.py
```

Run Linux/ext4 timing experiments:

```bash
bash experiments/run_timing_interleaved.sh source_data mount
python3 experiments/plot_results.py
```

Run native Linux page-cache hit/miss comparison:

```bash
RUNS=20 bash experiments/run_linux_cache_hit_comparison.sh source_data mount
python3 experiments/summarize_linux_cache_hit_comparison.py
```

Generate APFS sonification outputs from saved APFS decision logs:

```bash
MPLCONFIGDIR=/private/tmp python3 experiments/generate_sonification_plots.py --platform apfs
python3 experiments/generate_seek_tone_audio.py --platform apfs --mode adaptive --run 1
MPLCONFIGDIR=/private/tmp python3 experiments/plot_seek_sonification.py --platform apfs --run 1
```

The convenience pipeline is also available:

```bash
bash experiments/run_all.sh source_data mount
```

## Sonification

JazzyFS has two sonification paths.

Post-workload summaries are generated after workloads finish. They map:

- mode to scale quality: `none` = major, `baseline` = natural minor,
  `adaptive` = harmonic minor
- phase to tempo: sequential is faster, irregular is slower
- confidence to melody direction: high confidence ascends, low confidence descends
- root note to one of the natural notes A through G

Seek-tone audio maps seek distance to short tones:

- contiguous reads are silent
- small nonzero seeks are lower-pitched
- larger offset jumps are higher-pitched

The public audio archive is available at:

```text
https://michelleg045.github.io/jazzyfs-audio/
```

It contains 24 post-workload WAV files and 8 adaptive-mode seek-tone WAV files.

## Output Files

| Path | Description |
| --- | --- |
| `logs/access.csv` | Per-read access log |
| `logs/decisions.csv` | Per-read phase, confidence, decay, seek, prefetch, cache-hit, and false-negative data |
| `results/linux/timing_summary.csv` | Linux/ext4 timing summary |
| `results/linux/decision_summary.csv` | Linux/ext4 decision summary |
| `results/linux/native/linux_cache_hit_miss_summary.csv` | Native Linux page-cache comparison |
| `results/linux/figures/` | Thesis result figures |
| `results/apfs/sonification/audio/Post workloads/` | Post-workload WAV summaries |
| `results/apfs/sonification/audio/seek_tones/` | Adaptive seek-tone WAV files |
| `results/apfs/sonification/plots/Post workloads/` | Sonification spectrogram plots |
| `results/apfs/sonification/plots/Seek tones/` | Seek-tone plot |

## Limitations

JazzyFS runs in user space through FUSE, so elapsed timing includes FUSE
overhead. Timing results should therefore be read as prototype overhead, not as
evidence that JazzyFS is faster than native Linux/ext4. The stronger evidence
for the thesis comes from the decision logs, prefetch rate, confidence, seek
suppression, cache-hit behavior, false negatives, and sonification outputs.

The performance results are Linux/ext4-only. APFS outputs are used for
sonification demonstration and future-work context.

## Thesis

Michelle Gurovith, *JazzyFS: Adaptive File Prefetching with Runtime Suppression
Signals and Sonification*, MS thesis, University of California, Santa Cruz,
2026.

Advisor: Professor Scott Brandt.
