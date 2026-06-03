#!/usr/bin/env python3
"""
Usage:
    python3 dump_prometheus_data.py <stack_name> [--prometheus URL]

Output:
    results/raw_data_<stack_name>.csv
    Columns: stack_name, test_name, iteration, time_relative, metric_name, value
"""

import argparse
import sys
import os
import time

import pandas as pd
import requests

TARGET_IP = os.getenv('TARGET_IP', '***USUNIETO***')

# Prometheus queries
METRICS = {
    "CPU_App": (
        'sum(rate(container_cpu_usage_seconds_total{namespace="default"}[1m]))',
        "CPU cores used by application pods",
    ),
    "CPU_Obs": (
        'sum(rate(container_cpu_usage_seconds_total{namespace=~"observability|logging|monitoring|istio-system|kube-system", container!=""}[1m]))',
        "CPU cores used by observability / infra pods",
    ),
    "RAM_App": (
        'sum(container_memory_working_set_bytes{namespace="default"})',
        "RAM bytes used by application pods",
    ),
    "RAM_Obs": (
        'sum(container_memory_working_set_bytes{namespace=~"observability|logging|monitoring|istio-system|kube-system"})',
        "RAM bytes used by observability / infra pods",
    ),
}

STEP = "5s"  # query resolution – must match plot_metrics.py
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds between retries


def query_prometheus_range(prom_url: str, promql: str, start: int, end: int) -> list[dict]:
    """
    Query the Prometheus range API and return a list of (timestamp, value) dicts.
    Retries on transient failures.
    """
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
                raise RuntimeError(f"Prometheus error: {data.get('error', 'unknown')}")

            results = data["data"]["result"]
            if not results:
                return []

            # Take first result vector (queries use sum() aggregation)
            return [{"time": float(ts), "value": float(val)} for ts, val in results[0]["values"]]

        except requests.exceptions.RequestException as exc:
            if attempt < MAX_RETRIES:
                print(f"      WARN: Attempt {attempt}/{MAX_RETRIES} failed: {exc}. "
                      f"Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"      ERROR: All {MAX_RETRIES} attempts failed for query. Skipping.", file=sys.stderr)
                return []


def load_timestamps(csv_path: str) -> pd.DataFrame:
    """Load the timestamps CSV produced by run_all_tests.sh."""
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    for col in ("start_time", "end_time"):
        df[col] = df[col].astype(int)
    df["iteration"] = df["iteration"].astype(int)
    return df


def main():
    parser = argparse.ArgumentParser(
        description="Dump raw Prometheus metrics to CSV for offline analysis."
    )
    parser.add_argument("stack_name", help="Stack identifier (e.g. stack_0, stack_1)")
    parser.add_argument(
        "--prometheus", default=f'http://{TARGET_IP}:30090',
        help=f'Prometheus base URL (default: http://{TARGET_IP}:30090)',
    )
    args = parser.parse_args()

    results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    csv_path = os.path.join(results_dir, f"{args.stack_name}_timestamps.csv")

    if not os.path.isfile(csv_path):
        print(f"ERROR: Timestamps file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    ts = load_timestamps(csv_path)
    test_ids = sorted(ts["test_name"].unique())

    print("=" * 65)
    print(f"  Prometheus Data Dumper")
    print(f"  Stack:      {args.stack_name}")
    print(f"  Tests:      {test_ids}")
    print(f"  Metrics:    {list(METRICS.keys())}")
    print(f"  Prometheus: {args.prometheus}")
    print("=" * 65)
    print()

    rows: list[dict] = []
    total_points = 0

    for test_id in test_ids:
        test_rows = ts[ts["test_name"] == test_id].sort_values("iteration")
        print(f"  [{test_id}] {len(test_rows)} iteration(s)")

        for _, row in test_rows.iterrows():
            iteration = int(row["iteration"])
            start_ts = int(row["start_time"])
            end_ts = int(row["end_time"])

            for metric_name, (promql, description) in METRICS.items():
                data_points = query_prometheus_range(
                    args.prometheus, promql, start_ts, end_ts
                )

                if not data_points:
                    print(f"    WARN: {metric_name} iter={iteration} → no data")
                    continue

                # Compute time relative to start of this test window (seconds)
                t0 = data_points[0]["time"]
                for pt in data_points:
                    rows.append({
                        "stack_name": args.stack_name,
                        "test_name": test_id,
                        "iteration": iteration,
                        "time_relative": round(pt["time"] - t0, 1),
                        "metric_name": metric_name,
                        "value": pt["value"],
                    })

                total_points += len(data_points)
                print(f"    ✓ {metric_name} iter={iteration} → {len(data_points)} points")

    if not rows:
        print("\nWARNING: No data extracted. Check Prometheus connectivity and timestamps.",
              file=sys.stderr)
        sys.exit(1)

    # Build DataFrame and save
    df = pd.DataFrame(rows, columns=[
        "stack_name", "test_name", "iteration", "time_relative", "metric_name", "value"
    ])

    out_path = os.path.join(results_dir, f"raw_data_{args.stack_name}.csv")
    df.to_csv(out_path, index=False)

    print()
    print("=" * 65)
    print(f"  ✓ Saved {total_points} data points ({len(df)} rows)")
    print(f"  ✓ Output: {out_path}")
    print(f"  ✓ File size: {os.path.getsize(out_path) / 1024:.1f} KB")
    print("=" * 65)


if __name__ == "__main__":
    main()
