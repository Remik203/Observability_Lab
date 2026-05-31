#!/bin/bash
# =============================================================================
# K6 Test Orchestrator – iterative mode with Prometheus timestamps
# Usage: ./run_all_tests.sh <stack_name> [iterations]
# =============================================================================

set -euo pipefail

if [ -z "${1:-}" ]; then
  echo "Error: Provide a name for the test run (e.g., baseline, stack1_otel)."
  echo "Usage: ./run_all_tests.sh <stack_name> [iterations]"
  exit 1
fi

STACK_NAME="$1"
ITERATIONS="${2:-5}"        # Default: 5 full iterations
COOLDOWN_SEC=300            # Cooldown between each individual test

RESULTS_DIR="results"
TIMESTAMP_FILE="${RESULTS_DIR}/${STACK_NAME}_timestamps.csv"

mkdir -p "$RESULTS_DIR"

# Initialize timestamps CSV (overwrite previous runs for this stack)
echo "test_name,iteration,start_time,end_time" > "$TIMESTAMP_FILE"

# ---------------------------------------------------------------------------
# Helper: run a single test, record start/end Unix timestamps, and cooldown
# Arguments: $1 = test_id (e.g. test_0), $2 = iteration number, $3+ = command
# ---------------------------------------------------------------------------
run_test() {
  local test_id="$1"
  local iteration="$2"
  shift 2

  echo "  [iter ${iteration}/${ITERATIONS}] Running ${test_id}..."
  local START_TIME
  START_TIME=$(date +%s)

  "$@" || true

  local END_TIME
  END_TIME=$(date +%s)

  echo "${test_id},${iteration},${START_TIME},${END_TIME}" >> "$TIMESTAMP_FILE"
  echo "  [iter ${iteration}/${ITERATIONS}] ${test_id} finished (${START_TIME} -> ${END_TIME})"
  
  echo "  Cooling down for ${COOLDOWN_SEC}s to let the cluster recover..."
  sleep ${COOLDOWN_SEC}
}

# ===========================================================================
echo "================================================================="
echo " Test suite: ${STACK_NAME}  |  Iterations: ${ITERATIONS}"
echo " Timestamps will be saved to: ${TIMESTAMP_FILE}"
echo "================================================================="

for i in $(seq 1 "$ITERATIONS"); do
  echo ""
  echo "================ ITERATION ${i} / ${ITERATIONS} ================"

  # Test 0 – Pure Baseline Load (no faults)
  run_test "test_0" "$i" k6 run test_0_baseline_load.js

  # Test 1 – OOMKilled
  run_test "test_1" "$i" ./test_1_OOMKilled.sh

  # Test 2 – Network Bottleneck
  run_test "test_2" "$i" k6 run test_2_network_bootleneck.js

  # Test 3 – Poisoned Request
  run_test "test_3" "$i" k6 run test_3_poisoned_request.js

  # Test 4 – Service Down
  run_test "test_4" "$i" ./test_4_service_down.sh

done

echo ""
echo "================================================================="
echo " All ${ITERATIONS} iterations completed."
echo " Timestamps saved to: ${TIMESTAMP_FILE}"
echo "================================================================="