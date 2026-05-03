#!/bin/bash

if [ -z "$1" ]; then
  echo "Error: Provide a name for the test run."
  echo "Usage: ./monitor_resources.sh baseline_test"
  exit 1
fi

TEST_NAME=$1
mkdir -p results
OUTPUT_FILE="results/${TEST_NAME}_metrics.csv"

# Automatyczne pobranie nazwy głównego węzła klastra
NODE_NAME=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')

echo "timestamp,cpu_millicores,memory_mb,net_rx_kbps,net_tx_kbps,disk_read_kbps,disk_write_kbps" > "$OUTPUT_FILE"
echo "Started comprehensive resource monitoring on node: $NODE_NAME."
echo "Logging CPU, RAM, Network I/O, and Disk I/O to $OUTPUT_FILE..."

PREV_RX=0; PREV_TX=0; PREV_DR=0; PREV_DW=0
FIRST_RUN=1

while true; do
    CURRENT_TIME=$(date '+%H:%M:%S')
    
    # 1. Pomiary CPU i RAM (Poprawiona kolumna $4 dla MEMORY)
    STATS=$(kubectl top nodes "$NODE_NAME" --no-headers 2>/dev/null)
    if [ -n "$STATS" ]; then
        CPU=$(echo "$STATS" | awk '{print $2}' | sed 's/[a-zA-Z]//g')
        RAM=$(echo "$STATS" | awk '{print $4}' | sed 's/[a-zA-Z]//g')
    else
        CPU=0; RAM=0
    fi

    # 2. Pomiary Sieci i Dysku z cAdvisor (Agregacja wyłącznie dla Podów klastra)
    CADVISOR=$(kubectl get --raw "/api/v1/nodes/$NODE_NAME/proxy/metrics/cadvisor" 2>/dev/null)
    
    if [ -n "$CADVISOR" ]; then
        # Wyrażenie regularne szuka etykiety 'namespace=', ignorując jej pozycję. Zlicza wszystko co K8s-owe.
        CUR_RX=$(echo "$CADVISOR" | awk '/^container_network_receive_bytes_total\{.*namespace=/ {sum+=$2} END {print sum}')
        CUR_TX=$(echo "$CADVISOR" | awk '/^container_network_transmit_bytes_total\{.*namespace=/ {sum+=$2} END {print sum}')
        CUR_DR=$(echo "$CADVISOR" | awk '/^container_fs_reads_bytes_total\{.*namespace=/ {sum+=$2} END {print sum}')
        CUR_DW=$(echo "$CADVISOR" | awk '/^container_fs_writes_bytes_total\{.*namespace=/ {sum+=$2} END {print sum}')

        CUR_RX=${CUR_RX:-0}; CUR_TX=${CUR_TX:-0}
        CUR_DR=${CUR_DR:-0}; CUR_DW=${CUR_DW:-0}

        if [ $FIRST_RUN -eq 1 ]; then
            FIRST_RUN=0
            PREV_RX=$CUR_RX; PREV_TX=$CUR_TX
            PREV_DR=$CUR_DR; PREV_DW=$CUR_DW
            sleep 5
            continue
        fi

        NET_RX_KBPS=$(awk "BEGIN { if ($CUR_RX >= $PREV_RX) print ($CUR_RX - $PREV_RX) / 5 / 1024; else print 0 }")
        NET_TX_KBPS=$(awk "BEGIN { if ($CUR_TX >= $PREV_TX) print ($CUR_TX - $PREV_TX) / 5 / 1024; else print 0 }")
        DISK_R_KBPS=$(awk "BEGIN { if ($CUR_DR >= $PREV_DR) print ($CUR_DR - $PREV_DR) / 5 / 1024; else print 0 }")
        DISK_W_KBPS=$(awk "BEGIN { if ($CUR_DW >= $PREV_DW) print ($CUR_DW - $PREV_DW) / 5 / 1024; else print 0 }")

        NET_RX_KBPS=$(printf "%.2f" $NET_RX_KBPS 2>/dev/null || echo "0")
        NET_TX_KBPS=$(printf "%.2f" $NET_TX_KBPS 2>/dev/null || echo "0")
        DISK_R_KBPS=$(printf "%.2f" $DISK_R_KBPS 2>/dev/null || echo "0")
        DISK_W_KBPS=$(printf "%.2f" $DISK_W_KBPS 2>/dev/null || echo "0")

        PREV_RX=$CUR_RX; PREV_TX=$CUR_TX
        PREV_DR=$CUR_DR; PREV_DW=$CUR_DW

        echo "${CURRENT_TIME},${CPU},${RAM},${NET_RX_KBPS},${NET_TX_KBPS},${DISK_R_KBPS},${DISK_W_KBPS}" >> "$OUTPUT_FILE"
    fi
    
    sleep 5
done
