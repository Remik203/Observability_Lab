#!/bin/bash

COOLDOWN_SEC=300

echo "Starting the complete automated test suite..."
echo "Ensure you are monitoring the observability tools."
echo "==================================================="

echo "Running Test 1: OOMKilled"
./test_1_OOMKilled.sh

echo "Test 1 finished."
sleep ${COOLDOWN_SEC}

echo "Running Test 2: Network Bottleneck"
k6 run test_2_network_bootleneck.js

echo "Test 2 finished."
sleep ${COOLDOWN_SEC}

echo "Running Test 3: Poisoned Request"
k6 run test_3_poisoned_request.js

echo "Test 3 finished."
sleep ${COOLDOWN_SEC}

echo "Running Test 4: Service Down"
./test_4_service_down.sh

echo "==================================================="
echo "All tests completed."