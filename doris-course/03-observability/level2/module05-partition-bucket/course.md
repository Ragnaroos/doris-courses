# Module 5: Partitioning and Bucketing for Observability Data

| Course information | Value |
| --- | --- |
| Course | Observability with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Environment | The DOG stack and the OpenTelemetry demo of Module 1, with the payment failure turned on |
| Estimated time | About 75 minutes: reading 30, Lab 35, quiz 10 |

[Course README](../../README.md) · [Open Lab 5](lab05_partition_and_bucket.ipynb) · [Open Quiz 5](quiz05_partition_and_bucket_choices.ipynb)

## Module goal

Make the queries of the incident window read only the partitions and tablets that can hold its rows, and choose how a telemetry table is partitioned, bucketed, and kept.

## Learning objectives

After completing this module, you will be able to:

1. Explain how Doris divides a table into partitions, buckets, and tablets.
2. Predict which partitions a query reads from its filter on the partition column.
3. Predict which partitions dynamic partitioning creates and drops.
4. Choose a partition grain and a partitioning method for a retention period and a query pattern.
5. Choose HASH or RANDOM bucketing from a table's filters and the distribution of its data.
6. Explain how Doris sets the number of buckets of each partition.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 5.1 Partitions, buckets, and tablets | 4 min | How Doris divides a table, and why |
| 5.2 Time partitions for telemetry | 5 min | The exporter's daily partitions and their retention |
| 5.3 Partition pruning | 5 min | Which partitions a query reads |
| 5.4 Choosing the partition grain | 4 min | Hours, days, or months |
| 5.5 AUTO PARTITION | 3 min | Partitions that the data creates |
| 5.6 HASH or RANDOM buckets | 6 min | Pruning against balance |
| 5.7 How many buckets | 3 min | Tablet size, and `BUCKETS AUTO` |
| Lab 5 | 35 min | The plans of the incident's queries, and three ways to bucket the spans |
| Quiz 5 | 10 min | Six questions on these objectives |

## 5.1 Partitions, buckets, and tablets

When the payment failures began, the questions narrowed to a time window and to a few services: the orders since the failures started, the charges of the payment service. A query that reads only the data that can answer it finishes sooner, and leaves the machine to the other queries. Doris makes this possible by dividing every table twice:

- **Partitions** divide the rows by the values of the partition columns, for telemetry by time: one partition per day, for example. A query that filters on the partition column skips the partitions that cannot match. A partition is also the unit of a table's lifecycle: dropping a partition deletes its rows at once, without rewriting any data.
- **Buckets** divide each partition again, by a hash of some columns or at random. Doris stores each bucket of each partition as a **tablet**: the unit that a BE stores, copies to replicas, compacts, and scans. A table with 5 partitions of 10 buckets has 50 tablets, and a scan can read the tablets of a partition in parallel.

Inside a tablet, Doris keeps rows sorted by the key in segments, with the zone maps and indexes that Module 6 measures. Partitions and buckets decide which tablets a query opens at all.

## 5.2 Time partitions for telemetry

The exporter creates each telemetry table with `PARTITION BY RANGE(timestamp)` and **dynamic partitioning** by day. Its settings from Module 2 become the table's properties:

| Property | Value | Meaning |
| --- | --- | --- |
| `dynamic_partition.time_unit` | `DAY` | One partition per day, named after the day, such as `p20261020` |
| `dynamic_partition.time_zone` | `UTC` | Days start at midnight UTC, like the times that the exporter writes |
| `dynamic_partition.end` | `1` | Keep the partitions up to tomorrow created in advance |
| `dynamic_partition.start` | `-7` | Drop the partitions of days more than 7 days before today (from `history_days: 7`) |
| `dynamic_partition.history_partition_num` | `3` | Create the partitions of 3 past days with the table (from `create_history_days: 3`) |
| `dynamic_partition.buckets` | `10` | The number of buckets of the partitions created with the table |

A scheduler in the FE applies these settings every 10 minutes (the FE setting `dynamic_partition_check_interval_seconds`, 600 by default): it creates the partitions that are missing up to `end`, and drops the ones before `start`. Retention therefore works a day at a time, and costs nothing: Doris deletes a whole partition's files. `start` also limits loads: a row older than the oldest partition has no partition to go to, and Doris rejects it.

`history_partition_num` cannot reach past `start`: a table with `start = -7` and `history_partition_num = 10` still creates only the partitions of 7 past days. So right after the exporter created `otel_traces`, it had five partitions: the 3 past days, today, and tomorrow. Lab 5 lists them with `SHOW PARTITIONS` and `SHOW DYNAMIC PARTITION TABLES`.

