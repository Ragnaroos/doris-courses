# Module 2: Deep Dive into Apache Doris Architecture

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 1 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | Approximately 65–70 minutes, including the guided lab and quiz |

## Module goal

This module explains the architectural and storage concepts that determine how
Apache Doris executes queries, organizes data, handles repeated keys, and
avoids unnecessary work.

By the end of the module, you will be able to connect a SQL query to both sides
of the system: the Frontend (FE) creates a distributed query plan and assigns
its plan fragments, while Backend (BE) nodes execute the assigned plan
fragments over distributed columnar data.

## Learning objectives

After completing this module, you will be able to:

1. Trace a SQL statement from FE planning to distributed, vectorized execution
   on BE nodes.
2. Explain the hierarchy from Table to Partition, Bucket/Tablet, Rowset, and
   Segment.
3. Explain how a load transaction creates Rowsets and Segments and why
   background Compaction is necessary.
4. Describe how the Duplicate Key model, Unique Key model, and Aggregate Key model
   define repeated-key behavior.
5. Distinguish partitioning, bucketing, the sort key, and the Prefix Index by
   the problem each one solves.
6. Use `EXPLAIN` and basic runtime evidence to compare effective and ineffective
   filter patterns.

## Module structure

| Section | Format | Time | Outcome |
| --- | --- | ---: | --- |
| 2.1 From SQL to Distributed Pipelines | Reading/visual | 7 min | Trace FE planning and BE execution through one query |
| 2.2 Columnar and Vectorized Processing | Reading/visual | 6 min | Explain why Doris reads columns and processes values in batches |
| 2.3 How Doris Organizes Stored Data | Animated walkthrough | 9 min | Relate the logical namespace to the physical storage hierarchy |
| 2.4 Load Transactions and Compaction | Reading/visual | 6 min | Connect load transactions, Rowsets, Segments, visibility, and Compaction |
| 2.5 Table Models and Repeated Keys | Scenario comparison | 6 min | Predict the result of repeated keys in all three table models |
| 2.6 How Doris Skips Work | SQL walkthrough | 7 min | Separate partition, tablet, and in-table scan reduction |
| Lab 2 | Hands-on | 20 min | Compare sort keys, pruning, runtime scan evidence, and table models |
| Quiz 2 | Interactive knowledge check | 5 min | Check the Module 2 architecture, storage, physical-design, and diagnostic mental models |

---

## 2.1 From SQL to Distributed Pipelines

Module 1 introduced the component boundary: FE creates and optimizes a
**distributed query plan**, then assigns its **plan fragments** to BE nodes. BE
nodes execute the **assigned plan fragments**. This section follows that path
in more detail.

Consider a query over the course event table:

```sql
SELECT
    region,
    SUM(revenue) AS total_revenue
FROM events
WHERE event_time >= '2020-03-01 00:00:00'
  AND event_time <  '2020-03-02 00:00:00'
  AND event_type = 'purchase'
GROUP BY region;
```

The client submits one SQL statement, but a distributed Doris cluster does not
run the entire statement as one indivisible task.

### FE: create the distributed query plan

The FE performs the SQL-layer work:

1. **Parse and analyze:** recognize the SQL structure, resolve names and types,
   and check privileges.
2. **Rewrite and optimize:** select physical operators and compare possible
   execution strategies.
3. **Prune from metadata:** exclude partitions and tablets that cannot satisfy
   compatible predicates.
4. **Create the distributed query plan:** arrange scans, filters,
   aggregations, data exchanges, and result collection.
5. **Assign plan fragments:** send the relevant work to BE nodes that can
   execute it.

A **plan fragment** is a distributable part of the distributed query plan. For example,
one plan fragment may scan and partially aggregate rows on several BEs, while
another receives those partial results and completes the aggregation.

The course wording maps to the names displayed by Doris documentation,
`EXPLAIN`, and source code as follows:

| Course term | Doris plan term | Relationship |
| --- | --- | --- |
| Distributed query plan | `PLAN` / execution plan | The complete physical plan for one SQL statement |
| Plan fragment | `FRAGMENT` / `PlanFragment` | A distributable part of the complete plan assigned to a BE |
| Physical operator | `PLAN NODE` / `PlanNode` | A scan, aggregation, join, exchange, or other operation inside a plan fragment |

These are three levels of one structure, not interchangeable names for the
same object.

### BE: execute the assigned plan fragments

