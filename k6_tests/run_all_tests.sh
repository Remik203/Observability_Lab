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
# Helper: run a single K6 JS test with --summary-export, record timestamps
# Arguments: $1 = test_id, $2 = iteration, $3 = k6 JS file
# ---------------------------------------------------------------------------
run_k6_test() {
  local test_id="$1"
  local iteration="$2"
  local k6_file="$3"

  local summary_file="${RESULTS_DIR}/k6_summary_${STACK_NAME}_${test_id}_iter_${iteration}.json"

  echo "  [iter ${iteration}/${ITERATIONS}] Running ${test_id} (k6 ${k6_file})..."
  local START_TIME
  START_TIME=$(date +%s)

  k6 run --summary-export="${summary_file}" "${k6_file}" || true

  local END_TIME
  END_TIME=$(date +%s)

  echo "${test_id},${iteration},${START_TIME},${END_TIME}" >> "$TIMESTAMP_FILE"
  echo "  [iter ${iteration}/${ITERATIONS}] ${test_id} finished (${START_TIME} -> ${END_TIME})"
  
  echo "  Cooling down for ${COOLDOWN_SEC}s to let the cluster recover..."
  sleep ${COOLDOWN_SEC}
}

# ---------------------------------------------------------------------------
# Helper: run a shell-wrapper test (test_1, test_4) that spawns K6 internally
# Arguments: $1 = test_id, $2 = iteration, $3 = shell script path
# ---------------------------------------------------------------------------
run_shell_test() {
  local test_id="$1"
  local iteration="$2"
  local script="$3"

  echo "  [iter ${iteration}/${ITERATIONS}] Running ${test_id} (${script})..."
  local START_TIME
  START_TIME=$(date +%s)

  # Export env vars so the child shell script can produce its own summary JSON
  K6_SUMMARY_EXPORT="${RESULTS_DIR}/k6_summary_${STACK_NAME}_${test_id}_iter_${iteration}.json" \
  K6_STACK_NAME="${STACK_NAME}" \
  K6_TEST_ID="${test_id}" \
  K6_ITERATION="${iteration}" \
    bash "${script}" || true

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
  run_k6_test "test_0" "$i" test_0_baseline_load.js

  # Test 1 – OOMKilled (shell wrapper with background k6)
  run_shell_test "test_1" "$i" ./test_1_OOMKilled.sh

  # Test 2 – Network Bottleneck
  run_k6_test "test_2" "$i" test_2_network_bootleneck.js

  # Test 3 – Poisoned Request
  run_k6_test "test_3" "$i" test_3_poisoned_request.js

  # Test 4 – Service Down (shell wrapper with background k6)
  run_shell_test "test_4" "$i" ./test_4_service_down.sh

done

echo ""
echo "================================================================="
echo " All ${ITERATIONS} iterations completed."
echo " Timestamps saved to: ${TIMESTAMP_FILE}"
echo "================================================================="