## 5.3 Partition pruning

A query that filters on the partition column reads only the partitions whose range can hold matching rows: **partition pruning**. `EXPLAIN` shows the plan of a query without running it, and the scan of each table in the plan says how many partitions and tablets it reads:

```text
0:VOlapScanNode
   TABLE: otel.otel_traces(otel_traces)
   PREDICATES: ((service_name = 'payment') AND (timestamp >= '2026-10-20 23:24:01.850805'))
   partitions=1/5 (p20261020)
   tablets=10/10
```

The query of the incident window reads one partition of five, today's, and all ten of its tablets. Three details help to read such plans:

- **Empty partitions are skipped too.** A query without any filter on time also reads `1/5` in a fresh environment, because only today's partition holds rows. On a table with a week of telemetry, it would read every partition, while the query of the incident window would still read one or two.
- **Doris must know the values when it plans the query.** A comparison with a constant, or with `UTC_TIMESTAMP() - INTERVAL 1 HOUR`, which Doris computes while it plans, prunes. In Doris 4.1.3, a comparison with `UTC_DATE()` does not: Doris does not compute that function while planning, and the scan reads every partition that has data. Lab 5 computes yesterday's range in Python and writes it into the query as text.
- **A filter that selects only empty partitions reads nothing.** For yesterday's range, the plan has no scan at all.

Filtering on the partition column is the first thing that keeps a telemetry query small: every Discover search, dashboard panel, and alert rule of this course has a time range.

## 5.4 Choosing the partition grain

The grain decides how finely queries can prune and retention can drop, and how many tablets the table has:

| Grain | Partitions for 7 days | Tablets with 10 buckets | Fits |
| --- | ---: | ---: | --- |
| Hour | 168 | 1,680 | Very large volumes, read in windows of hours, kept a few days |
| Day | 7 | 70 | Most telemetry: queries of minutes to days, retention in days |
| Month | 1 | 10 | Small volumes kept for years |

Each partition and tablet is metadata that the FE keeps in memory, and each tablet is files that a BE opens, compacts, and reports. Hourly partitions multiply them by 24, which pays off only when a day's data is too large to scan and the queries need hours. Monthly partitions do not stop you from querying one day: the filter on time still selects the rows. But the query reads the whole month's partition to find them, and retention can only drop a month at a time. For telemetry, daily partitions are the usual choice, as the exporter makes.

Whatever the grain, set a retention. A table that creates partitions and never drops them grows until its disk is full.

## 5.5 AUTO PARTITION

With **AUTO PARTITION**, the table starts without partitions, and a load creates the partition of each row that has none:

```sql
CREATE TABLE spans_by_service (...)
DUPLICATE KEY(timestamp, service_name)
AUTO PARTITION BY RANGE (date_trunc(timestamp, 'day')) ()
DISTRIBUTED BY HASH(service_name) BUCKETS 10
PROPERTIES ("partition.retention_count" = "7")
```

There are no empty partitions: no past days that hold nothing, and no partition of tomorrow until a row of tomorrow arrives. This suits data that arrives irregularly, or late: a row of a day long past gets its partition instead of being rejected. The partition column must be `NOT NULL`.

AUTO PARTITION does not drop old partitions by itself. `partition.retention_count = 7` keeps the 7 newest partitions of past days and drops the older ones; the partition of the current day and future ones are always kept. The same scheduler as for dynamic partitions applies it, every 10 minutes. An AUTO PARTITION table can also have dynamic partitioning, which then creates partitions ahead of time and drops them by its `start`, as Litefuse's tables in Module 7 do; `partition.retention_count` cannot be combined with dynamic partitioning.

## 5.6 HASH or RANDOM buckets

The distribution decides which bucket of a partition each row goes to:

| | `DISTRIBUTED BY HASH(column)` | `DISTRIBUTED BY RANDOM` |
| --- | --- | --- |
| Where a row goes | The bucket of the hash of its value | Any bucket |
| A filter `column = value` | Reads one bucket: **bucket pruning** | Reads every bucket |
| Balance | Only as even as the values: a value with many rows makes a large bucket | Even |
| Allowed for | Every model | DUPLICATE tables, and AGGREGATE tables without `REPLACE` columns |

Lab 5 copies the spans of `otel_traces` into a table bucketed by `HASH(service_name)` into 10 buckets. The query of the payment service then reads `1/10` tablets. But the services are very uneven: in one measurement, one tablet held 38% of the rows (`flagd`, `frontend-proxy`, and `accounting` share it), another 28%, and one held none, while `payment`'s tablet had a few dozen rows. A partition is only as fast as its largest tablet: its loads, its compaction, and every scan of all of it wait for that tablet. The exporter's `otel_traces` uses RANDOM, and its ten tablets each hold about a tenth of the rows.

