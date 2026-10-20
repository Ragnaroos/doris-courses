# Module 2: Ingesting Observability Data

| Course information | Value |
| --- | --- |
| Course | Observability with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Collector | OpenTelemetry Collector Contrib 0.144.0, with its Doris exporter |
| Estimated time | About 70 minutes: reading 30, Lab 30, quiz 10 |

[Course README](../../README.md) · [Open Lab 2](lab02_ingest_observability_data.ipynb) · [Open Quiz 2](quiz02_ingesting_observability_data.ipynb)

## Module goal

Build OpenTelemetry Collector pipelines that load logs, metrics, and traces into Doris, know what each part of a pipeline does and does not guarantee, and find the evidence of one failed order in each signal.

## Learning objectives

After completing this module, you will be able to:

1. Describe what the receivers, processors, exporters, and extensions of a Collector pipeline do.
2. Choose a receiver for a source that pushes its telemetry and for one that must be pulled.
3. Predict when a batch processor sends its data, and what a sending queue and retries guarantee.
4. Explain which settings of the Doris exporter apply only when it creates a table.
5. Judge what a successful export call shows and what only a query in Doris shows.
6. Find the evidence of one request in each signal, and tell which services send which signals.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 2.1 A Collector is a set of pipelines | 5 min | Read a Collector configuration |
| 2.2 Getting telemetry in | 6 min | Push, pull, and file receivers |
| 2.3 Processing on the way | 4 min | Name the source, batch the records |
| 2.4 Loading into Doris | 7 min | What the exporter does with a batch, and with the tables |
| 2.5 From OTLP fields to columns | 4 min | Where each part of a record ends up |
| 2.6 What proves that a record arrived | 2 min | Export calls versus rows in Doris |
| 2.7 One failed order, three signals | 2 min | Which services send which signals |
| Lab 2 | 30 min | Three pipelines of your own, and one failed order followed into Doris |
| Quiz 2 | 10 min | Six questions on these objectives |

## 2.1 A Collector is a set of pipelines

In Module 1, the telemetry of the demo passed through two Collectors before it reached Doris. In this module you configure Collectors yourself. A Collector's configuration is a YAML file with five parts:

| Part | What it declares |
| --- | --- |
| `receivers` | How data comes in: listening for OTLP, scraping a URL, or reading files |
| `processors` | What happens to the data on the way: adding attributes, filtering, batching |
| `exporters` | Where the data goes: here, the Doris exporter |
| `extensions` | Helpers that are not on the data path, such as health checks or storage for state |
| `service` | Which of the declared parts run, and how they connect into **pipelines** |

A component that is declared but not used in a pipeline does nothing. A pipeline belongs to one signal, `logs`, `metrics`, or `traces`; data flows from its receivers through its processors, in the order listed, to its exporters. This is the log collector of Lab 2, shortened:

```yaml
extensions:
  file_storage:
    directory: /var/lib/otelcol/file_storage

receivers:
  filelog:
    include: [ /var/log/doris-fe/fe.log ]
    start_at: beginning
    storage: file_storage

processors:
  resource:
    attributes:
      - key: service.name
        value: doris-fe
        action: upsert
  batch:
    send_batch_size: 10000
    timeout: 2s

exporters:
  doris:
    endpoint: http://doris-obs:8040
    database: otel
    table:
      logs: otel_logs
    create_schema: false

service:
  extensions: [file_storage]
  pipelines:
    logs:
      receivers: [filelog]
      processors: [resource, batch]
      exporters: [doris]
```

The Collector of the DOG stack works the same way, with three pipelines that receive OTLP and export to Doris. Each pipeline is separate: a broken log pipeline does not stop the traces, and a working trace pipeline says nothing about the logs.

## 2.2 Getting telemetry in

A receiver either waits for data or fetches it.

**Push: the `otlp` receiver.** Services that use an OpenTelemetry SDK send their telemetry to the Collector over OTLP, on port 4317 (gRPC) or 4318 (HTTP). The receiver listens and accepts whatever arrives, so the SDK decides when to send. A receiver is only useful if senders can reach it: Lab 2's trace collector publishes its port 4318 on your computer as 127.0.0.1:24328, so that the Python code in the notebook can send to it. A receiver on a port that nothing can reach receives nothing, which is why Lab 2's metric collector has no OTLP receiver.

**Pull: the `prometheus` receiver.** Many programs publish their metrics as Prometheus text at an HTTP path, usually `/metrics`, and wait to be asked. The Doris FE (port 8030) and BE (port 8040) do. The receiver **scrapes** each target at a fixed interval, 15 seconds in Lab 2, and turns each sample into an OpenTelemetry data point. It names the series after the scrape job, `doris_cluster`, which becomes the `service_name`, and the target, which becomes the `service_instance_id`. When a target is down, the scrape fails and no points arrive for it; the program being measured does not notice.

**Files: the `filelog` receiver.** Programs that only write log files, as the Doris FE does with `fe.log`, need a receiver that reads the files. The filelog receiver follows the files that match `include`, joins the lines of a multi-line record (a Java stack trace, for example) by the pattern of a record's first line, and parses each record with operators, such as a regular expression that extracts the time and the severity. Two details matter in practice:

