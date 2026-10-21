# Module 6: Table Properties, Materialized Views, and Indexes

| Course information | Value |
| --- | --- |
| Course | Observability with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Environment | The DOG stack and the OpenTelemetry demo of Module 1, with the payment failure turned on |
| Estimated time | About 85 minutes: reading 35, Lab 40, quiz 10 |

[Course README](../../README.md) · [Open Lab 6](lab06_properties_mv_index.ipynb) · [Open Quiz 6](quiz06_properties_mv_and_indexes.ipynb)

## Module goal

Measure what makes the incident's searches and summaries fast and its telemetry cheap to keep: the inverted index of the log messages, a materialized view of the incident's counts, and the table properties for compaction and compression.

## Learning objectives

After completing this module, you will be able to:

1. Read the storage properties of a table from `SHOW CREATE TABLE`, including the ones that it leaves out.
2. Design a comparison of compression algorithms that changes only the algorithm.
3. Explain how the inverted index of a text column answers `MATCH_ANY`, `MATCH_ALL`, and `MATCH_PHRASE`.
4. Interpret the row counters of a Query Profile without claiming more than they show.
5. Explain how a synchronous materialized view is built, kept up to date, and stored.
6. Predict whether Doris can answer a query from a materialized view.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 6.1 What a table's definition says | 4 min | Read `SHOW CREATE TABLE`, and what it leaves out |
| 6.2 Loads, rowsets, and compaction | 5 min | The time-series policy and group commit |
| 6.3 Compression | 5 min | ZSTD or LZ4, and a fair comparison |
| 6.4 Inverted indexes for log search | 6 min | How `MATCH_PHRASE` finds the failed checkouts |
| 6.5 Measuring a search with a Query Profile | 5 min | What the counters show, and what they do not |
| 6.6 Synchronous materialized views | 5 min | A summary that Doris keeps up to date |
| 6.7 When Doris uses a view | 5 min | Which queries a view can answer |
| Lab 6 | 40 min | The index, a view of the incident's counts, and two compressions, measured |
| Quiz 6 | 10 min | Six questions on these objectives |

## 6.1 What a table's definition says

In Module 3 you found the failed checkouts by searching the access log, and in Module 4 you kept the incident's counts in a table of your own. Whether such work is fast and cheap depends on how its table was defined. `SHOW CREATE TABLE otel_logs` returns the statement that would create the table as it is now, about 60 lines. Read it from the top:

- **Columns.** `body` is text. `resource_attributes` and `log_attributes` are `VARIANT`: Doris stores each key that the attributes contain as a column of its own, up to `variant_max_subcolumns_count`, 2048 keys, so a query on one key, such as `log_attributes['log.file.name']`, reads only that key.
- **Indexes.** One inverted index per column. Only `idx_body` has properties: `"parser" = "unicode"`, `"lower_case" = "true"`, and `"support_phrase" = "true"` (section 6.4).
- **Key, partitions, and buckets.** `DUPLICATE KEY(timestamp, service_name)`, daily partitions with dynamic partitioning, and `RANDOM BUCKETS AUTO` (Modules 4 and 5).
- **Properties.** The dynamic partitioning, the compaction policy and its settings (section 6.2), `group_commit_interval_ms` and `group_commit_data_bytes`, and `inverted_index_storage_format` = `V2`, which the exporter sets explicitly.

The definition does not list every setting. `SHOW CREATE TABLE` leaves out properties whose value is the default. The exporter created the table with `"compression" = "zstd"`, and the line is missing because ZSTD is the default compression in Doris 4.x. To know what a table does, read its definition and know the defaults of your version.

## 6.2 Loads, rowsets, and compaction

Every load writes the rows that it brings to a tablet as a new **rowset**, a set of files with its own version. The exporter loads each table every few seconds, so each tablet collects thousands of small rowsets a day. A query must read all of them, so Doris **compacts** them in the background: it merges rowsets into larger ones, which also removes deleted rows and combines the rows of AGGREGATE and UNIQUE tables.

How it merges is the table's `compaction_policy`:

