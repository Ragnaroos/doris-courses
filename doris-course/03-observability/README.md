# Observability with Apache Doris

This directory contains the DOG observability labs and a shared Python runtime
for notebook cells. The runtime follows the same learner-facing pattern as the
real-time analytics course.

## Set up the Python environment

Run these commands from this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` also installs `doris_labkit`, the notebook runtime shared by the
courses, from `../common`. Run the command from this directory and keep the
repository together.

Start JupyterLab from the same directory:

```bash
.venv/bin/jupyter lab
```

Every executable notebook finds this course root, imports the stable `DorisLab`
facade (the observability-specific class is also exported as
`ObservabilityLab`), and creates a `lab` object. Once that cell has run, a learner
can execute shell or Doris commands directly from later cells:

```python
lab.shell("docker ps", title="Running containers")
lab.sql("SHOW FRONTENDS", title="Doris frontends")
lab.execute("CREATE DATABASE IF NOT EXISTS otel")
```

Module 1 prepares the persistent DOG stack. It checks out the pinned upstream
stack into the ignored `.runtime/` directory, mounts the Doris log directories,
and starts Doris, Grafana, and the OpenTelemetry Collector. It then starts the
OpenTelemetry demo and waits until the demo's traces, logs, and metrics reach
Doris; the Level 2 labs that analyze this data check for it first. Module 2 starts
dedicated collectors for logs, metrics, and traces.

Docker state is kept outside the course files. Re-running an environment cell
reuses existing containers and data instead of replacing them.

## Environment

The labs run in Docker. Module 1 starts the DOG stack and the OpenTelemetry demo
storefront, which keeps sending telemetry to the stack. Both come from the
upstream [ai-observe-stack](https://github.com/ai-observe/ai-observe-stack)
repository at commit `2c1fbee` (2026-09-23). The environment cell checks out
that commit into `.runtime/` and never pulls newer upstream code.

| Component | Image | Containers |
| --- | --- | --- |
| Apache Doris 4.1.3 | `apache/doris:all-in-one-4.1.3` | `doris-obs` |
| OpenTelemetry Collector | `otel/opentelemetry-collector-contrib:0.144.0` | `doris-obs-otel-collector` |
| Grafana with the Doris App plugin | `grafana/grafana:11.4.0` | `doris-obs-grafana` |
| OpenTelemetry demo (Astronomy Shop) 2.0.2 | 23 images, mostly `ghcr.io/open-telemetry/demo:2.0.2-*` | `doris-obs-demo-*` (23) |

The Doris image digest is
`sha256:82a5cabc7900ebcd3d080412d636c0cebd6602799fffe2605c652b2ea7d42609`.
`SHOW FRONTENDS` and `SHOW BACKENDS` report its version as
`doris-4.1.3-rc02-7126cf65d96`: the 4.1.3 release is that build.

- **Docker:** Docker Compose 2.24.4 or later. The environment cell checks it.
- **Downloads:** about 2.1 GB of images for the DOG stack and 2.7 GB for the
  demo. Grafana also downloads two small plugins when it first starts.
- **Time:** once the images are downloaded, the Module 1 environment cells take
  about a minute: about 25 seconds for the DOG stack, 10 for the demo, and a few
  more until the demo's telemetry reaches Doris. The first run also downloads
  the images, which takes several minutes more.
- **Memory:** the DOG stack uses about 5 GB, most of it for Doris, and the demo
  about 3 GB. Give Docker at least 10 GB of memory.
- **Disk:** about 16 GB for the images, plus the data that Doris keeps.
- **Platforms:** all images are published for linux/amd64 and linux/arm64. The
  environment was verified on macOS with Apple silicon and Docker Desktop.

All ports bind to 127.0.0.1. To use another port, set its variable before
starting Jupyter, for example `DORIS_OBS_GRAFANA_PORT=23001 .venv/bin/jupyter lab`.

| Host port | Service | Variable |
| --- | --- | --- |
| 29030 | Doris FE query port (MySQL protocol) | `DORIS_OBS_QUERY_PORT` |
| 28030 | Doris FE HTTP | `DORIS_OBS_HTTP_PORT` |
| 28040 | Doris BE HTTP | `DORIS_OBS_BE_HTTP_PORT` |
| 23000 | Grafana (user `admin`, password `admin`) | `DORIS_OBS_GRAFANA_PORT` |
| 24317 | Collector OTLP gRPC | `DORIS_OBS_OTLP_GRPC_PORT` |
| 24318 | Collector OTLP HTTP | `DORIS_OBS_OTLP_HTTP_PORT` |
| 24328 | Module 2 trace collector OTLP HTTP | `DORIS_OBS_TRACES_OTLP_HTTP_PORT` |
| 28082 | Demo storefront | `DORIS_OBS_DEMO_PORT` |

The Compose override files in `environments/dog-stack/` apply these names and
ports on top of the upstream Compose files. The Module 2 trace collector
publishes its port when the Module 2 lab starts it.

## Stop and clean up

- `lab.stop_demo()` stops and removes the demo containers. The telemetry already
  in Doris stays, and `lab.start_demo()` starts the demo again.
- `lab.teardown()` removes every container, network, and volume of this course:
  the demo, the Module 2 collectors, and the DOG stack.
  `lab.teardown(keep_data=True)` keeps the Doris and Grafana volumes, so a later
  `lab.prepare_environment()` continues with the same data.
- The upstream checkout and the Doris logs stay in `.runtime/`. Delete that
  directory when you no longer need them.

## Interactive quizzes

Each module includes a six-question, single-choice knowledge check. The
quizzes use the shared `doris_course.quiz` interface and do not require a
running Docker environment or external services.

Level 1:

- Module 1: Observability Foundations in the DOG Stack — [Notebook](level1/module01-observability-introduction/quiz01_observability_foundations.ipynb) · [Question YAML](level1/module01-observability-introduction/quiz01_observability_foundations.yaml)
- Module 2: Ingesting Observability Data — [Notebook](level1/module02-data-ingest/quiz02_ingesting_observability_data.ipynb) · [Question YAML](level1/module02-data-ingest/quiz02_ingesting_observability_data.yaml)
- Module 3: Visualizing Observability Data — [Notebook](level1/module03-data-visualization/quiz03_observability_visualization.ipynb) · [Question YAML](level1/module03-data-visualization/quiz03_observability_visualization.yaml)

Level 2:

- Module 4: Table Models for Observability Data — [Notebook](level2/module04-table-model/quiz04_observability_table_models.ipynb) · [Question YAML](level2/module04-table-model/quiz04_observability_table_models.yaml)
- Module 5: Partitioning and Bucketing for Observability Data — [Notebook](level2/module05-partition-bucket/quiz05_partition_and_bucket_choices.ipynb) · [Question YAML](level2/module05-partition-bucket/quiz05_partition_and_bucket_choices.yaml)
- Module 6: Table Properties, Materialized Views, and Indexes — [Notebook](level2/module06-property-mv-index/quiz06_properties_mv_and_indexes.ipynb) · [Question YAML](level2/module06-property-mv-index/quiz06_properties_mv_and_indexes.yaml)
- Module 7: Trace Analysis and Litefuse — [Notebook](level2/module07-data-analysis-litefuse/quiz07_analysis_and_litefuse.ipynb) · [Question YAML](level2/module07-data-analysis-litefuse/quiz07_analysis_and_litefuse.yaml)
- Module 8: Alerting with Grafana — [Notebook](level2/module08-alerting/quiz08_alerting_rules.ipynb) · [Question YAML](level2/module08-alerting/quiz08_alerting_rules.yaml)