Each participating BE executes its assigned plan fragments with physical
operators such as scan, filter, exchange, and aggregate. An **Exchange** moves
intermediate data between plan fragments when the next operation requires rows
to be repartitioned or gathered.

```text
MySQL-compatible client
          |
          | SQL
          v
Frontend (FE)
  parse -> analyze -> optimize
  create a distributed query plan
  assign plan fragments
          |
          v
Backend (BE) nodes
  execute assigned plan fragments
  scan -> filter -> partial aggregate
          |
          | Exchange when required
          v
  merge -> final result -> client
```

This is **Massively Parallel Processing (MPP)**: work is distributed across BE
nodes. Within one BE, the **Pipeline execution engine** schedules operators as
parallel tasks across CPU cores. MPP describes parallelism across the cluster;
Pipeline execution describes how work is scheduled efficiently inside each BE.

The source code reflects the same boundary. FE planning code produces fragment
execution parameters, and the BE internal service passes incoming fragments to
its fragment manager for Pipeline execution. See the project
[source repository](https://github.com/apache/doris) and BE
[`internal_service.cpp`](https://github.com/apache/doris/blob/master/be/src/service/internal_service.cpp).

> **Mental model:** FE decides what distributed work should run and where. BE
> nodes perform the assigned scan, filter, exchange, join, and aggregation work.

---

## 2.2 Columnar and Vectorized Processing

Analytical queries commonly read a small set of columns across many rows. The
example query needs `event_time`, `event_type`, `region`, and `revenue`; it does
not need `event_id`, `user_id`, or `product_id`.

### Row-oriented and column-oriented access

In a row-oriented layout, the values for one row are stored together. This is
useful when a request fetches or changes most columns of a small number of rows.

```text
Row 1: event_time | event_id | user_id | event_type | region | revenue
Row 2: event_time | event_id | user_id | event_type | region | revenue
```

In a column-oriented layout, values from the same column are stored together.

```text
event_time:  t1 | t2 | t3 | ...
event_type:  view | cart | purchase | ...
region:      region_01 | region_03 | region_01 | ...
revenue:     0.00 | 0.00 | 42.50 | ...
```

Doris internal tables use columnar storage by default. That design helps
analytical queries in three ways:

- **Column pruning:** the scan reads only the columns required by the query.
- **Compression:** adjacent values of the same type and similar distribution
  often compress efficiently.
- **CPU locality:** a tight sequence of values can be processed without
  repeatedly unpacking complete rows.

### Vectorized execution

Vectorized execution passes a batch of column values between operators instead
of interpreting one complete row at a time. Filtering a batch of
`event_type` values or summing a batch of `revenue` values reduces per-row
overhead and can use CPU vector instructions where applicable.

```text
Columnar Segment
       |
       | batch of selected columns
       v
Vectorized scan -> vectorized filter -> vectorized aggregate
```

Columnar storage and vectorized execution solve related but different
problems. Columnar storage reduces and organizes the bytes read from storage;
vectorized execution improves how operators process those values in memory.

Doris also supports an optional row-store copy for workloads dominated by
wide point queries. This hybrid option does not change the default analytical
model: the columnar copy remains available, and enabling another representation
has storage and write-cost tradeoffs. See the official
[storage layout overview](https://doris.apache.org/docs/4.x/table-design/storage-layout-overview/).

---

## 2.3 How Doris Organizes Stored Data

Doris first names data through a logical namespace:

```text
Internal Catalog
└── Database
    └── Table
```

The course uses `internal.doris_course.events`:

- `internal` is the Catalog for Doris internal tables.
- `doris_course` is the Database.
- `events` is the Table.

Inside an internal Table, data is organized physically:

```text
Table
└── Partition              logical range and lifecycle boundary
    └── Bucket / Tablet    distribution rule / physical data shard
        └── Rowset         version unit created by a load transaction or Compaction
            └── Segment    immutable columnar data file
```

### Partition

A **Partition** is a logical subset of a Table, commonly defined by time or
another lifecycle boundary. A daily event table might have one Partition for
each date.

Partitioning supports two main responsibilities:

- lifecycle operations, such as dropping expired data by Partition;
- coarse pruning, so FE can exclude nonmatching Partitions from a distributed
  query plan.

Partitioning is optional. An unpartitioned table still has one default
Partition.

### Bucket and Tablet

Each Partition is divided by a bucketing rule. A **Bucket** is a slot produced
by that rule; the corresponding physical data shard is a **Tablet**. If a Table
has 26 Partitions and 10 Buckets per Partition, it has 260 Tablets.

Hash bucketing deterministically maps equal bucket-key values to the same
Bucket. This can let FE prune Tablets for compatible equality predicates.
Random bucketing distributes incoming rows without a bucket key, so it cannot
provide the same key-based bucket (tablet) pruning.

A Tablet is the basic unit of data distribution, balancing, and parallel scan.
In the integrated storage-compute architecture, a Tablet may have replicas on
BE nodes. The single-node course sandbox uses one replica; replication strategy
is outside this module's scope.

### Rowset

A **Rowset** is a versioned collection of data inside one Tablet. One load
transaction may touch many Tablets and create a Rowset in each affected
Tablet. It does not create one global Rowset for the whole Table.

### Segment

A **Segment** is an immutable columnar data file inside a Rowset. It contains
column data, metadata, and index structures used during a scan. A Rowset can
contain multiple Segments, depending on the volume and shape of the write.

The names are not interchangeable:

| Concept | Main responsibility |
| --- | --- |
| Table | SQL object and schema |
| Partition | Logical range and lifecycle boundary |
| Bucket | Distribution rule within a Partition |
| Tablet | Physical shard corresponding to a Bucket |
| Rowset | Version unit within one Tablet |
| Segment | Immutable columnar file within a Rowset |

See [partitioning and bucketing concepts](https://doris.apache.org/docs/4.x/table-design/data-partitioning/basic-concepts/)
and [data bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/data-bucketing/).

---

## 2.4 Load Transactions and Compaction

A successful load changes many physical objects but becomes visible as one
transactional result.

### From incoming rows to a visible version

At a high level, the integrated write path is:

1. Doris identifies the target Partition for each incoming row.
2. The bucketing rule routes the row to a Tablet.
3. A BE buffers and organizes rows for the target Tablet, including sorting by
   the Table's Key columns.
4. Flushing the buffered data creates immutable Segments in a Rowset.
5. The load transaction commits and publishes its visible version.
6. Queries can read the newly committed data.

```text
One load transaction
       |
       +--> Tablet A --> new Rowset --> Segment(s)
       +--> Tablet B --> new Rowset --> Segment(s)
       +--> Tablet C --> new Rowset --> Segment(s)
       |
       v
commit and publish -> new data becomes visible
```

The precise number of Rowsets and Segments is a storage-engine result, not a
number the application should infer from the count of SQL statements alone.
The important relationship is that versions belong to Tablets and Segments are
immutable files within Rowsets.

### Why Compaction is necessary

Frequent small loads can leave a Tablet with many small Rowsets. A query must
then open and reconcile more inputs, increasing read amplification and
metadata overhead.

**Compaction** is a background BE operation that selects Rowsets within one
Tablet and rewrites them into fewer, larger Rowsets. Depending on the table
model, Compaction also applies repeated-key semantics and obsolete-data
cleanup. It does not merge data across unrelated Tablets, and it does not
change the logical query result.

```text
Before Compaction                  After Compaction
Tablet                             Tablet
├── Rowset v1                       └── Rowset v1–v4
├── Rowset v2                           ├── Segment
├── Rowset v3                           └── Segment
└── Rowset v4
```

Compaction balances two forms of work: extra background I/O when Rowsets are
rewritten, and less read amplification for later queries. That is why a healthy
system manages Compaction automatically rather than compacting after every
individual write.

`SHOW TABLETS` exposes fields such as visible versions and `VersionCount` that
can help identify version pressure. `VersionCount` is operational evidence; it
is not a direct count of Rowsets or Segments.

The official [Compaction principles](https://doris.apache.org/docs/4.x/admin-manual/trouble-shooting/compaction-principles/)
and [Data Compaction](https://doris.apache.org/docs/4.x/key-features/data-compaction/)
describe the storage-engine behavior in more depth.

---

## 2.5 Table Models and Repeated Keys

Every Doris internal table has a **table model**. The model defines what a key
means when another row arrives with the same key values.

Use these three input rows:

```text
user_id | event_date | revenue
1001    | 2026-01-01 | 10.00
1002    | 2026-01-01 | 20.00
1001    | 2026-01-01 | 15.00   <- repeated Key
```

### Duplicate Key model

The Duplicate Key model retains every input row. Its key columns define the
sort key; they do not form a uniqueness constraint.

```text
1001 | 2026-01-01 | 10.00
1001 | 2026-01-01 | 15.00
1002 | 2026-01-01 | 20.00
```

This model suits append-oriented detail data such as events and logs. A Doris
`DUPLICATE KEY` is therefore not equivalent to a MySQL `PRIMARY KEY`.

### Unique Key model

The Unique Key model exposes one logical row per key. A later upsert for the
same key replaces the earlier logical row.

```text
1001 | 2026-01-01 | 15.00
1002 | 2026-01-01 | 20.00
```

This model suits mutable entity state or CDC-driven tables where the latest
value for a business key must be visible.

### Aggregate Key model

The Aggregate Key model combines value columns according to the aggregation
function declared in the DDL. If `revenue` is declared with `SUM`, repeated
keys produce:

```text
1001 | 2026-01-01 | 25.00
1002 | 2026-01-01 | 20.00
```

Other supported value-column behaviors include functions such as `MIN`, `MAX`,
and `REPLACE`; specialized types support additional aggregation functions. The
function is part of the stored-data contract, not an instruction added only at
query time.

### Choose by row semantics

| Requirement | Starting table model | Repeated-key behavior |
| --- | --- | --- |
| Retain every original event | Duplicate Key model | Keep every row |
| Keep one current row per business key | Unique Key model | Expose the latest row |
| Store a pre-aggregated metric by key | Aggregate Key model | Merge declared value columns |

All three models can use key columns for sorting. The model decision must first
match the required row semantics; query acceleration comes after correctness.

See the official [Duplicate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/duplicate/),
[Unique Key model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/),
and [Aggregate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/)
documentation.

---

## 2.6 How Doris Skips Work

Fast analytics is not only about processing scanned data quickly. It is also
about proving that physical data cannot match a predicate and avoiding that
work entirely.

### Four design tools, four responsibilities

| Design tool | Scope | Primary responsibility | Example benefit |
| --- | --- | --- | --- |
| Partitioning | Table lifecycle and coarse data range | Separate data into logical boundaries | A one-day predicate selects one daily Partition |
| Hash bucketing | Distribution within every Partition | Place rows by a stable key and balance parallel work | `user_id = 610871788` can select one matching Tablet per Partition |
| Sort key | Row order within Tablets | Cluster common filter columns together | A leading `user_id` filter narrows local key ranges |
| Prefix Index | Sparse index over the leading sort-key prefix | Locate candidate row ranges inside selected Tablets | Skip ranges whose leading key values cannot match |

These tools are complementary. A time Partition cannot replace a good sort
key for every filter. A Prefix Index cannot exclude a whole Tablet merely
because a different column appears somewhere later in the schema.

### Prefix Index and leading-key filters

Doris automatically builds a sparse **Prefix Index** from the beginning of the
sort key. The indexed prefix is limited by supported types and index length, so
the order of Key columns matters.

Suppose two tables contain identical rows:

```sql
-- Baseline sort key
DUPLICATE KEY(event_time, event_id, user_id)

-- User-first sort key
DUPLICATE KEY(user_id, event_time, event_id)
```

An equality filter on `user_id` aligns with the leading sort-key prefix of the
second table. A time-only range aligns with the leading sort-key prefix of the
first. Choosing one order creates a tradeoff; a longer sort key does not make
every predicate equally efficient.

The [Prefix Index documentation](https://doris.apache.org/docs/4.x/table-design/index/prefix-index/)
describes the automatic index and its prefix limits.

### FE pruning and BE scan reduction

The query path has two levels of data reduction:

1. **FE pruning:** while creating the distributed query plan, FE uses metadata
   to exclude Partitions and Tablets.
2. **BE scan reduction:** while executing assigned plan fragments, BE uses the
   sort key, Prefix Index, Min/Max metadata, and applicable secondary indexes
   to skip smaller data ranges inside selected Tablets.

This wording matters. **Predicate pushdown** means that BE evaluates a
predicate in the scan operator close to storage instead of passing every row to
a later Filter operator. It does not necessarily mean that FE pruned a
Partition or Tablet.

### Read `EXPLAIN` as planned evidence

`EXPLAIN` shows the distributed query plan without executing the analytical
query. In an OLAP scan, look for evidence such as:

```text
partitions=1/26
tablets=1/260
PREDICATES: event_time >= ... AND user_id = ...
```

- `partitions=1/26` means FE selected one of 26 Partitions.
- `tablets=1/260` means FE selected a smaller Tablet set from the Table's
  physical layout. Exact denominator presentation can vary by version.
- `PREDICATES` shows scan-side predicate evaluation; it is separate from the
  selected/total pruning ratios.

If the plan reports `partitions=26/26`, no Partition was excluded. That can be
correct for a user-only predicate on a table partitioned by time: all dates may
contain that user even when Hash bucketing selects fewer Tablets within each
Partition.

### Use runtime evidence for executed work

`EXPLAIN` proves the planned scan scope. Query Profile records what happened
when BE nodes executed the assigned plan fragments. Useful scan evidence
includes:

- rows examined by the scan;
- bytes examined by the scan;
- rows returned after scan-side filtering;
- scan and operator time.

Metric names can vary by Doris version, and cache state or Compaction can alter
exact values. Use controlled query pairs:

1. keep the data and query result identical;
2. change one physical-design choice;
3. compare the selected/total plan ratios and runtime scan volume;
4. confirm that both queries return the same result.

The official [Data Pruning](https://doris.apache.org/docs/4.x/key-features/data-pruning/),
[`EXPLAIN`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/),
and [Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)
documentation provide the complete inspection workflow.

---

## Lab 2: Make Doris Scan Less Data

The lab keeps the logical dataset constant while changing its physical design.
It reuses all 10,158,080 rows in `doris_course.events`; it does not read from or
write to S3.

You will:

1. Inspect the default physical design selected for the Lab 1 `events` table.
2. Map the table to its Partition, Tablet, Rowset, and Segment hierarchy.
3. Build `events_v2` with `user_id` as the leading sort-key column.
4. Compare BE runtime scan evidence for user and time filters.
5. Build `events_v3` with daily Auto Partitioning and
   `HASH(user_id)` bucketing.
6. Use storage metadata to connect load transactions, Tablet versions, and Compaction.
7. Use `EXPLAIN` to compare FE partition pruning and bucket (tablet) pruning.
8. Verify that a smaller scan scope does not change the query result.
9. Load the same repeated keys into tables using the Duplicate Key model,
   Unique Key model, and Aggregate Key model, then compare their logical
   results.

Open the notebook:

[Lab 2 — Make Doris Scan Less Data](lab2_scan_less_data.ipynb)

## Module summary

- FE parses and analyzes SQL, creates and optimizes a distributed query plan,
  prunes from metadata, and assigns plan fragments to BE nodes.
- BE nodes execute the assigned plan fragments through vectorized operators and
  Pipeline execution; Exchange operators move intermediate data when required.
- The logical namespace is Catalog, Database, and Table. Inside an internal
  Table, the physical hierarchy is Partition, Bucket/Tablet, Rowset, and
  Segment.
- A load transaction can create a new Rowset in every affected Tablet. Rowsets
  contain immutable columnar Segments.
- Background Compaction merges Rowsets within a Tablet to reduce read
  amplification while preserving the logical query result.
- The Duplicate Key model retains repeated keys, the Unique Key model exposes
  one current row per key, and the Aggregate Key model merges declared value
  columns.
- Partitioning, bucketing, the sort key, and the Prefix Index solve different
  data-skipping and placement problems.
- `EXPLAIN` shows planned partition pruning and bucket (tablet) pruning. Query
  Profile provides runtime evidence from BE execution.
- Predicate pushdown is not the same as pruning: a predicate can run inside the
  scan operator even when no entire Partition or Tablet is excluded.

## Official references

- [Apache Doris source repository](https://github.com/apache/doris)
- [System Architecture](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)
- [Storage Layout Overview](https://doris.apache.org/docs/4.x/table-design/storage-layout-overview/)
- [Partitioning and Bucketing Concepts](https://doris.apache.org/docs/4.x/table-design/data-partitioning/basic-concepts/)
- [Data Bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/data-bucketing/)
- [Duplicate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/duplicate/)
- [Unique Key model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/)
- [Aggregate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/)
- [Prefix Index](https://doris.apache.org/docs/4.x/table-design/index/prefix-index/)
- [Data Pruning](https://doris.apache.org/docs/4.x/key-features/data-pruning/)
- [Compaction Principles](https://doris.apache.org/docs/4.x/admin-manual/trouble-shooting/compaction-principles/)
- [Data Compaction](https://doris.apache.org/docs/4.x/key-features/data-compaction/)
- [EXPLAIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/)
- [Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)
- [BE plan-fragment execution source](https://github.com/apache/doris/blob/master/be/src/service/internal_service.cpp)
