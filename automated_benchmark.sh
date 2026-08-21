#!/bin/bash
# =============================================================================
# automated_benchmark.sh – Automated Benchmark Orchestrator
# =============================================================================
# Master script that deploys, tests, dumps, and cleans ALL 5 observability
# stacks in sequence. Run it before bed, get thesis-ready data in the morning.
#
# Usage:
#   ./automated_benchmark.sh                  # Run all stacks (stack_0..stack_4)
#   ./automated_benchmark.sh stack_1 stack_2  # Run only selected stacks
#
# Prerequisites:
#   1. K3s cluster is running (ansible/playbooks/site.yml already applied)
#   2. Vault password file exists at ansible/.vault_pass
#   3. Python dependencies: pip install pandas numpy matplotlib requests
#   4. k6 is installed on the load generator node
# =============================================================================

# Ensure PATH includes pipx / local user binaries
export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANSIBLE_DIR="${SCRIPT_DIR}/ansible"
K6_DIR="${SCRIPT_DIR}/k6_tests"
RESULTS_DIR="${K6_DIR}/results"
VAULT_PASS_FILE="${ANSIBLE_DIR}/.vault_pass"
INVENTORY="${ANSIBLE_DIR}/inventory.ini"

# K3s Node SSH Details for fetching fresh certificates
PRIMARY_IP="$TARGET_IP"
PRIMARY_USER="student"

ITERATIONS=3                   # Number of k6 test iterations per stack
POD_WAIT_TIMEOUT=300              # Max seconds to wait for pods to be ready
DEPLOY_SETTLE_TIME=120            # Seconds to wait after deploy for metrics to stabilize

# Stacks to test
if [ $# -gt 0 ]; then
    STACKS=("$@")
else
    STACKS=(stack_0 stack_1 stack_2 stack_3 stack_4)
fi

mkdir -p "${RESULTS_DIR}"
LOG_FILE="${RESULTS_DIR}/automated_run.log"

# Redirect all output to both terminal and log file
exec > >(tee -a "${LOG_FILE}") 2>&1

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

log_header() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║ $1"
    echo "║ $(timestamp)"
    echo "╚══════════════════════════════════════════════════════════════════╝"
}

log_info() { echo "[$(timestamp)] INFO: $*"; }
log_warn() { echo "[$(timestamp)] WARN: $*" >&2; }
log_error() { echo "[$(timestamp)] ERROR: $*" >&2; }
log_success() { echo "[$(timestamp)] ✓ $*"; }

check_vault_pass() {
    if [ ! -f "${VAULT_PASS_FILE}" ]; then
        log_error "Vault password file not found: ${VAULT_PASS_FILE}"
        exit 1
    fi
    log_info "Vault password file found: ${VAULT_PASS_FILE}"
}


reset_cluster() {
    local stack_name="${1:-default}"
    log_header "CLUSTER CLEANUP: Wiping & Rebuilding K3s for ${stack_name}"
    
    local cni_arg=""
    if [[ "${stack_name}" == "stack_2" || "${stack_name}" == "stack_3" || "${stack_name}" == "stack_4" ]]; then
        cni_arg="-e cni_plugin=cilium"
    else
        cni_arg="-e cni_plugin=flannel"
    fi
    export ANSIBLE_ROLES_PATH="${ANSIBLE_DIR}/roles"
    export ANSIBLE_CONFIG="${ANSIBLE_DIR}/ansible.cfg"
    
    # 1. Reset K3s na primary_node
    log_info "Tearing down K3s cluster on primary_node..."
    (cd "${ANSIBLE_DIR}" && ansible-playbook -i "inventory.ini" playbooks/reset_k3s.yml --limit primary_node --vault-password-file "${VAULT_PASS_FILE}") || true
    
    # 2. Rebuild K3s na primary_node
    log_info "Deploy fresh K3s cluster on primary_node..."
    if (cd "${ANSIBLE_DIR}" && ansible-playbook -i "inventory.ini" playbooks/site.yml --limit primary_node --vault-password-file "${VAULT_PASS_FILE}" ${cni_arg}); then
        log_success "K3s rebuilt successfully!"
    else
        log_error "Failed to rebuild K3s!"
        exit 1
    fi

    # 3. Fetch Fresh Kubeconfig
    log_info "Fetching Kubeconfig certificates from PrimaryVM..."
    mkdir -p ~/.kube
    ssh -o StrictHostKeyChecking=no "${PRIMARY_USER}@${PRIMARY_IP}" "cat /etc/rancher/k3s/k3s.yaml" > ~/.kube/config
    sed -i "s/127.0.0.1/${PRIMARY_IP}/g" ~/.kube/config
    chmod 600 ~/.kube/config
    log_success "New certificates installed."
    
    # 4. Wait for API to stabilize
    log_info "Waiting for K3s API to become responsive..."
    until kubectl get nodes >/dev/null 2>&1; do
        sleep 2
    done
    sleep 10
}

