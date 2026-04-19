# Observability Lab: Load and Chaos Test Suite

This directory contains a suite of automated load and chaos tests designed to evaluate the effectiveness of observability tools in a Kubernetes environment (Google Online Boutique).

## Directory Structure

* `utils/config.js`: Central configuration file for global parameters (target IP, test duration, threshold limits).
* `test_0_baseline_load.js`: Generates clean, standard user traffic to establish a baseline for normal system behavior.
* `test_1_OOMKilled.sh`: Bash script that runs baseline load and intentionally starves the `cartservice` of RAM to trigger a Kubernetes OOMKilled event.
* `test_2_network_bootleneck.js`: K6 script utilizing `xk6-disruptor` to inject 500ms network latency into the `cartservice` while maintaining standard load.
* `test_3_poisoned_request.js`: K6 script where 20% of users send an invalid product ID, intentionally triggering application-level HTTP 500 errors in the catalog backend.
* `test_4_service_down.sh`: Bash script that runs baseline load and scales the `checkoutservice` to 0 replicas, simulating a complete service outage.
* `run_all_tests.sh`: Master script that executes tests 1 through 4 sequentially with a 5-minute cooldown period between them to ensure clean metric separation on observability dashboards.

## Prerequisites

1.  **K6:** Custom build required with `xk6-faker` and `xk6-disruptor` extensions.
2.  **Kubectl:** Configured and authenticated to communicate with the target Kubernetes cluster.
3.  **Permissions:** Scripts require execution rights (`chmod +x *.sh`).

## Usage

To execute a single test, use the appropriate interpreter:

* For Bash tests: `./test_1_OOMKilled.sh`
* For K6 tests: `k6 run test_2_network_bootleneck.js`

To run the entire suite automatically with predefined cooldown periods:
`./run_all_tests.sh`