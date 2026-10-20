# Observability with Apache Doris

This directory contains the DOG observability labs and a shared Python runtime
for notebook cells. The runtime follows the same learner-facing pattern as the
real-time analytics course.

## Set up the Python environment

Run these commands from this directory, with Python 3.10 to 3.13:

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
stack into the ignored `.runtime/` directory, mounts the Doris FE's log directory,
and starts Doris, Grafana, the OpenTelemetry Collector, and Mailpit, a local mail
server that receives Grafana's alert emails in Module 8. It then starts the
OpenTelemetry demo and waits until the demo's traces, logs, and metrics reach
Doris; the Level 2 labs that analyze this data check for it first. At the end of
Module 1 you turn on one of the demo's feature flags, `paymentFailure`, so that
half of the store's payments fail: the course follows this incident from module
to module. Module 2 starts dedicated collectors for logs, metrics, and traces. Module 7 starts Litefuse, an
observability platform for LLM applications that keeps its tables in the same Doris.
Its optional Lab 7A gives the Lab's LLM application a real model: a small open model
that llama.cpp's server runs on your computer, or OpenAI's API with your own key.

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
| Mailpit, a local mail server and inbox | `axllent/mailpit:v1.31.3` | `doris-obs-mailpit` |
| OpenTelemetry demo (Astronomy Shop) 2.0.2 | 23 images, mostly `ghcr.io/open-telemetry/demo:2.0.2-*` | `doris-obs-demo-*` (23) |
| Litefuse 26.3.0 for Module 7: web UI and API, worker | `litefuse/litefuse-web:26.3.0`, `litefuse/litefuse-worker:26.3.0` | `doris-obs-litefuse-web`, `doris-obs-litefuse-worker` |
| Litefuse's PostgreSQL, Redis, and object storage ([Silo](https://github.com/pgsty/silo), a maintained fork of MinIO) | `postgres:17.11`, `redis:7.4.11`, `pgsty/silo:RELEASE.2026-10-18T00-00-00Z` | `doris-obs-litefuse-postgres`, `-redis`, `-silo` |
| llama.cpp server with Qwen2.5 0.5B Instruct (4-bit, Apache 2.0), for the optional Lab 7A | `ghcr.io/ggml-org/llama.cpp:server-b11429`; the model file `qwen2.5-0.5b-instruct-q4_k_m.gguf` from [Hugging Face](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF) | `doris-obs-llm` |
| CPU load for Module 8, for a few minutes | `busybox:1.37.0` | `doris-obs-cpu-load` |

The Doris image digest is
`sha256:82a5cabc7900ebcd3d080412d636c0cebd6602799fffe2605c652b2ea7d42609`.
`SHOW FRONTENDS` and `SHOW BACKENDS` report its version as
`doris-4.1.3-rc02-7126cf65d96`: the 4.1.3 release is that build.

- **Docker:** Docker Compose 2.24.4 or later. The environment cell checks it.
- **Downloads:** about 2.1 GB of images for the DOG stack and 2.7 GB for the
  demo. Module 7 downloads about 1.2 GB for Litefuse, and its optional Lab 7A
  about 300 MB for the model server and 491 MB for the model. Grafana also
  downloads two small plugins when it first starts, and Module 8 downloads the
  2 MB `busybox` image.
- **Time:** once the images are downloaded, the Module 1 environment cells take
  about a minute: about 25 seconds for the DOG stack, 10 for the demo, and a few
  more until the demo's telemetry reaches Doris. The first run also downloads
  the images, which takes several minutes more.
- **Memory:** the DOG stack uses about 5 GB, most of it for Doris, the demo
  about 3 GB, and Litefuse about 1 GB from Module 7 on; the model server of the
  optional Lab 7A about 0.4 GB more. Give Docker at least 10 GB of memory.
- **CPU:** Module 8 keeps every CPU of the Docker host busy for up to 5 minutes,
  at the lowest priority, to make an alert fire. Your computer may run its fans.
- **Disk:** about 21 GB for the images, 5 GB of them Litefuse's, plus the data
  that Doris keeps. The optional Lab 7A needs about 1.7 GB more for its image
  and model.
- **Accounts and keys:** none. Module 7's LLM application calls a simulated
  model, and Litefuse runs locally with a user and API keys that it creates on
  its first start. The optional Lab 7A runs a model locally too; it can call
  OpenAI's API instead, with your own key in `OPENAI_API_KEY`.
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
| 28025 | Mailpit inbox for Grafana's emails | `DORIS_OBS_MAILPIT_PORT` |
| 23100 | Litefuse web UI and API (user `learner@example.com`, password `doris-course-1`) | `DORIS_OBS_LITEFUSE_PORT` |
| 28080 | Local model server of the optional Lab 7A (OpenAI-compatible API) | `DORIS_OBS_LLM_PORT` |

