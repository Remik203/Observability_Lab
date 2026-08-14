#!/usr/bin/env python3
"""
plot_metrics.py — Wykresy czasowe metryk infrastrukturalnych dla każdego narzędzia w stosie
===========================================================================================
Każdy panel zawiera jedną linię per **narzędzie** (np. Istio, Fluent Bit,
OTel Collector), a nie per namespace czy kontener.  Linia przedstawia
wygładzoną medianę z iteracji (rolling window = 5 próbek / 25 s).

Oś Y automatycznie obcinana jest do 99. percentyla (+ 10 % marginesu),
co zapobiega spłaszczeniu wykresu przez jednorazowe anomalie.

Użycie:
    python3 plot_metrics.py <stack_name>

Wymagania:
    pip install pandas numpy matplotlib
"""

import argparse
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

SMOOTHING_WINDOW = 5   # okno średniej kroczącej

# Metryki bazowe i mapowanie jednostek
BASE_METRICS = [
    "CPU", "RAM",
    "DiskRead", "DiskWrite",
    "NetRX", "NetTX",
    "Logs_Ingestion_Rate", "Spans_Ingestion_Rate",
    "Context_Switches",
    "HTTP_Errors_Istio", "HTTP_Errors_Beyla",
]

UNIT_RULES = [
    ("CPU",               "CPU [rdzenie]",           1),
    ("RAM",               "RAM [MiB]",               1024 ** 2),
    ("DiskRead",          "Odczyt dysku [MB/s]",     1e6),
    ("DiskWrite",         "Zapis dysku [MB/s]",      1e6),
    ("NetRX",             "Sieć RX [MB/s]",          1e6),
    ("NetTX",             "Sieć TX [MB/s]",          1e6),
    ("Logs_Ingestion",    "Logi [MB/s]",             1e6),
    ("Spans_Ingestion",   "Span-y [1/s]",            1),
    ("Context_Switches",  "Ctx Switches [1/s]",      1),
    ("HTTP_Errors",       "Błędy HTTP [req/s]",      1),
]

# Mapowanie komponentów na czytelne nazwy narzędzi
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

# Kolory narzędzi
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

# Etykieta osi Y
def resolve_units(metric_name: str) -> tuple[str, float]:
    for pattern, ylabel, divisor in UNIT_RULES:
        if pattern in metric_name:
            return ylabel, divisor
    return "Wartość", 1

# Nazwa metryki bez nazwy narzędzia
def get_base_metric(metric_name: str) -> str:
    for suffix in TOOL_LABELS.keys():
        if metric_name.endswith(f"_{suffix}"):
            return metric_name[: -(len(suffix) + 1)]
    return metric_name

METRIC_ORDER = [
    "CPU",
    "RAM",
    "DiskRead",
    "DiskWrite",
    "NetRX",
    "NetTX",
    "Logs_Ingestion_Rate",
    "Spans_Ingestion_Rate",
    "Context_Switches",
    "HTTP_Errors_Istio",
    "HTTP_Errors_Beyla",
]

# Wyodrębnij nazwę komponentu
def get_component(name: str) -> str:
    bm = get_base_metric(name)
    return "Total" if name == bm else name[len(bm) + 1 :]

# Zwraca etykietę do legendy wykresu
def tool_label(component: str) -> str:
    return TOOL_LABELS.get(component, component)


def tool_color(component: str) -> str:
    return TOOL_COLORS.get(component, "#333333")

# Zmiana podkreślenia na spcaję
def pretty_title(metric_name: str) -> str:
    return metric_name.replace("_", " ")