wait_for_pods() {
    local stack_name="$1"
    local timeout="${POD_WAIT_TIMEOUT}"
    local interval=15
    local elapsed=0

    log_info "Waiting for all pods to be Ready (timeout: ${timeout}s)..."
    sleep 30

    while [ $elapsed -lt $timeout ]; do
        local not_ready
        not_ready=$(kubectl get pods -A --no-headers 2>/dev/null | grep -v -E 'Completed|Succeeded' | grep -v -E '([0-9]+)/\1' | wc -l)
        local total
        total=$(kubectl get pods -A --no-headers 2>/dev/null | grep -v -E 'Completed|Succeeded' | wc -l)

        if [ "$not_ready" -eq 0 ] && [ "$total" -gt 0 ]; then
            log_success "All ${total} pods are Ready (waited ${elapsed}s)"
            return 0
        fi

        log_info "  ${not_ready}/${total} pods not ready yet (${elapsed}s / ${timeout}s)"
        sleep $interval
        elapsed=$((elapsed + interval))
    done

    log_warn "Timeout! Some pods may not be ready after ${timeout}s."
    kubectl get pods -A --no-headers 2>/dev/null | grep -v -E 'Running|Completed|Succeeded' || true
    return 1
}

run_ansible() {
    local playbook="$1"
    local desc="$2"
    local extra_vars="${3:-}"

    log_info "Running Ansible: ${desc}"
    log_info "  Playbook: ${playbook}"
    
    local max_retries=3
    local attempt=1
    local success=false

    export ANSIBLE_ROLES_PATH="${ANSIBLE_DIR}/roles"
    export ANSIBLE_CONFIG="${ANSIBLE_DIR}/ansible.cfg"

    while [ $attempt -le $max_retries ]; do
        if (cd "${ANSIBLE_DIR}" && ansible-playbook -i "${INVENTORY}" "${playbook}" ${extra_vars} --vault-password-file "${VAULT_PASS_FILE}"); then
            success=true
            break
        fi
        log_error "Ansible FAILED (Attempt $attempt/$max_retries): ${desc}. Retrying in 15 seconds..."
        sleep 15
        ((attempt++))
    done

    if [ "$success" = false ]; then
        log_error "Ansible FAILED after $max_retries attempts: ${desc}"
        return 1
    fi
    log_success "Ansible completed: ${desc}"
    return 0
}

save_audit_log() {
    local stack_name="$1"
    local audit_file="${RESULTS_DIR}/audit_${stack_name}.log"

    log_info "Saving audit snapshot → ${audit_file}"
    {
        echo "=========================================="
        echo " Audit Log: ${stack_name}"
        echo " Timestamp: $(timestamp)"
        echo "=========================================="
        echo ""
        echo "── Helm Releases ──"
        helm list -A 2>&1 || echo "(helm not available)"
        echo ""
        echo "── All Pods ──"
        kubectl get pods -A -o wide 2>&1 || echo "(kubectl not available)"
        echo ""
        echo "── Node Resources ──"
        kubectl top nodes 2>&1 || echo "(metrics-server not available)"
        echo ""
        echo "── Pod Resources ──"
        kubectl top pods -A --sort-by=cpu 2>&1 || echo "(metrics-server not available)"
        echo ""
        echo "── Recent Events (last 100) ──"
        kubectl get events -A --sort-by='.metadata.creationTimestamp' 2>&1 | tail -100
        echo ""
        echo "── PVCs ──"
        kubectl get pvc -A 2>&1 || echo "(none)"
        echo ""
        echo "── Warnings & Errors ──"
        kubectl get events -A --field-selector type!=Normal 2>&1 || echo "(none)"
    } > "${audit_file}" 2>&1

    log_success "Audit saved: ${audit_file}"
}

