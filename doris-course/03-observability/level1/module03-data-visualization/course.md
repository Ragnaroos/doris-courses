# Module 3: Visualizing Observability Data

| Course information | Value |
| --- | --- |
| Course | Observability with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Grafana | Grafana 11.4.0 with the Doris App plugin 1.0.5 |
| Estimated time | About 85 minutes: reading 30, Lab 45, quiz 10 |

[Course README](../../README.md) · [Open Lab 3](lab03_data_visualization.ipynb) · [Open Quiz 3](quiz03_observability_visualization.ipynb)

## Module goal

Investigate the payment failures in Grafana: search the logs, follow a failed order's trace to the span where the failure starts, rule out the host's CPU, and keep the evidence on a dashboard.

## Learning objectives

After completing this module, you will be able to:

1. Search logs in the Discover page of the Doris App with Lucene and with SQL conditions.
2. Explain why a search by severity misses failures that a service does not log as errors.
3. Set a time range that matches how Doris stores time.
4. Follow a trace from a log line to the span where an error starts.
5. Measure a host's CPU from per-core, per-state samples.
6. Build dashboard panels from SQL with Grafana's time macros.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 3.1 Grafana and the Doris App | 3 min | The pages that you work in |
| 3.2 Time ranges and time zones | 4 min | A range that finds the newest rows |
| 3.3 Searching logs | 7 min | Lucene and SQL searches, and the index behind them |
| 3.4 When failures are not error logs | 3 min | What a severity search can and cannot find |
| 3.5 Reading a trace | 6 min | From a log line to the failing span |
| 3.6 Measuring a host's CPU | 4 min | Busy share from per-core samples |
| 3.7 Dashboards | 3 min | SQL panels that follow the time range |
| Lab 3 | 45 min | The incident investigated, and a dashboard of it |
| Quiz 3 | 10 min | Six questions on these objectives |

## 3.1 Grafana and the Doris App

Grafana shows data from many kinds of data sources. The DOG stack gives it one, named **Doris**, which connects to Doris over the MySQL protocol with the database `otel`; every page and panel in this module reads Doris through it, with SQL.

The **Doris App** is a Grafana plugin made for telemetry in Doris. Its pages are in Grafana's menu under **Doris App**:

| Page | What it searches | Use it to |
| --- | --- | --- |
| **Discover** | The rows of one table, such as `otel_logs` | Find log records, filter them, and see how many arrived over time |
| **Traces** | Whole traces in `otel_traces` | Find requests by their spans' attributes and duration, and open their waterfall |
| **Dashboard** | Grafana's dashboards | Keep panels of SQL queries, such as counts per minute |

Grafana in the DOG stack lets visitors view its pages without signing in, which is enough for Discover and Traces. Creating a dashboard needs an account: the stack's administrator is `admin` with the password `admin`, and Grafana asks for a new password the first time, which you may skip on this local stack.

## 3.2 Time ranges and time zones

Every search in Grafana has a time range, and observability data is about time: the newest minutes matter most during an incident. Two clocks are involved. Doris stores the telemetry's times in UTC, as the exporter writes them, and Discover shows the stored times. Your browser runs in your computer's time zone.

Grafana's own panels convert correctly: they send the range to the data source as an exact moment, and show the results in the browser's time zone. The Doris App 1.0.5, however, turns its range into text in the browser's time zone and compares that text with the UTC times in Doris. On a computer in UTC+8, **Last 15 minutes** then asks for rows stamped 8 hours in the future and finds none; west of UTC it searches the past and misses the newest rows. Only on a computer that uses UTC does a relative range work as expected.

Two consequences:

- In Discover and Traces, set an **absolute** time range in UTC: in the time picker, type the start and end times under **Absolute time range**. Lab 3 prints them for you.
- When a page shows no rows, check the range before you conclude that data is missing. An empty panel is evidence about the query, not about the data, until a query over the right period agrees.

The Traces page's waterfall shows times in the browser's time zone, so the same span can show 19:37 in Discover and 20:37 in the waterfall on a computer in UTC+1.

## 3.3 Searching logs

Discover offers two ways to write a search, set by its **Mode**.

**Lucene** is a short syntax for searching fields. The Doris App turns it into SQL:

| Lucene | Meaning | SQL that Doris runs |
| --- | --- | --- |
| `service_name:cart` | The field contains the word | `service_name MATCH_ANY 'cart'` |
| `body:"POST /api/checkout"` | The field contains these words next to each other, in this order | `body MATCH_PHRASE 'POST /api/checkout'` |
| `severity_number:>=17` | A comparison on a number | `severity_number >= 17` |
| `a AND b`, `a OR b`, `NOT a` | Combinations | The same in SQL |

