# Observability with Apache Doris

Run an online store on your computer, let it fail, and investigate the failure with the DOG stack:
the OpenTelemetry Collector collects the store's logs, metrics, and traces, Apache Doris stores and
queries them, and Grafana searches, charts, and alerts on them. Over eight modules you follow one
incident, from the first failed order to the alert that resolves when it ends, and learn how to
design Doris tables for telemetry and measure what each design choice does.

## Who this course is for

- Engineers who operate services, and developers who want to know what their services record.
- Data engineers who want to use Doris for logs, metrics, and traces.

You need:

- SQL: `SELECT` with `WHERE`, `GROUP BY`, and joins. The course explains Doris's own syntax.
- Docker: starting containers and reading their logs, and setting Docker's memory.
- Python and Jupyter: running notebook cells and reading short Python code.
- No earlier knowledge of Doris, OpenTelemetry, or Grafana.

## What you will learn

- Collect logs, metrics, and traces with OpenTelemetry Collector pipelines into Doris, and check
  with SQL that they arrived.
- Investigate an incident in Grafana: search logs with Lucene and SQL, follow a trace to the span
  where a failure starts, and build a dashboard.
- Design telemetry tables in Doris: table models, partitions and buckets, compaction and compression,
  inverted indexes, and materialized views, and measure their effect with `EXPLAIN` and Query Profiles.
- Analyze traces with SQL: failure rates, percentiles, where failures start, and window functions;
  and trace an LLM application with Litefuse, which keeps its data in Doris.
- Alert with Grafana on queries over Doris, route the notifications, and keep the rules as code.

## Course outline

Each module has a lesson, a Lab notebook, and a quiz of six questions. Read the lesson, run the Lab,
then take the quiz. The times include all three.

| Level | Module | What you will do | Time |
| --- | --- | --- | --- |
| 1 | [Module 1: Observability Foundations in the DOG Stack](level1/module01-observability-introduction/course.md) | Start the stack and the store, check that the three signals reach Doris, then turn on a feature flag that makes half of the payments fail, and see the failed orders in the traces. | 70 min |
| 1 | [Module 2: Ingesting Observability Data](level1/module02-data-ingest/course.md) | Build Collector pipelines of your own into Doris, then follow one failed order into the three tables, and find which services send no logs. | 70 min |
| 1 | [Module 3: Visualizing Observability Data](level1/module03-data-visualization/course.md) | Investigate in Grafana: the error search misses the failure, the access log finds it, the trace shows the payment service's exception, the host's CPU is ruled out, and a dashboard keeps the evidence. | 85 min |
| 2 | [Module 4: Table Models for Observability Data](level2/module04-table-model/course.md) | Keep compact summaries of the incident: requests and failures per service and minute in an AGGREGATE table, and one alert per kind of error in a UNIQUE table. | 70 min |
| 2 | [Module 5: Partitioning and Bucketing for Observability Data](level2/module05-partition-bucket/course.md) | Make the queries of the incident window read only the partitions and tablets that can hold its rows, and compare three ways to bucket the spans. | 75 min |
| 2 | [Module 6: Table Properties, Materialized Views, and Indexes](level2/module06-property-mv-index/course.md) | Measure how the index of the log messages speeds up the incident's search, keep its counts in a materialized view, and compare two compressions. | 85 min |
| 2 | [Module 7: Trace Analysis and Litefuse](level2/module07-data-analysis-litefuse/course.md) | Measure the incident with SQL, its failure rates, latency, and the service where every failure starts, then trace an LLM application with Litefuse. | 90 min |
| 2 | [Module 8: Alerting with Grafana](level2/module08-alerting/course.md) | Alert on the host's CPU and on the failed orders, keep a rule as code, then turn the flag off and watch the alert resolve. | 95 min |

The whole course takes about 11 hours. The modules build on each other: Module 1 starts the
environment and the incident, which every later module uses. Module 7 has an optional Lab 7A, which
traces a real model, on your computer or with your own OpenAI key.

## Environment

