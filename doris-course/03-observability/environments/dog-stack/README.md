# DOG stack

The observability course uses the upstream
[`ai-observe/ai-observe-stack`](https://github.com/ai-observe/ai-observe-stack)
Docker Compose environment at the commit pinned in `doris_course/environment.py`
(`STACK_COMMIT`). `ObservabilityLab.prepare_environment()` checks out that commit
under the ignored `.runtime/` directory and starts:

- Apache Doris all-in-one 4.1.3
- OpenTelemetry Collector
- Grafana with the Doris data source
- Mailpit, which receives Grafana's emails (added by this course)

The files in this directory are layered on the upstream Compose files:

- `compose.dog.yml` (Compose project `doris-obs`) renames the containers and the
  network, publishes the host ports on 127.0.0.1 only, runs Doris 4.1.3 with its
  metadata and data in two volumes, and bind-mounts the Doris FE and BE log
  directories under `.runtime/doris-logs/`. Module 2 reads the FE log from there.
  It also adds the Mailpit service, points Grafana's SMTP settings at it, and runs
  the DOG Collector in the Docker host's UTS namespace with a second
  configuration file.
- `collector-host-metrics.yml` is that second file. The Collector merges it into
  the upstream configuration: it moves the host metrics to a pipeline of their own
  and labels them with `host.name`, which Module 8's alert groups by.
- `compose.demo.yml` (Compose project `doris-obs-demo`) renames the 23 demo
  containers, publishes only the storefront, and connects the demo Collector to
  the `doris-obs` network.
- `demo-collector-extras.yml` makes the demo Collector forward its telemetry to
  the DOG Collector over that network. Upstream sends it to port 4317 on the
  host instead.

Both override files name every upstream service, and `compose.dog.yml` adds
`mailpit`. After moving `STACK_COMMIT`, run `prepare_environment()` once, then
`tests/test_environment.py`: its last test compares the services with the
upstream Compose files, and checks that `collector-host-metrics.yml` still
restates every receiver of the upstream Collector's `metrics` pipeline.

Litefuse, which Module 7 starts, has a Compose file of its own in
`environments/litefuse/` (Compose project `doris-obs-litefuse`). It joins the
`doris-obs` network and keeps its tables in this Doris, in the database
`litefuse`. `ObservabilityLab.start_litefuse()` first gives the Doris BE the tag
`private_endpoint` = `doris-obs:8040`: the BE of the all-in-one image registers
as 127.0.0.1, and without the tag the FE redirects Litefuse's Stream Loads to an
address that the Litefuse containers cannot reach.
