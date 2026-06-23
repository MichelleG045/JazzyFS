#!/usr/bin/env python3
"""Render one clean post-workload sonification WAV from a decisions.csv file."""

import argparse
import csv
import hashlib
import os
import wave

import numpy as np


SAMPLE_RATE = 44100
FAST = 0.15
SLOW = 1.2

SCALE_INTERVALS = {
    "none": [0, 2, 4, 5, 7, 9, 11],
    "baseline": [0, 2, 3, 5, 7, 8, 10],
    "adaptive": [0, 2, 3, 5, 7, 8, 11],
}

CHORD_PROGRESSIONS = {
    "none": [[0, 4, 7], [5, 9, 12], [7, 11, 14], [0, 4, 7]],
    "baseline": [[0, 3, 7], [5, 8, 12], [7, 10, 14], [0, 3, 7]],
    "adaptive": [[0, 3, 7], [5, 8, 12], [7, 11, 14], [0, 3, 7]],
}

CHROMATIC_ROOTS_HZ = [
    130.81, 138.59, 146.83, 155.56, 164.81, 174.61, 185.00, 196.00,
    207.65, 220.00, 233.08, 246.94,
]

NATURAL_ROOTS = [
    (0, "C"),
    (2, "D"),
    (4, "E"),
    (5, "F"),
    (7, "G"),
    (9, "A"),
    (11, "B"),
]


def normalize_phase(phase):
    if phase == "sequential":
        return "sequential"
    if phase in ("irregular", "seek-suppressed"):
        return "irregular"
    return None


def read_params(decisions_path):
    pattern = []
    confidences = []
    with open(decisions_path, newline="") as f:
        for row in csv.DictReader(f):
            phase = normalize_phase(row.get("phase"))
            if phase and (not pattern or pattern[-1] != phase):
                pattern.append(phase)
            try:
                confidences.append(float(row.get("confidence") or 0.0))
            except ValueError:
                pass

    if not pattern:
        raise RuntimeError(f"No phase data found in {decisions_path}")

    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return pattern, confidence


def root_for(mode, workload):
    seed = os.environ.get("JAZZYFS_ROOT_SEED", "jazzyfs")
    digest = hashlib.sha256(f"{seed}:{mode}:{workload}".encode("utf-8")).digest()
    return NATURAL_ROOTS[digest[0] % len(NATURAL_ROOTS)]


def build_scale(root_hz, intervals):
    return [root_hz * (2 ** (i / 12)) for i in intervals]


def sine(freq, duration, vol=1.0, fade_in=0.02, fade_out=0.05):
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    wave_data = vol * np.sin(2 * np.pi * freq * t)
    fi = int(fade_in * SAMPLE_RATE)
    fo = int(fade_out * SAMPLE_RATE)
    if 0 < fi < n:
        wave_data[:fi] *= np.linspace(0, 1, fi)
    if 0 < fo < n:
        wave_data[-fo:] *= np.linspace(1, 0, fo)
    return wave_data


def overlay(track, signal, at_sample):
    end = at_sample + len(signal)
    if end > len(track):
        track = np.pad(track, (0, end - len(track)))
    track[at_sample:end] += signal
    return track


def generate_segment(mode, workload, tempo, confidence):
    root_idx, _ = root_for(mode, workload)
    root_hz = CHROMATIC_ROOTS_HZ[root_idx]
    scale_hz = build_scale(root_hz, SCALE_INTERVALS[mode])
    n_notes = len(scale_hz) + 1
    ascending = confidence >= 0.5
    progression = CHORD_PROGRESSIONS[mode]
    slow = tempo >= 0.5

    def melody_hz(i):
        if ascending:
            return scale_hz[0] * 2 if i == len(scale_hz) else scale_hz[i]
        return scale_hz[0] * 2 if i == 0 else scale_hz[len(scale_hz) - i]

    total_samples = int(SAMPLE_RATE * (len(progression) * n_notes * tempo + tempo * 2))
    track = np.zeros(total_samples)
    cursor = 0

    if not slow:
        for cycle_idx, chord in enumerate(progression):
            chord_dur = tempo * n_notes
            for semitone in chord:
                freq = root_hz * 2 * (2 ** (semitone / 12))
                track = overlay(track, sine(freq, chord_dur, vol=0.10), cursor)
            for i in range(n_notes):
                track = overlay(track, sine(melody_hz(i), tempo * 0.85, vol=0.7,
                                            fade_out=tempo * 0.15), cursor)
                cursor += int(tempo * SAMPLE_RATE)
    else:
        slow_groups = [3, 3, 1, 1]
        for cycle_idx in range(len(progression)):
            note_i = 0
            for group_idx, group_size in enumerate(slow_groups):
                chord_idx = (cycle_idx * len(slow_groups) + group_idx) % len(progression)
                is_cadence = cycle_idx == len(progression) - 1 and group_idx == len(slow_groups) - 1
                chord_dur = tempo * 2.0 if is_cadence else tempo * group_size
                chord_vol = 0.35 if is_cadence else 0.30
                for semitone in progression[chord_idx]:
                    freq = root_hz * 2 * (2 ** (semitone / 12))
                    track = overlay(track, sine(freq, chord_dur, vol=chord_vol / 3), cursor)
                for j in range(group_size):
                    track = overlay(track, sine(melody_hz(note_i + j), tempo * 0.85,
                                                vol=0.7, fade_out=tempo * 0.15), cursor)
                    cursor += int(tempo * SAMPLE_RATE)
                note_i += group_size

    return track[: cursor + int(tempo * SAMPLE_RATE)]


def generate_audio(mode, workload, pattern, confidence):
    segments = []
    for phase in pattern:
        tempo = FAST if phase == "sequential" else SLOW
        segments.append(generate_segment(mode, workload, tempo, confidence))
    audio = np.concatenate(segments)
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.8
    return audio


def save_wav(audio, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pcm = (audio * 32767).astype(np.int16)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--mode", required=True, choices=sorted(SCALE_INTERVALS))
    parser.add_argument("--workload", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pattern, confidence = read_params(args.decisions)
    audio = generate_audio(args.mode, args.workload, pattern, confidence)
    save_wav(audio, args.output)
    _, root = root_for(args.mode, args.workload)
    direction = "up" if confidence >= 0.5 else "down"
    print(f"[Render] decisions={args.decisions}")
    print(f"[Render] output={args.output}")
    print(f"[Render] pattern={' -> '.join(pattern)}")
    print(f"[Render] confidence={confidence:.4f}, root={root}, direction={direction}")


if __name__ == "__main__":
    main()
