#!/usr/bin/env python3
"""
generate_sonification_plots.py

Synthesizes audio and generates spectrogram plots for all JazzyFS
sonification combinations (3 modes × 8 workloads) using the current
decision_summary.csv generated from experimental decision logs. The script
fails if the summary data or decision logs are missing so it cannot create
placeholder plots that look like real results.

Outputs:
  results/{platform}/sonification/audio/Post workloads/{mode}_{workload}.wav
  results/{platform}/sonification/plots/Post workloads/{mode}_{workload}.png
  results/{platform}/sonification/plots/Post workloads/sonification_grid.png
"""

import argparse
import csv
import hashlib
import os
import platform
import wave

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# --------------------------------------------------
# Platform
# --------------------------------------------------

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument("--platform", default=None)
_args, _ = _parser.parse_known_args()
PLATFORM = _args.platform or ("apfs" if platform.system() == "Darwin" else "linux")
OUT_DIR = os.path.join("results", PLATFORM, "sonification")
POST_WORKLOAD_PLOT_DIR = os.path.join(OUT_DIR, "plots", "Post workloads")

# --------------------------------------------------
# Audio Constants (mirrored from jazzyfs.py)
# --------------------------------------------------

SAMPLE_RATE = 44100
FAST = 0.15   # sequential access tempo (seconds per note)
SLOW = 1.2    # irregular access tempo

SCALE_INTERVALS = {
    "none":     [0, 2, 4, 5, 7, 9, 11],   # Major
    "baseline": [0, 2, 3, 5, 7, 8, 10],   # Natural Minor
    "adaptive": [0, 2, 3, 5, 7, 8, 11],   # Harmonic Minor
}

CHORD_PROGRESSIONS = {
    "none":     [[0, 4, 7], [5, 9, 12], [7, 11, 14], [0, 4, 7]],    # I IV V I
    "baseline": [[0, 3, 7], [5, 8, 12], [7, 10, 14], [0, 3, 7]],    # i iv v i
    "adaptive": [[0, 3, 7], [5, 8, 12], [7, 11, 14], [0, 3, 7]],    # i iv V i
}

_CHROMATIC_ROOTS_HZ = [
    130.81, 138.59, 146.83, 155.56, 164.81, 174.61, 185.00, 196.00,
    207.65, 220.00, 233.08, 246.94, 261.63, 277.18, 293.66, 311.13,
    329.63, 349.23, 369.99, 392.00, 415.30, 440.00, 466.16, 493.88, 523.25,
]

# --------------------------------------------------
# Workload Parameters (loaded from experimental results)
# --------------------------------------------------

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

NATURAL_ROOTS = [
    (0, "C"),
    (2, "D"),
    (4, "E"),
    (5, "F"),
    (7, "G"),
    (9, "A"),
    (11, "B"),
]

MODES = ["none", "baseline", "adaptive"]

SHORT = {
    "sequential":            "Sequential",
    "random":                "Random",
    "phase_change":          "Phase Change",
    "gradual_drift":         "Gradual Drift",
    "seek_suppression":      "Seek Suppression",
    "tar_workload":          "Tar",
    "python_import":         "Python Import",
    "cache_lookup_workload": "Cache Lookup",
}

def load_workload_params():
    """Load sonification parameters from regenerated experiment outputs."""
    params = {}
    summary_path = os.path.join("results", PLATFORM, "decision_summary.csv")
    if not os.path.exists(summary_path):
        raise FileNotFoundError(
            f"Missing {summary_path}. Run experiments/result_summary.py --platform {PLATFORM} first."
        )

    with open(summary_path, newline="") as f:
        for row in csv.DictReader(f):
            workload = row.get("workload")
            mode = row.get("mode")
            if workload not in WORKLOADS or mode not in MODES:
                continue
            try:
                confidence = float(row["avg_confidence"])
            except (KeyError, ValueError):
                continue
            params[(mode, workload)] = {
                "confidence": confidence,
            }

    missing = [(mode, workload) for mode in MODES for workload in WORKLOADS
               if (mode, workload) not in params]
    if missing:
        raise RuntimeError(f"Missing sonification summary rows: {missing}")

    for mode in MODES:
        for workload in WORKLOADS:
            pattern = infer_phase_pattern_from_decision_logs(workload, mode)
            if not pattern:
                raise RuntimeError(
                    f"Could not infer phase pattern for {mode}/{workload}; missing or empty decision logs."
                )
            params[(mode, workload)]["pattern"] = pattern
            params[(mode, workload)]["phase"] = summarize_phase_pattern(pattern)
    return params


