# Module 10: Controlling Storage Cost and Data Lifecycle in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris · Level 3 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox and `events_modelled` from Lab 4, with the Module 9 cluster stopped |
| Estimated time | About 115 minutes: reading 60, Lab 45, quiz 10; the Lab's optional real-clock part adds a wait of up to about an hour |

[Course README](../../README.md) · [Open Lab 10](lab10_manage_data.ipynb) · [Open Quiz 10](quiz10_data_lifecycle_and_recovery.ipynb)

## Module goal

Give one growing event table a lifecycle: store the rows that must stay
online in fewer bytes, remove complete old time ranges on a schedule, and know
how to recover data that was removed by mistake.

An online commerce service has kept every event since launch. Its dashboards
mostly read recent events, storage keeps growing, some events arrive late,
and an accidental deletion must not become an unrecoverable incident. The
team makes four related decisions: how Doris compresses stored Pages, how
event time defines Partitions that can be managed, when complete old ranges
leave the online table, and which recovery mechanism applies after data is
removed. Module 9 used replicas to keep current data available during a BE
failure; this module asks what happens when old data is removed on purpose,
or when a valid delete was a business mistake.

## Learning objectives

After completing this module, you will be able to:

1. Explain the separate roles of column encoding and Page compression, and choose a compression algorithm from the constrained resource.
2. Design a fair compression comparison that keeps the input, layout, loads, and replicas equal.
3. Choose Manual, Auto, or Dynamic Partitioning from what creates and what removes Partitions.
4. Read a Dynamic Partition window from its time unit, offsets, and time zone, and predict what happens to late data.
5. Separate an accepted configuration, scheduler action, SQL visibility, and storage reclamation when a Partition expires.
6. Decide when the recycle bin is enough and when an independent backup or a replay from the source is needed.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 10.1 Define the Lifecycle Before Choosing a Feature | 6 min | State heat, retention, late-data, and recovery requirements first |
| 10.2 Understand Where Doris Compresses Data | 9 min | Relate column encoding to Page compression, and choose from the constrained resource |
| 10.3 Compare Compression Choices with Controlled Input | 8 min | Hold input and layout equal, and read the storage report conservatively |
| 10.4 Choose How Partitions Are Created and Removed | 7 min | Choose Manual, Auto, or Dynamic Partitioning |
| 10.5 Define a Rolling Window and Its Late-Data Policy | 9 min | Read a window's ranges, and decide what happens to late events |
| 10.6 Separate Configuration, Scheduling, Visibility, and Reclamation | 8 min | Verify an expiry in four layers |
| 10.7 Treat Tiered Storage as a Deployment Decision | 5 min | Place retained cold data only on real tiers |
| 10.8 Establish the Recovery Boundary Before Data Is Removed | 8 min | Use the recycle bin, a backup, or a replay for the failure at hand |
| Lab 10 | 45 min | Compare three compression settings, expire an hourly Partition, and recover a dropped one |
| Quiz 10 | 10 min | Six questions on these objectives |

## 10.1 Define the Lifecycle Before Choosing a Feature

“Manage old data” can describe several different requirements. Start by
separating them.

| Requirement | Primary Doris mechanism | Question it answers |
| --- | --- | --- |
| Store the same rows in fewer bytes | Column encoding and table-level compression | How much space does the retained data use? |
| Organize rows into manageable time ranges | Partition design | Which complete range can be added, scanned, moved, or removed? |
| Keep only a rolling online window | Dynamic Partitioning or an external lifecycle process | Which time ranges should remain queryable now? |
| Undo a recent eligible object drop | Catalog recycle bin and `RECOVER` | Can this recently removed Database, Table, or Partition return? |
| Recover from cluster loss or an old logical error | Repository backup or authoritative-source replay | Can data be restored independently of this live cluster? |
| Move colder data to a cheaper medium | Local or remote tiered storage | Where should retained cold data live? |

These mechanisms can be combined, but they are not substitutes for each
other. Compression does not remove old rows. A replica does not preserve a
previous business state. The recycle bin is not independent of the cluster.
Tiered storage changes location and cost; it does not define how long the data
is required.

### Ask the operational questions first

For an event table, write down:

- which time range supports frequent queries;
- the longest expected arrival delay for an event;
- any legal or business exceptions to the normal retention window;
- whether storage bytes, read I/O, write CPU, or query CPU is the constrained
  resource;
