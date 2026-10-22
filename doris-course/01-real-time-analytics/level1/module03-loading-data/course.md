# Module 3: Loading Data into Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Lab 1; Lab 3 also starts a Kafka broker |
| Estimated time | About 85 minutes: reading 45, Lab 30, quiz 10 |

[Course README](../../README.md) · [Open Lab 3](lab03_load_data.ipynb) · [Open Quiz 3](quiz03_load_methods_and_retry_safety.ipynb)

## Module goal

Choose a load method from what the source and its consumers require, then
check every load's result and make its retry safe.

A load is a contract: where the data is, whether it is bounded or continuous,
how quickly it must become visible, which transformations it needs, what
evidence of completion the client receives, and which state stops a retry
from loading the same data twice.

## Learning objectives

After completing this module, you will be able to:

1. Select a Doris load method from the source, volume, latency, transformation, and retry requirements of a workload.
2. Explain the roles of Stream Load, `INSERT INTO SELECT` with the S3 TVF, Routine Load, and Group Commit.
3. Load a local CSV file with Stream Load and read its synchronous JSON response.
4. Query Parquet objects with the S3 TVF and persist them with `INSERT INTO SELECT`.
5. Explain when a Routine Load job fits continuous Kafka consumption, and how it tracks its progress.
6. Validate loaded and filtered row counts, recognize a rejected load, and retry a batch safely.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 3.1 Select a Load Method from a Workload Contract | 7 min | Match the source and its requirements to a load method |
| 3.2 Push a Bounded File with Stream Load | 10 min | Explain parsing, mapping, quality counts, and label-based retry protection |
| 3.3 Read S3 Objects and Persist a SQL Result | 7 min | Separate reading S3 through the S3 TVF from the `INSERT INTO SELECT` that stores the rows |
| 3.4 Continuously Load Kafka Data with Routine Load | 10 min | Explain jobs, tasks, micro-batches, committed offsets, and job state |
| 3.5 Reduce Small-Write Pressure with Group Commit | 5 min | Distinguish grouping small writes from a source connector |
| 3.6 Validate Results and Design Safe Retries | 6 min | Choose the completion, quality, and retry evidence of each method |
| Lab 3 | 30 min | Load a CSV file, Parquet objects, and Kafka JSON with three methods |
| Quiz 3 | 10 min | Six questions on these objectives |

## 3.1 Select a Load Method from a Workload Contract

A file extension does not fully describe a load requirement. A CSV file may
be a five-row upload from a laptop or a multi-terabyte object set in remote
storage. Both contain CSV records, but they require different operational
contracts.

Evaluate these questions before choosing a load method:

| Requirement | Question to ask |
| --- | --- |
| Source | Is the data on a client host, in object storage, or arriving in Kafka? |
| Volume and boundedness | Is this one bounded batch, a fixed object set, many tiny writes, or a continuous stream? |
| Latency | Must the caller know the result before returning, or may a managed job make data visible asynchronously? |
| Delivery direction | Does a client push bytes, does Doris read remote objects, or does Doris continuously consume messages? |
| Transformation | Is column mapping sufficient, or is a full SQL query needed? |
| Completion evidence | Is success reported by an HTTP response, a SQL statement, or a long-running job state? |
| Retry state | Does Doris remember a label, does an orchestrator track an object set, or does a job track Kafka offsets? |

### Method selection map

| Workload contract | Recommended starting point | Deciding requirement |
| --- | --- | --- |
| A client has one bounded local CSV or JSON batch and needs an immediate per-batch response | Stream Load | The client pushes bytes and receives synchronous transaction and quality evidence |
| Parquet objects already exist in S3-compatible storage and SQL must inspect or transform them | S3 TVF with `INSERT INTO SELECT` | Doris reads a temporary relation, and one SQL statement persists its result |
| A Kafka topic keeps receiving CSV or JSON messages | Routine Load | A Doris-managed, long-running Kafka consumer job maintains continuous progress |
| An application sends frequent tiny `INSERT INTO VALUES` or Stream Load writes | Group Commit with the existing write method | Compatible small writes should share fewer server-side load transactions |

These are alternatives selected for different workloads, not four mandatory
stages of one data pipeline. For example, a Routine Load job is not needed to
copy a fixed Parquet object set, and an S3 TVF does not manage Kafka offsets.

### Bounded and continuous sources

A **bounded source** has a known end: one client file, one request body, or one
fixed set of objects. A **continuous source** can receive new records after the
load starts.