def normalize_phase(phase):
    if phase == "sequential":
        return "sequential"
    if phase in ("irregular", "seek-suppressed"):
        return "irregular"
    return None


def infer_phase_pattern_from_decision_logs(workload, mode):
    """Infer the ordered phase pattern from the first saved run."""
    workload_dir = os.path.join("results", PLATFORM, workload, mode)
    if not os.path.isdir(workload_dir):
        return None

    for run_name in sorted(os.listdir(workload_dir)):
        decisions_path = os.path.join(workload_dir, run_name, "decisions.csv")
        if not os.path.exists(decisions_path):
            continue
        pattern = []
        with open(decisions_path, newline="") as f:
            for row in csv.DictReader(f):
                phase = normalize_phase(row.get("phase"))
                if phase and (not pattern or pattern[-1] != phase):
                    pattern.append(phase)
        if pattern:
            return pattern
    return None


def summarize_phase_pattern(pattern):
    if len(set(pattern)) > 1:
        return "mixed"
    return pattern[0]


WORKLOAD_PARAMS = load_workload_params()

MODE_LABELS = {
    "none":     "None (Major)",
    "baseline": "Baseline (Natural Minor)",
    "adaptive": "Adaptive (Harmonic Minor)",
}


def _root_for(mode, workload):
    seed = os.environ.get("JAZZYFS_ROOT_SEED", "jazzyfs")
    digest = hashlib.sha256(f"{seed}:{mode}:{workload}".encode("utf-8")).digest()
    return NATURAL_ROOTS[digest[0] % len(NATURAL_ROOTS)]

# --------------------------------------------------
# Audio Synthesis
# --------------------------------------------------

def _build_scale(root_hz, intervals):
    return [root_hz * (2 ** (i / 12)) for i in intervals]


def _sine(freq, duration, vol=1.0, fade_in=0.02, fade_out=0.05):
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    w = vol * np.sin(2 * np.pi * freq * t)
    fi = int(fade_in * SAMPLE_RATE)
    fo = int(fade_out * SAMPLE_RATE)
    if fi > 0 and fi < n:
        w[:fi] *= np.linspace(0, 1, fi)
    if fo > 0 and fo < n:
        w[-fo:] *= np.linspace(1, 0, fo)
    return w


def _overlay(track, signal, at_sample):
    end = at_sample + len(signal)
    if end > len(track):
        track = np.pad(track, (0, end - len(track)))
    track[at_sample:end] += signal
    return track


def _generate_segment(mode, workload, tempo, confidence):
    root_idx, _ = _root_for(mode, workload)
    root_hz   = _CHROMATIC_ROOTS_HZ[root_idx]
    scale_hz  = _build_scale(root_hz, SCALE_INTERVALS[mode])
    n         = len(scale_hz)        # 7
    n_notes   = n + 1                # 8
    ascending = confidence >= 0.5
    progression = CHORD_PROGRESSIONS[mode]
    n_cycles  = len(progression)     # 4
    slow      = tempo >= 0.5

    def melody_hz(i):
        if ascending:
            return scale_hz[0] * 2 if i == n else scale_hz[i]
        else:
            return scale_hz[0] * 2 if i == 0 else scale_hz[n - i]

    total_samples = int(SAMPLE_RATE * (n_cycles * n_notes * tempo + tempo * 2))
    track = np.zeros(total_samples)
    cursor = 0  # in samples

    if not slow:
        for cycle_idx in range(n_cycles):
            chord_dur = tempo * n_notes
            for s in progression[cycle_idx]:
                freq = root_hz * 2 * (2 ** (s / 12))
                track = _overlay(track, _sine(freq, chord_dur, vol=0.10), cursor)
            for i in range(n_notes):
                track = _overlay(track, _sine(melody_hz(i), tempo * 0.85, vol=0.7,
                                              fade_out=tempo * 0.15), cursor)
                cursor += int(tempo * SAMPLE_RATE)
    else:
        SLOW_GROUPS = [3, 3, 1, 1]
        for cycle_idx in range(n_cycles):
            note_i = 0
            for group_idx, group_size in enumerate(SLOW_GROUPS):
                chord_idx  = (cycle_idx * len(SLOW_GROUPS) + group_idx) % n_cycles
                is_cadence = (cycle_idx == n_cycles - 1 and
                               group_idx == len(SLOW_GROUPS) - 1)
                chord_dur  = tempo * 2.0 if is_cadence else tempo * group_size
                chord_vol  = 0.35 if is_cadence else 0.30
                for s in progression[chord_idx]:
                    freq = root_hz * 2 * (2 ** (s / 12))
                    track = _overlay(track,
                                     _sine(freq, chord_dur, vol=chord_vol / 3),
                                     cursor)
                for j in range(group_size):
                    track = _overlay(track,
                                     _sine(melody_hz(note_i + j), tempo * 0.85,
                                           vol=0.7, fade_out=tempo * 0.15),
                                     cursor)
                    cursor += int(tempo * SAMPLE_RATE)
                note_i += group_size

    track = track[:cursor + int(tempo * SAMPLE_RATE)]

    peak = np.max(np.abs(track))
    if peak > 0:
        track = track / peak * 0.8
    return track