process_stack() {
    local stack_name="$1"
    local stack_start
    stack_start=$(date +%s)

    log_header "STACK: ${stack_name}"
    
    # ZAWSZE sterylizujemy klaster przed wdrożeniem stosu, 
    # używając prawidłowego CNI dla TEGO stosu.
    reset_cluster "${stack_name}"
    
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Cannot reach Kubernetes cluster after reset. Skipping ${stack_name}."
        return 1
    fi
    log_success "Kubernetes cluster is reachable and sterile!"
    
    local playbook="${ANSIBLE_DIR}/playbooks/deploy_${stack_name}.yml"
    if [ ! -f "${playbook}" ]; then
        log_error "Playbook not found: ${playbook}. Skipping."
        return 1
    fi

    if ! run_ansible "${playbook}" "Deploy ${stack_name}"; then
        log_error "Deployment failed for ${stack_name}. Saving audit and skipping to next."
        save_audit_log "${stack_name}"
        return 1
    fi
    
    wait_for_pods "${stack_name}"

    if [[ "${stack_name}" == "stack_4" ]]; then
        log_info "Generating warm-up traffic for Beyla eBPF auto-discovery..."
        (cd "${K6_DIR}" && k6 run --vus 2 --duration 20s ./test_0_baseline_load.js >/dev/null 2>&1 || true)

        log_info "Checking if Beyla target is UP in Prometheus for ${stack_name}..."
        local retries=0
        local max_retries=18
        until curl -s "http://${PRIMARY_IP}:30090/api/v1/targets" | grep -q '"job":"beyla"'; do
            if [ $retries -ge $max_retries ]; then
                log_warn "Timeout waiting for Beyla target in Prometheus! Proceeding..."
                break
            fi
            log_info "  Waiting for Beyla target in Prometheus (${retries}/${max_retries})..."
            sleep 5
            ((retries++))
        done
    fi

    log_info "Settling time: waiting ${DEPLOY_SETTLE_TIME}s for metrics to stabilize..."
    (cd "${K6_DIR}" && k6 run --vus 2 --duration 30s test_0_baseline_load.js >/dev/null 2>&1 || true)
    log_info "Waiting 60s for metrics pipeline to settle..."
    sleep 60


    log_info "Starting k6 test suite for ${stack_name} (${ITERATIONS} iterations)..."
    if (cd "${K6_DIR}" && bash ./run_all_tests.sh "${stack_name}" "${ITERATIONS}"); then
        log_success "K6 tests completed for ${stack_name}"
    else
        log_warn "K6 tests had failures for ${stack_name} (continuing with data dump)"
    fi

    log_info "Dumping Prometheus data for ${stack_name}..."
    if (cd "${K6_DIR}" && python3 dump_prometheus_data.py "${stack_name}"); then
        log_success "Prometheus data dumped for ${stack_name}"
    else
        log_error "Prometheus data dump FAILED for ${stack_name}"
    fi

    log_info "Generating plots for ${stack_name}..."
    if (cd "${K6_DIR}" && python3 plot_metrics.py "${stack_name}"); then
        log_success "Plots generated for ${stack_name}"
    else
        log_warn "Plot generation failed for ${stack_name} (non-critical)"
    fi

    log_info "Backing up Prometheus TSDB & Loki raw data for ${stack_name}..."
    # Prometheus TSDB backup via Alpine sidecar
    if kubectl exec -n monitoring prometheus-prometheus-stack-kube-prom-prometheus-0 -c sidecar-tools -- tar czf - -C /prometheus-data . > "${RESULTS_DIR}/prometheus_tsdb_${stack_name}.tar.gz" 2>/dev/null; then
        log_success "Prometheus TSDB backup saved: prometheus_tsdb_${stack_name}.tar.gz"
    else
        log_warn "Failed to backup Prometheus TSDB for ${stack_name}"
    fi

    # Loki raw data backup via Loki container
    if kubectl exec -n monitoring loki-0 -c loki -- tar czf - -C /var/loki . > "${RESULTS_DIR}/loki_data_${stack_name}.tar.gz" 2>/dev/null; then
        log_success "Loki raw data backup saved: loki_data_${stack_name}.tar.gz"
    else
        log_warn "Failed to backup Loki data for ${stack_name}"
    fi

    save_audit_log "${stack_name}"

    local stack_end
    stack_end=$(date +%s)
    local duration=$(( stack_end - stack_start ))
    log_success "${stack_name} completed in $(( duration / 60 ))m $(( duration % 60 ))s"
}