```text
Bounded client file                 Fixed remote object set
        |                                      |
        | HTTP push                            | Doris reads
        v                                      v
   Stream Load                         S3 TVF -> SELECT
                                              |
                                              v
                                     INSERT INTO target

Continuous Kafka topic              Frequent tiny application writes
        |                                      |
        | Doris consumes                       | INSERT / Stream Load
        v                                      v
 Routine Load job                         Group Commit
```

All four mechanisms can participate in transactional writes, but they expose
different control and completion models. Select the model that matches the
producer rather than forcing every source through the same interface.

See the official [Load Overview](https://doris.apache.org/docs/4.x/data-operate/import/load-manual/)
for the complete load-method matrix.

## 3.2 Push a Bounded File with Stream Load

**Stream Load** is an HTTP-based load method for a bounded client-side byte
stream. It is commonly used for local CSV or JSON files and for applications
that can send a batch in an HTTP request.

In the course sandbox, the client sends a request to the Frontend (FE) HTTP
port. FE authenticates and redirects the request to a Backend (BE). The BE
parses and writes the rows, and the load transaction is committed through FE.
The client receives one synchronous JSON response.

```text
Client-local CSV
      |
      | HTTP PUT + Stream Load headers
      v
Frontend (FE) ---- redirect ----> Backend (BE)
      ^                                |
      |                                | parse, map, filter, write
      |                                v
      +---------- JSON response -- load transaction
```

`curl --location-trusted` follows the authenticated FE-to-BE redirect. In a
secured environment, use TLS and an appropriately scoped Doris account rather
than the password-free local course account.

### Make the parsing contract explicit

The request headers describe how Doris should interpret the byte stream. A
Stream Load request has this shape:

```bash
curl --location-trusted -u root: \
  -H "label:module3_csv_<run_id>" \
  -H "format:csv" \
  -H "column_separator:|" \
  -H "strict_mode:true" \
  -H "max_filter_ratio:0" \
  -H "columns:event_time,event_id,user_id,event_type,region,product_id,revenue" \
  -T stream_events.csv \
  -X PUT http://127.0.0.1:18030/api/doris_course/events_stream/_stream_load
```

The request goes to FE's HTTP port (`8030` in Doris; host port `18030` in the
course sandbox). FE answers with a redirect to a BE, and `--location-trusted`
lets curl follow it with the same credentials.

| Header | Responsibility |
| --- | --- |
| `label` | Identifies one batch for duplicate protection and retry inspection |
| `format` | Selects the input parser |
| `column_separator` | Defines the boundary between CSV fields; the Stream Load default is a tab character |
| `strict_mode` | Controls how invalid type conversions are handled |
| `max_filter_ratio` | Sets the tolerated proportion of malformed rows before the transaction fails |
| `columns` | Maps source fields to target columns and can define derived columns |
| `where` | Optionally excludes valid rows that are outside the target selection |

The separator is part of the data contract. A pipe-separated file is still
read by the CSV parser, but `column_separator:|` must be supplied because the
bytes do not use the default tab separator.

### Map, transform, and select rows

The `columns` header can first assign source fields to temporary names and then
derive target columns:

```text
columns:
  event_time,event_id,user_id,event_type,region_raw,product_id,revenue_raw,
  region=upper(region_raw),
  revenue=cast(revenue_raw as decimal(12,2))
```

This mapping performs two separate jobs:

- it declares which source field supplies each value;
- it applies expressions before the row reaches the target table.

A `where` header applies a selection rule. A valid row excluded by `where` is
**unselected**; it is not a malformed row.

### Read the synchronous response

A successful Stream Load response contains evidence such as:

```json
{
  "Status": "Success",
  "Label": "module3_csv_001",
  "TxnId": 1842,
  "NumberTotalRows": 1024,
  "NumberLoadedRows": 1024,
  "NumberFilteredRows": 0,
  "NumberUnselectedRows": 0
}
```

`TxnId` and timing values vary on every run. Interpret the stable fields:

| Field | Meaning |
| --- | --- |
| `Status` | Overall request and transaction outcome |
| `Label` | Batch identity supplied by the client |
| `ExistingJobStatus` | State of the earlier batch when `Status` is `Label Already Exists` |
| `TxnId` | Doris transaction identifier for the attempted load |
| `NumberTotalRows` | Source rows processed by the request |
| `NumberLoadedRows` | Rows accepted by the load |
| `NumberFilteredRows` | Malformed or nonconforming rows removed by quality rules |
| `NumberUnselectedRows` | Valid rows excluded by a `where` selection |
| `ErrorURL` | Temporary diagnostic URL for sample error rows when Doris provides one |