**SQL** mode takes a `WHERE` condition directly, such as `severity_number >= 17 AND service_name = 'cart'`. Use it for anything that Lucene cannot say, such as functions or columns of a `VARIANT`.

Text searches are fast because the Doris exporter created `otel_logs` with an **inverted index** on `body`. When a row is loaded, the index splits its body into words, called tokens, and records which rows contain each word. The index of `body` uses the `unicode` parser and lowercases the words, so the access log line `"POST /api/checkout?currencyCode=USD HTTP/1.1" 500` becomes `post`, `api`, `checkout`, `currencycode`, `usd`, `http`, `1.1`, and `500`; punctuation is dropped. `MATCH_ANY` finds rows that contain any of the words of a search, `MATCH_ALL` rows that contain all of them, and `MATCH_PHRASE` rows that contain them next to each other, in order. Doris answers these from the index, without reading every body.

Words, not characters, are what a phrase compares, which has two effects:

- A phrase ignores punctuation and case: `POST /api/checkout` and `post api checkout` find the same rows.
- Extra words break a phrase. The storefront page sends its checkout to `/api/checkout?currencyCode=USD`, so the phrase `"POST /api/checkout HTTP/1.1 500"` misses those requests, because `currencycode` and `usd` stand between `checkout` and `http`. Two phrases joined with `AND`, `body:"POST /api/checkout" AND body:"HTTP/1.1 500"`, find both the load generator's and the page's failed checkouts.

## 3.4 When failures are not error logs

During an incident, a search for errors is the natural first step: `severity_number:>=17` finds every log record of severity ERROR or FATAL, whatever label its source used. In this incident it finds almost nothing: a few errors of the Doris FE and perhaps one of a demo service when the demo started, none about payments.

The reason is in the sources, as Module 2 showed. The payment and checkout services send no logs to a Collector, and the storefront proxy's access log, which records every failed checkout, has no severity. A search can only find what the system records, in the way that it records it. Here the evidence is an access log line with status `500`, and the search has to ask for that.

So a search that returns nothing is evidence of absence only if the data that would show the failure is collected. Before relying on a quiet error search, check which services send logs, and what their failures look like.

## 3.5 Reading a trace

Every access log line carries the trace ID of its request, so a failed checkout's line leads to its trace. Clicking a `trace_id` in Discover opens the **Trace Panel**, the trace as a waterfall:

- Each row is a span: the service in bold, the operation, and the duration. Children are indented under their parent, and the bar on the right shows when each span started and how long it took, within the request.
- A red icon marks a span with an error status. Errors pass upward: when payment fails, checkout's call to payment fails, then checkout's own span, the frontend's, the proxy's, and the load generator's. Most red rows only report an error from below.
- The **origin** of the failure is the deepest span with an error: the one whose children, if it has any, have no errors. In this incident it is the payment service's `grpc.oteldemo.PaymentService/Charge` span. Its children, such as the `charge` span, have no error.
- Clicking a row opens the span's details: its kind, its status, and its attributes. The payment span's attributes include `grpc.error_message`: `Payment request failed. Invalid token. app.loyalty.level=gold`.

The **Traces** page searches whole traces. Its **Service** and **Operation** filters select traces by their first span, the root, which for the load generator's orders is its own `POST`, not a span of checkout. **Tags** select by the attributes of any span: `http.status_code=500` finds the traces in which some span recorded HTTP status 500, which are the failed checkouts. The page shows each trace as a dot by start time and duration, and lists them with their spans and services.

## 3.6 Measuring a host's CPU

Before blaming the application, rule out the machine: an overloaded host makes many services fail at once. The DOG Collector measures the CPU of the Docker host every 15 seconds, as the metric `system.cpu.utilization` in `otel_metrics_gauge`. The Docker host is Docker Desktop's Linux virtual machine on macOS and Windows, and your computer on Linux.

The rows are fine-grained. Each one holds the share of time, between 0 and 1, that **one CPU core** spent in **one state**, such as `user`, `system`, or `idle`, since the previous measurement; `attributes` name the core and the state. On a host with 8 cores, each measurement writes 8 cores times 8 states, 64 rows. A single row says little: a core that is idle 97% of the time writes `0.97` in its `idle` row, and a filter such as `value > 0.9` finds mostly idle cores.

The share of time that the host was busy is therefore 1 minus the average `idle` share over all cores:

```sql
SELECT (1 - AVG(value)) * 100 AS busy_percent
FROM otel_metrics_gauge
WHERE metric_name = 'system.cpu.utilization'
  AND attributes['state'] = 'idle'
  AND scope_name LIKE '%hostmetricsreceiver%'
  AND resource_attributes['host.name'] IS NOT NULL
  AND timestamp >= UTC_TIMESTAMP() - INTERVAL 1 MINUTE
```

Several programs report a metric of this name, among them the demo's Collector and two Python services; the last two conditions keep the DOG Collector's measurements, which carry the host's name. In this incident the host stays 5 to 15 percent busy, before and after the failures began, so the host is not the cause. Module 8 builds an alert on this query, at 90 percent.

## 3.7 Dashboards

A dashboard keeps the queries of an investigation as panels that refresh themselves. A panel has a data source, a query, and a visualization. With the Doris data source, the query is SQL, written in the query editor's **Code** mode.

For a time series, the query returns a time column named `time` and one numeric column per series, and its **Format** is **Time series**. Grafana provides macros that adapt the SQL to the dashboard:

| Macro | Grafana replaces it with |
| --- | --- |
| `$__timeFilter(timestamp)` | A condition that keeps the rows of the dashboard's time range |
| `$__timeGroupAlias(timestamp, 1m)` | The start of each row's minute, named `time` |

Because the macros pass the range as exact moments, a dashboard's relative range, such as **Last 30 minutes**, works in any time zone, unlike the Doris App's pages. Lab 3's dashboard, `Payment incident`, has two panels: the orders per minute, split into succeeded and failed with stacked bars, and the host's CPU. Grafana saves dashboards in its own database, and any viewer can read them back through Grafana's API, which Lab 3 does to check yours.

## Lab 3: Investigate the Payment Failures in Grafana

Open [Lab 3: Investigate the Payment Failures in Grafana](lab03_data_visualization.ipynb). You:

1. Check that orders are failing, and set an absolute UTC time range in Discover.
2. Search for error logs, and see why they miss the incident.
3. Find the failed checkouts in the access log, with Lucene and with SQL.
4. Open the trace of a failed checkout and find the payment service's error; search the Traces page.
5. Rule out the host's CPU.
6. Build and save the `Payment incident` dashboard.
7. Practice: compute the share of failed charges.

You need the DOG stack and the demo from Module 1, with the payment failure turned on.

## Summary

- Discover searches the rows of one table, with Lucene or with a SQL condition; the Traces page searches whole traces; dashboards keep SQL panels.
- Doris stores UTC. The Doris App compares its range in the browser's time zone, so set absolute UTC ranges there; dashboard panels convert correctly.
- `MATCH_PHRASE` and `MATCH_ANY` use the inverted index of `body`, which splits text into lowercase words. A phrase must match the words in order, so extra words, such as a query string, break it.
- A search by severity finds only what the sources log as errors. This incident leaves no error log, only access log lines with status 500.
- In a trace, the error starts at the deepest span with an error; the spans above it only report it. Here it is the payment service's charge.
- A host's busy share is 1 minus the average idle share over its cores. The host's CPU stays low, so the cause is in the application.
- `$__timeFilter` and `$__timeGroupAlias` make a SQL panel follow the dashboard's time range.

## Quiz 3

Open [Quiz 3: Visualizing Observability Data](quiz03_observability_visualization.ipynb). It has six single-choice questions and needs no running environment.

Next: this is the last module of Level 1. Level 2 starts with [Module 4: Table Models for Observability Data](../../level2/module04-table-model/lab04_table_models.ipynb).

## References

- [Grafana: dashboards](https://grafana.com/docs/grafana/v11.4/dashboards/) and [use dashboards (time range)](https://grafana.com/docs/grafana/v11.4/dashboards/use-dashboards/)
- [Grafana: MySQL data source, query editor and macros](https://grafana.com/docs/grafana/v11.4/datasources/mysql/query-editor/)
- [Apache Doris: inverted index](https://doris.apache.org/docs/4.x/table-design/index/inverted-index/overview/) and its [search operators](https://doris.apache.org/docs/4.x/table-design/index/inverted-index/search-operators/), such as `MATCH_ANY` and `MATCH_PHRASE`
- [Apache Doris: TOKENIZE](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/string-functions/tokenize/)
- [Host metrics receiver: CPU metrics](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.144.0/receiver/hostmetricsreceiver/internal/scraper/cpuscraper/documentation.md)
