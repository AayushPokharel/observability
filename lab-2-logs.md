# Lab 2 — Structured Logging, Fluent Bit, OpenSearch, and Correlation IDs

**Target time:** 40 minutes  
**Core skill:** Build and query a central container log pipeline.

## Instructor preparation

- Make sure OpenSearch host prerequisites are already fixed; see `troubleshooting.md`.
- Warn students that OpenSearch is the heaviest component in this workshop.
- Have `http://localhost:5601` ready to open in the browser.

## Student objective

Students will:

1. Start OpenSearch, OpenSearch Dashboards, Fluent Bit, and the demo services.
2. Use Docker's Fluentd logging driver to forward logs to Fluent Bit.
3. Parse application JSON logs.
4. Store records in OpenSearch using a daily index prefix.
5. Search by `service`, `level`, `request_id`, and HTTP status.
6. Discuss log volume and index-cost controls.

## Expected result

A searchable OpenSearch index contains structured application logs with fields such as:

`level`, `service`, `method`, `path`, `status`, `duration_ms`, `request_id`, and `message`.

## Common failure

The usual failure is OpenSearch exiting immediately because the host has an insufficient `vm.max_map_count`, followed by Fluent Bit being unable to connect. Fix the storage first; do not debug the shipper while the destination is down.

## Teaching point

Structured logs are a data contract. The application creates predictable fields; the logging pipeline transports, parses, filters, and stores them.

---

## 1. Set student scope

Create a unique project scope.

```bash
export STUDENT="student01"  # Pick a unique student identifier
```

Scope every Docker resource to the student's project.

```bash
export COMPOSE_PROJECT_NAME="observe-${STUDENT}"  # Isolate the logging lab
```

Render all workshop configuration before starting the lab.

```bash
./Manifests/render-manifests.sh  # Generate the logging configuration
```

## 2. Validate the logging Compose file

Validate the Compose model before creating the logging stack.

```bash
docker compose -f Manifests/rendered/logging/docker-compose.yml config  # Validate YAML and Compose interpolation
```

## 3. Start the log infrastructure first

The Docker daemon will forward application logs to Fluent Bit on the host's published `24224` port. Start Fluent Bit and OpenSearch before creating the application containers.

Start only the logging infrastructure first.

```bash
docker compose -f Manifests/rendered/logging/docker-compose.yml up -d opensearch opensearch-dashboards fluent-bit  # Start the destination and shipper first
```

Check the infrastructure containers.

```bash
docker compose -f Manifests/rendered/logging/docker-compose.yml ps opensearch opensearch-dashboards fluent-bit  # Confirm the logging pipeline components are running
```

## 4. Wait for OpenSearch health

Query the OpenSearch health endpoint until it returns a cluster response.

```bash
curl -fsS http://localhost:9200/_cluster/health?pretty  # Verify that OpenSearch is accepting requests
```

Look for:

- `status` of `green` or `yellow` in this single-node training cluster
- a non-zero `number_of_nodes`

`yellow` is normal in a single-node setup if replica shards cannot be placed. Do not spend live-training time making a one-node cluster green.

## 5. Start application containers second

Start the three demo services after the Fluent Bit forward listener is ready.

```bash
docker compose -f Manifests/rendered/logging/docker-compose.yml up -d --build gateway orders inventory  # Start applications that use Docker's Fluentd log driver
```

## 6. Generate normal and error traffic

Create successful request records with a stable request identifier.

```bash
curl -fsS -H 'X-Request-ID: demo-checkout-001' http://localhost:8080/checkout >/dev/null  # Produce a correlated successful request
```

Create a failing record with a different correlation ID.

```bash
curl -sS -o /dev/null -H 'X-Request-ID: demo-failure-001' http://localhost:8080/fail  # Produce a structured error log
```

Generate additional traffic so searches return a useful sample.

```bash
for i in $(seq 1 15); do curl -sS http://localhost:8080/checkout >/dev/null; done  # Add a small volume of normal requests
```

## 7. Inspect raw Fluent Bit activity

Read the Fluent Bit logs for parsing and output errors.

```bash
docker compose -f Manifests/rendered/logging/docker-compose.yml logs --tail=80 fluent-bit  # Check whether records are being accepted and delivered
```