For a successful selected batch, reconcile the response rather than reading
only `Status`:

```text
total rows = loaded rows + filtered rows + unselected rows
```

### Distinguish a filtered row from a rejected transaction

A **filtered row** is an individual source row that cannot satisfy the parsing,
type, or data-quality contract. A **rejected transaction** is the outcome for
the complete batch when the filtered-row ratio exceeds `max_filter_ratio`.

If one `revenue` value is `not-a-number` and `max_filter_ratio` is `0`, Doris
reports the conversion problem and rejects the complete load transaction. The
other valid rows from that request do not become visible. When the response
contains `ErrorURL`, retrieve it promptly:

```bash
curl "<ErrorURL from the Stream Load response>"
```

`ErrorURL` is a short-lived diagnostic resource, not durable audit storage.
The source pipeline should retain its own rejected data and error history.

### Retry the same batch with the same label

An HTTP connection can fail after Doris commits but before the client receives
the response. The client then knows that the result is uncertain, not that the
transaction failed.

Retry the same bytes with the **same label**. If the earlier load finished,
Doris reports that the label already exists and does not append the batch
again. Inspect `ExistingJobStatus`: `FINISHED` means the earlier batch
succeeded, while `RUNNING` means the client should wait for its outcome. A
different label represents a new load transaction and can append the same rows
again to a Duplicate Key model table.

```text
First request
  bytes A + label L ----> transaction commits
  response is lost

Safe retry
  bytes A + label L ----> existing successful label; no second commit

New write
  bytes A + label M ----> new transaction
```

This provides label-based At-Most-Once duplicate protection for one Stream
Load batch. It does not identify semantic duplicates across different source
batches.

See the official [Stream Load documentation](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/)
for the complete request headers, response fields, and label states.

## 3.3 Read S3 Objects and Persist a SQL Result

The **S3 table-valued function (S3 TVF)** exposes files in S3-compatible object
storage as a temporary relation. It supports formats including Parquet, CSV,
JSON, and ORC.

```sql
SELECT
    event_time,
    event_id,
    user_id,
    event_type,
    region,
    product_id,
    revenue
FROM S3(
    "uri" = "s3://course-bucket/events/*.parquet",
    "s3.endpoint" = "https://s3.us-east-1.amazonaws.com",
    "s3.region" = "us-east-1",
    "s3.access_key" = "<read-only access key>",
    "s3.secret_key" = "<read-only secret key>",
    "format" = "parquet"
)
LIMIT 10;
```

The `SELECT` reads remote objects while the query runs. It does not create an
internal table and does not persist the result in Doris-managed storage.

This example reads a private bucket, so it passes a read-only key pair. The
course bucket in Lab 3 is public: there the two key properties are replaced by
`"s3.credentials_provider_type" = "ANONYMOUS"`, which tells Doris to send
unsigned requests instead of looking for credentials.

The course's S3 calls also set `"s3.connection.timeout" = "10000"` and
`"s3.connection.request.timeout" = "30000"` (milliseconds). By default Doris
gives up on a connection that takes more than 1 second to open, or on a read
that receives no data for 3 seconds. A slow network or a proxy can exceed both,
and the query then fails with `curlCode: 28, Timeout was reached`. With the
longer timeouts, the same network only makes the read slower.

### Persist the result with `INSERT INTO SELECT`

`INSERT INTO SELECT` saves the result of a query into a target internal table:

```sql
INSERT INTO events_s3 (
    event_time,
    event_id,
    user_id,
    event_type,
    region,
    product_id,
    revenue
)
SELECT
    event_time,
    event_id,
    user_id,
    event_type,
    region,
    product_id,
    revenue
FROM S3(
    "uri" = "s3://course-bucket/events/*.parquet",
    "s3.endpoint" = "https://s3.us-east-1.amazonaws.com",
    "s3.region" = "us-east-1",
    "s3.access_key" = "<read-only access key>",
    "s3.secret_key" = "<read-only secret key>",
    "format" = "parquet"
);
```

```text
S3 Parquet objects
        |
        | S3 TVF read
        v
temporary relation
        |
        | SELECT projection / filtering / transformation
        v
INSERT INTO target internal table
        |
        v
committed rows in Doris-managed storage
```

The responsibilities remain distinct:

- the S3 TVF accesses and parses the remote files;
- `SELECT` defines projection, filtering, joins, or expressions;
- `INSERT INTO` creates the load transaction that persists the query result.

Use an explicit target column list so a schema-order change does not silently
redirect values to the wrong columns. Add `CAST` only when source and target
types require conversion; a matching Parquet schema does not need decorative
casts.

### Completion and retry state

`INSERT INTO SELECT` is synchronous: the SQL client receives the statement
outcome. The Lab's statement has no label, so blindly rerunning a successful
statement is a new load transaction: on a Duplicate Key model target, it
appends another copy of every row. `INSERT INTO <table> WITH LABEL <label>
SELECT ...` gives the statement a label, as a Stream Load request has one.
Doris then rejects a second load with a label that a successful load has
already used (`Label [...] has already been used`), so a retry of the same
batch with the same label cannot load its rows twice.

A production batch workflow should also record the exact object set and
statement outcome, then use an idempotent design appropriate to its
availability requirements. Examples include loading into a run-specific
staging table, atomically replacing a target Partition, or using a table model
and business key whose repeated-key semantics match the data.

Use read-only object-storage credentials and keep secret values outside the
notebook or SQL source. The official [S3 TVF](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/)
and [`INSERT INTO SELECT`](https://doris.apache.org/docs/4.x/data-operate/import/import-way/insert-into-manual/)
documentation provide the complete options.

## 3.4 Continuously Load Kafka Data with Routine Load

A Kafka topic is a durable, ordered message stream divided into Partitions.
Producers append messages; consumers read them by position, called an
**offset**.

A **Routine Load job** is a Doris-managed, long-running Kafka consumer job. It
is appropriate when new CSV or JSON messages continue to arrive and should
become queryable with low latency without an external process submitting one
load command for every batch.

```text
Application producers
        |
        | append JSON messages
        v
Kafka topic and Partitions
        |
        | consume from tracked offsets
        v
Routine Load job
        |
        | schedule micro-batch tasks
        v
BE nodes -> load transaction -> target internal table
```

### Job and task responsibilities

A Routine Load **job** holds the long-running configuration and progress. Doris
splits the job into short-lived **tasks**. Each task consumes a range of Kafka
messages and writes one micro-batch load transaction. When a task finishes,
Doris schedules another task so consumption can continue.

FE and BE divide the work as follows:

- FE manages Routine Load job state, schedules tasks, and commits load
  transactions;
- BE nodes execute the assigned tasks, consume Kafka messages, parse and
  transform rows, and write the target data.

Routine Load commits the table data and corresponding Kafka offset progress as
one transactional result. Doris documents this as Exactly-Once consumption:
committed offsets are not replayed after normal task retry or recovery, and an
offset is not advanced for an uncommitted transaction. This guarantee does not
deduplicate two separate messages that a producer intentionally writes with
the same business content.

### Map nested JSON to target columns

Kafka messages often contain nested JSON rather than flat table columns:

```json
{
  "meta": {"occurred_at": "2019-12-01T03:08:44", "event_id": 1},
  "actor": {"user_id": 520569166},
  "event": {"type": "CART", "revenue": 0.0},
  "geo": {"region": "region_07"},
  "product_id": 1005115
}
```

In `CREATE ROUTINE LOAD`:

- `format=json` selects the JSON parser;
- `jsonpaths` extracts nested values in a declared order, such as
  `$.meta.occurred_at`, `$.event.type`, and `$.event.revenue` for the message
  above;
- `COLUMNS` assigns those extracted values to temporary names or target
  columns;
- expressions convert timestamps, normalize strings, or convert numeric
  values before writing the target table.

The mapping is between the **message structure** and the **target-table
schema**. Kafka stores message bytes; it does not know which JSON field should
become `events_routine.event_time` or how `CART` should become `cart`.

### Observe an asynchronous job

`CREATE ROUTINE LOAD` creates the job but does not wait for a finite “complete”
state because the source is continuous. Use:

```sql
SHOW ROUTINE LOAD FOR module3_events_json;
```

Inspect:

- job state, such as `NEED_SCHEDULE`, `RUNNING`, or `PAUSED`;
- task count and Kafka progress;
- total, loaded, error, and unselected row counters;
- `ReasonOfStateChanged` and `ErrorLogUrls` when diagnosis is required.

Validate committed data separately with target-table queries. Job progress
answers “how far has the consumer committed?” A table query answers “what is
currently queryable?”

### Pause, resume, and stop

`PAUSE ROUTINE LOAD` stops new consumption tasks without deleting the job,
committed offsets, or target rows. `RESUME ROUTINE LOAD` schedules consumption
again from the job's committed offsets.

`STOP ROUTINE LOAD` is terminal for that job. The job cannot be resumed, but
rows already committed to the target table remain. Stopping a Routine Load job
is different from stopping the Kafka container or the Doris sandbox: those
actions change process availability, while the SQL command changes the
managed consumer's lifecycle.

See [Routine Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/routine-load-manual/)
and [Routine Load Principles and Best Practices](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/routine-load-best-practices/).

## 3.5 Reduce Small-Write Pressure with Group Commit

Many applications send frequent tiny `INSERT INTO VALUES` statements or
Stream Load requests. If each tiny write creates an independent load
transaction and small Rowsets, FE performs repeated planning and transaction
work while BE storage accumulates version pressure.

**Group Commit** is a server-side optimization that groups compatible small
writes to the same table into a shared load transaction. It is not simply
“concurrent writing,” and it is not a standalone connector for S3 or Kafka.

```text
Application workers
   |     |     |     |       many compatible small writes
   +-----+-----+-----+
             |
             v
     BE Group Commit queue
             |
             | time or size trigger
             v
     one grouped load transaction
             |
             v
       fewer new Rowsets
```

Group Commit layers on top of compatible `INSERT INTO VALUES`, JDBC prepared
statements, or Stream Load requests. It reduces per-write planning,
transaction, and Rowset overhead.

### Choose the acknowledgement mode

| Mode | When the request returns | Tradeoff |
| --- | --- | --- |
| `sync_mode` | After the grouped load transaction commits and the rows are visible | Strong, immediate completion evidence with some grouping delay |
| `async_mode` | After the rows are durable in the BE write-ahead log (WAL) | Lower request latency; the grouped transaction commits and becomes visible later |
| `off_mode` | Uses the regular ungrouped write path | No Group Commit behavior for the request |

Group Commit changes the unit and acknowledgement timing of compatible small
writes. It does not turn a bounded S3 object set into a stream, manage Kafka
offsets, or replace application-level data semantics.

See the official [Group Commit documentation](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/group-commit-manual/)
for supported statements, modes, flush triggers, and fallback conditions.

## 3.6 Validate Results and Design Safe Retries

“The command returned” is not a complete correctness test. Each load method
has different control-plane evidence, and every target needs data-level
validation.

### Match evidence to the load method

| Load method | Primary completion evidence | Data-level validation | Retry state |
| --- | --- | --- | --- |
| Stream Load | Synchronous JSON response with status, label, transaction, and quality counts | Target count, totals, boundaries, and sampled rows | Reuse the same label for the same uncertain batch |
| S3 TVF with `INSERT INTO SELECT` | SQL statement outcome | Compare source and target counts, aggregates, and expected transformations | Reuse the statement's `WITH LABEL` label for the same uncertain batch; the orchestrator records the object set and statement outcome |
| Routine Load | `SHOW ROUTINE LOAD` state, progress, statistics, and error information | Query committed target rows and business totals | Doris-managed job state and committed Kafka offsets |
| Group Commit | Mode-specific acknowledgement | Query visible target rows at the point promised by the selected mode | Depends on the underlying write and acknowledgement mode |

### Validate invariants, not only row counts

A row count can detect a missing or duplicated batch, but equal counts do not
prove that values were mapped correctly. Use a small set of stable invariants:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT event_id) AS distinct_events,
    MIN(event_time) AS min_event_time,
    MAX(event_time) AS max_event_time,
    SUM(revenue) AS total_revenue
