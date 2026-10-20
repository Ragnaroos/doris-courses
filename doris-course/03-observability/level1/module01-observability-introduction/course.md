# Module 1: Observability Foundations in the DOG Stack

| Course information | Value |
| --- | --- |
| Course | Observability with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | The DOG stack (Doris, the OpenTelemetry Collector 0.144.0, and Grafana 11.4.0) and the OpenTelemetry demo 2.0.2 |
| Estimated time | About 70 minutes: reading 25, Lab 35 (plus the first download of about 4.8 GB of images), quiz 10 |

[Course README](../../README.md) · [Open Lab 1](lab01_observability_introduction.ipynb) · [Open Quiz 1](quiz01_observability_foundations.ipynb)

## Module goal

Start an observability stack and the online store that it watches, check that the store's logs, metrics, and traces reach Doris, and start the incident that the rest of the course investigates.

## Learning objectives

After completing this module, you will be able to:

1. Choose logs, metrics, or traces for an operational question.
2. Explain how the trace ID and the parent span ID join the spans of one request.
3. Assign collection, storage, and visualization to the parts of the DOG stack.
4. Trace the path that the demo's telemetry takes from a service to a table in Doris.
5. Judge what evidence shows that telemetry reached Doris.
6. Start a failure with a feature flag and confirm it in the telemetry.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 1.1 What observability is for | 3 min | The questions that telemetry answers |
| 1.2 Three kinds of telemetry | 6 min | Logs, metrics, and traces, and when to use each |
| 1.3 Inside a trace | 5 min | The fields of a span, and how spans form a request |
| 1.4 The DOG stack and the demo | 5 min | Who collects, stores, and shows the telemetry, and the path it takes |
| 1.5 Evidence that telemetry arrived | 3 min | What a running container proves, and what a row in Doris proves |
| 1.6 The incident of this course | 3 min | A feature flag that makes payments fail |
| Lab 1 | 35 min | A running stack and store, and the first failed orders in Doris |
| Quiz 1 | 10 min | Six questions on these objectives |

## 1.1 What observability is for

An online store has many services: one shows products, one keeps the cart, one takes payments. When customers report that "checkout is broken", the engineer on call has to answer questions such as: Is it broken for everyone or for some customers? Since when? Which service fails, and why? What changed?

The engineer cannot attach a debugger to production or ask every service to explain itself. They can only read what the services recorded while they ran: their **telemetry**. A system is *observable* when its telemetry answers such questions, including new ones that nobody thought of when the services were written. This course builds that ability with three open tools, the OpenTelemetry Collector, Apache Doris, and Grafana, and uses them on a real store that you run on your computer.

## 1.2 Three kinds of telemetry

Services record three kinds of telemetry, called **signals**. Each answers a different kind of question.

| Signal | What one record is | Questions it answers | Example from the store |
| --- | --- | --- | --- |
| **Logs** | A timestamped text event, with a severity and attributes | What exactly happened here, at this moment? | The storefront proxy's line `"POST /api/checkout HTTP/1.1" 500` |
| **Metrics** | A number measured at a time, for a named measure and a set of attributes | How much, how often, and how does it change over time? | The share of time that one CPU core of the host was idle |
| **Traces** | One request's path through the services, as a tree of spans | Where did this request go, how long did each step take, and which step failed? | An order that went from the proxy to the frontend, checkout, and payment |

The signals complement each other:

- **Metrics** are the cheapest to keep and to query over long periods: a measure produces a few numbers per interval, however many requests there were. They show trends and percentiles, and they drive alerts. They do not tell you which request failed.
- **Logs** keep the detail of single events, in whatever words the developer chose. They are the place for error messages and stack traces, but only if the service writes them, and their format differs from service to service.
- **Traces** follow one request across services. They show where time was spent and where an error started, which neither a log line nor a metric can do on its own.

An investigation usually moves between them: a metric shows that something changed, a log or a trace shows a request where it happened, and the trace shows which service caused it. Module 3 makes this move in Grafana.

### Severity, and the OpenTelemetry scale

Each log record has two severity fields. `severity_text` is the label that the source wrote, such as `ERROR`, `Error`, or `WARN`; it differs between programming languages and libraries. `severity_number` puts every source on the same OpenTelemetry scale: 1 to 4 is TRACE, 5 to 8 DEBUG, 9 to 12 INFO, 13 to 16 WARN, 17 to 20 ERROR, and 21 to 24 FATAL. A record without a severity, such as an access log line, has `severity_number` 0.

### Kinds of metrics

A metric has a type, which says how to read its numbers. A **gauge** is a value at a moment, such as a CPU share or a queue length. A **sum**, or counter, adds up events, such as requests served; it usually only grows, from a start time. A **histogram** counts the measurements that fell into each of several buckets, such as request durations. Doris keeps each type in its own table, because their columns differ.

## 1.3 Inside a trace

A trace is made of **spans**. A span is one unit of work: a request that a service received, a call that it made to another service, or a step inside it. Every span records:

