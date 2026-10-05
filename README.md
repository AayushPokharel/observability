# Observability: Metrics, Logs, and Traces

**Audience:** Developers and DevOps engineers with basic Docker knowledge  
**Format:** Instructor-led, lab-first, Docker Compose 
**Scope:** Local containers only; no Kubernetes, cloud, or managed services

## Workshop promise

By the end of the session, students will have a working local observability stack and will use it to answer an incident question three different ways: **what is happening, which requests are failing, and where the time is going?**

The workshop deliberately uses a small three-service application like `gateway`, `orders`, and `inventory` to create realistic traffic without introducing unnecessary platform complexity.

## Course of topoc

| Segment | Instructor mode | Student outcome |
|---|---|---|
| Setup + mental model | Explain + verify | Render manifests, validate Docker |
| Lab 1 — Metrics | 10 min explain / 25 min lab / 5 min debrief | Prometheus + Grafana SLO dashboard + alert |
| Lab 2 — Logs | 8 min explain / 27 min lab / 5 min debrief | Fluent Bit → OpenSearch → Dashboards |
| Lab 3 — Traces | 10 min explain / 28 min lab / 7 min debrief | OpenTelemetry → Collector → Jaeger |
| Correlated incident | Instructor-led investigation | Metrics → logs → traces in one incident |
| Troubleshooting + production notes | Guided Q&A | Recover common failures |
| Wrap | Takeaways | Three-pillar workflow remembered |


## Prerequisites

Students need:

- Docker Engine + Docker Compose v2 (`docker compose`)
- A shell on native Linux/macOS or WSL2 Ubuntu with Docker available
- A browser
- At least **6 GB RAM available to Docker**; **8 GB+ is strongly recommended** because OpenSearch is Java-based

## Student isolation

Use a project name per student so named networks, containers, and volumes are not shared accidentally.


```bash
export STUDENT="student01"  # Choose a unique identifier such as student01 or your initials
```
```bash
export COMPOSE_PROJECT_NAME="observe-${STUDENT}"  # Isolate Docker resources by student
```

## Render all workshop manifests once

The workshop intentionally keeps templates separate from rendered files. Students customize only the small set of environment variables; the render script materializes all manifests together.


```bash
chmod +x Manifests/render-manifests.sh  # Allow the manifest renderer to run
```
```bash
./Manifests/render-manifests.sh  # Render all Compose files and configuration templates
```
```bash
find Manifests/rendered -maxdepth 3 -type f | sort  # Review the generated workshop configuration
```

## Environment used by every lab

```text
                     +--------------------+
                     |  demo application   |
                     | gateway/orders/etc. |
                     +----------+---------+
                                |
                    +-----------+-----------+
                    |   Docker bridge net   |
                    +-----------+-----------+
                                |
          +---------------------+----------------------+
          |                     |                      |
      Metrics                Logs                  Traces
          |                     |                      |
   Prometheus             Fluent Bit             OTel Collector
          |                     |                      |
       Grafana             OpenSearch                Jaeger
                               |                      |
                       Dashboards UI              Trace UI
```

## URLs

After each lab starts its stack. **host ports are intentionally simple defaults**. If students run more than one stack at the same time, use alternate host ports or stop the previous lab.

| Component | Default URL |
|---|---|
| Demo gateway | http://localhost:8080 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |
| OpenSearch | http://localhost:9200 |
| OpenSearch Dashboards | http://localhost:5601 |
| Jaeger | http://localhost:16686 |

## Files in this repo

- `module-observability.md` : the verbal teaching track and architecture diagrams.
- `lab-1-metrics.md` : SLO-oriented metrics, PromQL, Grafana, and alerting.
- `lab-2-logs.md` : structured logs, Docker shipping, Fluent Bit, OpenSearch, and search.
- `lab-3-traces.md` : OpenTelemetry instrumentation, Collector, Jaeger, and sampling.
- `troubleshooting.md` : common local Docker failures and recovery steps.
- `Manifests/templates/full/docker-compose.yml` : optional capstone stack that runs all three pillars together for correlation.
- `Manifests/` : renderable lab configuration plus the demo application source.

## Production boundary

- This is a **training environment**. 
- OpenSearch security is disabled to keep the lab short, Jaeger uses transient in-memory storage, and the example alert receiver is local. 
- Those choices are deliberate teaching shortcuts—not recommended production defaults. 
- The official OpenSearch quickstart similarly documents disabled security as a test-only setup, and Jaeger all-in-one defaults to in-memory storage.

## Official references used for the workshop

The workshop configuration and teaching notes were checked against current vendor documentation available on 2026-10-01. The local webhook receiver uses a pinned version of `mendhak/http-https-echo`, which exposes request details in its container logs. Pin versions in the manifests are deliberate; update them as a reviewed workshop dependency change rather than switching blindly to `latest`.

- Prometheus metric types and instrumentation: https://prometheus.io/docs/concepts/metric_types/
- Prometheus configuration and scraping: https://prometheus.io/docs/prometheus/latest/configuration/configuration/
- Grafana provisioning and alerting: https://grafana.com/docs/grafana/latest/administration/provisioning/
- Fluent Bit Docker installation and OpenSearch output: https://docs.fluentbit.io/manual/
- OpenSearch Docker installation and host settings: https://docs.opensearch.org/latest/install-and-configure/install-opensearch/docker/
- OpenTelemetry Collector with Docker: https://opentelemetry.io/docs/collector/install/docker/
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/
- Jaeger Docker / all-in-one: https://www.jaegertracing.io/docs/2.21/getting-started/