def generate_audio(mode, workload):
    params     = WORKLOAD_PARAMS[(mode, workload)]
    confidence = params["confidence"]
    patterns   = params["pattern"]

    segments = []
    for p in patterns:
        tempo = FAST if p == "sequential" else SLOW
        segments.append(_generate_segment(mode, workload, tempo, confidence))

    audio = np.concatenate(segments)
    peak  = np.max(np.abs(audio))
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


# --------------------------------------------------
# Plotting
# --------------------------------------------------

def _plot_one(ax_wave, ax_spec, audio, title,
              title_fs=11, label_fs=10, tick_fs=9):
    t = np.linspace(0, len(audio) / SAMPLE_RATE, len(audio))

    ax_wave.plot(t, audio, linewidth=0.5, color="#2c7bb6")
    ax_wave.set_ylabel("Amplitude", fontsize=label_fs)
    ax_wave.set_title(title, fontsize=title_fs, pad=4, fontweight="bold")
    ax_wave.set_xlim(0, t[-1])
    ax_wave.tick_params(labelsize=tick_fs)
    ax_wave.set_xticks([])
    ax_wave.spines["top"].set_visible(False)
    ax_wave.spines["right"].set_visible(False)

    ax_spec.specgram(audio, Fs=SAMPLE_RATE, cmap="plasma",
                     NFFT=2048, noverlap=1024, scale="dB")
    ax_spec.set_ylim(0, 1200)
    ax_spec.set_ylabel("Frequency (Hz)", fontsize=label_fs)
    ax_spec.set_xlabel("Time (s)", fontsize=label_fs)
    ax_spec.tick_params(labelsize=tick_fs)
    ax_spec.spines["top"].set_visible(False)
    ax_spec.spines["right"].set_visible(False)


def plot_individual(audio, mode, workload, path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6.5),
                                    gridspec_kw={"height_ratios": [1, 2]})
    _, root_label = _root_for(mode, workload)
    title = f"{SHORT[workload]}  |  Mode: {MODE_LABELS[mode]}  |  Root: {root_label}"
    _plot_one(ax1, ax2, audio, title, title_fs=16, label_fs=14, tick_fs=12)

    conf  = WORKLOAD_PARAMS[(mode, workload)]["confidence"]
    phase = WORKLOAD_PARAMS[(mode, workload)]["phase"]
    pattern = "-".join(WORKLOAD_PARAMS[(mode, workload)]["pattern"])
    direction = "ascending" if conf >= 0.5 else "descending"
    fig.text(0.01, 0.01,
             f"phase={phase}   pattern={pattern}   confidence={conf:.4f}   melody={direction}   root={root_label}",
             fontsize=12, color="#555555")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()