- `size_based`, the default, merges small rowsets into larger ones in levels. Data can be rewritten several times on its way to a large rowset: write amplification.
- `time_series`, which the exporter sets for its DUPLICATE tables, suits data that is only appended in time order. It waits until a tablet's new rowsets reach about `time_series_compaction_goal_size_mbytes` (1024 MB), or `time_series_compaction_file_count_threshold` files (1000), or `time_series_compaction_time_threshold_seconds` (an hour) have passed, and merges them once into a final rowset. Each row is rewritten about once, which saves disk I/O and CPU on tables that receive many loads. The exporter's UNIQUE table, `otel_traces_graph`, keeps `size_based`, because its rows replace each other.

**Group commit** attacks the same problem from the other side: when many clients send small loads, Doris can collect them into one transaction and one rowset on the BE. A load asks for it, for example with the Stream Load header `group_commit: async_mode`; since Doris 4.1, a table can also make it the default for its loads with the property `group_commit_mode`, which `SHOW CREATE TABLE` shows unless it is `off_mode`. The table's `group_commit_interval_ms` (10 seconds) and `group_commit_data_bytes` (128 MB) then decide when the collected data is committed. These two settings appear in every table's definition, but they apply only to loads that use group commit. The exporter's tables do not: they have no `group_commit_mode`, and the exporter sends no such header, because its `batch` processor already collects up to 10,000 records into one Stream Load.

## 6.3 Compression

Doris compresses each column of each page before it writes it to disk, with the algorithm of the table's `compression` property. In Doris 4.x the default is **ZSTD**, which compresses well at a higher CPU cost. **LZ4** (and its variant LZ4F) is fast, with a moderate compression ratio. Telemetry is written once, kept for days, and read in small parts, so the space that ZSTD saves usually matters more than the CPU it costs, and the Doris documentation recommends it for logs. The algorithm is set when a table is created; changing it means creating a new table and copying the data.

To compare two algorithms, change nothing else. Lab 6 creates two tables that differ only in `compression`, without indexes and with one bucket, and loads the same log rows into each with one `INSERT`, so that each holds its rows in one rowset laid out the same way. Two traps it avoids:

- **Different layouts.** A table that has received thousands of small loads, such as `otel_logs`, stores its rows differently from a table loaded once, and it holds indexes too: comparing it with a fresh copy compares much more than the algorithm.
- **Unreported sizes.** `SHOW DATA` and `information_schema.tables` show the sizes that the BEs report, every minute or so. Right after a load, they still show 0. Wait until both tables report all of their rows.

In one run of Lab 6, the same 79,000 log rows took 6.7 MB with ZSTD and 10.5 MB with LZ4: LZ4 needed about 1.6 times the space; in a fresh environment, 27,000 rows took 2.2 MB and 3.3 MB, 1.5 times. That holds for those rows and that layout. Other data compresses differently, and the result says nothing about speed.

## 6.4 Inverted indexes for log search

An **inverted index** maps each value of a column to the rows that contain it. For a text column with a parser, the values are words:

- The **parser** splits the text into tokens. `unicode` splits text in most languages into words and drops punctuation; `english` and `chinese` are alternatives for those languages.
- `lower_case` indexes the tokens in lowercase, so that searches ignore case.
- `support_phrase` also records where each token occurs in a row, which phrase searches need.

`TOKENIZE(text, '"parser" = "unicode", "lower_case" = "true"')` shows the tokens that `idx_body` makes of a text: the access-log line `"POST /api/checkout HTTP/1.1" 500` becomes `post`, `api`, `checkout`, `http`, `1.1`, and `500`. Searches compare tokens:

| Search | Matches rows whose text contains |
| --- | --- |
| `body MATCH_ANY 'checkout payment'` | any of the tokens |
| `body MATCH_ALL 'checkout payment'` | all of the tokens, anywhere |
| `body MATCH_PHRASE 'POST /api/checkout'` | the tokens next to each other, in this order |

With the index, Doris looks up the tokens and their positions, and reads only the rows that match. Without it, Doris must read every row's text, tokenize it, and compare. `LIKE '%...%'` always works that way: it compares characters, and no inverted index can answer it. The other columns' indexes have no parser: they keep each value whole and answer `=`, `IN`, and ranges, such as `service_name = 'cart'`.

