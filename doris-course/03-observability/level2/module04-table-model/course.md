# Module 4: Table Models for Observability Data

| Course information | Value |
| --- | --- |
| Course | Observability with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Environment | The DOG stack and the OpenTelemetry demo of Module 1, with the payment failure turned on |
| Estimated time | About 70 minutes: reading 25, Lab 35, quiz 10 |

[Course README](../../README.md) · [Open Lab 4](lab04_table_models.ipynb) · [Open Quiz 4](quiz04_observability_table_models.ipynb)

## Module goal

Keep the evidence of the payment incident in compact tables, and choose for each table the model that decides what Doris does with rows that share a key.

## Learning objectives

After completing this module, you will be able to:

1. Choose DUPLICATE, AGGREGATE, or UNIQUE from what must happen to rows that share a key.
2. Explain why raw logs, spans, and metric points belong in DUPLICATE tables.
3. Choose the key of an AGGREGATE table at the grain of the questions that it answers.
4. Predict the rows of an AGGREGATE table after overlapping or repeated loads.
5. Build an alert identity that stays the same for every occurrence of an error.
6. Predict which row a UNIQUE table keeps, and what one row says about occurrences.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 4.1 Keys and models | 4 min | What the key clause of a table decides |
| 4.2 DUPLICATE: keep every event | 4 min | Why raw telemetry keeps every row |
| 4.3 AGGREGATE: keep the counts | 6 min | A summary at the grain of its questions |
| 4.4 UNIQUE: keep the current state | 6 min | One row per alert, and what it means |
| 4.5 The exporter's UNIQUE table | 2 min | A job that may count the same minute twice |
| 4.6 Choosing a model | 3 min | Matching the model to the question |
| Lab 4 | 35 min | A summary of the incident per minute, and one alert per kind of error |
| Quiz 4 | 10 min | Six questions on these objectives |

## 4.1 Keys and models

Since Module 1, about half of the store's orders fail. While an incident lasts, and long after it, people ask the same questions: how many requests each service handled each minute, and how many failed; which kinds of errors occurred, and which are still open. Answering them from the raw spans means reading every span of the period on every refresh of a dashboard. A table that keeps the answers instead is smaller and faster, if Doris knows what to do with rows that describe the same thing.

That is what the **data model** of a table says. Every Doris table has a key, set by the key clause of `CREATE TABLE`: one or more columns at the start of the table. The model decides what happens to rows that have the same values in all key columns:

| Model | Rows with the same key | Typical use |
| --- | --- | --- |
| `DUPLICATE KEY` | All are kept. The key only sets the order in which rows are stored. | Raw logs, spans, and metric points |
| `AGGREGATE KEY` | Combined into one row. Each value column names the function that combines it, such as `SUM`. | Counts and totals per period, kept ahead of time |
| `UNIQUE KEY` | Only one row is kept, the one loaded last. | The current state of something, such as an alert |

The model is fixed when the table is created. Doris stores the rows of each tablet sorted by the key, which also helps queries that filter on the first key columns.

## 4.2 DUPLICATE: keep every event

A log line, a span, and a metric point are each a separate event. Two spans of the same service can start in the same millisecond: the frontend, whose SDK records milliseconds, starts several spans for one request at once, and Lab 4 finds keys that ten or more spans share. They are different events, with different span IDs, and a table that kept one row per key would lose all but one of them.

The Doris exporter therefore creates its tables of raw telemetry, `otel_logs`, `otel_traces`, and the five `otel_metrics_*` tables, with `DUPLICATE KEY`, on the time and the service. Doris keeps every row that it loads, and the key only orders the rows, so that a query for one service over a time range reads them close together. A table created without a key clause is a DUPLICATE table too.

DUPLICATE keeps exact copies as well. If the same data is loaded twice, every row is there twice, and every count doubles. Nothing in the table protects it from a repeated load; the loader must avoid it. That is why the log collector of Module 2 saves its read position: without it, a restart would load the whole FE log again.

## 4.3 AGGREGATE: keep the counts

A summary of the incident needs one row per service and minute, with the number of requests and the number that failed. In an AGGREGATE table, the key holds the **grain** of the summary, and every other column declares how Doris combines values of rows with the same key:

```sql
CREATE TABLE IF NOT EXISTS requests_per_minute (
    request_minute  DATETIME,
    service_name    VARCHAR(200),
    requests        BIGINT SUM,
    failed_requests BIGINT SUM
)
AGGREGATE KEY(request_minute, service_name)
DISTRIBUTED BY HASH(service_name) BUCKETS 1
```

A load job adds one row per server span, with `requests = 1` and `failed_requests = 1` or `0`. When a row arrives whose key the table already has, `SUM` adds its values to the existing row. Doris combines rows while it loads them, merges what is left in the background (compaction), and combines anything that remains when a query reads the table, so a query always sees one row per key. Besides `SUM`, a value column can declare `MAX`, `MIN`, `REPLACE` (the value loaded last), `REPLACE_IF_NOT_NULL`, and functions for approximate distinct counts such as `HLL_UNION` and `BITMAP_UNION`.

**The key is the grain.** The key holds the minute, `DATE_TRUNC(end_time, 'minute')`, not the time of each span. With the span's time in the key, only spans from the same microsecond would be combined, and the table would be almost as large as `otel_traces`. In the other direction, the table answers only questions at its grain or coarser: it can add up minutes into hours, but it cannot say which requests failed, or how long they took. Choose the grain from the questions, and keep the raw table for the rest.

**Count each event once, in the right bucket.** A span's `timestamp` is when it started, but the span reaches Doris only after it ends. A request that takes long, such as one of `flagd`'s flag streams, which stay open for up to 10 minutes, would arrive long after its starting minute had been summarized. The summary therefore counts each request in the minute in which it ended. The same reasoning applies to any summary loaded on a schedule: load each period only after its data has arrived.

**Load each source row exactly once.** An AGGREGATE table cannot tell a new row from a repeated one. When two loads overlap, or one runs twice, the counts of the repeated rows are added twice, and the table is wrong without any error. Lab 4 loads its summary in two batches that meet at a moment inside a minute: the second batch adds to the rows of that minute, loads of 4 and then 7 for one key leave 11, and a join against `otel_traces` checks that every count matches.

## 4.4 UNIQUE: keep the current state

Every failed order leaves error spans in several services: the payment service, the checkout service, the frontend, the proxy, and the load generator. An alerting job that raised an alert for each error span would send several alerts a minute about one problem. What the on-call engineer needs is one alert per kind of error, with its current status.

A UNIQUE table keeps one row per key. With the day and an **alert identity** as the key, each kind of error has one row per day, however often it occurs:

```sql
CREATE TABLE IF NOT EXISTS error_alerts (
    alert_date   DATE,
    alert_hash   VARCHAR(32),
    service_name VARCHAR(200),
    span_name    STRING,
    status       VARCHAR(16),
    message      STRING
)
UNIQUE KEY(alert_date, alert_hash)
DISTRIBUTED BY HASH(alert_hash) BUCKETS 1
```

A UNIQUE table must be distributed by a hash of key columns, so that all rows with one key reach the same tablet. In Doris 4.x, UNIQUE tables are **Merge-on-Write** (MoW) by default: when a row arrives whose key exists, Doris marks the old row as deleted while it writes the new one, so queries read only the current row without merging at query time.

**A stable identity.** The identity must be the same for every occurrence of a kind of error and differ between kinds. Lab 4 builds it from the service, the operation (`span_name`), and the status message of the error span, hashed with `MD5`. Messages often contain parts that change with every occurrence: times, addresses, ports, and IDs. Replacing every number with `0` before hashing makes `connect ECONNREFUSED 169.254.169.254:80` and the same message with another address one kind of error. The recommendation service's flag stream, for example, ends with `DEADLINE_EXCEEDED` every 10 minutes, with a message that contains the time: without the replacement, each occurrence would be a new alert.

**The row loaded last wins.** Loading the same error spans again leaves the table unchanged, so the alerting job can run every minute without creating duplicates. To resolve an alert, the job writes its row again with `status = 'resolved'`; a later load of the same key replaces it again. Loads that can arrive out of order need a **sequence column**: with `"function_column.sequence_col" = "last_seen"`, Doris keeps the row with the largest `last_seen`, whatever the load order, so an old open row loaded late cannot overwrite a newer resolved one.

**One row is not one occurrence.** The alert of the payment service's charge has one row in `error_alerts` and one error span per failed order in `otel_traces`. A UNIQUE table keeps the current state, not a count. To know how often an error occurred, count its spans, or keep the count in an AGGREGATE table.

