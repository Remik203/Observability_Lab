#!/bin/bash



if [ -z "$1" ]; then
    echo "ERROR: No remote host probvided."
    echo "Usage: $0 <user@remote_host>"
    exit 1
fi

PORTS=(30030 30080 30086)
REMOTE_HOST=$1

for PORT in "${PORTS[@]}"; do
    if ! nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1; then
        echo "[INFO] Port $PORT is free. Opening tunnel..."
        ssh -L "$PORT":127.0.0.1:"$PORT" "$REMOTE_HOST" -N -f
        
        if [ $? -eq 0 ]; then
            echo "[SUCCESS] Tunnel on port $PORT established."
        else
            echo "[ERROR] Failed to establish tunnel on port $PORT."
        fi
    else
        echo "[SKIP] Port $PORT is already in use. Tunnel might already be running."
    fi
done
