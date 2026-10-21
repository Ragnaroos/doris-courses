# Module 2: Doris Storage Architecture and Write Mechanisms

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1 |
| Estimated time | About 55 minutes: reading 25, Lab 20, quiz 10 |

[Course README](../../README.md) · [Open Lab 2](lab02_observe_storage.ipynb) · [Open Quiz 2](quiz02_storage_and_write_batches.ipynb)

## Module goal

Follow a query from the FE to the BE, and see how Doris stores what you write: in tablets, as versioned rowsets of columnar segments, which compaction later merges.

## Learning objectives

After completing this module, you will be able to:

1. Trace a query to explain FE planning and BE execution.
2. Explain the hierarchy of table, partition, tablet, rowset, and segment.
3. Explain when loaded rows become visible, and what compaction changes afterward.
4. Compare batch and row-by-row writes with everything else held constant.
5. Read a tablet's versions and rowsets, and explain what they show about write batches and compaction.
6. Use EXPLAIN for what a query plans and the Query Profile for what its scan read.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 2.1 The Query Path and Columnar Storage | 5 min | What the FE and the BE do for one query, and why it reads few columns |
| 2.2 Tablets, Rowsets, and Segments | 6 min | Where a written row ends up |
| 2.3 Visibility and Compaction | 4 min | When rows can be queried, and what compaction changes |
| 2.4 One Batch or Ten Writes | 4 min | A fair comparison, and what versions and rowsets show |
| 2.5 The Plan and the Work | 6 min | EXPLAIN against the Query Profile's scan counters |
| Lab 2 | 20 min | Write ten orders two ways and read their versions, rowsets, and scans |
| Quiz 2 | 10 min | Six questions on these objectives |

## 2.1 The Query Path and Columnar Storage

Suppose an analyst wants the amount of order 1, not the whole order table. After Lab 2, you can run:

```sql
SELECT order_id, order_amount
FROM orders_batch
WHERE order_id = 1;
```

Expect one row: order 1, 2300.00. The client sends one SQL statement; inside Doris, the work is split:

```text
Notebook or SQL client
        │ SQL
        ▼
FE: parse the statement → optimize it → build and send the execution plan
        │ plan fragments
        ▼
BE: scan the needed columns → filter on the order ID → return the amount
        │
        ▼
Client: show the result
```

The FE decides what work to do; each BE does its share. A large query can scan and aggregate on several BEs and combine their results; the course's single node shows the roles, not scaling. Planning and executing are separate stages: a query that the FE planned can still fail while a BE runs its part.

### Why analysis reads only some columns

The order table also holds the customer, the date, the line count, and the source, but this query needs only two columns. **Columnar storage** keeps the values of each column together, so a scan can read just the columns that a query uses. Reading fewer columns (column pruning) and skipping rows or blocks that cannot match (filtering) are two different savings; 2.5 measures both.

## 2.2 Tablets, Rowsets, and Segments

When rows reach Doris, the table's partitioning and bucketing decide which tablet stores each row, and the BE writes them into columnar files.

```text
Table: a table in SQL
└── Partition: a range of rows, such as one day
    └── Bucket = Tablet: one shard of a partition, stored by a BE
        └── Rowset: the versioned set of rows that one write (or one compaction) produced
            └── Segment: an immutable columnar file of a rowset
```

| Layer | In the order tables | Not to be confused with |
| --- | --- | --- |
| Partition | One range of order dates; a table without `PARTITION BY` has one partition | A BE node |
| Bucket / Tablet | A shard of a partition; each bucket of each partition is a tablet | A replica: replicas are copies of a tablet |
| Rowset | What one write added to a tablet, with its version | A file shared by the whole table |
| Segment | A file that holds a rowset's columns; a large rowset has several | A business order |

Two days as two partitions, with four buckets each, give eight tablets. Replicas add copies of each tablet on other BEs, not more data; the course's sandbox has one BE, so one replica. The count above assumes only the table's own data, its base index: a synchronous materialized view or a rollup stores its own copy in more tablets.

For Lab 2's single-bucket table, a write of ten orders adds one rowset to the one tablet; ten writes of one order add ten rowsets. A large write can produce several segments. Business rows, write requests, and files are three different counts.

## 2.3 Visibility and Compaction

A write is a load transaction. Once it commits and is published as a new **version**, queries can read its rows. Nothing else has to happen first.

Many small writes leave many small rowsets, and a query of the tablet has to read and merge all of them. **Compaction** merges rowsets in the background into fewer, larger ones:

```text
Within one tablet:
Write A → rowset [2-2] ┐
Write B → rowset [3-3] ├─ cumulative compaction → rowset [2-4]
Write C → rowset [4-4] ┘
```

