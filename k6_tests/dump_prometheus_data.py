#!/usr/bin/env python3
"""
dump_prometheus_data.py — Eksport surowych metryk z Prometheusa do CSV
======================================================================
Użycie:
    python3 dump_prometheus_data.py <stack_name> [--prometheus URL]

Wymagania:
    pip install pandas requests
"""

import argparse
import os
import sys
import time
from typing import Any

import pandas as pd
import requests

# Konfiguracja 
TARGET_IP = os.getenv("TARGET_IP", "150.254.32.183")
STEP = "5s"
RATE_WINDOW = "1m"
MAX_RETRIES = 3
RETRY_DELAY = 5

# Definicje metryk PromQL
METRICS: dict[str, tuple[str, str]] = {
    "CPU": (
        f'sum by (namespace, pod, container) ('
        f'  rate(container_cpu_usage_seconds_total'
        f'    {{container!="POD", container!=""}}[{RATE_WINDOW}])'
        f')',
        "Zużycie CPU per kontener [rdzenie]",
    ),
    "RAM": (
        'sum by (namespace, pod, container) ('
        '  container_memory_working_set_bytes'
        '    {container!="POD", container!=""}'
        ')',
        "Pamięć working-set per kontener [bajty]",
    ),
    "DiskRead": (
        f'sum by (namespace, pod, container) ('
        f'  rate(container_fs_reads_bytes_total'
        f'    {{container!="POD", container!=""}}[{RATE_WINDOW}])'
        f')',
        "Odczyty dyskowe per kontener [B/s]",
    ),
    "DiskWrite": (
        f'sum by (namespace, pod, container) ('
        f'  rate(container_fs_writes_bytes_total'
        f'    {{container!="POD", container!=""}}[{RATE_WINDOW}])'
        f')',
        "Zapisy dyskowe per kontener [B/s]",
    ),
    "NetRX": (
        f'sum by (namespace, pod) ('
        f'  rate(container_network_receive_bytes_total[{RATE_WINDOW}])'
        f')',
        "Ruch sieciowy przychodzący per pod [B/s]",
    ),
    "NetTX": (
        f'sum by (namespace, pod) ('
        f'  rate(container_network_transmit_bytes_total[{RATE_WINDOW}])'
        f')',
        "Ruch sieciowy wychodzący per pod [B/s]",
    ),
    "Logs_Ingestion_Rate": (
        f'sum(rate(loki_distributor_bytes_received_total[{RATE_WINDOW}])) '
        f'or sum(rate(loki_ingester_chunk_stored_bytes_total[{RATE_WINDOW}])) '
        f'or sum(rate(vector_component_received_events_total{{component_id="kubernetes_logs"}}[{RATE_WINDOW}])) '
        f'or vector(0)',
        "Logi — tempo przyjmowania [event/s lub B/s]",
    ),
    "Spans_Ingestion_Rate": (
        f'sum(rate(otelcol_receiver_accepted_spans[{RATE_WINDOW}])) '
        f'or sum(rate(otelcol_receiver_accepted_spans_total[{RATE_WINDOW}])) '
        f'or sum(rate(jaeger_collector_spans_received_total[{RATE_WINDOW}])) '
        f'or sum(rate(beyla_network_flow_bytes_total{{k8s_dst_owner_type=~"Deployment|Service"}}[{RATE_WINDOW}])) '
        f'or sum(rate(http_server_request_duration_seconds_count[{RATE_WINDOW}])) '
        f'or vector(0)',
        "Ślady — przepustowość / spany [items/s]",
    ),
    "Context_Switches": (
        f'sum(rate(node_context_switches_total[{RATE_WINDOW}]))',
        "Przełączenia kontekstu jądra [1/s] — narzut eBPF vs sidecar",
    ),
    "Http_Errors_Istio": (
        f'sum(rate(istio_requests_total{{response_code=~"4..|5.."}}[{RATE_WINDOW}])) '
        f'or sum(rate(envoy_cluster_upstream_rq_5xx[{RATE_WINDOW}])) '
        f'or sum(rate(envoy_cluster_upstream_rq_timeout[{RATE_WINDOW}])) '
        f'or sum(rate(envoy_http_downstream_rq_toobig[{RATE_WINDOW}])) '
        f'or sum(rate(envoy_http_downstream_rq_rx_reset[{RATE_WINDOW}])) '
        f'or (sum(rate(istio_requests_total[{RATE_WINDOW}])) * 0) '
        f'or vector(0)',
        "Envoy / Istio — wskaźnik błędów sidecara [błędów/s]",
    ),
    "HTTP_Errors_Beyla": (
        f'sum(rate(http_server_request_duration_seconds_count'
        f'{{http_response_status_code=~"4..|5.."}}[{RATE_WINDOW}])) '
        f'or (sum(rate(http_server_request_duration_seconds_count[{RATE_WINDOW}])) * 0)',
        "Beyla eBPF — tempo żądań 4xx/5xx [req/s]",
    ),
}


