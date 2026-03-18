#!/usr/bin/env python3
"""
plot_results.py — Generate thesis figures from JazzyFS experiment results.

Reads:  results/{platform}/timing_summary.csv
        results/{platform}/decision_summary.csv

Outputs PNG figures to results/{platform}/figures/
"""

import csv
import os
import platform
import sys

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    print("ERROR: matplotlib and numpy required. Run: pip install matplotlib numpy")
    sys.exit(1)

PLATFORM = "apfs" if platform.system() == "Darwin" else "linux"
RESULTS_DIR = f"results/{PLATFORM}"
FIGURES_DIR = os.path.join(RESULTS_DIR, "figures")

WORKLOADS = [
    "sequential", "random", "phase_change",
    "tar_workload", "python_import", "cache_lookup_workload",
]
MODES  = ["none", "baseline", "adaptive"]
DEPTHS = [1, 2, 4, 8]

COLORS = {
    "native":   "#888888",
    "none":     "#4e79a7",
    "baseline": "#f28e2b",
    "adaptive": "#59a14f",
}
DEPTH_COLORS = {1: "#4e79a7", 2: "#f28e2b", 4: "#59a14f", 8: "#e15759"}

SHORT = {
    "sequential":            "seq",
    "random":                "rand",
    "phase_change":          "phase",
    "tar_workload":          "tar",
    "python_import":         "pyimport",
    "cache_lookup_workload": "cache",
}


# --------------------------------------------------
# Data loaders
# --------------------------------------------------

def load_timing_summary():
    path = os.path.join(RESULTS_DIR, "timing_summary.csv")
    if not os.path.exists(path):
        print(f"[WARN] {path} not found — skipping timing plots")
        return {}
    data = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                data[(row["workload"], row["mode"])] = {
                    "avg":  float(row["avg_real"]),
                    "ci95": float(row["ci95_real"]),
                    "std":  float(row["std_real"]),
                }
            except (ValueError, KeyError):
                continue
    return data


def load_decision_summary():
    path = os.path.join(RESULTS_DIR, "decision_summary.csv")
    if not os.path.exists(path):
        print(f"[WARN] {path} not found — skipping decision plots")
        return {}
    data = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                data[(row["workload"], row["mode"])] = {
                    "prefetch_rate":  float(row["avg_prefetch_rate"]),
                    "confidence":     float(row["avg_confidence"]),
                    "std_confidence": float(row["std_confidence"]),
                }
            except (ValueError, KeyError):
                continue
    return data


# --------------------------------------------------
# Plots
# --------------------------------------------------

