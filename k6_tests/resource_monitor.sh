#!/bin/bash

# Ensure a test name argument is provided
if [ -z "$1" ]; then
  echo "Error: Provide a name for the test run."
  echo "Usage: ./monitor_resources.sh baseline_test"
  exit 1
fi

TEST_NAME=$1

# Create a dedicated directory for results if it does not exist
mkdir -p results

# Prepend the directory path to the output file
OUTPUT_FILE="results/${TEST_NAME}_metrics.csv"

# Initialize the CSV file with headers
echo "timestamp,cpu_millicores,memory_mb" > "$OUTPUT_FILE"

echo "Started background resource monitoring. Logging to $OUTPUT_FILE..."

# Infinite loop, broken when the process is killed by the orchestrator
while true; do
    CURRENT_TIME=$(date '+%H:%M:%S')
    
    # Get resources for all nodes (discard header and sum if more than 1)
    STATS=$(kubectl top nodes --no-headers 2>/dev/null)
    
    if [ -n "$STATS" ]; then
        # Extract values and remove 'm' (millicores) and 'Mi' (Megabytes) letters
        CPU=$(echo "$STATS" | awk '{sum+=$2} END {print sum}' | sed 's/[a-zA-Z]//g')
        RAM=$(echo "$STATS" | awk '{sum+=$4} END {print sum}' | sed 's/[a-zA-Z]//g')

        # Append to CSV
        echo "${CURRENT_TIME},${CPU},${RAM}" >> "$OUTPUT_FILE"
    fi
    
    # Sample every 5 seconds
    sleep 5
done