- the acceptable Recovery Point Objective (RPO), or how much recent data can
  be lost;
- the acceptable Recovery Time Objective (RTO), or how long restoration can
  take; and
- whether an authoritative upstream event log can replay the missing range.

These answers define the policy. SQL properties only implement it.

### Use Partition as the lifecycle unit

Module 4 introduced Partition and Bucket for query pruning and distribution.
The same hierarchy now serves data management:

```text
Table
  Partition: a business range, commonly an hour, day, or month
    Bucket -> Tablet: a distributed storage and replica unit
```

A retention operation can remove one complete Partition efficiently. It does
not need to identify and delete each expired event individually. That benefit
also creates a boundary: every row in the selected Partition leaves the online
table together.

Module 7 already covered row-level updates, deletes, `TRUNCATE`, and
`INSERT OVERWRITE`. This module focuses on storage and range lifecycle rather
than repeating those modification choices.

The policy now identifies the first cost problem: required online rows occupy
storage and must be read by queries. Before removing any history, the team
needs to understand how Doris stores those retained rows.

## 10.2 Understand Where Doris Compresses Data

Doris stores data by column. Values from the same column commonly have similar
types and patterns, which gives the storage engine more compression
opportunities than mixing complete rows together.

A useful simplified path is:

```text
logical column values
        |
        v
column encoding
        |
        v
encoded bytes divided into Pages
        |
        v
table-selected compression algorithm applied per Page
        |
        v
Segment storage
```

The two middle steps solve related but distinct problems.

### Column encoding represents values efficiently

An encoding changes the representation of values before general Page
compression. Examples include:

- dictionary encoding, which can replace repeated strings with smaller
  dictionary identifiers; and
- Run-Length Encoding (RLE), which can represent a consecutive run as a value
  plus its repeat count.

Consider an `event_type` column:

```text
cart, cart, purchase, cart, purchase, cart, ...
```

If a dictionary assigns `cart -> 0` and `purchase -> 1`, the encoded stream can
use compact identifiers. This is more precise than saying “Doris stores the
word once and makes every row point to it.” The Segment still needs enough
metadata and encoded positions to reconstruct the value for every row, and
Doris selects encodings according to storage format and data characteristics.

### Page compression finds repeated byte patterns

After encoding, each column is divided into Pages. The configured compression
algorithm operates on the bytes inside each Page. At query time Doris
decompresses the Pages required by the scan rather than decompressing an
entire table in advance.

A string does not have to repeat as a complete value to contain compressible
structure. These two messages have different event IDs but share many bytes:

```text
{"source":"commerce-web","schema":"event-v1","event_id":"101",...}
{"source":"commerce-web","schema":"event-v1","event_id":"102",...}
```

The complete values are unique. Their field names and descriptive text still
repeat. Page compression can exploit repeated byte sequences, while column
encoding can independently benefit a low-cardinality column such as
`event_type`.

### The table property chooses one compression family

Doris exposes compression as a table property:

```sql
PROPERTIES (
    "compression" = "ZSTD"
)
```

The property applies the selected compression algorithm to the table's column
Pages. It is not a per-column codec declaration. A
table can still use column-specific internal encodings, but this DDL does not
let the course assign a different compression algorithm to every column.

Apache Doris supports `none`, `LZ4`, `LZ4F`, `LZ4HC`, `ZSTD`, `Snappy`, and
`Zlib`. The local Doris 4.1.3 build used by the Lab accepts and displays the
no-Page-compression setting as `NO_COMPRESSION`. In Doris 4.x the Frontend
(FE) default is ZSTD; confirm the effective value in the target build because
an administrator can change `default_compression_type`.

### Choose from the constrained resource

The candidates below follow the quick-selection guide of Doris's Data
Compression page. Its algorithm table describes LZ4 as extremely fast with a
moderate ratio, LZ4F as fast with a moderate ratio, and ZSTD as a high ratio
with fast decompression; the guide lists LZ4F next to ZSTD for the balance of
storage cost and query performance.

| Need | Candidate to test | Reason to test it | Evidence still required |
| --- | --- | --- | --- |
| Fast decompression for frequent reads | LZ4 or Snappy | Designed for low decompression overhead | Query CPU, I/O, concurrency, and latency on the real workload |
| Balance storage and query cost | ZSTD or LZ4F | Listed together by the guide for this balance; ZSTD is the default recommendation | Stored bytes and workload measurements |
| Storage efficiency for colder data | ZSTD, Zlib, or LZ4HC | Can favor compression ratio | Load CPU, read latency, and operating cost |
| Establish a Page-compression baseline | No compression | Separates the observed effect of Page compression | Remember that encoding and table overhead still remain |

