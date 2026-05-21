#!/usr/bin/env python3
"""
Plot JazzyFS real-time seek sonification behavior from saved decision logs.

The figure mirrors the seek-tone mapping implemented in source/jazzyfs.py:
sequential reads are silent, while larger seek deltas map logarithmically to
higher short tones between 150 Hz and 1800 Hz.
"""

import argparse
import csv
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
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

SHORT = {
    "sequential": "Sequential",
    "random": "Random",
    "phase_change": "Phase Change",
    "gradual_drift": "Gradual Drift",
    "seek_suppression": "Seek Suppression",
    "tar_workload": "Tar",
    "python_import": "Python Import",
    "cache_lookup_workload": "Cache Lookup",
}

MIN_FREQ = 150
MAX_FREQ = 1800
MIN_SEEK = 4096
MAX_SEEK = 1024 * 1024 * 1024


def seek_delta_to_frequency(seek_delta):
    if seek_delta <= 0:
        return 0.0
    clamped = min(max(seek_delta, MIN_SEEK), MAX_SEEK)
    ratio = math.log(clamped / MIN_SEEK) / math.log(MAX_SEEK / MIN_SEEK)
    return MIN_FREQ + ratio * (MAX_FREQ - MIN_FREQ)


def read_seek_frequencies(path, max_points):
    frequencies = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            seek_delta = float(row.get("seek_delta") or 0)
            frequencies.append(seek_delta_to_frequency(seek_delta))

    if len(frequencies) > max_points:
        idx = np.linspace(0, len(frequencies) - 1, max_points).astype(int)
        frequencies = [frequencies[i] for i in idx]
    return np.array(frequencies, dtype=float)


def plot_seek_sonification(platform, run, max_points):
    out_dir = os.path.join("results", platform, "sonification")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "seek_tone_by_workload.png")

    plt.rcParams.update(
        {
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "figure.titlesize": 18,
        }
    )

    fig, axes = plt.subplots(4, 2, figsize=(11, 13), sharey=True)
    axes = axes.flatten()

    for ax, workload in zip(axes, WORKLOADS):
        path = os.path.join(
            "results",
            platform,
            workload,
            "adaptive",
            f"run{run}",
            "decisions.csv",
        )
        freqs = read_seek_frequencies(path, max_points)
        x = np.arange(1, len(freqs) + 1)
        audible = freqs > 0
        audible_percent = (audible.mean() * 100) if len(freqs) else 0

        ax.scatter(x[~audible], freqs[~audible], s=11, color="#c7cdd4", alpha=0.8)
        ax.vlines(x[audible], 0, freqs[audible], color="#2f6f8f", alpha=0.28, linewidth=0.9)
        ax.scatter(x[audible], freqs[audible], s=14, color="#184e77", alpha=0.9)
        ax.axhline(MIN_FREQ, color="#8d99ae", linewidth=0.8, linestyle="--", alpha=0.7)
        ax.axhline(MAX_FREQ, color="#8d99ae", linewidth=0.8, linestyle="--", alpha=0.7)
        ax.set_title(f"{SHORT[workload]} ({audible_percent:.1f}% audible)")
        ax.set_ylim(-80, 1900)
        ax.set_xlabel("Read index")
        ax.grid(True, axis="y", alpha=0.25)

    for ax in axes[::2]:
        ax.set_ylabel("Seek tone frequency (Hz)")

    fig.suptitle("Real-Time Seek Sonification by Workload (Adaptive Mode)", y=0.995)
    fig.text(
        0.5,
        0.015,
        "0 Hz represents silence for contiguous reads; nonzero points use JazzyFS's logarithmic 150-1800 Hz seek-tone mapping.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0.035, 1, 0.975])
    fig.savefig(out_path, dpi=220)
    print(out_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="linux")
    parser.add_argument("--run", type=int, default=1)
    parser.add_argument("--max-points", type=int, default=320)
    args = parser.parse_args()
    plot_seek_sonification(args.platform, args.run, args.max_points)


if __name__ == "__main__":
    main()
