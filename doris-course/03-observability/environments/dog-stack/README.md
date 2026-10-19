# DOG stack

The observability course uses the upstream
[`ai-observe/ai-observe-stack`](https://github.com/ai-observe/ai-observe-stack)
Docker Compose environment at the commit pinned in `doris_course/environment.py`
(`STACK_COMMIT`). `ObservabilityLab.prepare_environment()` checks out that commit
under the ignored `.runtime/` directory and starts:

- Apache Doris all-in-one 4.1.3
- OpenTelemetry Collector
- Grafana with the Doris data source

The files in this directory are layered on the upstream Compose files:

- `compose.dog.yml` (Compose project `doris-obs`) renames the containers and the
  network, publishes the host ports on 127.0.0.1 only, runs Doris 4.1.3 with its
  metadata and data in two volumes, and bind-mounts the Doris FE and BE log
  directories under `.runtime/doris-logs/`. Module 2 reads the FE log from there.
- `compose.demo.yml` (Compose project `doris-obs-demo`) renames the 23 demo
  containers, publishes only the storefront, and connects the demo Collector to
  the `doris-obs` network.
- `demo-collector-extras.yml` makes the demo Collector forward its telemetry to
  the DOG Collector over that network. Upstream sends it to port 4317 on the
  host instead.

Both override files name every upstream service. After moving `STACK_COMMIT`,
run `prepare_environment()` once, then `tests/test_environment.py`: its last
test compares the services with the upstream Compose files.