Compaction changes how the rows are stored, never which rows a query returns: whether a load is visible and whether its files were compacted are two separate questions. When a load seems to be missing, check its transaction first, then its files. The merged-away rowsets stay listed as **stale** for a while before the BE deletes them. See [Compaction principles](https://doris.apache.org/docs/4.x/admin-manual/trouble-shooting/compaction-principles/).

## 2.4 One Batch or Ten Writes

Lab 2 writes the same ten orders twice, into two tables that differ only in how they are written:

| Compared | orders_batch | orders_rowwise |
| --- | --- | --- |
| Data and columns | The same ten orders | The same ten orders |
| Buckets and replicas | One bucket, one replica | One bucket, one replica |
| Writes | One `INSERT` of ten rows | Ten `INSERT` statements of one row |
| Group Commit | off_mode | off_mode |
| Business result | Ten rows, 12220.60 | Ten rows, 12220.60 |

Only the writes differ: changing the bucket count or the data at the same time would leave no way to say which change caused what. Group Commit, which can merge small writes on the server (Module 5), is off so that each write commits on its own.

### What versions and rowsets show

Check the business result first, then the storage:

```sql
SHOW PARTITIONS FROM orders_batch;
SHOW TABLETS FROM orders_batch;
SHOW TABLETS FROM orders_rowwise;
```

| Field | How to read it | What it is not |
| --- | --- | --- |
| TabletId | Identifies the tablet for further inspection | An order ID |
| Version | The last committed version: an empty tablet starts at 1, and each load adds one | A count of files; compaction does not lower it |
| VersionCount | The number of versions that the BE reported at its last report, about once a minute | A count of writes or of segments |

The batch table is at version 2 and the row-by-row table at version 11: ten writes, ten transactions. A tablet's rowsets are listed by the BE that stores it: `SHOW TABLET <TabletId>` returns a `DetailCmd`, a `SHOW PROC` statement that lists the tablet's replicas, and each replica has a `CompactionStatus` URL on its BE. Lab 2 reads it for both tables:

| Table | Rowsets right after the writes | After cumulative compaction |
| --- | --- | --- |
| orders_batch | `[0-1]`, the empty start, and `[2-2]`, the ten rows | Unchanged: one load rowset has nothing to merge |
| orders_rowwise | `[0-1]` and `[2-2]` … `[11-11]`, one per write | `[0-1]` and `[2-11]`, with the ten old rowsets listed as stale |

`[2-11]` is a range of versions, not ten orders. On the sandbox, compaction usually merges the ten small rowsets within seconds, so what you see depends on when you look; the business result does not. Only read the status here: do not trigger compaction or touch storage files. See [Tablet status access](https://doris.apache.org/docs/4.x/admin-manual/trouble-shooting/tablet-local-debug/).

Ten rows show the mechanism, not throughput: measuring write performance needs large data, fixed concurrency, and observation over time of versions, latency, and whether compaction keeps up.

## 2.5 The Plan and the Work

`EXPLAIN` shows the plan that the FE built, without running it: the table, the columns, the filter, and how many partitions and tablets it will read.

```sql
EXPLAIN SELECT order_id, order_amount
FROM orders_batch
WHERE order_id = 1;
```

A plan is not a measurement: it says nothing about how many rows or bytes a scan actually read. The **Query Profile** records that. With `enable_profile = true` in a session, Doris keeps a Profile for each query; `SELECT last_query_id()` right after a query returns its query ID, which is also its Profile ID, and the FE serves the Profile's text and shows it on the QueryProfile page of its Web UI. Lab 2 turns Profiles on for its session, turns off the SQL cache so that a repeated query really scans, and restores both settings afterwards.

A scan's row counters tell how it found its rows:

| Counter | What it counts |
| --- | --- |
| ScanRows | Rows the scan read from its segments |
| RowsKeyRangeFiltered | Rows the sort key's index let it skip without reading |
| RowsVectorPredFiltered | Rows it read and then dropped with the filter |
| RowsRead | Rows that passed the filter |

All three of Lab 2's queries return order 1, but they do different work. `WHERE order_id = 1` reads one row: `order_id` is the sort key, and its index narrows the range. `WHERE customer_id = 832` reads all ten rows and drops nine. Selecting all columns instead of two, with the same filter, reads more bytes. On ten rows, these counters describe the kind of work, not its speed; compare speed only on the same machine, data, and cache. See [Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/).

## Lab 2: Observe Storage and Write Batches

Open [Lab 2: Observe Storage and Write Batches](lab02_observe_storage.ipynb). You:

1. Create two tables with the same definition and write the same ten orders as one batch and as ten single-row writes.
2. Check that both tables contain ten rows and 12220.60.
3. Read the partitions' and tablets' versions, then the rowsets of each tablet and what compaction did with them.
4. Compare a query's plan with the scan counters of its Query Profile.
5. Practice: one date in both tables, and why the sort key does not help that filter.

You need the course sandbox from Module 1. The [Level 1 extension labs](../extensions/README.md) repeat these observations on 100,000 rows.

## Summary

- The client sends SQL, the FE plans the query and distributes it, and the BE reads the needed columns and filters and aggregates them; a planned query can still fail while it runs.
- A table's partitions hold ranges of rows, each bucket of a partition is a tablet, each write adds a versioned rowset to a tablet, and a rowset's columns are in segment files.
- Rows are visible once their transaction is published; compaction merges rowsets afterward and never changes which rows a query returns.
- Compare write methods with the same data, table definition, and settings: both of Lab 2's tables hold ten rows and 12220.60.
- One batch made version 2 and one rowset; ten writes made version 11 and ten rowsets, which compaction merges into `[2-11]`.
- EXPLAIN shows what a query plans to read, and the Query Profile what its scan read and skipped; ten rows show mechanisms, not speed.

## Quiz 2

Open [Quiz 2: Doris Storage Architecture and Write Mechanisms](quiz02_storage_and_write_batches.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 3: Doris Table Models, Partitioning, and Bucketing](../module03-table-design/course.md).

## References

- [Apache Doris: System architecture](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)
- [Apache Doris: Partitioning and bucketing basics](https://doris.apache.org/docs/4.x/table-design/data-partitioning/basic-concepts/)
- [Apache Doris: Compaction principles](https://doris.apache.org/docs/4.x/admin-manual/trouble-shooting/compaction-principles/)
- [Apache Doris: EXPLAIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/)
- [Apache Doris: Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)
- [Apache Doris: Group Commit](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/group-commit-manual/)
