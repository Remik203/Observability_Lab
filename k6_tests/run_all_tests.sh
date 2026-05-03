#!/bin/bash

if [ -z "$1" ]; then
  echo "Error: Provide a name for the test run (e.g., baseline, stack1_otel)."
  echo "Usage: ./run_all_tests.sh <stack_name>"
  exit 1
fi

STACK_NAME=$1
COOLDOWN_SEC=300

echo "Starting the complete automated test suite for: $STACK_NAME"
echo "Ensure you are monitoring the observability tools."
echo "==================================================="

echo "Starting resource monitor in background..."
./monitor_resources.sh "$STACK_NAME" &
MONITOR_PID=$!

echo "Running Test 0: Pure Baseline Load (No faults)"
k6 run test_0_baseline_load.js || true

echo "Test 0 finished. Cooling down for ${COOLDOWN_SEC} seconds..."
sleep ${COOLDOWN_SEC}

echo "Running Test 1: OOMKilled"
./test_1_OOMKilled.sh || true

echo "Test 1 finished. Cooling down for ${COOLDOWN_SEC} seconds..."
sleep ${COOLDOWN_SEC}

echo "Running Test 2: Network Bottleneck"
k6 run test_2_network_bootleneck.js || true

echo "Test 2 finished. Cooling down for ${COOLDOWN_SEC} seconds..."
sleep ${COOLDOWN_SEC}

echo "Running Test 3: Poisoned Request"
k6 run test_3_poisoned_request.js || true 

echo "Test 3 finished. Cooling down for ${COOLDOWN_SEC} seconds..."
sleep ${COOLDOWN_SEC}

echo "Running Test 4: Service Down"
./test_4_service_down.sh || true

echo "==================================================="
echo "All tests completed successfully. Stopping resource monitor..."
kill $MONITOR_PID
echo "Metrics saved to CSV."