# *** Mapowanie kontenerów / podów na komponenty logiczne ***
# Kategorie:
#   GoogleApp      – mikroserwisy aplikacji Online Boutique
#   Istio          – sidecar proxy, istiod, ingress
#   Cilium         – agent Cilium, Hubble
#   FluentBit      – kolektor logów Fluent Bit
#   Vector         – kolektor logów Vector
#   OTel_Collector – OpenTelemetry Collector
#   Jaeger         – Jaeger (backend tracingu)
#   Beyla          – Grafana Beyla (auto-instrumentacja eBPF)
#   Loki           – Grafana Loki (backend logów)
#   Monitor_Base   – Prometheus, Grafana, Promtail, node-exporter
#   K3s_Infra      – CoreDNS, Traefik, metrics-server, local-path-provisioner
#   System_Unknown – kontenery niezaklasyfikowane

_GOOGLE_APP_CONTAINERS = frozenset([
    "adservice", "cartservice", "checkoutservice", "currencyservice",
    "emailservice", "frontend", "paymentservice", "productcatalogservice",
    "recommendationservice", "shippingservice", "loadgenerator", "redis-cart",
])


def _classify_by_name(name: str) -> str | None:
    """Próbuje zaklasyfikować na podstawie fragmentu nazwy kontenera/poda."""
    n = name.lower()
    if "fluent-bit" in n or "fluentbit" in n:
        return "FluentBit"
    if "vector" in n:
        return "Vector"
    if "istio" in n or "discovery" in n:
        return "Istio"
    if "cilium" in n or "hubble" in n:
        return "Cilium"
    if "jaeger" in n:
        return "Jaeger"
    if "opentelemetry" in n or "otel-" in n or "otel_" in n or n == "otel":
        return "OTel_Collector"
    if "beyla" in n:
        return "Beyla"
    if "loki" in n:
        return "Loki"
    if any(kw in n for kw in ("prometheus", "grafana", "promtail",
                                "node-exporter", "kube-state-metrics")):
        return "Monitor_Base"
    if n in _GOOGLE_APP_CONTAINERS or any(svc in n for svc in _GOOGLE_APP_CONTAINERS):
        return "GoogleApp"
    if any(kw in n for kw in ("coredns", "metrics-server", "local-path-provisioner",
                                "svclb", "traefik")):
        return "K3s_Infra"
    return None


def get_component(labels: dict[str, str]) -> str:
    """Mapuje etykiety Prometheusa na nazwę komponentu logicznego."""
    container = labels.get("container", "")
    pod = labels.get("pod", "")
    ns = labels.get("namespace", "")

    # 1. Klasyfikacja po nazwie kontenera
    if container:
        result = _classify_by_name(container)
        if result:
            return result

    # 2. Klasyfikacja po nazwie poda
    if pod:
        result = _classify_by_name(pod)
        if result:
            return result

    # 3. Klasyfikacja po namespace
    if ns in ("monitoring", "logging", "observability"):
        return "Monitor_Base"
    if ns == "kube-system":
        return "K3s_Infra"
    if ns in ("istio-system", "istio-ingress"):
        return "Istio"
    if ns == "cert-manager":
        return "K3s_Infra"

    return "System_Unknown"


# Komunikacja z Prometheusem