FROM events_stream;
```

Choose checks that correspond to the source contract:

- row count checks completeness;
- distinct business identifiers reveal duplicate or missing records;
- minimum and maximum timestamps reveal a truncated object or offset range;
- numeric totals reveal mapping, conversion, and default-value mistakes;
- a small ordered sample makes string normalization visible.

### Use the correct meaning of “retry”

| Action | Same logical attempt? | Expected consequence |
| --- | --- | --- |
| Send the same Stream Load bytes with the same successful label | Yes | Doris identifies the existing batch and does not commit it again |
| Send the same Stream Load bytes with a different label | No | Doris treats it as a new load transaction |
| Blindly rerun a successful `INSERT INTO SELECT` | No | A new load transaction can append the query result again |
| Pause and resume one Routine Load job | Yes | Consumption continues from committed Kafka offsets |
| Publish the same JSON content to Kafka again | No | Kafka contains new messages for Routine Load to consume |

Retry safety comes from persistent identity and progress state. The mechanism
is a Stream Load label, an orchestrator's batch record, or committed Kafka
offsets—not the fact that two requests happen to contain identical text.

## Lab 3: Load Data from a File, S3, and Kafka

The lab reuses the `doris_course` Database and the ecommerce event schema from
Labs 1 and 2. It creates independent target tables so that each load method
can be observed without mixing its rows or completion evidence with another
method. It needs the course sandbox from Lab 1, and it starts a Kafka broker
(`apache/kafka:3.9.1`, about 0.2 GB to download). Plan about 30 minutes.

You will:

1. Match four workload contracts to Stream Load, S3 TVF with
   `INSERT INTO SELECT`, Routine Load, and Group Commit.
2. Create independent `events_stream`, `events_s3`, and `events_routine`
   target tables.
3. Download a 1,024-row event sample to a visible local path and push its
   pipe-separated CSV representation with Stream Load.
4. Read the synchronous response and verify the committed rows.
5. Retry the uncertain request with the same label and confirm that no rows
   are appended.
6. Submit an isolated malformed batch with `max_filter_ratio:0`, retrieve its
   `ErrorURL`, and observe transaction-level rejection.
7. Read the complete Parquet dataset through an S3 TVF and persist it with
   `INSERT INTO SELECT`.
8. Start a local Kafka broker, create a Routine Load job, and map nested JSON
   fields to the target schema.
9. Publish four 256-message batches and observe the temporary Kafka backlog,
   committed Routine Load progress, and queryable target rows.
10. Pause, resume, and stop the Routine Load job without confusing job
    lifecycle with container lifecycle.

Open the notebook:

[Lab 3 — Load Data from a File, S3, and Kafka](lab03_load_data.ipynb)

### Shared dataset

The Stream Load CSV and Routine Load JSON Lines fixtures represent the same
1,024 logical ecommerce events in different source formats. The S3 exercise
uses the same 10,158,080-row Parquet dataset introduced in Lab 1. Separate
tables isolate the load methods; the event semantics remain consistent across
the Level 1 course.

The Lab ends with a practice: predict what `max_filter_ratio:0.1` does with the
same bad batch. Predict the result first, then write the code in the empty cell;
the collapsed reference solution after it also runs with Run All and leaves the
Lab's tables as they were.

## Summary

- Choose a load method from the complete workload contract, not from a file
  extension: a client batch, objects in S3, a Kafka topic, and many tiny writes
  each have a starting point.
- Stream Load pushes one bounded client batch; the S3 TVF exposes remote
  objects as a temporary relation, which `INSERT INTO SELECT` persists; a
  Routine Load job consumes Kafka continuously; Group Commit groups compatible
  small writes into fewer load transactions.
- A Stream Load request declares how to parse its bytes, and its synchronous
  JSON response reports the transaction and the total, loaded, filtered, and
  unselected rows.
- Querying an S3 TVF reads the files without storing them; `INSERT INTO
  SELECT` writes the query result into an internal table in one load
  transaction, and rerunning it blindly loads the rows again.
- A Routine Load job maps nested JSON with `jsonpaths` and `COLUMNS`, and each
  micro-batch commits its rows together with the Kafka offsets it reached, so
  pause and resume continue where it stopped.
- Every load needs data-level validation, such as counts, distinct
  identifiers, time ranges, and totals; a filtered-row ratio above
  `max_filter_ratio` rejects the whole transaction, and the same Stream Load
  label makes the retry of an uncertain batch safe.

## Quiz 3: Loading Data into Apache Doris

Open [Quiz 3: Loading Data into Apache Doris](quiz03_load_methods_and_retry_safety.ipynb).
It has six single-choice questions and needs no running environment.

Next: this is the last module of Level 1. Level 2 starts with [Module 4: Modeling Data in Apache Doris](../../level2/module04-modeling/course.md).

## References

- [Apache Doris source repository](https://github.com/apache/doris)
- [Load Overview](https://doris.apache.org/docs/4.x/data-operate/import/load-manual/)
- [Stream Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/)
- [S3 table-valued function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/)
- [`INSERT INTO SELECT`](https://doris.apache.org/docs/4.x/data-operate/import/import-way/insert-into-manual/)
- [Routine Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/routine-load-manual/)
- [Routine Load Principles and Best Practices](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/routine-load-best-practices/)
- [Group Commit](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/group-commit-manual/)