def plot_timing_overhead(timing):
    """Grouped bar chart: avg wall-clock time per workload/mode with 95% CI error bars."""
    fig, ax = plt.subplots(figsize=(13, 5))
    x = np.arange(len(WORKLOADS))
    width = 0.20
    offsets = [-1.5, -0.5, 0.5, 1.5]
    all_modes = ["native", "none", "baseline", "adaptive"]

    for idx, mode in enumerate(all_modes):
        avgs = [timing.get((w, mode), {}).get("avg", 0) for w in WORKLOADS]
        errs = [timing.get((w, mode), {}).get("ci95", 0) for w in WORKLOADS]
        ax.bar(x + offsets[idx] * width, avgs, width,
               label=mode, color=COLORS[mode], yerr=errs, capsize=3, alpha=0.9)

    ax.set_xlabel("Workload")
    ax.set_ylabel("Average Wall-Clock Time (s)")
    ax.set_title("JazzyFS Workload Timing by Mode (with 95% CI)")
    ax.set_xticks(x)
    ax.set_xticklabels([SHORT[w] for w in WORKLOADS], rotation=15, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    out = os.path.join(FIGURES_DIR, "timing_by_mode.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[OK] {out}")


def plot_overhead_percent(timing):
    """Bar chart: % overhead vs native for none/baseline/adaptive."""
    fig, ax = plt.subplots(figsize=(13, 5))
    x = np.arange(len(WORKLOADS))
    width = 0.25
    offsets = [-1, 0, 1]

    for idx, mode in enumerate(MODES):
        pcts = []
        for w in WORKLOADS:
            native = timing.get((w, "native"), {}).get("avg")
            mode_t = timing.get((w, mode), {}).get("avg")
            if native and mode_t and native > 0:
                pcts.append(((mode_t - native) / native) * 100)
            else:
                pcts.append(0)
        ax.bar(x + offsets[idx] * width, pcts, width,
               label=mode, color=COLORS[mode], alpha=0.9)

    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Workload")
    ax.set_ylabel("Overhead vs Native (%)")
    ax.set_title("FUSE Overhead by Mode Relative to Native Filesystem")
    ax.set_xticks(x)
    ax.set_xticklabels([SHORT[w] for w in WORKLOADS], rotation=15, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    out = os.path.join(FIGURES_DIR, "overhead_percent.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[OK] {out}")


def plot_prefetch_rate(decisions):
    """Grouped bar: prefetch rate per workload/mode."""
    fig, ax = plt.subplots(figsize=(13, 5))
    x = np.arange(len(WORKLOADS))
    width = 0.25
    offsets = [-1, 0, 1]

    for idx, mode in enumerate(MODES):
        rates = [decisions.get((w, mode), {}).get("prefetch_rate", 0) for w in WORKLOADS]
        ax.bar(x + offsets[idx] * width, rates, width,
               label=mode, color=COLORS[mode], alpha=0.9)

    ax.set_xlabel("Workload")
    ax.set_ylabel("Average Prefetch Rate")
    ax.set_title("Prefetch Rate by Workload and Mode")
    ax.set_xticks(x)
    ax.set_xticklabels([SHORT[w] for w in WORKLOADS], rotation=15, ha="right")
    ax.set_ylim(0, 1.15)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    out = os.path.join(FIGURES_DIR, "prefetch_rate.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[OK] {out}")


def plot_confidence(decisions):
    """Grouped bar: avg confidence per workload/mode with std dev error bars."""
    fig, ax = plt.subplots(figsize=(13, 5))
    x = np.arange(len(WORKLOADS))
    width = 0.25
    offsets = [-1, 0, 1]

    for idx, mode in enumerate(MODES):
        confs = [decisions.get((w, mode), {}).get("confidence", 0) for w in WORKLOADS]
        stds  = [decisions.get((w, mode), {}).get("std_confidence", 0) for w in WORKLOADS]
        ax.bar(x + offsets[idx] * width, confs, width,
               label=mode, color=COLORS[mode], yerr=stds, capsize=3, alpha=0.9)

    ax.axhline(0.5, color="red", linestyle="--", linewidth=1.2,
               label="threshold (ascending ↔ descending)")
    ax.set_xlabel("Workload")
    ax.set_ylabel("Average Confidence Score")
    ax.set_title("Phase Detection Confidence by Workload and Mode")
    ax.set_xticks(x)
    ax.set_xticklabels([SHORT[w] for w in WORKLOADS], rotation=15, ha="right")
    ax.set_ylim(0, 1.15)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    out = os.path.join(FIGURES_DIR, "confidence_by_workload.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[OK] {out}")


def plot_depth_sweep(timing):
    """Line chart: avg timing vs prefetch depth per workload."""
    fig, ax = plt.subplots(figsize=(10, 5))

    for w in WORKLOADS:
        times = [timing.get((w, f"adaptive_depth{d}"), {}).get("avg") for d in DEPTHS]
        if all(t is None for t in times):
            continue
        times = [t if t is not None else float("nan") for t in times]
        ax.plot(DEPTHS, times, marker="o", label=SHORT[w])

    ax.set_xlabel("Prefetch Depth (blocks)")
    ax.set_ylabel("Average Wall-Clock Time (s)")
    ax.set_title("Adaptive Prefetch Depth Sweep")
    ax.set_xticks(DEPTHS)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    out = os.path.join(FIGURES_DIR, "depth_sweep.png")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"[OK] {out}")


# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    os.makedirs(FIGURES_DIR, exist_ok=True)
    print(f"[Platform] {PLATFORM}")
    print(f"[Output]   {FIGURES_DIR}")

    timing   = load_timing_summary()
    decisions = load_decision_summary()

    if timing:
        plot_timing_overhead(timing)
        plot_overhead_percent(timing)
        plot_depth_sweep(timing)

    if decisions:
        plot_prefetch_rate(decisions)
        plot_confidence(decisions)

    print("[DONE] All figures saved.")


if __name__ == "__main__":
    main()