The Compose override files in `environments/dog-stack/` apply these names and
ports on top of the upstream Compose files. They also add Mailpit, give Grafana
its SMTP settings, and label the DOG Collector's host metrics with the name of
the Docker host, which Module 8 alerts on. The Module 2 trace collector
publishes its port when the Module 2 lab starts it. Litefuse has a Compose file
of its own, `environments/litefuse/compose.litefuse.yml`, and keeps its tables
in the DOG stack's Doris, in the database `litefuse`; `lab.start_litefuse()`
starts it in Module 7. The model server of the optional Lab 7A has
`environments/llm/compose.llm.yml`; when huggingface.co cannot be reached, set
`DORIS_OBS_LLM_MODEL_URL` to the same model file on a mirror.

## Stop and clean up

- `lab.stop_demo()` stops and removes the demo containers. The telemetry already
  in Doris stays, and `lab.start_demo()` starts the demo again. The feature flags
  stay as you set them in the demo's flag page; to end the payment failure, set
  `paymentFailure` back to `off` there.
- `lab.stop_litefuse()` stops and removes the Litefuse containers. Its user,
  keys, and traces stay in its volumes and in Doris, and `lab.start_litefuse()`
  starts it again with them.
- `lab.stop_local_model()` stops the model server of the optional Lab 7A. The
  downloaded model stays in its volume.
- `lab.teardown()` removes every container, network, and volume of this course:
  the demo, Litefuse, the local model, the Module 2 collectors, the Module 8 CPU
  load if it still runs, and the DOG stack. The Grafana volume holds the alert
  rule, the notification policy, and the contact point of Module 8. It also
  removes `.runtime/collector-state/`, where the Module 2 log collector keeps its
  read position, and turns the demo's feature flags off.
  `lab.teardown(keep_data=True)` keeps the volumes of Doris, Grafana, Litefuse,
  and the local model, the read position, and the flags, so a later
  `lab.prepare_environment()` and `lab.start_litefuse()` continue with the same
  data.
- The upstream checkout and the Doris FE logs stay in `.runtime/`. Delete that
  directory when you no longer need them.

## Modules

Each module of Level 1 has a lesson, a Lab notebook, and a quiz; the modules of
Level 2 have a Lab and a quiz. Read the lesson, run the Lab, then take the quiz.
Each quiz has six single-choice questions; it uses the shared `doris_course.quiz`
interface and needs no running Docker environment or external services.

Level 1:

- Module 1: Observability Foundations in the DOG Stack — [Lesson](level1/module01-observability-introduction/course.md) · [Lab](level1/module01-observability-introduction/lab01_observability_introduction.ipynb) · [Quiz](level1/module01-observability-introduction/quiz01_observability_foundations.ipynb)
- Module 2: Ingesting Observability Data — [Lesson](level1/module02-data-ingest/course.md) · [Lab](level1/module02-data-ingest/lab02_ingest_observability_data.ipynb) · [Quiz](level1/module02-data-ingest/quiz02_ingesting_observability_data.ipynb)
- Module 3: Visualizing Observability Data — [Lesson](level1/module03-data-visualization/course.md) · [Lab](level1/module03-data-visualization/lab03_data_visualization.ipynb) · [Quiz](level1/module03-data-visualization/quiz03_observability_visualization.ipynb)

Level 2:

- Module 4: Table Models for Observability Data — [Lab](level2/module04-table-model/lab04_table_models.ipynb) · [Quiz](level2/module04-table-model/quiz04_observability_table_models.ipynb)
- Module 5: Partitioning and Bucketing for Observability Data — [Lab](level2/module05-partition-bucket/lab05_partition_and_bucket.ipynb) · [Quiz](level2/module05-partition-bucket/quiz05_partition_and_bucket_choices.ipynb)
- Module 6: Table Properties, Materialized Views, and Indexes — [Lab](level2/module06-property-mv-index/lab06_properties_mv_index.ipynb) · [Quiz](level2/module06-property-mv-index/quiz06_properties_mv_and_indexes.ipynb)
- Module 7: Trace Analysis and Litefuse — [Lab](level2/module07-data-analysis-litefuse/lab07_data_analysis_litefuse.ipynb) · [Quiz](level2/module07-data-analysis-litefuse/quiz07_analysis_and_litefuse.ipynb)
- Module 8: Alerting with Grafana — [Lab](level2/module08-alerting/lab08_alerting.ipynb) · [Quiz](level2/module08-alerting/quiz08_alerting_rules.ipynb)
