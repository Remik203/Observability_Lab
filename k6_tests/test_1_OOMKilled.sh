#!/bin/bash

CONFIG_FILE="$HOME/Observability_Lab/k6_tests/config.js"

# Extracting variables with fallback defaults
RAMP_TIME_SEC=$(grep -m 1 "RAMP_UP_SECONDS=" "$CONFIG_FILE" | cut -d'=' -f2)
RAMP_TIME_SEC=${RAMP_TIME_SEC:-120}

FAILURE_TIME_SEC=$(grep -m 1 "FAILURE_DURATION_SECONDS=" "$CONFIG_FILE" | cut -d'=' -f2)
FAILURE_TIME_SEC=${FAILURE_TIME_SEC:-180}

echo "Starting K6 load test in background..."
K6_THRESHOLDS_HTTP_REQ_FAILED="rate<=1.0" k6 run ./test_0_baseline_load.js &
K6_PID=$!

echo "Waiting for cluster warm-up (${RAMP_TIME_SEC} seconds)..."
sleep "${RAMP_TIME_SEC}"

echo "INITIATING FAILURE: OOMKilled cartservice"
kubectl set resources deployment cartservice -c server --limits=memory=20Mi --requests=memory=20Mi

echo "Simulating outage for ${FAILURE_TIME_SEC} seconds to collect data..."
sleep "${FAILURE_TIME_SEC}"

echo "RESTORING SERVICE: Resetting memory limits..."
kubectl set resources deployment cartservice -c server --limits=memory=64Mi --requests=memory=64Mi

echo "Service restored. Waiting for K6 to finish..."
wait $K6_PID || true

echo "Test scenario completed"