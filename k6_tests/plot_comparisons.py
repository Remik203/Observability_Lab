#!/usr/bin/env python3
"""
plot_comparisons.py – Cross-Stack Comparison Dashboards
========================================================
Generates comparison dashboards from raw_data_*.csv files AND
business-impact dashboards from k6_business_metrics.csv.

Dashboards:
  A) Istio vs eBPF (stack_1 vs stack_2)
  B) Fluent Bit vs Vector (stack_2 vs stack_3)
  C) Overhead (stack_0 vs stack_4)
  D) All stacks
  E) Business Impact – p95 Latency & Failure Rate (from K6 summaries)

Usage:  python3 plot_comparisons.py [--results-dir DIR]
"""

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Stack palette
PALETTE = {
    "stack_0": ("#4CAF50", "Stack 0 – Baseline"),
    "stack_1": ("#2196F3", "Stack 1 – Istio (sidecar)"),
    "stack_2": ("#FF5722", "Stack 2 – Cilium+FluentBit"),
    "stack_3": ("#9C27B0", "Stack 3 – Cilium+Vector"),
    "stack_4": ("#FF9800", "Stack 4 – Full eBPF (Beyla)"),
}

# Unit conversion & label rules
UNIT_RULES = [
    ("CPU",             "CPU (cores)",          1),
    ("RAM",             "RAM (MiB)",            1024 ** 2),
    ("NetRX",           "Network RX (MB/s)",    1e6),
    ("NetTX",           "Network TX (MB/s)",    1e6),
    ("DiskWrite",       "Disk Write (MB/s)",    1e6),
    ("Logs_Ingestion",  "Log Ingest (MB/s)",    1e6),
    ("Spans_Ingestion", "Spans/s",              1),
    ("Context_Switches","Switches/sec",         1),
]

def resolve_units(metric_name: str) -> tuple[str, float]:
    for pattern, ylabel, divisor in UNIT_RULES:
        if pattern in metric_name:
            return ylabel, divisor
    return "Value", 1

def pretty_title(metric_name: str) -> str:
    return metric_name.replace("_", " – ", 1).replace("_", " ")

plt.rcParams.update({"font.size": 11, "figure.dpi": 150, "savefig.dpi": 200})