## 6.5 Measuring a search with a Query Profile

A **Query Profile** records what each operator of a query did. Collect one with the session variable `enable_profile = true`, at `profile_level = 2`, which includes the scan's row counters, and with the SQL cache and the condition cache off, so that a repeated query really scans the table. `SELECT last_query_id()` right after the query gives its ID, which is also the ID of its profile; `SHOW QUERY PROFILE` lists the profiles; the FE HTTP API returns the text.

In the text, each scan instance reports in `DetailProfile`, under `SegmentIterator`, where each row of the segments that it considered went:

| Counter | The rows that were |
| --- | --- |
| `RowsStatsFiltered` | skipped unread: the zone maps (minimum and maximum of a column per segment and page) rule out a match |
| `RowsInvertedIndexFiltered` | skipped unread: the inverted index shows that they do not match |
| `RowsVectorPredFiltered` | read, then dropped by a filter on a column's value |
| `RowsExprPredFiltered` | read, then dropped by a filter expression, such as `LIKE` or a `MATCH` without its index |
| `RowsRead` | read, and kept |

For the search of the failed checkouts, Lab 6 measured about 80,000 rows under `RowsInvertedIndexFiltered` and 27 under `RowsRead` with the index, and the same 80,000 under `RowsExprPredFiltered` without it: without the index, Doris read every message of the table to find 27. Two things to watch for:

- A `COUNT(*)` with an indexed filter can be answered from the index alone (`COUNT_ON_INDEX` in the plan), so `RowsRead` then no longer counts rows that were really read. Lab 6 groups its count by service to avoid it.
- The counters are evidence of what this scan of this query did. They do not show how much faster the query became, where else it spent its time, or what another query would do. Measure each query that you want to make such a claim about.

## 6.6 Synchronous materialized views

Module 4 kept the requests and failures of each service and minute in `requests_per_minute`, which a load job had to fill exactly once. A **synchronous materialized view** keeps such a summary without a job:

```sql
CREATE MATERIALIZED VIEW server_minutes_mv AS
SELECT date_trunc(end_time, 'minute') AS mv_request_minute,
       service_name AS mv_service_name,
       COUNT(*) AS mv_requests,
       SUM(IF(status_code = 'STATUS_CODE_ERROR', 1, 0)) AS mv_failed_requests
FROM otel_traces
WHERE span_kind = 'SPAN_KIND_SERVER'
GROUP BY date_trunc(end_time, 'minute'), service_name
```

- **Built by a job.** `CREATE MATERIALIZED VIEW` returns as soon as Doris accepts it; a job then builds the view from the rows that the table already has. The view answers queries only after `SHOW ALTER TABLE MATERIALIZED VIEW` shows the job `FINISHED`.
- **Kept up to date.** From then on, every load into the table also updates the view, in the same transaction, so the view is never behind the table. The price is more work on every load, and more disk.
- **Stored with the table.** The view is an index of the table: `DESC otel_traces ALL` lists it as an `AGG_KEYS` index, whose `COUNT` and `SUM` columns combine rows by `SUM`, like `requests_per_minute`. Here it held about 1,800 rows for 175,000 server spans.
- **Named columns.** Doris 4.1.3 rejects a view whose columns have the names of the table's columns, or of another view's, with `Duplicate column name`: give every column a name of its own, as the `mv_` prefix does. This is also why the exporter's own view, `<table>_services`, fails on 4.1.3 (Module 2). And `IF NOT EXISTS` does not skip an existing view in 4.1.3: drop it first to recreate it.

A synchronous view belongs to one table. To summarize several tables, or to refresh on a schedule, Doris has **asynchronous materialized views**, which are separate tables that Doris refreshes.

## 6.7 When Doris uses a view

Queries keep naming the table, and Doris rewrites a query to read the view when it can compute the query's result from the view's rows. `EXPLAIN` shows the decision: the scan reads `otel_traces(server_minutes_mv)` instead of `otel_traces(otel_traces)`, and a section of the plan lists each view that Doris considered as chosen or not usable, with the reason. In Lab 6:

