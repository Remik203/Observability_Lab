#!/usr/bin/env python3
"""
Dashboards:
  A) Istio vs eBPF (stack_1 vs stack_2)
  B) Fluent Bit vs Vector (stack_2 vs stack_3)
  C) Overhead (stack_0 vs stack_4)

Usage:  python3 plot_comparisons.py [--results-dir DIR]
"""
import argparse, glob, os, sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

PALETTE = {
    "stack_0": ("#4CAF50", "Stack 0 – Baseline"),
    "stack_1": ("#2196F3", "Stack 1 – Istio (sidecar)"),
    "stack_2": ("#FF5722", "Stack 2 – Cilium+FluentBit"),
    "stack_3": ("#9C27B0", "Stack 3 – Cilium+Vector"),
    "stack_4": ("#FF9800", "Stack 4 – Full eBPF (Beyla)"),
}
METRIC_LABELS = {
    "CPU_App": ("CPU – Application Pods", "CPU (cores)"),
    "CPU_Obs": ("CPU – Observability Infra", "CPU (cores)"),
    "RAM_App": ("RAM – Application Pods", "RAM (MiB)"),
    "RAM_Obs": ("RAM – Observability Infra", "RAM (MiB)"),
}
plt.rcParams.update({"font.size": 11, "figure.dpi": 150, "savefig.dpi": 200})


def load_all(results_dir):
    pattern = os.path.join(results_dir, "raw_data_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"ERROR: No raw_data_*.csv in {results_dir}", file=sys.stderr)
        sys.exit(1)
    frames = []
    for f in files:
        df = pd.read_csv(f); frames.append(df)
        print(f"  Loaded {os.path.basename(f)} ({len(df)} rows)")
    return pd.concat(frames, ignore_index=True)


def aggregate(df, stack, metric, test=None):
    mask = (df["stack_name"] == stack) & (df["metric_name"] == metric)
    if test: mask &= df["test_name"] == test
    sub = df[mask]
    if sub.empty: return np.array([]), np.array([]), np.array([])
    grid = np.arange(0, sub["time_relative"].max() + 5, 5.0)
    curves = []
    for _, g in sub.groupby("iteration"):
        if len(g) < 2: continue
        curves.append(np.interp(grid, g["time_relative"].values, g["value"].values,
                                left=np.nan, right=np.nan))
    if not curves: return np.array([]), np.array([]), np.array([])
    m = np.array(curves)
    return grid, np.nanmean(m, 0), np.nanstd(m, 0)


def plot_metric(ax, df, stacks, metric, test=None):
    title, ylabel = METRIC_LABELS[metric]
    is_ram = "RAM" in metric
    for s in stacks:
        col, lbl = PALETTE.get(s, ("gray", s))
        t, mean, std = aggregate(df, s, metric, test)
        if len(t) == 0: continue
        t_min = t / 60.0
        if is_ram: mean /= 1024**2; std /= 1024**2; ylabel = "RAM (MiB)"
        ax.plot(t_min, mean, lw=2, color=col, label=lbl)
        ax.fill_between(t_min, mean - std, mean + std, alpha=0.2, color=col)
    ax.set_title(title, fontweight="bold"); ax.set_ylabel(ylabel)
    ax.set_xlabel("Time (min)"); ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, ls="--", alpha=0.4); ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))


def dashboard(df, stacks, title, fname, rdir, test=None):
    avail = df["stack_name"].unique()
    valid = [s for s in stacks if s in avail]
    if not valid:
        print(f"  ⚠ SKIP {fname} – no data for {stacks}"); return
    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    fig.suptitle(title, fontsize=17, fontweight="bold", y=0.98)
    sub = "All tests" if test is None else f"Test: {test}"
    fig.text(0.5, 0.95, sub, ha="center", fontsize=11, color="gray")
    for ax, m in zip(axes.flat, METRIC_LABELS):
        plot_metric(ax, df, valid, m, test)
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    out = os.path.join(rdir, fname); plt.savefig(out); plt.close(fig)
    print(f"  ✓ {out}")


def main():
    p = argparse.ArgumentParser(description="Cross-stack comparison dashboards.")
    p.add_argument("--results-dir",
                   default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"))
    args = p.parse_args()
    rdir = args.results_dir; os.makedirs(rdir, exist_ok=True)

    print("=" * 70); print("  Cross-Stack Comparison Dashboard Generator"); print("=" * 70)
    df = load_all(rdir)
    tests = sorted(df["test_name"].unique())
    print(f"\n  Stacks: {sorted(df['stack_name'].unique())}")
    print(f"  Tests:  {tests}\n")

    # A: Istio vs eBPF
    print("── A: Istio vs Cilium ──")
    dashboard(df, ["stack_1","stack_2"],
              "Challenge A: Istio (Sidecar) vs Cilium (eBPF)\nObservability Resource Usage",
              "comparison_A_istio_vs_ebpf.png", rdir)
    for t in tests:
        dashboard(df, ["stack_1","stack_2"], f"A: Istio vs Cilium – {t}",
                  f"comparison_A_{t}.png", rdir, t)

    # B: Fluent Bit vs Vector
    print("\n── B: Fluent Bit vs Vector ──")
    dashboard(df, ["stack_2","stack_3"],
              "Challenge B: Fluent Bit (C) vs Vector (Rust)\nLog Agent Comparison",
              "comparison_B_fluentbit_vs_vector.png", rdir)
    for t in tests:
        dashboard(df, ["stack_2","stack_3"], f"B: FluentBit vs Vector – {t}",
                  f"comparison_B_{t}.png", rdir, t)

    # C: Overhead
    print("\n── C: Overhead ──")
    dashboard(df, ["stack_0","stack_4"],
              "Challenge C: Observability Overhead\nBaseline vs Full eBPF Stack",
              "comparison_C_overhead.png", rdir)
    for t in tests:
        dashboard(df, ["stack_0","stack_4"], f"C: Overhead – {t}",
                  f"comparison_C_{t}.png", rdir, t)

    # Bonus: all stacks
    print("\n── All Stacks ──")
    dashboard(df, ["stack_0","stack_1","stack_2","stack_3","stack_4"],
              "All Stacks – Complete Resource Usage Comparison",
              "comparison_ALL_stacks.png", rdir)

    print(f"\n{'='*70}\n  ✓ All dashboards generated.\n  ✓ Dir: {rdir}\n{'='*70}")

if __name__ == "__main__":
    main()
