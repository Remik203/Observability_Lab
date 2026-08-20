#!/usr/bin/env python3
"""
plot_comparisons.py — Wykresy porównawcze między stosami obserwowalności
========================================================================
Użycie:
    python3 plot_comparisons.py [--results-dir PATH]

Wymagania:
    pip install pandas numpy matplotlib
"""

import argparse
import glob
import math
import os
import sys
import warnings

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import pandas as pd

# Konfiguracja globalna
warnings.filterwarnings(action="ignore", message="All-NaN slice encountered")

plt.rcParams.update({
    # --- Czcionki ---
    "font.family": "serif",          
    "font.size": 10,                 # Bazowy rozmiar
    "axes.labelsize": 11,            # Podpisy osi (X, Y)
    "axes.titlesize": 12,            # Tytuł wykresu
    "xtick.labelsize": 9,            # Wartości na osi X
    "ytick.labelsize": 9,            # Wartości na osi Y
    "legend.fontsize": 9,            # Rozmiar tekstu legendy
    "legend.title_fontsize": 10,

    # --- Ramki i linie ---
    "axes.linewidth": 0.8,           # Grubość osi wykresu
    "lines.linewidth": 1.5,          # Grubość linii danych (czytelna po przeskalowaniu)
    "lines.markersize": 5,           # Wielkość punktów na wykresie

    # --- Siatka ---
    "axes.grid": True,
    "grid.alpha": 0.4,
    "grid.linestyle": ":",           # Kropkowana siatka nie odwraca uwagi od danych
    "grid.linewidth": 0.6,

    # --- Wygląd tła i legendy ---
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "legend.frameon": True,          # Ramka wokół legendy
    "legend.framealpha": 0.9,        # Lekko przezroczyste tło pod legendą
    "legend.edgecolor": "#CCCCCC",

    # --- Jakość renderowania ---
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

# Paleta kolorów stosów
PALETTE: dict[str, tuple[str, str]] = {
    "stack_0": ("#4CAF50", "Stack 0 (Baseline)"),
    "stack_1": ("#2196F3", "Stack 1 (Istio)"),
    "stack_2": ("#FF5722", "Stack 2 (Cilium+FluentBit)"),
    "stack_3": ("#9C27B0", "Stack 3 (Cilium+Vector)"),
    "stack_4": ("#FF9800", "Stack 4 (eBPF Beyla)"),
}

# Czytelne nazwy narzędzi i kolory
TOOL_LABELS: dict[str, str] = {
    "Istio":          "Istio (sidecar proxy)",
    "Cilium":         "Cilium (eBPF CNI)",
    "FluentBit":      "Fluent Bit",
    "Vector":         "Vector",
    "OTel_Collector": "OTel Collector",
    "Jaeger":         "Jaeger v2",
    "Beyla":          "Beyla (eBPF auto-instrumentacja)",
    "Loki":           "Grafana Loki",
    "GoogleApp":      "Aplikacja (Online Boutique)",
    "K3s_Infra":      "Infrastruktura K3s",
    "Monitor_Base":   "Prometheus + Grafana + Promtail",
    "System_Unknown": "Pozostałe procesy systemowe",
}

TOOL_COLORS: dict[str, str] = {
    "Istio":          "#1565C0",
    "K3s_Infra":      "#1A237E",
    "Vector":         "#00838F",
    "Monitor_Base":   "#546E7A",
    "GoogleApp":      "#2E7D32",
    "OTel_Collector": "#6A1B9A",
    "Jaeger":         "#C2185B",
    "Cilium":         "#C62828",
    "FluentBit":      "#EF6C00",
    "Loki":           "#5D4037",
    "Beyla":          "#F9A825",
    "System_Unknown": "#757575",
}

# Metryki bazowe i jednostki
BASE_METRICS = [
    "CPU", "RAM",
    "DiskRead", "DiskWrite",
    "NetRX", "NetTX",
    "Logs_Ingestion_Rate", "Spans_Ingestion_Rate",
    "Context_Switches",
    "HTTP_Errors_Istio", "HTTP_Errors_Beyla",
]

# Wyodrębnienie nazwy metryki
def get_base_metric(name: str) -> str:
    for bm in BASE_METRICS:
        if name.startswith(bm):
            return bm
    return name

# Wyodrębnienie nazwy komponentu
def get_component(name: str) -> str:
    bm = get_base_metric(name)
    return "Total" if name == bm else name[len(bm) + 1 :]

# Zwracanie etykiety narzędzia
def tool_label(component: str) -> str:
    return TOOL_LABELS.get(component, component)

# Etykiety osi na podstawie nazwy metryki
def resolve_units(bm: str) -> tuple[str, float]:
    rules = [
        ("CPU",              "CPU [rdzenie]",        1),
        ("RAM",              "RAM [MiB]",            1024 ** 2),
        ("DiskRead",         "Odczyt dysku [MB/s]",  1e6),
        ("DiskWrite",        "Zapis dysku [MB/s]",   1e6),
        ("NetRX",            "Sieć RX [MB/s]",       1e6),
        ("NetTX",            "Sieć TX [MB/s]",       1e6),
        ("Logs_Ingestion",   "Logi [MB/s]",          1e6),
        ("Spans_Ingestion",  "Span-y [1/s]",         1),
        ("Context_Switches", "Ctx Switches [1/s]",   1),
        ("HTTP_Errors",      "Błędy HTTP [req/s]",   1),
    ]
    for pattern, ylabel, divisor in rules:
        if pattern in bm:
            return ylabel, divisor
    return "Wartość", 1

# Zmiana podkteśleń na spacje 
def pretty_title(name: str) -> str:
    return name.replace("_", " ")


# Wyrównanie i przetwarzanie szeregów czasowych

def align_and_resample(
    series_list: list[pd.DataFrame],
    freq_seconds: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    if not series_list:
        return np.array([]), np.array([])

    max_duration = max(
        df["time_relative"].max() for df in series_list if not df.empty
    )
    if pd.isna(max_duration):
        return np.array([]), np.array([])

    grid = np.arange(0, max_duration + freq_seconds, freq_seconds)
    resampled = []
    for df in series_list:
        if df.empty:
            resampled.append(np.full_like(grid, np.nan))
            continue
        interp = np.interp(
            grid,
            df["time_relative"].values,
            df["value"].values,
            left=np.nan,
            right=np.nan,
        )
        resampled.append(interp)
    return grid, np.array(resampled)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generuje wykresy porównawcze i tabelę metryk.",
    )
    parser.add_argument(
        "--results-dir",
        default=os.path.join(os.path.dirname(__file__), "results"),
    )
    args = parser.parse_args()
    rdir = args.results_dir

    files = sorted(glob.glob(os.path.join(rdir, "raw_data_*.csv")))
    if not files:
        print("ERROR: Nie znaleziono plików raw_data_*.csv", file=sys.stderr)
        sys.exit(1)

    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

    # 1. Obliczanie statystyk per narzędzie do tabeli
    print("Obliczanie kluczowych metryk per narzędzie...")
    summary_rows: list[dict] = []

    for stack in sorted(df["stack_name"].unique()):
        for test in sorted(df["test_name"].unique()):
            sub = df[(df["stack_name"] == stack) & (df["test_name"] == test)]
            if sub.empty:
                continue

            for m_name in sub["metric_name"].unique():
                bm = get_base_metric(m_name)
                comp = get_component(m_name)
                _, div = resolve_units(bm)

                m_sub = sub[sub["metric_name"] == m_name]
                iter_frames = [
                    g.sort_values("time_relative")
                    for _, g in m_sub.groupby("iteration")
                ]
                if not iter_frames:
                    continue

                t, vals_2d = align_and_resample(iter_frames)
                if len(t) == 0:
                    continue

                # Mediana po iteracjach
                median_curve = np.nanmedian(vals_2d, axis=0) / div
                valid = median_curve[~np.isnan(median_curve)]
                if len(valid) == 0:
                    continue

                summary_rows.append({
                    "Stack":     stack,
                    "Test":      test,
                    "Metric":    bm,
                    "Component": comp,
                    "Tool":      tool_label(comp),
                    "Mean":      round(float(np.mean(valid)), 6),
                    "Median":    round(float(np.median(valid)), 6),
                    "StdDev":    round(float(np.std(valid)), 6),
                    "P95":       round(float(np.percentile(valid, 95)), 6),
                    "P99":       round(float(np.percentile(valid, 99)), 6),
                    "Max":       round(float(np.max(valid)), 6),
                })

    sum_df = pd.DataFrame(summary_rows)
    sum_path = os.path.join(rdir, "metrics_summary.csv")
    sum_df.to_csv(sum_path, index=False)
    print(f"Zapisano tabelę metryk: {sum_path}")

    # 2. Wykresy słupkowe (stacked bar, P95) per narzędzie
    print("Generowanie wykresów słupkowych...")
    for test in sorted(df["test_name"].unique()):
        test_sum = sum_df[sum_df["Test"] == test]
        if test_sum.empty:
            continue

        bms = sorted(test_sum["Metric"].unique())
        ncols = 2
        nrows = math.ceil(len(bms) / ncols)

        fig, axes = plt.subplots(
            nrows, ncols,
            figsize=(12 * ncols, 7 * nrows),
            squeeze=False,
        )
        fig.suptitle(
            f"Porównanie narzutu zasobów (P95) — {test.upper()}",
            fontsize=18, fontweight="bold",
        )

        for idx, bm in enumerate(bms):
            row, col = divmod(idx, ncols)
            ax = axes[row][col]
            ylab, _ = resolve_units(bm)

            bm_df = test_sum[test_sum["Metric"] == bm]
            stacks = sorted(bm_df["Stack"].unique())
            comps = sorted(bm_df["Component"].unique())
            if any(c for c in comps if c != "Total"):
                comps = [c for c in comps if c != "Total"]

            bottoms = np.zeros(len(stacks))

            for c in comps:
                c_vals = []
                for s in stacks:
                    val = bm_df[
                        (bm_df["Stack"] == s) & (bm_df["Component"] == c)
                    ]["P95"].sum()
                    c_vals.append(val)
                ax.bar(
                    stacks, c_vals, bottom=bottoms,
                    label=tool_label(c),
                    color=TOOL_COLORS.get(c, "#333333"),
                    edgecolor="white", linewidth=0.5,
                )
                bottoms += np.array(c_vals)

            ax.set_ylabel(f"P95 {ylab}")
            ax.set_title(pretty_title(bm), fontsize=13)
            ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left")

            # Symlog osi Y dla metryk z kolosalnymi roznicami skali (np. Spans Ingestion)
            if bm in ("Spans_Ingestion_Rate", "Logs_Ingestion_Rate"):
                ax.set_yscale("symlog", linthresh=1.0)
                ax.set_ylabel(f"P95 {ylab} (Log Scale)")

            # Etykiety osi X
            ax.set_xticks(range(len(stacks)))
            ax.set_xticklabels(
                [PALETTE.get(s, (None, s))[1] for s in stacks],
                rotation=30, ha="right", fontsize=10,
            )

            # Wypisywanie dokladnych wartosci nad slupkami
            for s_idx, s in enumerate(stacks):
                val = bottoms[s_idx]
                if val > 0:
                    if val >= 1_000_000:
                        txt = f"{val/1e6:.2f}M"
                    elif val >= 10_000:
                        txt = f"{val/1e3:.1f}k"
                    elif val >= 10.0:
                        txt = f"{val:.1f}"
                    elif val >= 0.001:
                        txt = f"{val:.3f}"
                    else:
                        txt = f"{val:.4f}"
                    ax.annotate(
                        txt,
                        xy=(s_idx, val),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha="center", va="bottom",
                        fontsize=8, fontweight="bold"
                    )

        # Ukryj puste panele
        for idx in range(len(bms), nrows * ncols):
            r, c = divmod(idx, ncols)
            axes[r][c].set_visible(False)

        plt.tight_layout()
        out = os.path.join(rdir, f"comparison_bar_{test}.png")
        plt.savefig(out, bbox_inches="tight")
        plt.close(fig)
        print(f"    → {out}")

    # 3. Boxploty p95 latency
    k6_csv = os.path.join(rdir, "k6_business_metrics.csv")
    if os.path.exists(k6_csv):
        print("Generowanie boxplotów p95 latency...")
        k6_df = pd.read_csv(k6_csv)
        fig, ax = plt.subplots(figsize=(14, 7))

        tests = sorted(k6_df["test_name"].unique())
        stacks = sorted(k6_df["stack_name"].unique())

        data: list[np.ndarray] = []
        positions: list[float] = []
        colors: list[str] = []
        tick_positions: list[float] = []

        pos = 1
        for t in tests:
            tick_positions.append(pos + (len(stacks) - 1) / 2.0)
            for s in stacks:
                vals = (
                    k6_df[
                        (k6_df["test_name"] == t) & (k6_df["stack_name"] == s)
                    ]["p95_latency_ms"]
                    .dropna()
                    .values
                )
                if len(vals) > 0:
                    data.append(vals)
                    positions.append(pos)
                    colors.append(PALETTE.get(s, ("gray", s))[0])
                pos += 1
            pos += 1  # przerwa między scenariuszami

        if data:
            bplot = ax.boxplot(
                data,
                positions=positions,
                patch_artist=True,
                notch=True,
                boxprops=dict(alpha=0.85),
                medianprops=dict(color="black", linewidth=2),
                whiskerprops=dict(linewidth=1.2),
                capprops=dict(linewidth=1.2),
            )
            for patch, color in zip(bplot["boxes"], colors):
                patch.set_facecolor(color)

            ax.set_xticks(tick_positions)
            ax.set_xticklabels(
                [t.upper() for t in tests],
                fontsize=12, fontweight="bold",
            )

            from matplotlib.patches import Patch

            legend_elements = [
                Patch(
                    facecolor=PALETTE.get(s, ("gray", s))[0],
                    label=PALETTE.get(s, ("gray", s))[1],
                )
                for s in stacks
            ]
            ax.legend(handles=legend_elements, loc="upper left", fontsize=11)

        ax.set_title(
            "Wpływ stosu na opóźnienia aplikacji — p95 Latency",
            fontsize=16, fontweight="bold",
        )
        ax.set_ylabel("p95 Latency [ms]", fontsize=13)
        ax.grid(axis="y", linestyle="--", alpha=0.6)
        plt.tight_layout()
        out = os.path.join(rdir, "comparison_E_p95_boxplot.png")
        plt.savefig(out, bbox_inches="tight")
        plt.close(fig)
        print(f"    → {out}")

    print("Wszystkie wykresy porównawcze wygenerowane.")


if __name__ == "__main__":
    main()