# Wyrównanie i przetworzenie szeregów czasowych

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
        description="Generuje dashboardy metryk dla wskazanego stosu.",
    )
    parser.add_argument("stack_name", help="Nazwa stosu (np. stack_0)")
    args = parser.parse_args()

    results_dir = os.path.join(os.path.dirname(__file__), "results")
    csv_path = os.path.join(results_dir, f"raw_data_{args.stack_name}.csv")
    ts_path = os.path.join(results_dir, f"{args.stack_name}_timestamps.csv")
    events_path = os.path.join(results_dir, "chaos_events.csv")

    if not os.path.isfile(csv_path):
        print(f"ERROR: plik nie istnieje: {csv_path}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path)
    ts_df = pd.read_csv(ts_path) if os.path.isfile(ts_path) else None
    events_df = (
        pd.read_csv(events_path, names=["timestamp", "event"])
        if os.path.isfile(events_path)
        else None
    )

    test_ids = sorted(df["test_name"].unique())

    for test_id in test_ids:
        test_df = df[df["test_name"] == test_id]
        iterations = sorted(test_df["iteration"].unique())
        n_iter = len(iterations)

        available_metrics = sorted(test_df["metric_name"].unique())
        if not available_metrics:
            continue

        def get_metric_sort_key(m: str) -> int:
            try:
                return METRIC_ORDER.index(m)
            except ValueError:
                return 999

        base_metrics_in_test = sorted(
            set(get_base_metric(m) for m in available_metrics),
            key=get_metric_sort_key
        )
        n_metrics = len(base_metrics_in_test)

        ncols = 2 if n_metrics > 1 else 1
        nrows = math.ceil(n_metrics / ncols)

        fig, axes = plt.subplots(
            nrows, ncols,
            figsize=(10 * ncols, 5.5 * nrows),
            squeeze=False,
        )
        fig.suptitle(
            f"{args.stack_name.upper()} — {test_id.upper()}"
            f"  ({n_iter} iteracji, mediana wygładzona, 99-pctl cap)",
            fontsize=16,
            fontweight="bold",
        )

        # Wczytanie zdarzeń OOMKill itp.
        rel_events: dict[str, list[float]] = {}
        if events_df is not None and ts_df is not None:
            for _, ts_row in ts_df[ts_df["test_name"] == test_id].iterrows():
                start_ts = int(ts_row["start_time"])
                end_ts = int(ts_row["end_time"])
                mask = (
                    (events_df["timestamp"] >= start_ts)
                    & (events_df["timestamp"] <= end_ts)
                )
                for _, ev_row in events_df[mask].iterrows():
                    ev_name = ev_row["event"]
                    rel_time = ev_row["timestamp"] - start_ts
                    rel_events.setdefault(ev_name, []).append(rel_time)

        # Rysowanie paneli
        for idx, bm in enumerate(base_metrics_in_test):
            row, col = divmod(idx, ncols)
            ax = axes[row][col]
            ylabel, divisor = resolve_units(bm)

            bm_metrics = [
                m for m in available_metrics if get_base_metric(m) == bm
            ]

            all_vals_for_bm: list[np.ndarray] = []
            has_data = False

            for m in bm_metrics:
                component = get_component(m)
                metric_df = test_df[test_df["metric_name"] == m]
                iter_frames = []
                for it in iterations:
                    it_df = metric_df[metric_df["iteration"] == it].sort_values(
                        "time_relative"
                    )
                    if not it_df.empty:
                        iter_frames.append(it_df)

                if not iter_frames:
                    continue

                t_axis, vals_2d = align_and_resample(iter_frames)
                if len(t_axis) == 0:
                    continue

                has_data = True
                vals_2d = vals_2d / divisor

                valid_vals = vals_2d[~np.isnan(vals_2d)]
                if len(valid_vals) > 0:
                    all_vals_for_bm.append(valid_vals)

                t_min = t_axis / 60.0
                color = tool_color(component)
                label = tool_label(component)

                median_raw = np.nanmedian(vals_2d, axis=0)
                median_smooth = (
                    pd.Series(median_raw)
                    .rolling(window=SMOOTHING_WINDOW, min_periods=1, center=True)
                    .mean()
                    .values
                )
                ax.plot(
                    t_min, median_smooth,
                    color=color, label=label, linewidth=2.0,
                )

            if has_data:
                # Ograniczenie osi Y do 99. percentyla
                if all_vals_for_bm:
                    flat = np.concatenate(all_vals_for_bm)
                    if len(flat) > 0:
                        p99 = np.percentile(flat, 99)
                        if p99 > 0:
                            ax.set_ylim(bottom=0, top=p99 * 1.1)
                        else:
                            ax.set_ylim(bottom=0)

                # Znaczniki wystąpienia zdarzeń 
                for ev_name, times in rel_events.items():
                    avg_t = np.mean(times) / 60.0
                    ax.axvline(
                        avg_t, color="red", linestyle="--",
                        linewidth=1.5, alpha=0.8,
                    )
                    ax.text(
                        avg_t, ax.get_ylim()[1] * 0.92,
                        ev_name, rotation=90, color="red",
                        fontsize=8, fontweight="bold",
                        verticalalignment="top",
                    )

                ax.set_ylabel(ylabel)
                ax.set_xlabel("Czas [min]")
                ax.set_title(pretty_title(bm))
                ax.legend(
                    loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=9,
                )
            else:
                ax.set_title(f"{bm} (brak danych)")

        for idx in range(n_metrics, nrows * ncols):
            r, c = divmod(idx, ncols)
            axes[r][c].set_visible(False)

        plt.tight_layout()
        out_path = os.path.join(
            results_dir, f"{args.stack_name}_{test_id}_dashboard.png",
        )
        plt.savefig(out_path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        print(f"    → zapisano: {out_path}")


if __name__ == "__main__":
    main()
