# DOG stack

The observability course uses the upstream
[`ai-observe/ai-observe-stack`](https://github.com/ai-observe/ai-observe-stack)
Docker Compose environment. `ObservabilityLab.prepare_environment()` stores the
checkout under the ignored `.runtime/` directory and starts:

- Apache Doris all-in-one
- OpenTelemetry Collector
- Grafana with the Doris data source

`compose.doris-logs.yml` adds bind mounts for the Doris FE and BE log
directories under `.runtime/doris-logs/`. Module 2 uses those files as inputs to
the log collector, while the demo environment sends its telemetry to the DOG
collector on the host.
