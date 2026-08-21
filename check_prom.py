import requests
resp = requests.get("http://192.168.56.11:30090/api/v1/query", params={"query": "container_memory_working_set_bytes{container!=\"POD\", container!=\"\"}"})
data = resp.json()["data"]["result"]
for r in data:
    if "opentelemetry" in r["metric"].get("container", "") or "jaeger" in r["metric"].get("container", ""):
        print(r["metric"].get("container"), r["metric"].get("pod"), r["value"][1])