## 4.5 The exporter's UNIQUE table

The exporter creates one table that is not raw telemetry: `otel_traces_graph`, the calls from service to service per minute, with `count` and `error_count`. A job that the exporter also creates, `otel_traces_graph_job`, fills it every 10 minutes from the spans of the last 10 minutes. Each run therefore counts again the minute in which the previous run started, which the previous run saw only in part, and writes rows with the same keys. Because the table is UNIQUE, the new, complete count replaces the old, partial one. With `SUM`, the two counts would be added; with DUPLICATE, the minute would appear twice. A UNIQUE table makes a recomputation safe to repeat, which is why jobs that recompute a recent window use it.

The incident shows in this table too: the calls from `checkout` to `payment` have an `error_count` of about half their `count` since the flag was turned on.

## 4.6 Choosing a model

Ask what must happen to two rows with the same key:

| If two rows with the same key... | Model | In this course |
| --- | --- | --- |
| are two different events that both matter | DUPLICATE | `otel_logs`, `otel_traces`, the metrics tables |
| are parts of one total, to be combined | AGGREGATE, with `SUM`, `MAX`, `MIN`, ... | `requests_per_minute`, `daily_log_counts` |
| are versions of one thing, the latest wins | UNIQUE, with a sequence column if loads can arrive out of order | `error_alerts`, `otel_traces_graph` |

Each choice has a price. A DUPLICATE table is the largest and keeps every detail. An AGGREGATE table is small and fast but answers only questions at its grain, and its loads must not overlap. A UNIQUE table costs a lookup of the key on every load, and it keeps only the latest version of each row.

## Lab 4: Table Models for Observability Data

Open [Lab 4: Table Models for Observability Data](lab04_table_models.ipynb). You:

1. Check that orders are failing.
2. List the models of the exporter's tables, and find spans that share a key.
3. Build `requests_per_minute`, load it in two batches, check it against `otel_traces`, and read the incident's orders and charges from it.
4. Build `error_alerts` from the error spans, load it twice, and resolve an alert.
5. Look at the exporter's `otel_traces_graph` and the job that fills it.
6. Practice: build a daily summary of the logs, and see why the incident adds no error logs to it.

You need the DOG stack and the demo from Module 1, with the payment failure turned on.

## Summary

- The key of a table and its model decide what Doris does with rows that share a key: keep them all (DUPLICATE), combine them (AGGREGATE), or keep the last one (UNIQUE).
- Raw telemetry uses DUPLICATE: every log line, span, and metric point is an event of its own, even when several share a key. Repeated loads are kept too, so loaders must avoid them.
- An AGGREGATE table's key is its grain, such as the minute and the service; it answers questions at that grain and coarser. Count each event in the period in which it reached its final state, such as the minute in which a request ended.
- Rows with the same key combine by their functions: loads of 4 and 7 under `SUM` leave 11. A repeated or overlapping load is added again, without any error.
- An alert identity must ignore what changes between occurrences: Lab 4 hashes the service, the operation, and the message with every number replaced.
- UNIQUE keeps the row loaded last, or with a sequence column the row with the largest sequence value. One row per alert says nothing about how often the error occurred.

## Quiz 4

Open [Quiz 4: Table Models for Observability Data](quiz04_observability_table_models.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 5: Partitioning and Bucketing for Observability Data](../module05-partition-bucket/course.md).

## References

- [Apache Doris: Table model overview](https://doris.apache.org/docs/4.x/table-design/data-model/intro/), and the [Duplicate Key](https://doris.apache.org/docs/4.x/table-design/data-model/duplicate/), [Aggregate](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/), and [Unique Key](https://doris.apache.org/docs/4.x/table-design/data-model/unique/) models
- [Apache Doris: Merge-on-Write](https://doris.apache.org/docs/4.x/table-design/data-model/merge-on-write/)
- [Apache Doris: Concurrent update control for the Unique Key model, with the sequence column](https://doris.apache.org/docs/4.x/data-operate/update/unique-update-concurrent-control/)
- [Apache Doris: DATE_TRUNC](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/date-time-functions/date-trunc/)
- [Doris exporter of the OpenTelemetry Collector](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/v0.144.0/exporter/dorisexporter)