def plot_grid(all_audio):
    """Workloads (rows) × 3 modes (cols), waveform + spectrogram per cell."""
    n_rows = len(WORKLOADS)
    n_cols = len(MODES)

    fig = plt.figure(figsize=(26, 7 * n_rows))
    fig.suptitle(
        "JazzyFS Sonification — Waveform & Spectrogram\n"
        "Rows: workloads   |   Columns: prefetch modes",
        fontsize=24, fontweight="bold", y=1.002
    )

    outer = fig.add_gridspec(n_rows, n_cols, hspace=0.65, wspace=0.35)

    for row, workload in enumerate(WORKLOADS):
        for col, mode in enumerate(MODES):
            audio = all_audio[(mode, workload)]
            inner = outer[row, col].subgridspec(2, 1,
                                                 height_ratios=[1, 2],
                                                 hspace=0.18)
            ax_w = fig.add_subplot(inner[0])
            ax_s = fig.add_subplot(inner[1])

            conf      = WORKLOAD_PARAMS[(mode, workload)]["confidence"]
            direction = "↑" if conf >= 0.5 else "↓"
            _, root_label = _root_for(mode, workload)
            title     = f"{SHORT[workload]} / {mode}  root={root_label}  {direction} conf={conf:.2f}"
            _plot_one(ax_w, ax_s, audio, title,
                      title_fs=15, label_fs=12, tick_fs=11)

            # Row label on left edge
            if col == 0:
                ax_w.set_ylabel("Amplitude", fontsize=12)
                ax_w.annotate(SHORT[workload], xy=(-0.18, 0.5),
                              xycoords="axes fraction", fontsize=14,
                              fontweight="bold", ha="center", va="center",
                              rotation=90)

    # Column headers
    for col, mode in enumerate(MODES):
        first_ax = fig.axes[col * 2]  # first row, two axes per cell
        first_ax.set_title(
            f"— {MODE_LABELS[mode]} —\n{first_ax.get_title()}",
            fontsize=16, fontweight="bold", pad=5
        )

    path = os.path.join(POST_WORKLOAD_PLOT_DIR, "sonification_grid.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[OK] Grid figure → {path}")


def plot_mode_grid(all_audio, mode):
    """Readable 2-column grid for one mode across all workloads."""
    fig = plt.figure(figsize=(18, 22))
    fig.suptitle(
        f"JazzyFS Sonification — {MODE_LABELS[mode]} Mode",
        fontsize=26, fontweight="bold", y=0.995
    )

    outer = fig.add_gridspec(4, 2, hspace=0.42, wspace=0.24)

    for idx, workload in enumerate(WORKLOADS):
        row = idx // 2
        col = idx % 2
        audio = all_audio[(mode, workload)]
        inner = outer[row, col].subgridspec(2, 1,
                                             height_ratios=[1, 2],
                                             hspace=0.16)
        ax_w = fig.add_subplot(inner[0])
        ax_s = fig.add_subplot(inner[1])

        conf = WORKLOAD_PARAMS[(mode, workload)]["confidence"]
        direction = "ascending" if conf >= 0.5 else "descending"
        _, root_label = _root_for(mode, workload)
        title = f"{SHORT[workload]}  |  root={root_label}, conf={conf:.2f}, {direction}"
        _plot_one(ax_w, ax_s, audio, title,
                  title_fs=18, label_fs=14, tick_fs=12)

    path = os.path.join(POST_WORKLOAD_PLOT_DIR, f"sonification_grid_{mode}.png")
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()
    print(f"[OK] {mode} grid figure → {path}")


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    audio_dir = os.path.join(OUT_DIR, "audio", "Post workloads")
    plot_dir  = POST_WORKLOAD_PLOT_DIR
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(plot_dir,  exist_ok=True)

    print(f"[Platform] {PLATFORM}")
    print(f"[Output]   {OUT_DIR}")

    all_audio = {}

    for mode in MODES:
        for workload in WORKLOADS:
            label = f"{mode}_{workload}"
            print(f"  Generating {label}...")

            audio = generate_audio(mode, workload)
            all_audio[(mode, workload)] = audio

            wav_path  = os.path.join(audio_dir, f"{label}.wav")
            plot_path = os.path.join(plot_dir,  f"{label}.png")

            save_wav(audio, wav_path)
            plot_individual(audio, mode, workload, plot_path)
            print(f"    [OK] {wav_path}")
            print(f"    [OK] {plot_path}")

    print("\n[Generating grid figure...]")
    plot_grid(all_audio)
    plot_mode_grid(all_audio, "adaptive")
    print(f"\n[DONE] All {len(WORKLOADS) * len(MODES)} sonification plots and audio files generated.")


if __name__ == "__main__":
    main()
