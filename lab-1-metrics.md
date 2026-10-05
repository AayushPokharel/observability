# Lab 1 : Metrics, Prometheus, Grafana, and SLO Alerting

**Core skill:** Build an operational dashboard from counters, gauges, and histograms.

> Ensure Docker has at least 6 GB available before starting the metrics lab if all other labs are stopped. The later OpenSearch lab is heavier.

## Preparation

- Confirm the rendered files exist.
- Have the browser tabs ready for Prometheus (`:9090`) and Grafana (`:3000`).
- Make sure students use unique `STUDENT` and `COMPOSE_PROJECT_NAME` values.

## Student objective

Students will:

1. Start the demo application, Prometheus, Grafana, and a local alert receiver.
2. Verify Prometheus scraping.
3. Use PromQL to calculate traffic, error rate, p90 latency, and a saturation proxy.
4. Inspect a provisioned SLO dashboard.
5. Create a Grafana alert that fires when the error ratio exceeds 5%.
6. Generate traffic and intentionally trigger errors.

## Expected result

Grafana shows a dashboard for the selected service with four operational signals:

- request rate
- error ratio
- p90 request latency
- in-flight requests

An alert fires when the gateway error ratio stays above 5% for the configured evaluation period.

## Common failure

The most common issue is **Prometheus showing the targets as DOWN**. First check the Compose network and the target container logs; do not start rewriting Prometheus configuration until you verify the service is reachable by its Compose service name.

## Teaching point

The dashboard is built around an **SLO and the four golden signals**, not CPU graphs or container counts.

---

## 1. Set student scope

Create the per-student identifier used by all Compose resources.

```bash
export STUDENT="student01"  # Pick a unique student identifier
```
Create the isolated Compose project name.

```bash
export COMPOSE_PROJECT_NAME="observe-${STUDENT}"  # Scope containers, networks, and volumes
```
Render the complete configuration set from the templates.

```bash
./Manifests/render-manifests.sh  # Generate all lab-ready files under Manifests/rendered/
```

## 2. Validate the Compose file

Validate the metrics Compose model before creating containers.

```bash
docker compose -f Manifests/rendered/metrics/docker-compose.yml config  # Catch YAML and interpolation mistakes first
```

## 3. Start the metrics stack

Start the application and observability components in detached mode.

```bash
docker compose -f Manifests/rendered/metrics/docker-compose.yml up -d --build  # Build the demo app and start the metrics stack
```

Confirm that the containers are running.

```bash
docker compose -f Manifests/rendered/metrics/docker-compose.yml ps  # Check service state and published ports
```

## 4. Generate a small amount of traffic

Call the normal checkout path repeatedly so Prometheus has useful samples.

```bash
for i in $(seq 1 20); do curl -fsS http://localhost:8080/checkout >/dev/null; done  # Generate successful requests
```

Generate intentionally slow requests for the latency histogram.

```bash
for i in $(seq 1 10); do curl -fsS "http://localhost:8080/checkout?slow=1" >/dev/null; done  # Create a visible latency tail
```

## 5. Verify Prometheus scraping

Open `http://localhost:9090/targets`.

Expected: `gateway`, `orders`, and `inventory` are **UP**.

Query total request rate directly in Prometheus.

```bash
curl -s http://localhost:9090/api/v1/query \
  --data-urlencode 'query=app_http_requests_total{service="gateway"}' \
  | jq   # Prove the application exposes Prometheus metrics
```
Use Prometheus's HTTP API to check that Prometheus can query the gateway metric.

```bash
curl -fsS 'http://localhost:9090/api/v1/query?query=app_http_requests_total' | head -c 1200  # Confirm a time series is stored
```

## 6. Read the metric types

Explain of metrics from the application:

| Metric | Type | Operational question |
|---|---|---|
| `app_http_requests_total` | Counter | How much traffic/errors happened? |
| `app_http_request_duration_seconds` | Histogram | What does latency look like? |
| `app_http_inflight_requests` | Gauge | How many requests are active now? |
| `app_queue_depth` | Gauge | How much work is waiting? |

Prometheus documents counters as monotonic values, gauges as values that can rise/fall, and histograms as bucketed distributions with count/sum data.

## 7. Practice PromQL