| Field | Meaning |
| --- | --- |
| `trace_id` | The ID of the request. Every span of the request has the same trace ID. |
| `span_id` | The ID of this span. |
| `parent_span_id` | The ID of the span that started this one. The first span of a request, the **root span**, has none. |
| `span_name` | The operation, such as `oteldemo.CheckoutService/PlaceOrder` |
| `span_kind` | `SERVER` for a request that the service received, `CLIENT` for a call it made, `INTERNAL` for a step inside it, `PRODUCER` and `CONSUMER` for messages |
| `timestamp`, `end_time`, `duration` | When it started and ended, and how long it took |
| `status_code` | `STATUS_CODE_ERROR` when the operation failed; otherwise `STATUS_CODE_OK` or, most often, `STATUS_CODE_UNSET` |
| `span_attributes`, `events` | Details, such as the HTTP status code, and timestamped events within the span, such as an exception |
| `resource_attributes` | What produced the span: the service's name (`service.name`, also stored as `service_name`), its version, its host |

The trace ID and the parent span ID join the spans into a tree. When checkout calls payment, checkout's SDK records a `CLIENT` span for the call and passes the trace ID and the span's ID along with the request, in an HTTP or gRPC header (the W3C `traceparent` header). Payment's SDK records its `SERVER` span with the same trace ID, and with checkout's client span as its parent. This passing of IDs from service to service is called **context propagation**. Because of it, the spans that ten services write separately can be put back together into one request.

Logs can join in too. An OpenTelemetry SDK stamps each log record with the trace ID and span ID of the request that the service was working on. A log line and the spans of its request then share a trace ID, so either one leads to the other.

## 1.4 The DOG stack and the demo