- **Rotation.** The FE renames `fe.log` when it gets large and starts a new `fe.log`. Lab 2 mounts the log *directory* into the collector's container, so the receiver sees the new file. A mount of the single file would keep pointing at the renamed old file.
- **Read position.** `start_at: beginning` reads a new file from its first line. Without storage, a restarted receiver does not know what it already read and loads the whole file again, which duplicates every row in Doris. The `file_storage` extension saves the position of each file, so a restart continues where the last run stopped.

## 2.3 Processing on the way

Processors run in the order that the pipeline lists them.

- The **`resource`** processor sets resource attributes, which describe the source of the data. A log file does not say which service wrote it, so the log collector sets `service.name` to `doris-fe`; the trace collector adds `deployment.environment.name`, which Lab 2 then finds on its span in Doris.
- The **`batch`** processor groups records before they are exported, because one load of 10,000 rows costs far less than 10,000 loads of one row. It sends a batch when it reaches `send_batch_size` records or when `timeout` has passed since the batch started, whichever comes first. With `timeout: 10s`, a single span waits up to 10 seconds before the collector exports it; under heavy load, batches fill and leave at once.
- The DOG Collector also uses a **`memory_limiter`**, which refuses data when the Collector runs short of memory, and a **`transform`** processor, which gives log records without a timestamp the time at which the Collector observed them.

## 2.4 Loading into Doris

The Doris exporter turns each batch into JSON lines and loads them into one table with a **Stream Load**: an HTTP `PUT` to `<endpoint>/api/<database>/<table>/_stream_load`. Doris parses the rows and writes them in one transaction, and its response says how many rows it loaded and how many it filtered out as invalid. `endpoint` is the BE's HTTP port, 8040, because the course's containers cannot follow a redirect from the FE to the address at which this single-container Doris registers its BE. The exporter writes the timestamps in the time zone of `timezone`, which is UTC in every Collector of this course.

When Doris or the network fails, two settings decide what happens to the data:

- **`sending_queue`** keeps batches in the Collector's memory while they wait to be exported, up to `queue_size` batches, with `num_consumers` exports in parallel. When the queue is full, the exporter refuses new data, which is lost unless its sender tries again.
- **`retry_on_failure`** retries a failed export after `initial_interval`, then after longer and longer waits up to `max_interval`, and gives up after `max_elapsed_time`.

Together they ride out a short outage. They do not make the pipeline durable: the queue lives in memory, so a crash or a restart of the Collector loses what is in it, and a long outage ends in dropped data once the retries give up or the queue fills.

### Creating the tables

With `create_schema: true`, the exporter connects to the FE's MySQL port (`mysql_endpoint`) when it starts, creates the database, and runs `CREATE TABLE IF NOT EXISTS` for the tables of its pipelines. These settings shape the tables it creates:

| Exporter setting | Table property it sets |
| --- | --- |
| `history_days: 7` | `dynamic_partition.start = -7`: daily partitions older than 7 days are dropped |
| `create_history_days: 3` | `dynamic_partition.history_partition_num = 3`: partitions for 3 past days are created with the table |
| `replication_num: 1` | One replica of each tablet, as a single BE requires |

They apply **only when the exporter creates a table**. `IF NOT EXISTS` leaves an existing table as it is, whatever the settings say now. In this course, the DOG Collector creates every table when Module 1 starts it, with the settings above, so Lab 2's collectors set `create_schema: false`: their tables exist, and they only load rows. Lab 2 shows the tables' partitioning with `SHOW DYNAMIC PARTITION TABLES FROM otel`.

The exporter creates more than the tables of the signals. For traces, it also creates `otel_traces_graph`, the calls between services per minute, and a Doris job, `otel_traces_graph_job`, that fills it every 10 minutes from the spans of the previous 10 minutes. Spans reach Doris a few seconds after they end, so a run can miss the last spans of the minute before it; the next run does not count that minute again, and it stays too low. Every Collector that starts with `create_schema: true` and a trace pipeline drops and creates the job again, which delays its next run by 10 minutes. The exporter also tries to create a materialized view on each table, `<table>_services`. Doris 4.1.3 rejects its statement with `Duplicate column name 'service_name'`; the exporter logs a warning, `failed to create materialized view`, and carries on. The loads are not affected.

## 2.5 From OTLP fields to columns

The exporter maps the parts of each OTLP record to columns. For a log record:

| OTLP | Column of `otel_logs` |
| --- | --- |
| The time of the record | `timestamp`, a `DATETIME(6)` in UTC |
| Resource attribute `service.name` | `service_name` |
| Resource attribute `service.instance.id` | `service_instance_id` |
| Trace ID and span ID | `trace_id`, `span_id`, as hexadecimal text |
| Severity number and text | `severity_number`, `severity_text` |
| Body | `body` |
| All resource attributes, all attributes of the record | `resource_attributes`, `log_attributes` |
| Name and version of the instrumentation scope | `scope_name`, `scope_version` |