# Data loading
def load_all(results_dir):
    pattern = os.path.join(results_dir, "raw_data_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"ERROR: No raw_data_*.csv in {results_dir}", file=sys.stderr)
        sys.exit(1)
    frames = []
    for f in files:
        df = pd.read_csv(f)
        frames.append(df)
        print(f"  Loaded {os.path.basename(f)} ({len(df)} rows)")
    return pd.concat(frames, ignore_index=True)

# Aggregation for Time-Series
def aggregate(df, stack, metric, test=None):
    mask = (df["stack_name"] == stack) & (df["metric_name"] == metric)
    if test:
        mask &= df["test_name"] == test
    sub = df[mask]
    if sub.empty:
        return np.array([]), np.array([]), np.array([])
    grid = np.arange(0, sub["time_relative"].max() + 5, 5.0)
    curves = []
    for _, g in sub.groupby("iteration"):
        if len(g) < 2:
            continue
        curves.append(np.interp(grid, g["time_relative"].values, g["value"].values,
                                left=np.nan, right=np.nan))
    if not curves:
        return np.array([]), np.array([]), np.array([])
    m = np.array(curves)
    return grid, np.nanmean(m, 0), np.nanstd(m, 0)

# Time-Series Plot (Per Test)
def plot_metric(ax, df, stacks, metric, test):
    ylabel, divisor = resolve_units(metric)
    for s in stacks:
        col, lbl = PALETTE.get(s, ("gray", s))
        t, mean, std = aggregate(df, s, metric, test)
        if len(t) == 0:
            continue
        t_min = t / 60.0
        mean = mean / divisor
        std = std / divisor
        ax.plot(t_min, mean, lw=2, color=col, label=lbl)
        ax.fill_between(t_min, mean - std, mean + std, alpha=0.2, color=col)
    ax.set_title(pretty_title(metric), fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Time (min)")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, ls="--", alpha=0.4)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))

# Bar Chart Plot (Overall Summary)
def plot_aggregate_bar(ax, df, stacks, metric):
    ylabel, divisor = resolve_units(metric)
    tests = sorted(df["test_name"].unique())
    x = np.arange(len(tests))
    n_stacks = len(stacks)
    bar_width = 0.8 / max(n_stacks, 1)

    for i, stack in enumerate(stacks):
        color, label = PALETTE.get(stack, ("gray", stack))
        
        means = []
        stds = []
        for t in tests:
            mask = (df["stack_name"] == stack) & (df["metric_name"] == metric) & (df["test_name"] == t)
            vals = df[mask]["value"].dropna() / divisor
            
            means.append(vals.mean() if not vals.empty else 0)
            stds.append(vals.std() if len(vals) > 1 else 0)

        offset = (i - n_stacks / 2 + 0.5) * bar_width
        ax.bar(x + offset, means, bar_width, yerr=stds, capsize=3,
               label=label, color=color, alpha=0.85)

    ax.set_title(f"{pretty_title(metric)} (Test Averages)", fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    ax.set_xticklabels(tests, rotation=30, ha="right")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", ls="--", alpha=0.4)

# Dynamic dashboard: discovers all metrics in the data
def dashboard(df, stacks, title, fname, rdir, test=None):
    avail = df["stack_name"].unique()
    valid = [s for s in stacks if s in avail]
    if not valid:
        print(f"  ⚠ SKIP {fname} – no data for {stacks}")
        return

    mask = df["stack_name"].isin(valid)
    if test:
        mask &= df["test_name"] == test
    sub = df[mask]
    metrics = sorted(sub["metric_name"].unique())
    if not metrics:
        print(f"  ⚠ SKIP {fname} – no metrics in data")
        return

    ncols = 2
    nrows = max(1, -(-len(metrics) // ncols))  # ceil division

    fig, axes = plt.subplots(nrows, ncols, figsize=(18, 5 * nrows), squeeze=False)
    fig.suptitle(title, fontsize=17, fontweight="bold", y=0.99)
    sub_title = "Overall Averages across tests" if test is None else f"Time-Series for Test: {test}"
    fig.text(0.5, 0.97, sub_title, ha="center", fontsize=11, color="gray")

    for idx, m in enumerate(metrics):
        row, col = divmod(idx, ncols)
        if test is None:
            plot_aggregate_bar(axes[row][col], df, valid, m)
        else:
            plot_metric(axes[row][col], df, valid, m, test)

    for idx in range(len(metrics), nrows * ncols):
        row, col = divmod(idx, ncols)
        axes[row][col].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out = os.path.join(rdir, fname)
    plt.savefig(out)
    plt.close(fig)
    print(f"  ✓ {out}")

# Business Impact Dashboard
def business_impact_dashboard(rdir):
    csv_path = os.path.join(rdir, "k6_business_metrics.csv")
    if not os.path.isfile(csv_path):
        print(f" SKIP Business Impact dashboard – {csv_path} not found")
        return

    bm = pd.read_csv(csv_path)
    if bm.empty:
        print(" SKIP Business Impact dashboard – CSV is empty")
        return

    stacks = sorted(bm["stack_name"].unique())
    tests = sorted(bm["test_name"].unique())
    n_stacks = len(stacks)

    print(f"  Business Impact: {n_stacks} stacks, {len(tests)} tests")

    fig, axes = plt.subplots(1, 2, figsize=(18, 7))
    fig.suptitle("Business Impact: K6 Client-Side Metrics", fontsize=17, fontweight="bold")

    # Left panel: p95 latency
    ax = axes[0]
    x = np.arange(len(tests))
    bar_width = 0.8 / max(n_stacks, 1)
    for i, stack in enumerate(stacks):
        color, label = PALETTE.get(stack, ("gray", stack))
        stack_df = bm[bm["stack_name"] == stack]
        means = [stack_df[stack_df["test_name"] == t]["p95_latency_ms"].dropna().mean() for t in tests]
        stds = [stack_df[stack_df["test_name"] == t]["p95_latency_ms"].dropna().std() for t in tests]
        offset = (i - n_stacks / 2 + 0.5) * bar_width
        ax.bar(x + offset, [m if not pd.isna(m) else 0 for m in means], bar_width, 
               yerr=[s if not pd.isna(s) else 0 for s in stds], capsize=3, label=label, color=color, alpha=0.85)

    ax.set_title("p95 Latency (ms) by Test", fontweight="bold")
    ax.set_ylabel("p95 Latency (ms)")
    ax.set_xticks(x)
    ax.set_xticklabels(tests, rotation=30, ha="right")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", ls="--", alpha=0.4)

    # Right panel: failure rate
    ax = axes[1]
    for i, stack in enumerate(stacks):
        color, label = PALETTE.get(stack, ("gray", stack))
        stack_df = bm[bm["stack_name"] == stack]
        means = [stack_df[stack_df["test_name"] == t]["req_failed_rate"].dropna().mean() * 100 for t in tests]
        stds = [stack_df[stack_df["test_name"] == t]["req_failed_rate"].dropna().std() * 100 for t in tests]
        offset = (i - n_stacks / 2 + 0.5) * bar_width
        ax.bar(x + offset, [m if not pd.isna(m) else 0 for m in means], bar_width, 
               yerr=[s if not pd.isna(s) else 0 for s in stds], capsize=3, label=label, color=color, alpha=0.85)

    ax.set_title("Request Failure Rate (%) by Test", fontweight="bold")
    ax.set_ylabel("Failure Rate (%)")
    ax.set_xticks(x)
    ax.set_xticklabels(tests, rotation=30, ha="right")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", ls="--", alpha=0.4)

    plt.tight_layout()
    out = os.path.join(rdir, "comparison_E_business_impact.png")
    plt.savefig(out)
    plt.close(fig)
    print(f"  ✓ {out}")

    # Dashboard E2: Boxplot
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.suptitle("Business Impact: p95 Latency Distribution per Stack", fontsize=15, fontweight="bold")

    box_data, box_labels, box_colors = [], [], []
    for stack in stacks:
        vals = bm[bm["stack_name"] == stack]["p95_latency_ms"].dropna()
        box_data.append(vals.values)
        color, label = PALETTE.get(stack, ("gray", stack))
        box_labels.append(label)
        box_colors.append(color)

    bp = ax.boxplot(box_data, labels=box_labels, patch_artist=True, notch=False)
    for patch, color in zip(bp["boxes"], box_colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)

    ax.set_ylabel("p95 Latency (ms)")
    ax.set_xlabel("Observability Stack")
    ax.grid(True, axis="y", ls="--", alpha=0.4)
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    out = os.path.join(rdir, "comparison_E_p95_boxplot.png")
    plt.savefig(out)
    plt.close(fig)
    print(f"  ✓ {out}")

def main():
    p = argparse.ArgumentParser(description="Cross-stack comparison dashboards.")
    p.add_argument("--results-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    args = p.parse_args()
    rdir = args.results_dir
    os.makedirs(rdir, exist_ok=True)

    print("=" * 70)
    print("  Cross-Stack Comparison Dashboard Generator")
    print("=" * 70)
    df = load_all(rdir)
    tests = sorted(df["test_name"].unique())

    print("── A: Istio vs Cilium ──")
    dashboard(df, ["stack_1", "stack_2"], "Challenge A: Istio (Sidecar) vs Cilium (eBPF)\nObservability Resource Usage", "comparison_A_istio_vs_ebpf.png", rdir)
    for t in tests:
        dashboard(df, ["stack_1", "stack_2"], f"A: Istio vs Cilium – {t}", f"comparison_A_{t}.png", rdir, t)

    print("\n── B: Fluent Bit vs Vector ──")
    dashboard(df, ["stack_2", "stack_3"], "Challenge B: Fluent Bit (C) vs Vector (Rust)\nLog Agent Comparison", "comparison_B_fluentbit_vs_vector.png", rdir)
    for t in tests:
        dashboard(df, ["stack_2", "stack_3"], f"B: FluentBit vs Vector – {t}", f"comparison_B_{t}.png", rdir, t)

    print("\n── C: Overhead ──")
    dashboard(df, ["stack_0", "stack_4"], "Challenge C: Observability Overhead\nBaseline vs Full eBPF Stack", "comparison_C_overhead.png", rdir)
    for t in tests:
        dashboard(df, ["stack_0", "stack_4"], f"C: Overhead – {t}", f"comparison_C_{t}.png", rdir, t)

    # D: All stacks
    print("\n── D: All Stacks ──")
    # 1. Wykres słupkowy (Średnie ze wszystkich testów dla wszystkich stosów)
    dashboard(df, ["stack_0", "stack_1", "stack_2", "stack_3", "stack_4"],
              "All Stacks – Complete Resource Usage Comparison (Averages)",
              "comparison_ALL_stacks_summary.png", rdir)
    
    # 2. Wykresy liniowe (Każdy test osobno z nałożonymi 5 liniami na raz!)
    for t in tests:
        dashboard(df, ["stack_0", "stack_1", "stack_2", "stack_3", "stack_4"], 
                  f"D: All Stacks Time-Series – {t}",
                  f"comparison_ALL_stacks_{t}.png", rdir, t)
    print("\n── E: Business Impact ──")
    business_impact_dashboard(rdir)

    # F: The Ultimate Showdown (Baseline vs Istio vs eBPF)
    print("\n── F: Baseline vs Istio vs eBPF ──")
    dashboard(df, ["stack_0", "stack_1", "stack_4"],
              "Challenge F: Architecture Showdown\nBaseline vs Istio (Sidecar) vs Full eBPF",
              "comparison_F_showdown.png", rdir)
    for t in tests:
        dashboard(df, ["stack_0", "stack_1", "stack_4"], f"F: Showdown – {t}",
                  f"comparison_F_{t}.png", rdir, t)

    print(f"\n{'=' * 70}\n  ✓ All dashboards generated.\n  ✓ Dir: {rdir}\n{'=' * 70}")

if __name__ == "__main__":
    main()
