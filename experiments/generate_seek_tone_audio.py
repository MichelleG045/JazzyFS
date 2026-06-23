#!/usr/bin/env python3
"""
Generate real-time seek-tone audio from JazzyFS decision logs.

This uses the same seek-distance mapping as plot_seek_sonification.py:
zero seek distance is silence, and nonzero seek distances are mapped
logarithmically into 150 Hz to 1800 Hz.
"""

import argparse
import csv
import math
import os
import wave

import numpy as np


WORKLOADS = [
    "sequential",
    "random",
    "phase_change",
    "gradual_drift",
    "seek_suppression",
    "tar_workload",
    "python_import",
    "cache_lookup_workload",
]

MIN_FREQ = 150
MAX_FREQ = 1800
MIN_SEEK = 4096
MAX_SEEK = 1024 * 1024 * 1024
SAMPLE_RATE = 44100
TONE_SECONDS = 0.08
GAP_SECONDS = 0.02


def seek_delta_to_frequency(seek_delta):
    if seek_delta <= 0:
        return 0.0
    clamped = min(max(seek_delta, MIN_SEEK), MAX_SEEK)
    ratio = math.log(clamped / MIN_SEEK) / math.log(MAX_SEEK / MIN_SEEK)
    return MIN_FREQ + ratio * (MAX_FREQ - MIN_FREQ)


def read_frequencies(path, max_events):
    frequencies = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            seek_delta = float(row.get("seek_delta") or 0)
            frequencies.append(seek_delta_to_frequency(seek_delta))

    if max_events and len(frequencies) > max_events:
        idx = np.linspace(0, len(frequencies) - 1, max_events).astype(int)
        frequencies = [frequencies[i] for i in idx]
    return frequencies


def synthesize_seek_tones(frequencies):
    tone_n = int(SAMPLE_RATE * TONE_SECONDS)
    gap_n = int(SAMPLE_RATE * GAP_SECONDS)
    fade_n = max(1, int(SAMPLE_RATE * 0.008))
    chunks = []

    for freq in frequencies:
        if freq <= 0:
            tone = np.zeros(tone_n, dtype=np.float32)
        else:
            t = np.arange(tone_n, dtype=np.float32) / SAMPLE_RATE
            tone = 0.45 * np.sin(2 * np.pi * freq * t)
            tone[:fade_n] *= np.linspace(0, 1, fade_n)
            tone[-fade_n:] *= np.linspace(1, 0, fade_n)
        chunks.append(tone)
        chunks.append(np.zeros(gap_n, dtype=np.float32))

    if not chunks:
        return np.zeros(1, dtype=np.float32)
    return np.concatenate(chunks)


def save_wav(audio, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767).astype(np.int16)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def generate_one(decisions_path, out_path, max_events):
    frequencies = read_frequencies(decisions_path, max_events)
    audio = synthesize_seek_tones(frequencies)
    save_wav(audio, out_path)

    audible = sum(1 for freq in frequencies if freq > 0)
    total = len(frequencies)
    audible_percent = (audible / total * 100) if total else 0
    print(f"[OK] {out_path} ({audible}/{total} audible events, {audible_percent:.1f}%)")


def generate(platform, mode, run, max_events):
    out_dir = os.path.join("results", platform, "sonification", "audio", "seek_tones")
    os.makedirs(out_dir, exist_ok=True)

    for workload in WORKLOADS:
        decisions_path = os.path.join(
            "results",
            platform,
            workload,
            mode,
            f"run{run}",
            "decisions.csv",
        )
        if not os.path.exists(decisions_path):
            raise FileNotFoundError(decisions_path)

        out_path = os.path.join(out_dir, f"{mode}_{workload}_seek_tones.wav")
        generate_one(decisions_path, out_path, max_events)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="linux")
    parser.add_argument("--mode", default="adaptive")
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--max-events", type=int, default=320)
    parser.add_argument("--decisions", help="Render one seek-tone WAV from this decisions.csv file.")
    parser.add_argument("--output", help="Output path when --decisions is used.")
    args = parser.parse_args()

    if args.decisions or args.output:
        if not args.decisions or not args.output:
            parser.error("--decisions and --output must be used together")
        generate_one(args.decisions, args.output, args.max_events)
        return

    generate(args.platform, args.mode, args.run, args.max_events)


if __name__ == "__main__":
    main()
