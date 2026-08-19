#!/bin/bash

CONFIG_FILE="$(dirname "$0")/utils/config.js"

# Wyciągnięcie zmiennych z config.js
WAIT_TIME_SEC=$(grep -m 1 "WAIT_BEFORE_FAILURE_SECONDS=" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d " ';\r\n")
WAIT_TIME_SEC=${WAIT_TIME_SEC:-240}

FAILURE_TIME_SEC=$(grep -m 1 "FAILURE_DURATION_SECONDS=" "$CONFIG_FILE" | cut -d'=' -f2 | tr -d " ';\r\n")
FAILURE_TIME_SEC=${FAILURE_TIME_SEC:-120}

K6_EXTRA_FLAGS=""
if [ -n "${K6_SUMMARY_EXPORT:-}" ]; then
  K6_EXTRA_FLAGS="--summary-export=${K6_SUMMARY_EXPORT}"
fi

echo "Starting K6 load test in background..."
K6_THRESHOLDS_HTTP_REQ_FAILED="rate<=1.0" k6 run ${K6_EXTRA_FLAGS} ./test_0_baseline_load.js &
K6_PID=$!

echo "Waiting for cluster warm-up and initial peak (${WAIT_TIME_SEC} seconds)..."
sleep "${WAIT_TIME_SEC}"

echo "INITIATING FAILURE: Scaling checkoutservice to 0 replicas"
echo "$(date +%s),ServiceDown_Start" >> results/chaos_events.csv
kubectl scale deployment checkoutservice -n default --replicas=0

echo "Simulating outage for ${FAILURE_TIME_SEC} seconds to collect observability data..."
sleep "${FAILURE_TIME_SEC}"

echo "RESTORING SERVICE: Scaling checkoutservice back to 1 replica..."
echo "$(date +%s),ServiceDown_End" >> results/chaos_events.csv
kubectl scale deployment checkoutservice -n default --replicas=1

echo "Service restored. Waiting for K6 to finish naturally..."
wait $K6_PID || true

echo "Test scenario completed successfully."