def query_prometheus_range(
    prom_url: str,
    promql: str,
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                f"{prom_url}/api/v1/query_range",
                params={"query": promql, "start": start, "end": end, "step": STEP},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

            if data["status"] != "success":
                raise RuntimeError(
                    f"Prometheus zwrócił błąd: {data.get('error', 'nieznany')}"
                )

            results = data["data"]["result"]
            if not results:
                return []

            all_data: list[dict[str, Any]] = []
            for series in results:
                labels = series.get("metric", {})
                for ts, val in series["values"]:
                    all_data.append({
                        "time": float(ts),
                        "value": float(val),
                        "labels": labels,
                    })
            return all_data

        except requests.exceptions.RequestException as exc:
            if attempt < MAX_RETRIES:
                print(
                    f"      WARN: Próba {attempt}/{MAX_RETRIES} nieudana: {exc}. "
                    f"Ponowienie za {RETRY_DELAY}s..."
                )
                time.sleep(RETRY_DELAY)
            else:
                print(
                    f"      ERROR: Wszystkie {MAX_RETRIES} prób nieudanych. Pomijam.",
                    file=sys.stderr,
                )
                return []


def load_timestamps(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    for col in ("start_time", "end_time"):
        df[col] = df[col].astype(int)
    df["iteration"] = df["iteration"].astype(int)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Eksport surowych metryk Prometheusa do CSV.",
    )
    parser.add_argument(
        "stack_name",
        help="Identyfikator stosu (np. stack_0, stack_1, …)",
    )
    parser.add_argument(
        "--prometheus",
        default=f"http://{TARGET_IP}:30090",
        help=f"URL bazowy Prometheusa (domyślnie http://{TARGET_IP}:30090)",
    )
    args = parser.parse_args()

    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    csv_path = os.path.join(results_dir, f"{args.stack_name}_timestamps.csv")

    if not os.path.isfile(csv_path):
        print(f"ERROR: Plik z timestampami nie istnieje: {csv_path}", file=sys.stderr)
        sys.exit(1)

    ts = load_timestamps(csv_path)
    test_ids = sorted(ts["test_name"].unique())

    # ── Podsumowanie konfiguracji ────────────────────────────────────────
    print("=" * 70)
    print("  Prometheus Data Dumper")
    print(f"  Stos:           {args.stack_name}")
    print(f"  Scenariusze:    {test_ids}")
    print(f"  Metryki:        {list(METRICS.keys())}")
    print(f"  Okno rate():    {RATE_WINDOW}")
    print(f"  Krok siatki:    {STEP}")
    print(f"  Prometheus URL: {args.prometheus}")
    print("=" * 70)
    print()

    rows: list[dict] = []
    total_points = 0
    empty_metrics: list[str] = []

    for test_id in test_ids:
        test_rows = ts[ts["test_name"] == test_id].sort_values("iteration")
        print(f"  [{test_id}] {len(test_rows)} iteracja(-e)")

        for _, row in test_rows.iterrows():
            iteration = int(row["iteration"])
            start_ts = int(row["start_time"])
            end_ts = int(row["end_time"])

            for metric_name, (promql, description) in METRICS.items():
                data_points = query_prometheus_range(
                    args.prometheus, promql, start_ts, end_ts,
                )

                if not data_points:
                    if metric_name not in empty_metrics:
                        empty_metrics.append(metric_name)
                    print(
                        f"    WARN: {metric_name} iter={iteration} "
                        f"→ brak danych (metryka może nie istnieć w tym stosie)"
                    )
                    continue

                t0 = min(pt["time"] for pt in data_points)
                for pt in data_points:
                    labels = pt.get("labels", {})
                    component = get_component(labels)

                    is_global = any(
                        kw in metric_name
                        for kw in ("Ingestion", "Context_Switches", "HTTP_Errors")
                    )
                    final_metric = metric_name if is_global else f"{metric_name}_{component}"

                    rows.append({
                        "stack_name": args.stack_name,
                        "test_name": test_id,
                        "iteration": iteration,
                        "time_relative": round(pt["time"] - start_ts, 1),
                        "metric_name": final_metric,
                        "value": pt["value"],
                    })

                total_points += len(data_points)
                print(f"    ✓ {metric_name} iter={iteration} → {len(data_points)} pkt")

    # Zapis wyników
    if not rows:
        print(
            "\nWARNING: Nie wyeksportowano żadnych danych. "
            "Sprawdź łączność z Prometheusem i poprawność timestampów.",
            file=sys.stderr,
        )
        sys.exit(1)

    df = pd.DataFrame(
        rows,
        columns=["stack_name", "test_name", "iteration",
                 "time_relative", "metric_name", "value"],
    )

    # Agregacja szeregów dla tych samych komponentów
    df = df.groupby(
        ["stack_name", "test_name", "iteration", "time_relative", "metric_name"],
        as_index=False
    )["value"].sum()

    out_path = os.path.join(results_dir, f"raw_data_{args.stack_name}.csv")
    df.to_csv(out_path, index=False)

    print()
    print("=" * 70)
    print(f"  ✓ Zapisano {total_points} punktów pomiarowych ({len(df)} wierszy)")
    print(f"  ✓ Plik:     {out_path}")
    print(f"  ✓ Rozmiar:  {os.path.getsize(out_path) / 1024:.1f} KB")
    if empty_metrics:
        print(f"  ⚠ Metryki bez danych w tym stosie: {empty_metrics}")
    print("=" * 70)


if __name__ == "__main__":
    main()