The Labs run in Docker. Module 1 starts the DOG stack and the OpenTelemetry demo, an online store
whose load generator keeps placing orders. Both come from the upstream
[ai-observe-stack](https://github.com/ai-observe/ai-observe-stack) repository at commit `2c1fbee`
(2026-09-23): the environment cell checks out that commit into the ignored `.runtime/` directory and
never pulls newer upstream code. Override files in `environments/dog-stack/` give every container,
network, and volume the prefix `doris-obs`, publish only the ports below, on 127.0.0.1, add Mailpit,
and label the host metrics with the name of the Docker host.

| Component | Image | Containers |
| --- | --- | --- |
| Apache Doris 4.1.3 | `apache/doris:all-in-one-4.1.3` | `doris-obs` |
| OpenTelemetry Collector | `otel/opentelemetry-collector-contrib:0.144.0` | `doris-obs-otel-collector` |
| Grafana 11.4.0 with the Doris App plugin | `grafana/grafana:11.4.0` | `doris-obs-grafana` |
| Mailpit, a local mail server and inbox for Grafana's emails | `axllent/mailpit:v1.31.3` | `doris-obs-mailpit` |
| OpenTelemetry demo (Astronomy Shop) 2.0.2 | 23 images, mostly `ghcr.io/open-telemetry/demo:2.0.2-*` | `doris-obs-demo-*` (23) |
| Module 2's collectors | `otel/opentelemetry-collector-contrib:0.144.0` | `doris-obs-log2doris`, `-metric2doris`, `-traces2doris` |
| Litefuse 26.3.0 for Module 7: web UI and API, worker | `litefuse/litefuse-web:26.3.0`, `litefuse/litefuse-worker:26.3.0` | `doris-obs-litefuse-web`, `doris-obs-litefuse-worker` |
| Litefuse's PostgreSQL, Redis, and object storage ([Silo](https://github.com/pgsty/silo), a maintained fork of MinIO) | `postgres:17.11`, `redis:7.4.11`, `pgsty/silo:RELEASE.2026-10-18T00-00-00Z` | `doris-obs-litefuse-postgres`, `-redis`, `-silo` |
| llama.cpp server with Qwen2.5 0.5B Instruct (4-bit, Apache 2.0), for the optional Lab 7A | `ghcr.io/ggml-org/llama.cpp:server-b11429`; the model file from [Hugging Face](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF) | `doris-obs-llm` |
| CPU load for Module 8, for a few minutes | `busybox:1.37.0` | `doris-obs-cpu-load` |

The Doris image digest is
`sha256:82a5cabc7900ebcd3d080412d636c0cebd6602799fffe2605c652b2ea7d42609`. `SHOW FRONTENDS` and
`SHOW BACKENDS` report its version as `doris-4.1.3-rc02-7126cf65d96`: the 4.1.3 release is that build.

- **Platforms:** all images are published for linux/amd64 and linux/arm64. The course was verified
  on macOS with Apple silicon and Docker Desktop; on Apple silicon, the environment cell adds the
  Java option that the demo's Java services need on M4 and later chips. Linux has not been verified;
  [On Linux](#on-linux) lists what differs there.
- **Software:** Docker with Docker Compose 2.24.4 or later (the environment cell checks it), Git,
  and Python 3.10 to 3.13.
- **Memory:** the DOG stack uses about 5 GB, most of it for Doris, the demo about 3 GB, and Litefuse
  about 1 GB from Module 7 on; the model server of the optional Lab 7A about 0.4 GB more. Give
  Docker at least 10 GB of memory; on Linux, keep at least 10 GB free for the containers.
- **CPU:** Module 8 keeps every CPU of the Docker host busy for up to 5 minutes, at the lowest
  priority, to make an alert fire. Your computer may run its fans.
- **Disk:** about 21 GB for the images, 5 GB of them Litefuse's, plus the data that Doris keeps. The
  optional Lab 7A needs about 1.7 GB more for its image and model.
- **Downloads:** about 2.1 GB of images for the DOG stack and 2.7 GB for the demo. Module 7 downloads
  about 1.2 GB for Litefuse, and its optional Lab 7A about 300 MB for the model server and 491 MB for
  the model. Grafana downloads two small plugins when it first starts, and Module 8 the 2 MB
  `busybox` image.
- **Time:** once the images are downloaded, Module 1 starts the environment in about a minute. Some
  steps wait on purpose: the first failed order after you turn on the flag (one to three minutes),
  and three waits of 3 to 6 minutes in Module 8.
- **Accounts and keys:** none. Module 7's LLM application calls a simulated model, and Litefuse runs
  locally with a user and API keys that it creates on its first start. The optional Lab 7A runs a
  model locally too; it can call OpenAI's API instead, with your own key in `OPENAI_API_KEY`.

All ports bind to 127.0.0.1. To use another port, set its variable before you start Jupyter, for
example `DORIS_OBS_GRAFANA_PORT=23001 .venv/bin/jupyter lab`. The environment cells check the ports
first, and stop with the variable to set when a port is in use.

| Host port | Service | Variable |
| --- | --- | --- |
| 29030 | Doris FE query port (MySQL protocol, user `root`, no password) | `DORIS_OBS_QUERY_PORT` |
| 28030 | Doris FE HTTP | `DORIS_OBS_HTTP_PORT` |
| 28040 | Doris BE HTTP | `DORIS_OBS_BE_HTTP_PORT` |
| 23000 | Grafana (user `admin`, password `admin`) | `DORIS_OBS_GRAFANA_PORT` |
| 24317 | Collector OTLP gRPC | `DORIS_OBS_OTLP_GRPC_PORT` |
| 24318 | Collector OTLP HTTP | `DORIS_OBS_OTLP_HTTP_PORT` |
| 24328 | Module 2 trace collector OTLP HTTP | `DORIS_OBS_TRACES_OTLP_HTTP_PORT` |
| 28082 | Demo storefront and its flag page, `/feature` | `DORIS_OBS_DEMO_PORT` |
| 28025 | Mailpit inbox for Grafana's emails | `DORIS_OBS_MAILPIT_PORT` |
| 23100 | Litefuse web UI and API (user `learner@example.com`, password `doris-course-1`) | `DORIS_OBS_LITEFUSE_PORT` |
| 28080 | Local model server of the optional Lab 7A (OpenAI-compatible API) | `DORIS_OBS_LLM_PORT` |

### On Linux

The course has been verified only with Docker Desktop on macOS. With Docker Engine on Linux, these
steps differ:

- Install Docker Engine and its Compose plugin from
  [Docker's repository](https://docs.docker.com/engine/install/). A distribution's own package can
  be older than Compose 2.24.4; the environment cell tells you if yours is.
- Let your user run `docker` without `sudo`, since the notebooks run it:
  `sudo usermod -aG docker "$USER"`, then sign out and in again.
- Docker Engine has no memory setting: the containers share the computer's memory with Jupyter and
  the browser. Keep at least 10 GB free for them.
- On Debian and Ubuntu, `python3 -m venv` needs the package `python3-venv`, for example
  `sudo apt install python3-venv`.
- Doris writes its logs in `.runtime/doris-logs/` as root, so on your computer they are root's files
  too. `lab.teardown()` gives them to your user at the end; run it before you delete `.runtime/`.
- Rootless Docker and Podman have not been tried. The demo's collector, for one, mounts Docker's
  socket at `/var/run/docker.sock`.

## Get started

1. Install Docker, give it at least 10 GB of memory, and start it. On Linux, read
   [On Linux](#on-linux) first.
2. Create the course's Python environment. Run these commands from this directory, with Python 3.10
   to 3.13:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r requirements.txt
   ```

   `requirements.txt` also installs `doris_labkit`, the notebook runtime shared by the courses, from
   `../common`, so run the command from this directory and keep the repository together.
3. Start JupyterLab from the same directory, with `.venv/bin/jupyter lab`.
4. Open the lesson of [Module 1](level1/module01-observability-introduction/course.md), then its Lab,
   and run the cells in order.

The first code cell of each notebook creates a `lab` object. Its methods start the environment, run
SQL on Doris, and read Grafana, Mailpit, and Litefuse, and each shows the SQL or the HTTP request
that it sends, so that you can repeat it in a MySQL client or with `curl`. Every Lab checks the data
that it needs before it uses it, and its cells can be rerun.

## Dataset

The course downloads no dataset. The telemetry comes from the systems that it runs:

- The [OpenTelemetry demo](https://opentelemetry.io/docs/demo/) (Astronomy Shop, Apache License
  2.0): about a dozen services in different languages, and a load generator that browses the store
  and places one to four orders a minute. While it runs, Doris receives roughly 10,000 spans and
  3,000 log lines a minute, and the metrics of the services, their hosts, and their containers.
- The incident: the demo's feature flag `paymentFailure`, which you set to 50% in Module 1, makes the
  payment service reject about half of the charges, so about half of the orders fail.
- The Doris FE's own log and metrics, which Module 2's collectors load.
- The traces of a small LLM application with a simulated model, which Module 7 sends to Litefuse.

Doris stores the telemetry in the database `otel`, in tables that the Doris exporter creates, with
times in UTC and one partition per UTC day, kept for 7 days. Litefuse keeps its tables in the database
`litefuse` of the same Doris.

## Clean up

- `lab.stop_demo()` stops and removes the demo's containers, with the volumes that Docker created for
  them. The telemetry already in Doris stays, and `lab.start_demo()` starts the demo again. The
  feature flags stay as you set them in the demo's flag page; Module 8 sets `paymentFailure` back to
  `off`.
- `lab.stop_litefuse()` stops and removes the Litefuse containers. Its user, keys, and traces stay in
  its volumes and in Doris, and `lab.start_litefuse()` starts it again with them.
- `lab.stop_local_model()` stops the model server of the optional Lab 7A. The downloaded model stays
  in its volume.
- `lab.teardown()` removes every container, network, and volume of this course: the demo, Litefuse,
  the local model, the Module 2 collectors, the Module 8 CPU load if it still runs, and the DOG stack,
  with Grafana's volume, which holds the dashboard of Module 3 and the alerting of Module 8. It also
  removes `.runtime/collector-state/`, where the Module 2 log collector keeps its read position, and
  turns the demo's feature flags off. `lab.teardown(keep_data=True)` keeps the volumes of the DOG
  stack, Litefuse, and the local model, the read position, and the flags, so that a later
  `lab.prepare_environment()` and `lab.start_litefuse()` continue with the same data.
- The upstream checkout and the Doris FE logs stay in `.runtime/`. Delete that directory when you no
  longer need them. Doris writes its logs as root; `lab.teardown()` gives them to your user, so that
  you can delete them on Linux too.

## Troubleshooting

- **A port is in use.** The environment cell stops before it starts any container and names the
  port's variable. Stop the program that uses the port, or set the variable to a free port and
  restart Jupyter.
- **The demo does not start, or its containers keep restarting.** Docker probably has too little
  memory: give it at least 10 GB, or on Linux free that much. The cell lists the containers that are
  not running; `docker logs <container>` shows why.
- **Docker reports "permission denied" (Linux).** Your user may not run Docker yet. Run
  `sudo usermod -aG docker "$USER"`, sign out and in again, and restart Jupyter.
- **`.runtime/` cannot be deleted (Linux).** Doris wrote files there as root. Run `lab.teardown()`,
  or `lab.teardown(keep_data=True)` to keep the data, which gives them to your user; then delete the
  directory.
- **Discover or Traces shows no hits.** The Doris App 1.0.5 compares its time range in your
  computer's time zone with the UTC times in Doris, so a relative range such as Last 15 minutes
  misses the newest rows unless your computer uses UTC. Set an absolute range in UTC; Lab 3 prints
  one. Grafana's dashboards are not affected.
- **No order fails.** Check that `paymentFailure` is `50%` in the flag page,
  [http://127.0.0.1:28082/feature](http://127.0.0.1:28082/feature), and that the demo runs. The load
  generator places only one to four orders a minute, so the first failure can take a few minutes.
- **Grafana refuses the admin password in Module 8.** If you set a new password when you first
  signed in, set `GRAFANA_ADMIN_PASSWORD` in the Lab to it. The other cells read Grafana without
  signing in.
- **The model of the optional Lab 7A does not download.** When huggingface.co cannot be reached, set
  `DORIS_OBS_LLM_MODEL_URL` to the same model file on a mirror before you start Jupyter.