Calculate traffic by service over the last five minutes.

```promql
sum(rate(app_http_requests_total[5m])) by (service)
```
Calculate the gateway error ratio as a percentage.

```promql
100 * sum(rate(app_http_requests_total{service="gateway",status=~"5.."}[5m])) / sum(rate(app_http_requests_total{service="gateway"}[5m]))
```
Calculate gateway p90 latency from the classic histogram buckets.

```promql
histogram_quantile(0.90, sum by (le) (rate(app_http_request_duration_seconds_bucket{service="gateway"}[5m])))
```
Use in-flight requests as a simple saturation proxy.

```promql
sum(app_http_inflight_requests{service="gateway"})
```

The workshop teaches the query shape rather than pretending `inflight_requests` is a universal saturation metric. 

In production, saturation should map to the real bottleneck: worker pools, CPU, memory, queue depth, connection pools, or another constrained resource.

## 8. Open Grafana

Open `http://localhost:3000`.

Login:

- user: `admin`
- password: `admin`

The container provisions the Prometheus data source and a starter dashboard. Grafana supports file-based provisioning for version-controlled data sources and dashboards.

## 9. Inspect the SLO dashboard

Navigate to **Dashboards → Observability Workshop → SLO Overview**.

Students should identify:

- traffic panel
- error ratio panel
- p90 latency panel
- in-flight requests panel
- `service` variable

### Question prompt

Ask: **“Which panel would make you page?”**

Expected answer: the error ratio or user-facing latency SLO, not a raw CPU graph.

## 10. Create the alert

create one alert in the UI to see the human workflow before moving to infrastructure-as-code provisioning later.


> In Grafana, open **Alerting → Alert rules → New alert rule**.

Use:

- Name: `GatewayHighErrorRatio`
- Query A:

```promql
100 * sum(rate(app_http_requests_total{service="gateway",status=~"5.."}[2m])) / sum(rate(app_http_requests_total{service="gateway"}[2m]))
```

- Condition: **IS ABOVE 5**
- For: **1 minute**
- No-data state: **NoData**
- Error state: **Error**

For a workshop, “1 minute” gives fast feedback. 

In production, tune evaluation windows to match traffic volume and the business impact of the SLO.

Avoid alerting on a value that is too noisy at low request rates.

## 11. Add a local webhook contact point

Use **Alerting → Contact points → New contact point**.

Set:

- Name: `workshop-webhook`
- Type: `Webhook`
- URL: `http://alert-receiver:8080/alerts`

The `alert-receiver` service is inside the same Compose bridge network, so Grafana can reach it by service name without exposing the receiver to the host.

## 12. Trigger the alert

Generate 5xx responses fast enough to cross the 5% threshold.

```bash
for i in $(seq 1 20); do
  curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:8080/fail
done  # Drive the gateway error ratio upward
```

Verify the receiver saw an alert webhook.

```bash
docker compose -f Manifests/rendered/metrics/docker-compose.yml logs --tail=50 alert-receiver  # Inspect the local notification receiver
```

## Core completion check

Students are done when they can explain, verbally, all four statements:

1. **Traffic:** “Requests are increasing/decreasing at X requests per second.”
2. **Errors:** “The error ratio is approximately X%.”
3. **Latency:** “The p90 latency is approximately X seconds.”
4. **SLO action:** “The alert would page because the error budget is being consumed too quickly.”

## Stretch: compare p50 and p90

Compare p50 and p90 latency to see why averages can hide a long tail.

```promql
histogram_quantile(0.50, sum by (le) (rate(app_http_request_duration_seconds_bucket{service="gateway"}[5m])))
```

```promql
histogram_quantile(0.90, sum by (le) (rate(app_http_request_duration_seconds_bucket{service="gateway"}[5m])))
```


## 13. Clean up before the next lab

Stop and remove this lab's containers and volumes so the next lab has memory and ports available.

```bash
docker compose -f Manifests/rendered/metrics/docker-compose.yml down -v  # Remove metrics lab containers, network, and training data
```

## Debrief questions

- Why is `rate()` used on the request counter?
- Why is a histogram better than a single average for latency?
- What label would be dangerous to add to `app_http_requests_total` in a high-cardinality production system?
- What action does the alert expect an engineer to take?