“Smaller” does not automatically mean “faster.” Reading fewer bytes can reduce
I/O, while decompression consumes CPU. The result depends on the dataset,
selected columns, storage device, cache state, concurrency, and host resources.

See [Data Compression](https://doris.apache.org/docs/4.x/table-design/column-compression/)
and the FE [`default_compression_type`](https://doris.apache.org/docs/4.x/admin-manual/config/fe-config/).

Understanding the two compression layers explains where savings can come
from. It does not tell the team whether changing the default helps its own
events, so the next step is a controlled comparison.

## 10.3 Compare Compression Choices with Controlled Input

Suppose the team is considering replacing the current default. A fair test
changes the compression algorithm and keeps the other causes of storage size
constant.

Hold these variables equal:

- columns, types, and nullability;
- Table Model and Key order;
- Partition boundaries;
- distribution column and Bucket count;
- replica count;
- input rows and generated values;
- number and shape of load batches; and
- the time at which storage metadata is sampled.

If one table was loaded twice, has more replicas, or produced more Segments,
its total size is not a controlled comparison with the others.

Reusing the same deterministic `INSERT ... SELECT` and confirming equal row
counts supports the intended comparison.

### Design data that exposes two different patterns

Lab 10 copies a bounded event day and adds a generated `event_context` string.
Each complete string includes a unique `event_id`, so complete contexts do not
repeat. The JSON keys, source, schema, pipeline, and message text do repeat.

The comparison therefore asks two questions:

1. Does a low-cardinality value such as `event_type` offer an encoding
   opportunity?
2. When entire strings are unique, do their shared byte patterns still give
   Page compression useful work?

The SQL can establish value shape:

```sql
SELECT event_type,
       COUNT(*) AS event_count,
       COUNT(DISTINCT event_context) AS distinct_contexts
FROM compression_example
GROUP BY event_type;
```

If `distinct_contexts = event_count`, complete messages are unique. That
explains why compression can still find structure in unique strings; it says
nothing about how many bytes either column saved.

### Read the storage report conservatively

Use `SHOW CREATE TABLE` to identify the declared or effective algorithm. Use
`SHOW DATA` and related metadata to read Doris's current stored-size report.
`SHOW DATA` includes the total data volume of all replicas, so replica count
must remain equal or be accounted for.

For a controlled comparison, a useful result has this shape:

| Algorithm | Logical rows | Partitions | Tablets | Replicas per Tablet | Reported stored size |
| --- | ---: | ---: | ---: | ---: | ---: |
| No Page compression | equal | equal | equal | equal | measured value |
| LZ4F | equal | equal | equal | equal | measured value |
| ZSTD | equal | equal | equal | equal | measured value |

The equal fields establish the controlled layout. The size field establishes
what Doris currently reports for the entire table. File headers, indexes,
Segment count, small-table overhead, metadata reporting delay, and rounding can
all affect the result.

### Make only the decision supported by the test

The comparison can support statements such as:

- the compressed tables store the same intended logical input;
- one algorithm used fewer reported bytes for this input and layout; or
- the difference was too small to justify changing the default on storage
  evidence alone.

It cannot support statements such as:

- one field accounts for all saved bytes;
- the measured percentage applies to production data;
- the smallest table has the lowest query latency; or
- the fastest single run identifies the best algorithm.

To change a production default, repeat the comparison with representative data
volume, load batch shape, selected-column patterns, concurrent queries, and
host resources. Measure storage, load cost, query CPU, bytes read, and latency.

Even the best compression result only makes retained rows smaller. The table
will still grow without limit if no old range ever leaves the online dataset.
The team must next choose a Partition lifecycle.

See [`SHOW DATA`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/data-and-status-management/SHOW-DATA/).

## 10.4 Choose How Partitions Are Created and Removed

Compression reduces the bytes used by retained rows. Retention controls which
rows remain online. In Doris, the retention design commonly starts with Range
Partitions over an event-time column.

Three Partition modes answer different creation questions:

| Mode | What creates a Partition? | Appropriate scenario | Lifecycle consequence |
| --- | --- | --- | --- |
| Manual Partitioning | Explicit table DDL or `ALTER TABLE` | Stable or business-defined ranges requiring precise control | Application or operator also manages later additions and removals |
| Auto Partitioning | An incoming Partition value during data ingestion | Sparse, unpredictable, or data-driven values | Creates missing Partitions on demand; AUTO RANGE tables can use `partition.retention_count = N` to retain only the N newest historical ranges |
| Dynamic Partitioning | A scheduler interpreting current time and table properties | Predictable time-series window with future pre-creation and rolling expiry | Creates and removes complete time ranges according to offsets |

Auto Partitioning is the recommended general approach for automatic creation
in current Doris documentation. Dynamic Partitioning remains the relevant
choice when the requirement specifically includes a clock-driven rolling
window: ranges counted back from the current time, with future ranges created
in advance.

### Keep Partition creation and retention separate

Suppose late files can contain arbitrary historical dates. Auto Partitioning
can create ranges from those incoming values. That solves unpredictable
creation. Retention is a separate setting: an Auto Range Partition table can
set `partition.retention_count`, and the same FE scheduler that runs Dynamic
Partitioning then keeps only that many historical ranges, the ones with the
latest values, and always keeps the current and future ranges. That rule
counts ranges; it does not define a window of days relative to today, and it
cannot be combined with Dynamic Partitioning on one table.

Suppose the commerce event table must always contain the last seven
calendar-day ranges and prepare tomorrow's Partition. Dynamic Partitioning
expresses that rolling clock rule. It may reject a row whose event time falls
outside every currently retained Partition.

Suppose a finance table closes one accounting period only after approval.
Manual Partitioning can keep the boundary under explicit business control.

### Understand the Dynamic Partition limits

Dynamic Partitioning supports:

- Range Partitioning;
- one `DATE` or `DATETIME` Partition Key; and
- `HOUR`, `DAY`, `WEEK`, `MONTH`, or `YEAR` scheduling units.

It does not calculate an independent expiry timestamp for every row: there is
no per-row time to live and no minute-level Dynamic Partition unit.

See [Manual Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/manual-partitioning/),
[Auto Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/auto-partitioning/),
and [Dynamic Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning/).

For this service, event ranges are predictable and the requirement includes
clock-driven removal, so Dynamic Partitioning fits the main path. Choosing the
mode is only the start; the team must express the actual business window and
its late-data policy.

## 10.5 Define a Rolling Window and Its Late-Data Policy

Dynamic Partition properties describe a window relative to the scheduler's
current time. The commerce team chooses a production policy with seven
calendar-day ranges through today and one range prepared for tomorrow.

Consider:

```sql
PROPERTIES (
    "dynamic_partition.enable" = "true",
    "dynamic_partition.time_unit" = "DAY",
    "dynamic_partition.start" = "-6",
    "dynamic_partition.end" = "1",
    "dynamic_partition.create_history_partition" = "true",
    "dynamic_partition.time_zone" = "Asia/Shanghai"
)
```

During calendar day `D0`, the intended window contains:

```text
D-6  D-5  D-4  D-3  D-2  D-1  D0  D+1
 |                             |    |
oldest retained day          today  prepared tomorrow
```

With historical creation enabled, these settings create eight daily
Partitions: six previous days, the current day, and one future day. Each Range
Partition uses a left-closed, right-open interval:

```text
[2026-09-22 00:00:00, 2026-09-23 00:00:00)
```

The first seven ranges form the current online retention window; the eighth
accepts tomorrow's early writes. An event exactly at
`2026-09-23 00:00:00` belongs to the next Partition, not the one ending at
that timestamp.

### Read each property as a decision

| Property | Decision |
| --- | --- |
| `time_unit` | Granularity at which complete ranges are created and removed |
| `start` | Earliest relative range retained; older ranges become eligible for removal |
| `end` | How far into the future Doris pre-creates ranges |
| `time_zone` | Clock used to calculate the boundaries |
| `create_history_partition` | Whether ranges between `start` and now are created during initial setup |
| `reserved_history_periods` | Explicit historical ranges exempted from normal removal |

For weekly and monthly units, start-day properties further define the boundary.
The session time zone used to generate event timestamps and the Dynamic
Partition time zone should be intentionally aligned, or the operator can
misread which Partition owns a row.

### A row expires with its whole day

Suppose the current date in `Asia/Shanghai` is `2026-09-28` and an event
timestamp is `2026-09-22 09:20:00`. With `start = -6`, it belongs to
`[2026-09-22, 2026-09-23)`, the oldest retained Partition. At midnight on
`2026-09-29`, the relative window advances and that complete Partition becomes
eligible for removal.

The event does not disappear exactly seven 24-hour periods after its own
timestamp. Every other row in that calendar-day range shares the same
lifecycle. Removal also waits for the scheduler to perform its next check.

### Define what happens to late data

A late event can fall into one of three cases:

1. Its timestamp still belongs to an online Partition, so the row can be
   written normally.
2. Its timestamp belongs to a deliberately reserved historical period, so the
   exception can remain online.
3. Its timestamp belongs to no Partition because the range has expired or was
   never created, so a normal insert fails with a missing-Partition error.

The third case requires a business choice: reject the event, send it to a
separate late-data path, create and manage a historical Partition explicitly,
or replay it into another authoritative system. Dynamic Partitioning cannot
infer that policy.

### Map the policy to an observable Lab window

Waiting a full day would make a poor guided exercise. Lab 10 applies the same
boundary logic with `HOUR`, `start = -3`, and `end = 1`. It places a known
event in the oldest hourly Partition and then moves the window forward by one
hour, or optionally waits for the next whole-hour boundary on the real clock.
This changes the demonstration scale, not the meaning of Dynamic Partitioning.
The hourly Lab setting is not a production recommendation for this commerce
service.

Defining the window still does not prove that Doris has acted on it. The team
must now distinguish an accepted policy from scheduler activity, online data
visibility, and eventual storage reclamation.

## 10.6 Separate Configuration, Scheduling, Visibility, and Reclamation

An accepted `CREATE TABLE` or `ALTER TABLE ... SET` statement proves that Doris
accepted the properties. It does not prove that the scheduler has already
created or dropped the intended Partition.

The Dynamic Partition thread checks tables according to the FE setting
`dynamic_partition_check_interval_seconds`. The documented default is 600
seconds, but deployments can change it. The interval determines when the
scheduler notices work; it does not change the configured `DAY` boundary or
give each row an individual expiry timestamp. Dynamic Partitioning supports
`HOUR` as its finest unit, while the production policy in this course uses
`DAY`.

### Use a four-layer evidence sequence

| Layer | Evidence | What it answers |
| --- | --- | --- |
| Policy definition | `SHOW CREATE TABLE` or table properties | What rule is configured? |
| Scheduler observation | `SHOW DYNAMIC PARTITION TABLES` | Is scheduling enabled, when did it run, and did create/drop report an error? |
| Online ranges | `SHOW PARTITIONS` | Which Partition boundaries currently exist? |
| Business visibility | A focused `SELECT` | Are the expected rows currently queryable? |

Useful scheduler fields include `Enable`, `State`, `LastSchedulerTime`,
`LastCreatePartitionMsg`, and `LastDropPartitionMsg`. A `NORMAL` state is not a
substitute for inspecting actual ranges or querying the business row.

### Observe expiry by moving the window or by waiting for the clock

Two observations show the scheduler removing an expired range, and neither
issues a manual `DROP PARTITION`:

- **Move the window.** Narrowing `start` by one unit makes the change that the
  clock makes one unit later: the oldest retained range falls outside the
  window. The scheduler removes it at its next check. In the course sandbox,
  setting `dynamic_partition_check_interval_seconds` to a few seconds makes
  that check happen almost at once, because the scheduler notices a changed
  interval within a few seconds. The setting applies to the whole FE, so the
  Lab restores it afterwards. This shows the removal, not the boundary
  arriving on its own.
- **Wait for the clock.** Record the oldest Partition boundary, wait until the
  next boundary for the configured unit, and then perform a bounded scheduler
  wait without changing the rule. If the boundary has not arrived, the Lab
  reports when to return and stops; after it, a bounded wait displays elapsed
  time and the last known scheduler state. The wait measures scheduling delay
  after eligibility, not a row-level TTL duration.

In production, neither change is a way to remove data early: narrowing `start`
drops every range it excludes, and the FE interval affects every
Dynamic Partition table.

### Logical disappearance is not physical reclamation

When a Partition leaves `SHOW PARTITIONS` and its rows no longer appear in SQL,
the online logical range is gone. This does not prove that every underlying
byte has already disappeared from BE storage.

Recycle-bin retention, metadata cleanup, and background storage work can occur
on different schedules. Do not infer immediate physical reclamation from:

- a zero-row SQL result;
- a Partition missing from the online table;
- a change in one reported size; or
- a Compaction that the Lab did not directly observe.

This evidence sequence tells the team when data has left the online dataset.
If older data must remain queryable instead of expiring, the next decision is
whether a real lower-cost storage tier is available.

## 10.7 Treat Tiered Storage as a Deployment Decision

Retention removes a range from the online table. Tiering keeps data available
while changing where it is stored.

### Local SSD and HDD tiering

In an integrated storage and compute deployment with actual SSD and HDD data paths, a
Partition can begin on SSD and move to HDD after a cooldown time. The choice
uses Partition storage properties such as `storage_medium` and
`storage_cooldown_time`.

This requires BEs with correctly configured SSD and HDD storage paths.

### Local and remote tiering

In the integrated storage and compute architecture, a Storage Policy can move colder data to an
S3-compatible object store or HDFS while hot data remains local. This can
reduce local storage cost, but it adds remote-storage availability, network,
security, and query-latency considerations.

Remote tiering is different from backup:

- tiered data remains part of the live table;
- a backup is a point-in-time snapshot in a Repository; and
- storage-policy tables have backup/restore restrictions that must be checked
  for the current Doris release.

The decoupled storage and compute architecture has its own storage and cache
model. Do not mix its assumptions with this Lab, which runs integrated storage
and compute.

Lab 10 runs on one Docker disk with no object storage, so it cannot show data
moving between tiers; this section therefore treats tiering as a deployment
choice, without a Lab step.

Tiering can lower the cost of data that remains part of the live table, but it
does not preserve an earlier business state. The final lifecycle decision is
how to recover when a valid deletion was a mistake or the live cluster is no
longer a usable recovery source.

See the [Tiered Storage overview](https://doris.apache.org/docs/4.x/table-design/tiered-storage/overview/).

## 10.8 Establish the Recovery Boundary Before Data Is Removed

Module 9 showed that replicas protect availability when a node is unavailable.
If a valid `DROP PARTITION` operation is committed, every healthy replica
converges on the new logical state. More replicas do not restore the old
business state.

The commerce team therefore defines the recovery path before enabling routine
expiry or allowing operators to remove ranges. A short-lived, same-cluster
undo mechanism and an independent disaster-recovery copy solve different
failures.

Choose recovery according to the failure:

| Failure | Appropriate recovery path |
| --- | --- |
| A BE temporarily stops | Replica availability and repair |
| A recent Database, Table, or manual Partition was dropped without `FORCE` | Catalog recycle bin and `RECOVER` while eligible |
| An object was dropped with `FORCE` | Independent backup or authoritative-source replay |
| Rows were changed or deleted through another data operation | Operation-specific correction, backup, or replay; do not assume `RECOVER` applies |
| Entire cluster or failure domain is lost | Repository backup restored to a viable cluster, or source replay |
| Dynamic retention removed an old range | Follow the designed archive/backup policy; do not depend on an accidental recycle-bin opportunity |

### Use the recycle bin for an eligible object drop

Without `FORCE`, a dropped Database, Table, or formal Partition can enter the
catalog recycle bin. Inspect it before recovery:

```sql
SHOW CATALOG RECYCLE BIN
WHERE NAME = 'p_recover';
```

Relevant identity fields include:

- object `Type` and `Name`;
- `DbId`, `TableId`, and `PartitionId`; and
- `DropTime`.

The documented default `catalog_trash_expire_second` is 86,400 seconds, or 24
hours. This is a configurable maximum retention period, not a recovery
guarantee. An entry can become ineligible or be purged, and `DROP ... FORCE`
bypasses this recovery path.

### Understand name-only recovery

Doris allows recovery by name without supplying an object ID. When several
deleted objects have the same name, name-only recovery selects the most
recently deleted matching metadata.

That is useful in a controlled exercise where the target was just dropped. In
a real incident, it can be ambiguous. Inspect the IDs and `DropTime`, then
identify the intended object explicitly when necessary. After `RECOVER`, verify
the structure and known business data; command success alone does not establish
that the correct historical object returned.

### Keep cleanup syntax out of the recovery lesson

An idempotent Lab may use:

```sql
DROP TABLE IF EXISTS lab_owned_table FORCE;
```

to remove an obsolete Lab-owned object before rebuilding it. That is reset
logic. The recovery demonstration must use a separate, deliberate drop without
`FORCE`:

```sql
ALTER TABLE recovery_example
DROP PARTITION p_recover;
```

Do not infer a production deletion recommendation from a sandbox reset.

### The recycle bin is not a backup

Recycle-bin metadata and data belong to the same Doris cluster and have a
limited retention window. A Repository backup creates a point-in-time snapshot
in independent remote storage and can support accidental deletion recovery,
cross-cluster migration, or disaster recovery.

Current Doris backup/restore documentation also lists limits that affect this
course sequence: the decoupled storage and compute architecture and tables using Storage Policies
are not supported by this backup path; asynchronous materialized views must be
rebuilt; `colocate_with` is not retained; and Dynamic Partitioning must be
re-enabled after restore. Recheck the target release before writing a recovery
runbook.

Test both RPO and RTO. A backup that exists but has never been restored does
not establish that the team can meet its recovery target.

See [Restore from Recycle Bin](https://doris.apache.org/docs/4.x/admin-manual/data-admin/recyclebin/),
[`RECOVER`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/recycle/RECOVER/),
and [Backup and Restore](https://doris.apache.org/docs/4.x/admin-manual/data-admin/backup-restore/overview/).

## Lab 10: Compare Compression and Verify a Partition Lifecycle

Open [Lab 10 — Compare Compression and Verify a Partition Lifecycle](lab10_manage_data.ipynb)
after completing Lab 9, and plan about 45 minutes; its optional real-clock part
needs you to come back after the next whole hour.
The Lab returns to the single-node `doris-rta` container from Modules 1–8 and the
`doris_course` Database. It reads one bounded day from `events_modelled`, does
not modify that source, and creates only Module 10 objects. It does not access
Amazon S3.

| Lab section | What you do | What the result establishes |
| --- | --- | --- |
| **1. Compare compression choices on structured event logs** | Check the bounded source day, load identical `NO_COMPRESSION`, `LZ4F`, and `ZSTD` copies, compare event count with distinct generated messages, and wait for the storage reports. | Layout, rows, load shape, and replica count stay equal while the Page-compression setting changes; Doris reports a whole-table storage difference for this sample, which does not isolate one column or rank CPU performance. |
| **2. Create an hourly Dynamic Partition window** | Rebuild a Dynamic Partition table with `HOUR`, `start=-3`, `end=1`, history creation, and `Asia/Shanghai`; insert events three hours ago, two hours ago, and now. | Five complete hourly ranges represent the rolling rule, and a row stays online with its complete hour until the window advances and the scheduler acts. |
| **3. Move the window forward and observe automatic expiry** | Narrow `start` from `-3` to `-2`, set the FE check interval to 10 seconds, wait for the oldest hour to disappear, restore the interval, and repeat the focused SQL. | The scheduler, not a manual drop, removes every complete range older than `start`; the oldest event leaves the online table, which does not prove that its bytes were already reclaimed. |
| **Try an event outside the current window** | Insert an event older than the window and require the missing-Partition error. | Dynamic Partitioning does not silently recreate expired history. |
| **Optional: watch the same expiry on the real clock** | Rebuild the Section 2 window, skip the shortcut cell of Section 3, and return after the printed boundary for a bounded scheduler wait. | Natural expiry removes the oldest range without any change to the rule; the wait reports scheduling delay rather than row-TTL precision. |
| **4. Recover a manually dropped Partition without a pre-recorded ID** | Create a separate manually partitioned table, drop one Partition without `FORCE`, inspect the recycle bin, recover by name, and rerun the business summary. | The recovery example is isolated from the scheduler; name-only recovery restores the just-dropped object in this controlled case, while IDs remain necessary when names are ambiguous. |
| **Stop and Restart** | Optionally stop the container, restart it, reconnect, and count the Lab-owned tables. | Named-volume persistence retains the local objects; it does not prove backup or cross-cluster recovery. |

Read the evidence in this order:

1. source and row checks define the logical input;
2. DDL and FE configuration identify the effective compression or retention
   rule;
3. storage metadata or scheduler metadata report the current physical or
   scheduling state;
4. `SHOW PARTITIONS` reports online ranges;
5. SQL reports the visible business answer; and
6. recycle-bin metadata identifies an eligible dropped object.

Only the optional clock-dependent step can span two Notebook sessions. There,
do not rerun the setup after the boundary, because rebuilding the table would
replace the evidence with a new window.

The Lab ends with a practice: predict a daily Dynamic Partition window before
you create it. Predict the result first, then write the code in the empty cell;
the collapsed reference solution after it also runs with Run All and leaves the
Lab's tables as they were.

## Summary

- Doris encodes each column's values, for example with a dictionary or
  run-length encoding, and then compresses the encoded bytes Page by Page with
  the table's algorithm; choose the algorithm from the constrained resource,
  ZSTD by default, LZ4 or Snappy when decompression CPU is the bottleneck.
- A fair comparison changes only the `compression` property: the same rows
  and load batches, the same Table Model, Partitions, Buckets, and replicas;
  its storage report then shows a difference for that sample, not a query
  speed.
- Manual Partitioning keeps creation and removal under explicit control. Auto
  Partitioning creates Partitions from incoming values; AUTO RANGE tables can
  retain the newest N historical ranges with `partition.retention_count`.
  Dynamic Partitioning keeps a window relative to the current time and creates
  future ranges in advance.
- A Dynamic Partition window is a set of half-open ranges counted from
  `start` to `end` in its `time_unit` and `time_zone`; a row leaves with its
  whole range, and a late event outside every range fails to load unless a
  late-data path handles it.
- An accepted `ALTER` sets the rule, the scheduler applies it at its next
  check, `SHOW PARTITIONS` and a query show what is online, and none of them
  shows when the BE has reclaimed the bytes.
- The recycle bin can restore a recent drop made without `FORCE`, for a
  limited time and inside the same cluster; replicas copy deletions too, so a
  dropped range with `FORCE`, an expired window, or a lost cluster needs an
  independent backup or a replay from the source.

## Quiz 10: Controlling Storage Cost and Data Lifecycle in Apache Doris

Open [Quiz 10: Controlling Storage Cost and Data Lifecycle in Apache Doris](quiz10_data_lifecycle_and_recovery.ipynb).
It has six single-choice questions and needs no running environment.

Next: this is the last module of the course.

## Where the course leaves you

Across ten modules, one event dataset took you through the work of a real-time
analytics system on Doris:

- **Level 1** started a sandbox, separated the FE's planning from the BE's
  storage and execution, and loaded data with Stream Load, the S3 TVF, and
  Routine Load, checking each load and making its retry safe.
- **Level 2** modeled the events into detail and summary tables, analyzed them
  in stages with functions and windows, joined them with a product dimension,
  and kept the current state of orders correct through updates and deletes.
- **Level 3** accelerated queries without changing their answers, spread one
  table over a cluster that survived a failed FE and a stopped BE, and gave the
  data a lifecycle with a tested way back.

Throughout, every result was checked three ways: the business answer, the plan
that `EXPLAIN` shows, and the work that the Query Profile records. Keep that
habit: it is what lets you trust a Doris design on your own data.

When you are done, remove the containers, volumes, and network of the course
with the commands in the Clean up section of the [course README](../../README.md).
To go further, the [Apache Doris documentation](https://doris.apache.org/docs/4.x/getting-started/what-is-apache-doris/)
covers every feature of this course in depth. The other courses in this
repository, on data warehousing, observability, and AI integrations, build on
the same Doris skills in other scenarios; each one stands on its own.

## References

- Compression: [Data Compression](https://doris.apache.org/docs/4.x/table-design/column-compression/), [FE Configuration](https://doris.apache.org/docs/4.x/admin-manual/config/fe-config/), and [`SHOW DATA`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/data-and-status-management/SHOW-DATA/)
- Partition modes: [Manual Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/manual-partitioning/), [Auto Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/auto-partitioning/), and [Dynamic Partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning/)
- Tiering: [Tiered Storage](https://doris.apache.org/docs/4.x/table-design/tiered-storage/overview/)
- Recovery: [Restore from Recycle Bin](https://doris.apache.org/docs/4.x/admin-manual/data-admin/recyclebin/), [`SHOW CATALOG RECYCLE BIN`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/recycle/SHOW-CATALOG-RECYCLE-BIN/), [`RECOVER`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/recycle/RECOVER/), and [Backup and Restore](https://doris.apache.org/docs/4.x/admin-manual/data-admin/backup-restore/overview/)