So choose a bucket column only when most queries filter on it with `=` or `IN`, and when it spreads the rows evenly: many distinct values, none dominant. The trace ID is such a column for a table that is read trace by trace: every lookup of one trace reads one tablet, and the tablets stay even, which is why Litefuse buckets its tables by trace ID. Raw telemetry is read in many ways, mostly by time, and its services are uneven, so RANDOM is the safer default; the inverted index of `service_name` finds the rows of one service inside the tablets (Module 6).

With RANDOM bucketing, a load sends each batch of rows to one tablet and the next batch to the next tablet, so its rows spread over the tablets of a partition, and the tablets come closer to even as batches add up. A Stream Load with the header `load_to_single_tablet: true` writes all of its rows to one tablet, and the next load to the next tablet, so that each load creates fewer and larger files, which helps tables that receive many loads. The exporter does not set it.

## 5.7 How many buckets

Doris's guidance is to keep each tablet between about 1 and 20 GB of compressed data, and at most 10 GB for UNIQUE tables, and to have about as many tablets as the cluster has disks. Too small tablets cost metadata and make many small files; too large ones are slow to copy, balance, and recover.

`BUCKETS AUTO` lets Doris choose the number for each new partition from the sizes of the earlier partitions that hold data: about one bucket up to 100 MB of compressed data per partition, two up to 1 GB, then one per 5 GB, capped by the cluster's disks and at 128. Two rules explain why every partition of the exporter's tables has 10 buckets:

- The partitions that Doris creates together with the table get `dynamic_partition.buckets`, 10.
- When the estimate for a new partition is less than half of the previous partition's number, Doris treats it as an error and keeps the previous number. The course's partitions hold megabytes, so the estimate is 1, less than half of 10, and Doris keeps 10.

In production, where a day of telemetry holds gigabytes, the estimate follows the data as it grows.

## Lab 5: Partitions and Buckets for the Incident Window

Open [Lab 5: Partitions and Buckets for the Incident Window](lab05_partition_and_bucket.ipynb). You:

1. Find the incident window: the time since the first failed order.
2. List the partitions of `otel_traces` and its dynamic partitioning.
3. Read the plans of a query of the incident window, of a query for yesterday, and of a query without a filter on time.
4. Count the rows in each tablet of `otel_traces`, copy its spans into a table bucketed by service, and compare the tablets and the plans.
5. See the partitions that AUTO PARTITION created.
6. Practice: bucket the spans by trace ID, and look up the trace of a failed order.

You need the DOG stack and the demo from Module 1, with the payment failure turned on.

## Summary

- Partitions divide a table by the partition column, buckets divide each partition, and each bucket of each partition is a tablet, the unit that Doris stores and scans.
- A filter on the partition column, with values known when the query is planned, makes the query read only the partitions that can match; Doris also skips empty partitions. `EXPLAIN` shows both as `partitions=read/total`.
- Dynamic partitioning creates partitions up to `end` and drops those before `start`, every 10 minutes; `history_partition_num` creates past partitions with the table, never beyond `start`.
- Daily partitions fit most telemetry: hourly ones multiply the tablets, monthly ones prune less and keep data a month at a time. AUTO PARTITION creates only the partitions that rows need, and `partition.retention_count` drops old ones.
- HASH bucketing prunes buckets for `=` filters on its column but is only as even as the values; RANDOM keeps tablets even and prunes nothing. Bucket by a column that most queries filter on and that has many evenly used values, such as a trace ID.
- `BUCKETS AUTO` estimates the number of buckets from the sizes of earlier partitions; partitions created with the table take `dynamic_partition.buckets`, and an estimate below half of the previous partition's number is ignored.

## Quiz 5

Open [Quiz 5: Partitioning and Bucketing for Observability Data](quiz05_partition_and_bucket_choices.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 6: Table Properties, Materialized Views, and Indexes](../module06-property-mv-index/course.md).

## References

- [Apache Doris: Data partitioning overview](https://doris.apache.org/docs/4.x/table-design/data-partitioning/overview/) and [basic concepts](https://doris.apache.org/docs/4.x/table-design/data-partitioning/basic-concepts/)
- [Apache Doris: Dynamic partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning/) and [auto partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/auto-partitioning/)
- [Apache Doris: Data bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/data-bucketing/)
- [Apache Doris: Stream Load parameters, including load_to_single_tablet](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/)
- [Apache Doris: EXPLAIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/)
