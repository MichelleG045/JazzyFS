# JazzyFS Sonification Audio Files

This folder contains generated audio for the macOS/APFS JazzyFS runs.
It includes post-workload music summaries and real-time seek-tone audio.

Post-workload summary audio files are in:

```text
results/apfs/sonification/audio/Post workloads/
```

Their file names are organized as:

```text
<mode>_<workload>.wav
```

Modes:

- `none`: no JazzyFS prefetching
- `baseline`: fixed prefetching after eligible reads
- `adaptive`: runtime adaptive prefetching

Post-workload summaries can use any natural-note root from A through G. The
mode then determines whether that root is rendered as major, natural minor, or
harmonic minor.

Workloads:

- `sequential`
- `random`
- `phase_change`
- `gradual_drift`
- `seek_suppression`
- `tar_workload`
- `python_import`
- `cache_lookup_workload`

Recommended listening examples:

- `adaptive_sequential.wav`: regular sequential access pattern
- `adaptive_random.wav`: irregular random access pattern
- `adaptive_cache_lookup_workload.wav`: large irregular lookup-style jumps
- `adaptive_phase_change.wav`: workload with changing access behavior

The matching spectrogram figures are in:

```text
results/apfs/sonification/plots/Post workloads/
```

Real-time seek-tone audio files are in:

```text
results/apfs/sonification/audio/seek_tones/
```

These files use the same seek-distance mapping shown in Figure 5.9 of the
thesis. Contiguous reads are silent, while larger seek distances become
higher-pitched short tones. Recommended seek-tone examples:

- `seek_tones/adaptive_sequential_seek_tones.wav`: mostly silent by design
- `seek_tones/adaptive_random_seek_tones.wav`: scattered high seek tones
- `seek_tones/adaptive_cache_lookup_workload_seek_tones.wav`: frequent seek tones
