# Role: fluent_bit

Instaluje **Fluent Bit** jako DaemonSet na klastrze K3s przy użyciu oficjalnego Helm charta `fluent/fluent-bit`.

## Przeznaczenie

Rola jest częścią **Stosu 2** frameworku badawczego Observability Lab.  
Zastępuje sidecar-based log collection (Istio) podejściem DaemonSet, eliminując "Paradoks Obserwatora".

## Architektura

```
[containerd CRI logs] → /var/log/containers/*.log
        ↓
[Fluent Bit DaemonSet] (1 pod / węzeł)
  ├── Input: tail + multiline CRI parser
  ├── Filter: Kubernetes metadata enrichment
  └── Output: Loki (monitoring namespace)
        ↓
[Grafana Loki] ← scrape ← [Prometheus ServiceMonitor]
```

## Kluczowe optymalizacje wydajności

| Parametr | Wartość | Uzasadnienie |
|---|---|---|
| `storage.type` | `memory` | Brak I/O na dysk – eliminuje wpływ na benchmark |
| `Mem_Buf_Limit` | `8MB` | Limit bufora RAM na INPUT, zapobiega OOM |
| `Flush` | `5s` | Rzadkie flush'e = mniej CPU w trybie idle |
| `Log_Level` | `warn` | Minimalna verbosity loggera Fluent Bit |
| `Kube_Meta_Cache_TTL` | `300s` | Cache API K8s – redukuje wywołania do apiserv |
| `Keep_Log` | `Off` | Usuwa pole `log` po merge – mniejszy payload |
| CPU request | `20m` | Konserwatywny – nie zakłóca benchmarku |
| Memory limit | `128Mi` | Bezpieczny sufit dla węzłów K3s |

## Zależności

- `prometheus_stack` (Loki musi być dostępny przed wdrożeniem)
- Kolekcja Ansible: `kubernetes.core`

## Zmienne

| Zmienna | Domyślna | Opis |
|---|---|---|
| `stack_state` | `present` | `present` / `absent` – steruje Helmem |
| `fluent_bit_chart_version` | `0.48.9` | Wersja Helm charta |
| `fluent_bit_loki_host` | `loki.monitoring.svc.cluster.local` | Adres Loki |
| `fluent_bit_loki_port` | `3100` | Port Loki |
