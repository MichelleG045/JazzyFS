# JazzyFS Real-Time Seek-Tone Audio

These WAV files were generated from the full adaptive-mode macOS/APFS decision
logs for run 1. They use the same seek-distance mapping as Figure 5.9 of the thesis:
zero seek distance is silence, and nonzero seek distances are mapped
logarithmically to short tones between 150 Hz and 1800 Hz.

Recommended examples:

- `adaptive_sequential_seek_tones.wav`: mostly silent because reads are contiguous
- `adaptive_random_seek_tones.wav`: scattered nonzero seek tones
- `adaptive_cache_lookup_workload_seek_tones.wav`: frequent nonzero seek tones

Generated with:

```text
venv/bin/python experiments/generate_seek_tone_audio.py --platform apfs --mode adaptive --run 1 --max-events 0
```
