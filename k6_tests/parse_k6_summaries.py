#!/usr/bin/env python3
"""
parse_k6_summaries.py – K6 Summary JSON → Business Metrics CSV
================================================================
Iterates over k6_summary_*.json files in the results/ directory and compiles
a single k6_business_metrics.csv with columns:

    stack_name, test_name, iteration, p95_latency_ms, avg_latency_ms,
    req_failed_rate, total_requests

Usage:
    python3 parse_k6_summaries.py [--results-dir DIR]
"""

import argparse
import glob
import json
import os
import re
import sys

import pandas as pd


# Regex to extract metadata from the filename convention:
#   k6_summary_<stack_name>_<test_id>_iter_<iteration>.json
FILENAME_RE = re.compile(
    r"k6_summary_(?P<stack>[^_]+_\d+)_(?P<test>test_\d+)_iter_(?P<iter>\d+)\.json$"
)


def parse_summary(filepath: str) -> dict | None:
    """
    Parse a single K6 summary JSON and extract business-impact metrics.
    Returns a dict or None on failure.
    """
    basename = os.path.basename(filepath)
    m = FILENAME_RE.search(basename)
    if not m:
        print(f"  WARN: Filename does not match expected pattern, skipping: {basename}")
        return None

    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  WARN: Could not read {basename}: {exc}")
        return None

    metrics = data.get("metrics", {})

    # --- HTTP request duration (latency) ---
    http_req_duration = metrics.get("http_req_duration", {})
    duration_values = http_req_duration.get("values", http_req_duration)
    p95_ms = duration_values.get("p(95)", None)
    avg_ms = duration_values.get("avg", None)

    # --- Request failure rate ---
    http_req_failed = metrics.get("http_req_failed", {})
    failed_values = http_req_failed.get("values", http_req_failed)
    req_failed_rate = failed_values.get("rate", failed_values.get("value", None))

    # --- Total requests ---
    http_reqs = metrics.get("http_reqs", {})
    reqs_values = http_reqs.get("values", http_reqs)
    total_requests = reqs_values.get("count", None)

    return {
        "stack_name": m.group("stack"),
        "test_name": m.group("test"),
        "iteration": int(m.group("iter")),
        "p95_latency_ms": round(p95_ms, 2) if p95_ms is not None else None,
        "avg_latency_ms": round(avg_ms, 2) if avg_ms is not None else None,
        "req_failed_rate": round(req_failed_rate, 6) if req_failed_rate is not None else None,
        "total_requests": int(total_requests) if total_requests is not None else None,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Compile K6 summary JSONs into a business-metrics CSV."
    )
    parser.add_argument(
        "--results-dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results"),
        help="Directory containing k6_summary_*.json files (default: ./results)",
    )
    args = parser.parse_args()

    pattern = os.path.join(args.results_dir, "k6_summary_*.json")
    json_files = sorted(glob.glob(pattern))

    if not json_files:
        print(f"ERROR: No k6_summary_*.json files found in {args.results_dir}", file=sys.stderr)
        sys.exit(1)

    print("=" * 65)
    print("  K6 Business Metrics Compiler")
    print(f"  Found {len(json_files)} summary file(s)")
    print("=" * 65)

    rows = []
    for filepath in json_files:
        result = parse_summary(filepath)
        if result:
            rows.append(result)
            print(f"  ✓ {os.path.basename(filepath)}: p95={result['p95_latency_ms']}ms, "
                  f"failed={result['req_failed_rate']}, reqs={result['total_requests']}")

    if not rows:
        print("\nERROR: No valid data extracted from any summary file.", file=sys.stderr)
        sys.exit(1)

    df = pd.DataFrame(rows, columns=[
        "stack_name", "test_name", "iteration",
        "p95_latency_ms", "avg_latency_ms", "req_failed_rate", "total_requests",
    ])

    out_path = os.path.join(args.results_dir, "k6_business_metrics.csv")
    df.to_csv(out_path, index=False)

    print()
    print("=" * 65)
    print(f"  ✓ Compiled {len(df)} rows from {len(json_files)} files")
    print(f"  ✓ Output: {out_path}")
    print(f"  ✓ Stacks: {sorted(df['stack_name'].unique())}")
    print(f"  ✓ Tests:  {sorted(df['test_name'].unique())}")
    print("=" * 65)


if __name__ == "__main__":
    main()