This course uses the **DOG stack**: **D**oris, the OpenTelemetry Collector, and **G**rafana, from the open-source [ai-observe-stack](https://github.com/ai-observe/ai-observe-stack) project. Each part has one job:

| Part | Its job | What it does not do |
| --- | --- | --- |
| **OpenTelemetry Collector** | Receives telemetry, processes it (adds attributes, batches it), and exports it, here to Doris | Store telemetry or draw charts |
| **Apache Doris** | Stores the telemetry in tables and answers SQL queries over it, also across signals | Collect telemetry from the services |
| **Grafana** | Shows the telemetry: searches, traces, dashboards, and alerts. It reads Doris with SQL | Store telemetry |

Doris is an analytical database: it stores data by column, compresses it, and runs queries on many cores in parallel. The DOG stack uses it as the single store for all three signals, so one SQL query can join logs and traces by trace ID, and full-text indexes make log search fast. Level 2 of this course looks at how Doris does that.

**OpenTelemetry** is the open standard behind the telemetry: an API and SDKs that services use to record logs, metrics, and spans; a protocol, **OTLP**, to send them; and the **Collector**. The Collector is built from **pipelines**, one per signal, each with receivers that take data in, processors that change it, and exporters that send it on. Module 2 builds Collectors of its own.

The system under observation is the [OpenTelemetry demo](https://opentelemetry.io/docs/demo/), the Astronomy Shop: an online store of telescopes made of more than a dozen services written in Go, Java, .NET, Node.js, Python, PHP, Ruby, Rust, and C++. Each service uses the OpenTelemetry SDK of its language. A **load generator** keeps browsing the store and placing orders, so the services keep producing telemetry while you work.

![On your computer, a browser opens the storefront and its flag page on port 28082 and Grafana on port 23000, and the Jupyter notebooks send SQL to Doris on port 29030. In the OpenTelemetry demo, requests pass through the storefront proxy to services that use the OpenTelemetry SDK; flagd serves their feature flags. The services send spans, logs, and metrics over OTLP to the demo's Collector, which adds span, host, and container metrics and forwards everything over OTLP to the DOG Collector. The DOG Collector adds the Docker host's metrics, and its Doris exporter loads the rows into the otel database of Doris with Stream Load. Grafana reads them from Doris with SQL.](images/dog-data-path.svg)

The path of the store's telemetry:

1. A service's SDK sends its spans, logs, and metrics over OTLP to the **demo's Collector**.
2. The demo's Collector adds metrics of its own: **span metrics**, which count the spans of each service and operation, and the metrics of the hosts and containers. It forwards everything over OTLP to the **DOG Collector**.
3. The DOG Collector adds the metrics of the Docker host that it runs on. Its **Doris exporter** loads the rows into Doris over HTTP, with a **Stream Load**, a few seconds after they arrive.
4. Doris keeps them in the database `otel`: spans in `otel_traces`, logs in `otel_logs`, and metrics in one table per type, such as `otel_metrics_gauge` and `otel_metrics_sum`. The exporter created these tables when it started.
5. Grafana reads the tables with SQL. Its **Doris App** plugin has a **Discover** page for searching rows and a **Traces** page for traces, and Grafana's own dashboards and alerts read Doris through the same data source.

The stack also runs Mailpit, a local mail server that receives Grafana's alert emails in Module 8. Every part runs in Docker on your computer, on ports from 23000 to 29030 that bind to 127.0.0.1; the [course README](../../README.md) lists them.

## 1.5 Evidence that telemetry arrived

Each step of the path can fail on its own: a service can lose its connection to the demo's Collector, the demo's Collector can fail to reach the DOG Collector, or the exporter can fail to load a batch into Doris. Each signal also has its own pipeline, so traces can arrive while logs do not. Running containers prove that the processes started, not that any telemetry passed through them.

The evidence that telemetry arrived is **rows in Doris**: recent rows, with timestamps close to the current time, in the table of each signal. Lab 1 checks exactly that: for each signal, it counts the rows of the last five minutes and the services that sent them. A Grafana page that shows the rows is the same evidence, seen through one more step.

The telemetry's timestamps are in UTC. The exporter writes UTC, and the tables split their data into one partition per UTC day, so the Lab compares timestamps with `UTC_TIMESTAMP()`, not with the local time of your computer.

## 1.6 The incident of this course

The demo can switch failure scenarios on and off with **feature flags**. A feature flag is a setting that a service reads at run time, here from the demo's flag service, **flagd**: when the flag changes, the service changes its behavior without a restart. The demo's flag page, at `/feature` on the storefront's port, shows each flag with its possible values.

This course follows one scenario: the flag `paymentFailure`. At `50%`, the payment service rejects about half of the charge requests that it receives, so about half of the store's orders fail. A customer whose payment fails stays on the cart page, with no message. At the end of Lab 1 you turn the flag on and see the first failed orders in Doris: the checkout service's span for each order, `oteldemo.CheckoutService/PlaceOrder`, has the status `STATUS_CODE_ERROR`.

From then on, the course investigates the failure as if you did not know its cause:

| Module | Its part in the investigation |
| --- | --- |
| 1 | The failure starts, and failed orders appear in the traces. |
| 2 | Find which tables hold the evidence of a failed order, and which pipeline brought each piece. |
| 3 | Find where the failure starts and why, in Grafana, and rule out the host's CPU. |
| 4–8 | Keep compact summaries, make the searches faster with Doris's table design and indexes, measure the failure with SQL, and alert on it. |

The flag stays on until you turn it off in the flag page, or until `lab.teardown()` removes the course's environment.

## Lab 1: Start the DOG Stack

Open [Lab 1: Start the DOG Stack](lab01_observability_introduction.ipynb) and run its cells in order. You:

1. Start the DOG stack: Doris, the DOG Collector, Grafana, and Mailpit.
2. Start the OpenTelemetry demo and check that traces, logs, and metrics from the last five minutes are in Doris.
3. Open the storefront and Grafana.
4. Turn on `paymentFailure` at 50% in the flag page, confirm the flag, and wait for the first failed order in Doris.
5. Practice: count the error spans of the last ten minutes by service.

You need Docker with at least 10 GB of memory and the course's Python environment; the [course README](../../README.md) describes both. The first run downloads about 4.8 GB of images, which takes a few minutes more.

## Summary

- Logs record single events, metrics measure quantities over time, and traces follow a request through the services; an investigation moves between them.
- A span records one unit of work. The trace ID, shared by every span of a request, and the parent span ID join the spans into a tree, across services, through context propagation.
- In the DOG stack, the OpenTelemetry Collector collects, Doris stores and queries, and Grafana shows the telemetry.
- The demo's services send their telemetry to the demo's Collector, which forwards it to the DOG Collector, whose Doris exporter loads it into one table per signal in the database `otel`.
- Running containers do not prove that telemetry arrived; recent rows in Doris do.
- The feature flag `paymentFailure` makes half of the payments fail, and the failed orders show up as checkout spans with an error status.

## Quiz 1

Open [Quiz 1: Observability Foundations in the DOG Stack](quiz01_observability_foundations.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 2: Ingesting Observability Data](../module02-data-ingest/course.md).

## References

- [OpenTelemetry: Observability primer](https://opentelemetry.io/docs/concepts/observability-primer/)
- [OpenTelemetry: Signals](https://opentelemetry.io/docs/concepts/signals/), including [traces](https://opentelemetry.io/docs/concepts/signals/traces/), [metrics](https://opentelemetry.io/docs/concepts/signals/metrics/), and [logs](https://opentelemetry.io/docs/concepts/signals/logs/)
- [OpenTelemetry: Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/)
- [OpenTelemetry logs data model: severity fields](https://opentelemetry.io/docs/specs/otel/logs/data-model/#field-severitynumber)
- [OpenTelemetry demo documentation](https://opentelemetry.io/docs/demo/) and its [feature flags](https://opentelemetry.io/docs/demo/feature-flags/)
- [Apache Doris: Observability overview](https://doris.apache.org/docs/4.x/observability/overview/)
- [ai-observe-stack (the DOG stack)](https://github.com/ai-observe/ai-observe-stack)