RUN_START=$(date +%s)

log_header "AUTOMATED BENCHMARK – START"
echo "  Stacks:     ${STACKS[*]}"
echo "  Iterations: ${ITERATIONS}"
echo "  Log file:   ${LOG_FILE}"
echo "  Started:    $(timestamp)"
echo ""

check_vault_pass

if ! python3 -c "import pandas, numpy, matplotlib, requests" 2>/dev/null; then
    log_error "Missing Python deps. Run: pip install pandas numpy matplotlib requests"
    exit 1
fi
log_success "Python dependencies verified"

echo ""

# Testy są uruchamiane po kolei

FAILED_STACKS=()
SUCCEEDED_STACKS=()

for STACK in "${STACKS[@]}"; do
    if process_stack "${STACK}"; then
        SUCCEEDED_STACKS+=("${STACK}")
    else
        FAILED_STACKS+=("${STACK}")
        log_warn "Stack ${STACK} failed but continuing with remaining stacks"
    fi
done

log_header "K6 BUSINESS METRICS COMPILATION"

log_info "Compiling K6 summary JSONs into business metrics CSV..."
if (cd "${K6_DIR}" && python3 parse_k6_summaries.py); then
    log_success "K6 business metrics CSV generated"
else
    log_warn "K6 business metrics compilation failed (non-critical)"
fi

log_header "CROSS-STACK COMPARISON DASHBOARDS"

if [ ${#SUCCEEDED_STACKS[@]} -ge 2 ]; then
    log_info "Generating comparison dashboards..."
    if (cd "${K6_DIR}" && python3 plot_comparisons.py); then
        log_success "Comparison dashboards generated"
    else
        log_error "Comparison dashboard generation failed"
    fi
else
    log_warn "Need at least 2 successful stacks for comparisons (got ${#SUCCEEDED_STACKS[@]})"
fi

RUN_END=$(date +%s)
TOTAL_DURATION=$(( RUN_END - RUN_START ))
HOURS=$(( TOTAL_DURATION / 3600 ))
MINS=$(( (TOTAL_DURATION % 3600) / 60 ))
SECS=$(( TOTAL_DURATION % 60 ))

log_header "AUTOMATED BENCHMARK – COMPLETE"
echo ""
echo "  Total duration:    ${HOURS}h ${MINS}m ${SECS}s"
echo "  Stacks tested:     ${STACKS[*]}"
echo "  Succeeded:         ${SUCCEEDED_STACKS[*]:-none}"
echo "  Failed:            ${FAILED_STACKS[*]:-none}"
echo ""
echo "  Results directory: ${RESULTS_DIR}"
echo "  Log file:          ${LOG_FILE}"
echo ""
if [ ${#FAILED_STACKS[@]} -gt 0 ]; then
    log_warn "${#FAILED_STACKS[@]} stack(s) failed. Check audit logs for details."
    exit 1
else
    log_success "All ${#SUCCEEDED_STACKS[@]} stacks completed successfully."
    exit 0
fi