Look for:

- forward listener activity
- no repeated connection refused errors
- no OpenSearch bulk rejection loop

## 8. Open OpenSearch Dashboards

Open `http://localhost:5601`.

Because this workshop disables the OpenSearch security plugin, students do not need credentials for the local UI.

> **PRODUCTION SAFETY**
>
> This is intentionally **not a production security configuration**. The OpenSearch quickstart documents disabled security as a test-only configuration. citeturn980876search5

## 9. Create the index pattern / data view

In OpenSearch Dashboards:

1. Open **Discover** or the **Management / Index Patterns** area, depending on the current UI.
2. Create a data view matching:

```text
observe-*
```

3. Use the timestamp field if the UI asks for a time field.

The Fluent Bit output uses a Logstash-style date suffix so the resulting index is approximately:

```text
observe-<student>-YYYY.MM.DD
```

Fluent Bit supports `Logstash_Format`, `Logstash_Prefix`, and `Suppress_Type_Name`; the last setting is important for modern OpenSearch because mapping types were removed. citeturn422533search4

## 10. Search structured logs

Use the Discover search bar.

### Search by service

```text
service:gateway
```

### Search only errors

```text
level:error
```

### Search one request across services

```text
request_id:demo-checkout-001
```

### Combine fields

```text
service:orders AND level:error
```

> **INSTRUCTOR NOTE**
>
> The exact query syntax can vary slightly with the Dashboards UI configuration. The important lesson is that students are filtering by **fields**, not grepping opaque message strings.

## 11. Inspect one structured event

A typical record should contain fields similar to:

```json
{
  "timestamp": "2026-10-05T...Z",
  "level": "info",
  "service": "orders",
  "method": "POST",
  "path": "/process",
  "status": 200,
  "duration_ms": 42.1,
  "request_id": "demo-checkout-001",
  "message": "request completed"
}
```

The exact timestamps and durations will vary.

## 12. Log levels

### What is it?

- `DEBUG`: diagnostic detail; usually disabled or sampled in production.
- `INFO`: normal lifecycle/business events.
- `WARNING`: unusual but not necessarily failed behavior.
- `ERROR`: an operation failed or needs attention.
- `CRITICAL`: severe failure requiring immediate action.

### Why does it matter?

- High-volume logs are expensive.
- The level should carry operational meaning, not developer emotion.
- A useful baseline is to keep `INFO` small and structured and reserve `DEBUG` for targeted troubleshooting.

### What should I remember?

**Log at the lowest useful volume that still explains an incident.**

## 13. Cost controls

Ask students which of these they would change first in production:

| Control | Why |
|---|---|
| Log level | Directly reduces volume |
| Message size | Reduces bytes per event |
| Field set | Prevents accidental payload bloat |
| Index strategy | Makes retention manageable |
| Retention period | Caps total storage |
| Sampling | Reduces repetitive low-value events |
| Compression | Reduces transfer/storage at CPU cost |

## Core completion check

Students should be able to answer:

> “Show me all error logs for the orders service for request `demo-checkout-001`, and explain why a JSON record is cheaper to operate than one giant formatted string.”

## Stretch: follow the Docker path

Print the logging driver configured for one running application container.

```bash
docker inspect "${COMPOSE_PROJECT_NAME}-gateway-1" --format '{{json .HostConfig.LogConfig}}' 2>/dev/null || docker inspect "${COMPOSE_PROJECT_NAME}_gateway_1" --format '{{json .HostConfig.LogConfig}}'  # Inspect the container's logging driver configuration
```

> **INSTRUCTOR NOTE**
>
> Container naming differs by Compose version/project naming conventions, so the fallback is included only for resilience.


## 14. Clean up before the next lab

Stop and remove the logging stack before starting tracing on a memory-constrained machine.

```bash
docker compose -f Manifests/rendered/logging/docker-compose.yml down -v  # Remove OpenSearch data and logging containers
```

## Debrief questions

- Why did we start Fluent Bit before the applications?
- What is the difference between a request ID and a trace ID?
- Why not index every free-form field?
- Why is daily index naming useful for retention?
