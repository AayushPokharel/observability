# Troubleshooting — Docker Observability Workshop

Use this section as a **rapid recovery guide**. Each issue follows the same pattern: **symptom → verify → look for → likely fix**.

## 1. Port already in use

### Symptom

Compose fails with an error similar to:

```text
Bind for 0.0.0.0:3000 failed: port is already allocated
```

### Verify

> **STUDENT**
>
> Check which process or container already owns the port.

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}' | grep -E ':(3000|5601|8080|9090|9200|16686)'
```

> **STUDENT**
>
> On Linux/WSL2, check host listeners too.

```bash
ss -lntp | grep -E ':(3000|5601|8080|9090|9200|16686)'
```

### Look for

Another container, local Grafana, an editor extension, or another student's stack holding the port.

### Likely fix

Stop the conflicting container, or change the host port in the rendered Compose file. Keep the container-side port unchanged.

---

## 2. OpenSearch exits immediately

### Symptom

`docker compose ps` shows `opensearch` as exited, often with a bootstrap error.

### Verify

> **STUDENT**
>
> Inspect the recent OpenSearch startup logs.

```bash
docker compose -f Manifests/rendered/logging/docker-compose.yml logs --tail=120 opensearch  # Look for bootstrap checks and JVM startup errors
```

> **STUDENT**
>
> Check the current kernel map-count value.

```bash
cat /proc/sys/vm/max_map_count  # OpenSearch requires a sufficiently high value
```

### Look for

A message similar to:

```text
max virtual memory areas vm.max_map_count [65530] is too low
```

OpenSearch documents a minimum of `262144` for Linux Docker hosts. citeturn980876search2turn980876search5

### Likely fix

> **INSTRUCTOR ONLY**
>
> Raise the host kernel setting before the class or before students proceed.

```bash
sudo sysctl -w vm.max_map_count=262144  # Raise the host value for the OpenSearch training stack
```

> **INSTRUCTOR ONLY**
>
> Verify the new value.

```bash
cat /proc/sys/vm/max_map_count  # Confirm the host now reports 262144 or higher
```

For persistence on Linux, configure `/etc/sysctl.conf` according to local operations policy rather than making students edit host configuration during the lab. OpenSearch also documents the WSL2 Docker Desktop path using the `docker-desktop` distribution. citeturn980876search1

---

## 3. Docker Desktop / WSL2 has insufficient memory

### Symptom

OpenSearch is OOM-killed, the UI is extremely slow, or multiple containers repeatedly restart.

### Verify

> **STUDENT**
>
> Check container memory usage and OOM status.

```bash
docker stats --no-stream  # Look for memory growth and containers hitting their limits
```

> **STUDENT**
>
> Check whether a container was killed with an OOM signal.

```bash
docker inspect "$(docker ps -aq --filter name=opensearch | head -1)" --format '{{json .State}}' 2>/dev/null | head -c 1200  # Inspect the OpenSearch container state
```

### Look for

- `OOMKilled: true`
- host swap pressure
- many stacks running simultaneously

### Likely fix

Stop older labs, increase Docker Desktop/WSL2 memory, or run the labs sequentially. OpenSearch is intentionally the memory-heavy portion of the workshop.

---

## 4. Prometheus target is DOWN

### Symptom

Prometheus `/targets` shows `gateway`, `orders`, or `inventory` as `DOWN`.

### Verify

> **STUDENT**
>
> Check the application container state.

```bash
docker compose -f Manifests/rendered/metrics/docker-compose.yml ps  # Confirm the target container is actually running
```

> **STUDENT**
>
> From inside Prometheus, test the target by Compose service name.

```bash
docker compose -f Manifests/rendered/metrics/docker-compose.yml exec prometheus wget -qO- http://gateway:8080/metrics | head -20  # Test bridge-network reachability
```

### Look for

- DNS resolution to the Compose service name
- HTTP 200 from `/metrics`
- application process still listening on `8080`

### Likely fix

Correct the Compose service name or port, restart the application, and recheck `/targets`.

---

## 5. Fluent Bit cannot connect to OpenSearch

### Symptom

Fluent Bit logs show connection errors or repeated failed bulk writes.

### Verify

> **STUDENT**
>
> Inspect Fluent Bit output errors.

```bash
docker compose -f Manifests/rendered/logging/docker-compose.yml logs --tail=120 fluent-bit  # Find OpenSearch connection or mapping errors
```

> **STUDENT**
>
> Check that OpenSearch itself answers.

```bash
curl -fsS http://localhost:9200/_cluster/health?pretty  # Verify the destination before debugging the shipper
```

### Look for

- connection refused → OpenSearch is not ready
- HTTP 400/500 bulk errors → output/configuration problem
- mapping errors → field type conflicts or index reuse

### Likely fix

Make OpenSearch healthy first, then restart Fluent Bit if necessary. Keep the training index names isolated by student/project.

---

## 6. Docker logs never reach Fluent Bit

### Symptom

Fluent Bit is running, but OpenSearch has no application logs.

### Verify

> **STUDENT**
>
> Confirm the application container uses the Fluentd logging driver.

```bash
docker inspect "$(docker ps --filter name=gateway --format '{{.ID}}' | head -1)" --format '{{json .HostConfig.LogConfig}}'  # Check the container logging driver
```

> **STUDENT**
>
> Confirm Fluent Bit publishes its host listener.

```bash
docker compose -f Manifests/rendered/logging/docker-compose.yml port fluent-bit 24224  # Show the host mapping for the forward listener
```

### Look for

- driver should be `fluentd`
- Fluent Bit should have host port `24224` published
- the logging infrastructure should have been started before the application containers

### Likely fix

Restart the application containers after Fluent Bit is listening.

---

## 7. Jaeger shows no traces

### Symptom

The Jaeger UI loads, but no recent traces appear.

### Verify

> **STUDENT**
>
> Inspect the Collector logs first.

```bash
docker compose -f Manifests/rendered/traces/docker-compose.yml logs --tail=120 otel-collector  # Check OTLP receiver and Jaeger export errors
```

> **STUDENT**
>
> Inspect the gateway environment to confirm telemetry is enabled.

```bash
docker compose -f Manifests/rendered/traces/docker-compose.yml exec gateway env | grep '^OTEL_'  # Verify the trace exporter settings inside the application
```

### Look for

- endpoint should reference `otel-collector:4317`
- protocol should be `grpc`
- Collector should be running on the same Compose network

### Likely fix

Fix the OTEL endpoint or Collector pipeline, then generate a fresh request. Jaeger all-in-one uses transient in-memory storage in this local configuration, so restarting it clears old traces. citeturn980876search3turn980876search11

---

## 8. Services cannot resolve each other

### Symptom

An app reports “connection refused” or DNS errors to `orders`, `inventory`, `prometheus`, or `otel-collector`.

### Verify

> **STUDENT**
>
> Inspect the Compose network list.

```bash
docker network ls --filter name="${COMPOSE_PROJECT_NAME}"  # Confirm the isolated project network exists
```

> **STUDENT**
>
> Inspect network membership.

```bash
docker network inspect "${COMPOSE_PROJECT_NAME}_default" 2>/dev/null || docker network inspect "${COMPOSE_PROJECT_NAME}-default"  # Check which services are attached to the bridge network
```

### Look for

All communicating services attached to the same Compose-created bridge network.

### Likely fix

Use the **Compose service name** and container port, not `localhost` between containers. `localhost` inside a container refers to that same container.

---

## 9. Grafana cannot query Prometheus

### Symptom

Dashboard panels show `No data` even though Prometheus has metrics.

### Verify

> **STUDENT**
>
> Check the data source health from Grafana's UI or query the Prometheus endpoint directly.

```bash
curl -fsS http://localhost:9090/-/ready  # Verify that Prometheus is ready for queries
```

### Look for

Grafana's provisioned data source should use:

```text
http://prometheus:9090
```

### Likely fix

Do not use `localhost:9090` in the Grafana container. Use the Compose service name `prometheus`.

---

## 10. Student stacks collide

### Symptom

Containers from different students appear in the same `docker ps` output, or one student's stack removes another's resources.

### Verify

> **STUDENT**
>
> Check the effective Compose project name.

```bash
docker compose -f Manifests/rendered/metrics/docker-compose.yml config --format json | head -c 800  # Inspect the rendered Compose model and project scoping
```

### Look for

A distinct project name per student, for example:

```text
observe-student01
observe-student02
```

### Likely fix

Set `STUDENT` and `COMPOSE_PROJECT_NAME` before rendering and before running Compose commands. Never reuse another student's project name.

---

## Production reminder

The local stack is intentionally simplified. In production, revisit at least:

- authentication and authorization for Grafana/OpenSearch/Jaeger
- TLS for telemetry and backend traffic
- persistent storage and backup
- retention and rollover policies
- high availability
- resource requests/limits and autoscaling
- alert routing, ownership, and runbooks
- cardinality controls for metrics and logs
- trace sampling and cost budgets