Spans map the same way to `otel_traces`, with `span_name`, `span_kind`, `parent_span_id`, `end_time`, `duration` (in microseconds), `status_code`, `status_message`, `span_attributes`, and `events`. Metrics go to one table per type: `otel_metrics_gauge`, `otel_metrics_sum`, `otel_metrics_histogram`, `otel_metrics_exponential_histogram`, and `otel_metrics_summary`, each with `metric_name`, `attributes`, and the value columns of its type.

The attribute columns are of type `VARIANT`: Doris stores each key that appears in them as a column of its own, typed by its values, so that a query on one key reads only that key. A key with dots, such as `log.file.name`, is stored as a nested path, and `log_attributes['log.file.name']` reads it, as Lab 2 does to find the FE log's rows.

## 2.6 What proves that a record arrived

An SDK exports spans in the background. When the Python code of Lab 2 ends its span, the span waits in the SDK's `BatchSpanProcessor`; `provider.force_flush()` makes the SDK send it now and waits for the attempt. But neither a printed message nor `force_flush()` reports whether the export succeeded: when the collector cannot be reached, the SDK only logs a warning. And a collector that accepted the span has not yet loaded it into Doris; its batch and its exporter come next.

Only a query in Doris shows that the span arrived. Lab 2 looks up the span by its trace ID, with a query that reruns until the row appears, usually within 20 seconds: the collector's batch timeout is 10 seconds, and Doris makes the load visible a few seconds after it commits.

## 2.7 One failed order, three signals

A failed order of the incident leaves evidence in all three signals, but not in every service:

| Signal | Evidence of one failed order | Where it comes from |
| --- | --- | --- |
| Traces, `otel_traces` | 25 to 40 spans in about ten services, with error spans in `payment` and in the services that called it | The SDK of each service |
| Logs, `otel_logs` | The storefront proxy's access log line, `"POST /api/checkout HTTP/1.1" 500`, with no severity; `INFO` lines of services such as `cart` and `currency` | The services that send logs |
| Metrics, `otel_metrics_sum` | The span metric `traces.span.metrics.calls`, which counts failed and successful charges, but no single order | The demo Collector's span metrics |

Not every service sends every signal. In the demo, `checkout`, `payment`, `frontend`, `product-catalog`, `shipping`, and `email` send traces but no logs: they write their logs only to their containers' output, where `docker logs doris-obs-demo-payment` shows the payment error. So the failure leaves no error log in Doris, and a search for errors by severity misses it, while the trace has it. Knowing which source sends which signal is part of reading telemetry: a missing row can mean that nothing happened, or that nothing was sent.

## Lab 2: Ingest Observability Data into DOG

Open [Lab 2: Ingest Observability Data into DOG with OpenTelemetry](lab02_ingest_observability_data.ipynb). You:

1. Start a log collector that reads the FE log, check its rows in Doris, and see where the table's settings come from.
2. Start a metric collector that scrapes the FE and the BE, and check its data points.
3. Start a trace collector, send it a span from Python, and find the span in Doris; then change the collector's configuration and see the change on a new span.
4. Follow one failed order into `otel_traces`, `otel_logs`, and `otel_metrics_sum`.
5. Practice: count the checkout requests in the access log by HTTP status.

You need the DOG stack and the demo from Module 1, with the payment failure turned on.

## Summary

- A Collector's pipelines connect receivers, processors, and exporters, one pipeline per signal; extensions, such as storage for the read position, sit beside them.
- An OTLP receiver waits for pushed data and must be reachable; a Prometheus receiver pulls metrics on an interval; a filelog receiver reads files, follows rotation when it can see the directory, and needs storage to remember its position.
- A batch processor sends when its batch is full or its timeout passes. A sending queue and retries survive short outages but keep data in memory, so they are not durable.
- The Doris exporter loads each batch with a Stream Load. Its table settings, such as `history_days`, apply only when it creates a table; existing tables keep theirs.
- A print statement or a flush does not prove that a span reached Doris; a query that finds it does.
- A failed order leaves spans in every service on its path, an access log line without severity, and counts in a span metric. The services that send no logs leave no error log.

## Quiz 2

Open [Quiz 2: Ingesting Observability Data](quiz02_ingesting_observability_data.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 3: Visualizing Observability Data](../module03-data-visualization/course.md).

## References

- [OpenTelemetry Collector: configuration](https://opentelemetry.io/docs/collector/configuration/)
- [OpenTelemetry Protocol (OTLP)](https://opentelemetry.io/docs/specs/otlp/)
- [Filelog receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.144.0/receiver/filelogreceiver), [Prometheus receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.144.0/receiver/prometheusreceiver), [File storage extension](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.144.0/extension/storage/filestorage)
- [Batch processor](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/batchprocessor) and [exporter queue and retry settings](https://github.com/open-telemetry/opentelemetry-collector/blob/main/exporter/exporterhelper/README.md)
- [Doris exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.144.0/exporter/dorisexporter)
- [Apache Doris: Stream Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/), [VARIANT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/VARIANT/), and [dynamic partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning/)