| Query | Uses the view? | Reason |
| --- | --- | --- |
| Requests and failures per service and minute | Yes | The same expressions, filter, and aggregates |
| The same per service only, or for one service | Yes | Doris adds up the view's rows to the coarser grain |
| With `date_trunc(end_time, 'minute') >= ...` | Yes | The filter uses the view's expression |
| With `end_time >= ...` | No: `Rewrite compensate predicate by view fail` | The view keeps the minute, not `end_time` |
| Every span, not only server spans | No: `Predicate compensate fail` | The view holds only server spans |
| `MAX(duration)` | No: `Query function roll up fail` | The view keeps no durations |
| Grouped by `DATE_FORMAT(end_time, ...)` | No: `View dimensions doesn't not cover the query dimensions` | Another expression, even with the same meaning |

The matching is structural: Doris compares the query's expressions, filters, and aggregates with the view's, and does not prove that two differently written expressions mean the same. A view pays off for queries that dashboards and alerts run again and again in one shape; write those queries in the view's terms, and check their plans.

| Need | Use |
| --- | --- |
| Find rows by words or values | An inverted index |
| The same summary, queried often, always current | A synchronous materialized view |
| A summary with its own retention, or loaded from several sources | An AGGREGATE table and a load job |
| Less disk for the same rows | Compression, chosen when the table is created |

## Lab 6: Compression, Materialized Views, and Inverted Indexes

Open [Lab 6: Compression, Materialized Views, and Inverted Indexes](lab06_properties_mv_index.ipynb). You:

1. Count the failed checkouts in the access log.
2. Read the definition of `otel_logs`.
3. Measure the search of the failed checkouts with and without the index of `body`.
4. Create `server_minutes_mv`, wait for its build, and check which queries Doris answers from it.
5. Compare ZSTD and LZ4 on the same log rows.
6. Practice: write a query of the payment service's requests per minute that the view answers.

You need the DOG stack and the demo from Module 1, with the payment failure turned on.

## Summary

- `SHOW CREATE TABLE` shows a table's definition but leaves out default values: the exporter's `compression = zstd` is missing because ZSTD is the 4.x default.
- Every load adds a rowset, and compaction merges them; the time-series policy merges appended data about once. Group commit collects small loads into one, but only for loads that use it, by a header or by the table's `group_commit_mode`.
- A fair comparison of compression changes only the algorithm, loads the same rows the same way, and waits for the BEs to report sizes. On the course's logs, LZ4 took 1.5 to 1.6 times the space of ZSTD.
- An inverted index with a parser lists, for each token, the rows that contain it; `MATCH_ANY`, `MATCH_ALL`, and `MATCH_PHRASE` compare tokens, and phrases need `support_phrase`. Without the index, or with `LIKE`, Doris reads every row's text.
- A Query Profile's row counters show where each row of a scan went in this query: skipped by zone maps or the index, read and dropped, or read and kept. They are not a measure of speed.
- A synchronous materialized view is built by a job, then updated with every load, and stored as an AGGREGATE index of its table. Doris uses it when the query's expressions, filters, and aggregates can be computed from it, which `EXPLAIN` shows.

## Quiz 6

Open [Quiz 6: Table Properties, Materialized Views, and Indexes](quiz06_properties_mv_and_indexes.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 7: Trace Analysis and Litefuse](../module07-data-analysis-litefuse/course.md).

## References

- [Apache Doris: Data compression](https://doris.apache.org/docs/4.x/table-design/column-compression/)
- [Apache Doris: Compaction](https://doris.apache.org/docs/4.x/admin-manual/trouble-shooting/compaction/) and the [CREATE TABLE properties](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/CREATE-TABLE/)
- [Apache Doris: Group commit](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/group-commit-manual/)
- [Apache Doris: Log storage and analysis](https://doris.apache.org/docs/4.x/observability/log/)
- [Apache Doris: Inverted index](https://doris.apache.org/docs/4.x/table-design/index/inverted-index/overview/) and its [search operators](https://doris.apache.org/docs/4.x/table-design/index/inverted-index/search-operators/)
- [Apache Doris: Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)
- [Apache Doris: Synchronous materialized views](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/sync-materialized-view/)
