#!/bin/bash

CONFIG_FILE="$HOME/k6_tests/utils/config.js"

# Extracting variables with fallback defaults
RAMP_TIME_SEC=$(grep -m 1 "RAMP_UP_SECONDS=" $CONFIG_FILE | cut -d'=' -f2)
RAMP_TIME_SEC=${RAMP_TIME_SEC:-120}

FAILURE_TIME_SEC=$(grep -m 1 "FAILURE_DURATION_SECONDS=" $CONFIG_FILE | cut -d'=' -f2)
FAILURE_TIME_SEC=${FAILURE_TIME_SEC:-180}

echo "Starting K6 load test in background..."
k6 run ~/k6_tests/test_0_baseline_load.js &
K6_PID=$!

echo "Waiting for cluster warm-up (${RAMP_TIME_SEC} seconds)..."
sleep ${RAMP_TIME_SEC}

echo "INITIATING FAILURE: Scaling checkoutservice to 0 replicas"
kubectl scale deployment checkoutservice --replicas=0

echo "Simulating outage for ${FAILURE_TIME_SEC} seconds to collect observability data..."
sleep ${FAILURE_TIME_SEC}

echo "RESTORING SERVICE: Scaling checkoutservice back to 1 replica..."
kubectl scale deployment checkoutservice --replicas=1

echo "Service restored. Waiting for K6 to finish naturally..."
wait $K6_PID

echo "Test scenario completed successfully."