# Module 5: Batch and Continuous Data Ingestion

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1 |
| Estimated time | About 90 minutes: reading 35, Lab 45, quiz 10 |

[Course README](../../README.md) · [Open Lab 5](lab05_stream_load.ipynb) · [Open Quiz 5](quiz05_load_methods_and_retry_safety.ipynb)

## Module goal

Load files into Doris in batches, check that each load did what it reports, and retry a load without loading anything twice.

## Learning objectives

After completing this module, you will be able to:

1. Choose a load method for a local file, files in object storage, a message stream, a database's changes, or many small writes.
2. Map CSV positions, Parquet fields, and default values to the columns of a target table.
3. Judge a load from its response and from the rows, relationships, and amounts in the target table.
4. Retry a load batch safely with its label, and tell a batch retry from business deduplication.
5. Explain what Group Commit changes for many small loads, and when their rows become visible.
6. Distinguish the grain and amount definitions of WWI historical orders, account receipts, and the simulated new orders.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 5.1 Choose a load method | 5 min | Match the way data arrives to a load method |
| 5.2 Types, columns, and defaults | 6 min | Map the fields of a file to the columns of a table |
| 5.3 Stream Load: request, response, and retries | 15 min | Read what a load reports, and retry it safely |
| 5.4 Many small loads: Group Commit | 4 min | Fewer transactions, and when their rows become visible |
| 5.5 Files in object storage | 3 min | INSERT INTO SELECT from the S3 table function, and Broker Load |
| 5.6 Two kinds of data, two grains | 2 min | WWI history, account receipts, and the simulated orders |
| Lab 5 | 45 min | Load a CSV, retry it, reject a bad batch, merge small loads, and load ten WWI tables |
| Quiz 5 | 10 min | Six questions on these objectives |

Continuous ingestion, where data keeps arriving, is optional in this course: Kafka with Routine Load, database changes with Flink CDC, and Doris's own Streaming Jobs are in the reading [Continuous Ingestion](optional05_continuous_ingestion.md), with its own quiz and the optional Labs 5A and 5B. Nothing in Modules 6 and 7 depends on them.

## 5.1 Choose a load method

A warehouse usually starts with history that already exists, then receives what keeps changing. The file format alone does not decide how to load: a Parquet file on your machine, a fixed set of Parquet files in object storage, and a directory of Parquet files that keeps growing need different methods.

| Where the data is and how it arrives | Load method | What to check |
| --- | --- | --- |
| A local CSV, JSON, or Parquet file; one finite batch | Stream Load: an HTTP request carries the file | The response, then the target table |
| A fixed set of files in object storage, to inspect with SQL first | The `S3` table function, with `INSERT INTO ... SELECT` to keep the rows | The query's result, then the target table |
| Large batches of files in object storage, as asynchronous jobs | Broker Load | The job's final state, then the target table |
| Many small writes from an application | Stream Load or INSERT with Group Commit | When the rows become visible |
| A message stream, such as Kafka | Routine Load (optional reading) | The job's state and progress |
| A business database's inserts, updates, and deletes | CDC, such as Flink CDC (optional reading) | The snapshot, the changes, and the position to resume from |

These are choices, not steps of one pipeline. Module 4 also showed a choice that loads nothing: querying the lake table where it is.

Lab 5 practices Stream Load on two kinds of data, ten simulated new orders in a CSV file and the ten tables of the WWI history in Parquet, and Group Commit on the same ten orders sent one at a time.

## 5.2 Types, columns, and defaults

A table's **schema** is its columns, their types, and whether they accept NULL. Choose each type from what the column is used for: `DECIMAL(18, 2)` for an amount with two decimal places, 18 digits in all; `BIGINT` for an ID; `DATE` for a calendar day; `DATETIME` for the moment an event happened. Decide what NULL means in a column, such as "payment time unknown", so that nobody reads it as zero. See [Data types](https://doris.apache.org/docs/4.x/table-design/data-type/).

A value that converts is not yet a valid business value. The text `not-a-number` cannot become an amount: that is a type error. The customer ID `999999` converts to an integer, yet there may be no such customer: that needs a business check against the customer dimension, which Module 6 builds.

### Tell the load which column each value fills

The simulated new orders come as a CSV file without a header, one order per line, eleven values separated by commas:

```text
order_id,customer_id,order_amount,status,event_version,event_id,
event_time,paid_amount,refund_amount,region,data_source
```

The `columns` parameter of a load names, in the file's order, the table column that each value fills. If a file puts the customer ID before the order ID and `columns` does not say so, every value still converts, and the two IDs are silently swapped; spot-check a few orders after a load for this reason.

| Input | Format settings | How fields reach columns |
| --- | --- | --- |
| The simulated `orders.csv` | `format=csv`, `column_separator=,` | By position, as `columns` lists them |
| A JSON array, such as Module 6's raw orders | `format=json`, `strip_outer_array=true` | By key name |
| The WWI `orders.parquet` and the other history files | `format=parquet` | By field name; the course's table definitions use the files' names |

A `columns` entry can also compute a value, such as `order_amount = amount_cents / 100.0` for a source that sends cents: 18000 becomes 180.00. That belongs to the load, because the rule is about one source's format. A rule that belongs to the table, whatever loads it, can be a generated column in the table definition instead; the [files and Group Commit extension](../extensions/extension45_files_and_group_commit.ipynb) compares the two.

### Defaults fill only what a load leaves out

A default is the value that a column gets when a write does not supply it. A table that only ever receives new orders can default `status` to `CREATED`; a table that receives orders in every state should take the state from the source. Facts such as a payment must come from the source, never from a default.

**SQL reading example: not executed in the lab.** To try it, use an orders_defaults_reading table that does not yet exist
in an isolated lab database, and run it only once; do not write this example into orders_imported.

<!-- reading-only-example -->
```sql
CREATE TABLE orders_defaults_reading (
    order_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT "CREATED"
) DUPLICATE KEY(order_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES("replication_num"="1");
INSERT INTO orders_defaults_reading (order_id) VALUES (901001);
INSERT INTO orders_defaults_reading (order_id, status) VALUES (901002, 'PAID');
SELECT order_id, status FROM orders_defaults_reading ORDER BY order_id;
```

The first row leaves out `status` and gets `(901001, CREATED)`; the second supplies it and keeps `(901002, PAID)`. A default handles a missing column; it does not repair a wrong value.

## 5.3 Stream Load: request, response, and retries

Stream Load sends a file to Doris in one HTTP `PUT` request. Doris parses it, checks each row against the table and the request's settings, and commits all accepted rows in one load transaction. See the [Stream Load manual](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/).

### The request

Lab 5's first load writes the request out in Python, so that you see every part; the later loads use `lab.stream_load()`, which sends the same request.

```text
PUT <BE HTTP address>/api/<database>/orders_imported/_stream_load
label: <a name for this batch, kept for retries>
format: csv
column_separator: ,
columns: <the column order of 5.2>
strict_mode: true
max_filter_ratio: 0
group_commit: off_mode
Request body: the bytes of orders.csv
```

`strict_mode` = true rejects a row whose value does not convert to its column's type, instead of loading NULL; `max_filter_ratio` = 0 fails the whole batch if any row is rejected. `group_commit` = off_mode commits this request on its own (5.4).

Usually a client sends Stream Load to the FE, which answers with a redirect to a BE, and the client follows it, as `curl --location-trusted` does. The FE redirects to the address that the BE registered. In the course's single-container sandbox, the BE registered `127.0.0.1:8040`, its address inside the container, which from your machine is not the BE: the sandbox publishes the BE's port 8040 as 51040. So the Lab sends Stream Load straight to the BE on 51040, and refuses to follow a redirect.

### The response, then the table

A load answers with JSON. An HTTP status of 200 only says that the request was received; the JSON says what happened to the rows:

```json
{
  "Status": "Success",
  "NumberLoadedRows": 10,
  "NumberFilteredRows": 0
}
```

Then query the table, because a load can succeed and still be wrong, with swapped columns for example:

```sql
SELECT COUNT(*) AS orders, SUM(order_amount) AS amount
FROM orders_imported;
```

Expect ten orders and 1400.00. For the WWI history, check also that keys are unique and that order lines, orders, customers, and products join without losing or doubling rows.

| `Status` | What it means, and what to do |
| --- | --- |
| `Success` | Read `NumberLoadedRows` and `NumberFilteredRows`, then check the table |
| `Label Already Exists` | A batch with this label exists: look at that batch's outcome. Nothing new was loaded |
| `Fail` | Nothing was loaded. Keep the response and read `ErrorURL` to find the rejected rows |
| `Publish Timeout`, or no answer at all | The outcome is unknown. Keep the label and check the original transaction before you retry |

### A label makes a retry safe, for a while

A **label** names a load batch in its database. If a request fails or its answer is lost, resend it with the same label: when the first attempt committed, Doris answers `Label Already Exists` and loads nothing; when it did not, the retry loads the batch once. Lab 5 resends its first file with the same label and checks that the table still holds ten orders.

A label is kept for a limited time. Doris remembers the label of a Stream Load or an INSERT for 12 hours after it finishes (the FE setting `streaming_label_keep_max_second`), and drops the oldest labels earlier when a database holds more than 2,000 finished loads (`label_num_threshold`). A retry after that, or with a new label, loads the batch again, and a Duplicate Key table keeps both copies. Retrying a load is therefore not deduplication: removing duplicates of business events needs stable business keys and versions, which Module 7 builds.

### A bad row fails the whole batch

Lab 5 then sends two rows with a new label, one with the amount `not-a-number`. With `strict_mode` and `max_filter_ratio` = 0, the response is `Fail`, `NumberFilteredRows` is 1, and the table keeps its ten orders and 1400.00: the good row of that batch is not loaded either. `ErrorURL` points to the rejected row and the reason, for a while; it is a clue for troubleshooting, not a record that you can query later. Module 6 keeps rejected rows in a table.

## 5.4 Many small loads: Group Commit

Each load transaction has a fixed cost: a commit, and a new version in every tablet it writes, which compaction later has to merge (Module 2). An application that sends one order at a time pays that cost for every order. **Group Commit** lets Doris collect small loads that arrive close together and commit them as one transaction.

| `group_commit` | When the client gets its answer | When the rows become visible |
| --- | --- | --- |
| `off_mode` | After its own commit | With that commit |
| `sync_mode` | After the group commit that contains its rows | With that commit |
| `async_mode` | As soon as its rows are in the write-ahead log (WAL) | At the group's commit, by default up to 10 seconds later |

A group commits when it has waited `group_commit_interval_ms`, a table property of 10,000 ms by default, or when it holds `group_commit_data_bytes`, 128 MB by default. Lab 5 sets the interval of its table to 2 seconds and sends the ten orders as ten single-row loads, once with `off_mode` and once with `async_mode`. With `off_mode`, ten loads make ten transactions and the tablet's version reaches 11. With `async_mode`, all ten responses carry the same transaction ID, the tablet reaches version 2, and right after the last response a query still finds none of the ten rows: they appear when the group commits, about 2 seconds later.

Two consequences. First, `sync_mode` merges only loads that are in flight at the same time: one client that waits for each answer before sending the next gets a commit per load, each taking up to the interval. Second, a Group Commit request cannot carry your label; Doris answers `label and group_commit can't be set at the same time`. Retrying such a load by label is therefore not possible, and the response's `GroupCommit` field and its generated label tell you which path the load took. See [Group Commit](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/group-commit-manual/).

## 5.5 Files in object storage

When the files are already in S3 or another S3-compatible store, Doris can read them there, in two ways:

```text
Fixed files in object storage ── S3 table function ── SELECT: look at the rows
                                                    └─ INSERT INTO ... SELECT: keep them
Fixed files in object storage ── Broker Load job ─── wait for FINISHED, then check the table
```

The `S3` table function reads the files you name as rows of a query; `SELECT` alone stores nothing, and `INSERT INTO ... SELECT` writes the rows into a table in the same statement. Lab 4 does exactly this with the lake table's data file. Broker Load submits an asynchronous job: the statement returns at once, and the load is done only when `SHOW LOAD` reports `FINISHED`.

**External environment example; not executed in the lab.** Placeholders in angle brackets stand for your own store; the [files and Group Commit extension](../extensions/extension45_files_and_group_commit.ipynb) runs the same job against the course's Silo.

<!-- external-service-example -->
```sql
LOAD LABEL <database>.orders_files_202601 (
    DATA INFILE("s3://<bucket>/orders/2026-01/*.parquet")
    INTO TABLE <target_table>
    FORMAT AS "parquet"
)
WITH S3 (
    "AWS_ENDPOINT" = "<endpoint>", "AWS_REGION" = "<region>",
    "AWS_ACCESS_KEY" = "<access_key>", "AWS_SECRET_KEY" = "<secret_key>"
)
PROPERTIES ("timeout" = "3600", "max_filter_ratio" = "0");
SHOW LOAD WHERE Label = 'orders_files_202601';
```

Before loading the same files again, decide what a second load should do: append, update by key, or replace a range. Appending a month's files to a Duplicate Key table twice counts that month twice. See [Broker Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/broker-load-manual/) and the [S3 table function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/).

## 5.6 Two kinds of data, two grains

```text
WWI history in Parquet ── Stream Load ──> wwi_* (ten business tables, 701,846 rows)
Simulated new orders (CSV) ── Stream Load ──> orders_imported (ten orders, practice target)
Raw new orders (JSON, with three errors) ── Stream Load in Module 6 ──> orders_raw ──> orders_clean ──> Module 7
```

`orders_imported` is only the practice table for loading, retrying, and rejecting in Lab 5. Module 6 loads the same new orders again, this time with three wrong inputs, into its own raw table and produces `orders_clean`. Module 7 builds `orders_current` and `order_events` from the clean orders; Level 2 starts from that current state and history. The WWI tables are the history: Module 6 reads its customer dimension from `wwi_customers` and Module 7 its products from `wwi_products`.

The history package keeps orders, order lines, customers, products, invoices, account transactions, and lookup tables: 701,846 rows in ten tables, which is not a number of orders. Each WWI order line is one product of an order, so `COUNT(*)` after joining lines to orders counts lines, and a daily report counts orders with `COUNT(DISTINCT o.OrderID)`:

```sql
SELECT o.OrderDate,
       COUNT(DISTINCT o.OrderID) AS orders,
       SUM(l.Quantity * l.UnitPrice) AS order_amount
FROM wwi_orders o
JOIN wwi_order_lines l ON o.OrderID = l.OrderID
GROUP BY o.OrderDate
ORDER BY o.OrderDate
LIMIT 10;
```

WWI's customer transactions are payments and invoices on a customer's account, not on an order: they cannot be split into per-order payments. The [further reading on invoices and account receipts](optional05_invoice_and_receipts.md) compares the three kinds of amounts; it is not part of the Lab. The simulated orders 900001–900010 use WWI's customers and products but their own prices, regions, and times, marked `COURSE_SIMULATION`.

## Lab 5: Batch Loading, Failures, and Retries

Open [Lab 5: Batch Loading, Failures, and Retries](lab05_stream_load.ipynb). You:

1. Load the ten simulated orders with a Stream Load request written out in Python, and check the response and the table: ten orders, 1400.00.
2. Resend the same batch with the same label, and load a batch with a bad amount; the table keeps its ten orders.
3. Send the same ten orders as ten single-row loads, without and with Group Commit, and compare transactions, versions, and visibility.
4. Load the ten WWI history tables from Parquet, and check their keys, relationships, and amounts.
5. Practice: load a CSV whose first two columns are in another order.

You need the course sandbox from Module 1. The Lab does not use the lake environment of Module 4.

## Summary

- Choose the load method from where the data is and how it arrives: Stream Load for a finite local file, the S3 table function or Broker Load for files in object storage, Group Commit for many small writes, and Routine Load or CDC for data that keeps arriving.
- A CSV is mapped by position with `columns`, JSON by key, and Parquet by field name; a default fills only a column that a write leaves out, and never stands in for a business fact.
- Read a load's JSON, not its HTTP status, and then check the table's rows, keys, relationships, and amounts; with `strict_mode` and `max_filter_ratio` = 0, one bad row fails the whole batch.
- A label makes a retry of the same batch load nothing twice, for about 12 hours; a new label loads again, and business duplicates need business keys and versions.
- Group Commit merges small loads into fewer transactions and versions; in `async_mode` the answer comes before the rows are visible, and a Group Commit load cannot carry a label.
- WWI order lines, account transactions, and the simulated orders have different grains and sources: count orders, not lines, and do not force account receipts onto orders.

## Quiz 5

Open [Quiz 5: Batch and Continuous Data Ingestion](quiz05_load_methods_and_retry_safety.ipynb). It has six single-choice questions and needs no running environment. The continuous ingestion reading has its own [quiz](quiz05_continuous_ingestion.ipynb).

Next module: [Module 6: Data Quality and Schema Validation](../module06-data-quality/course.md).

## References

- [Apache Doris: Loading overview](https://doris.apache.org/docs/4.x/data-operate/import/load-manual/)
- [Apache Doris: Stream Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/)
- [Apache Doris: Group Commit](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/group-commit-manual/)
- [Apache Doris: S3 table function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/)
- [Apache Doris: INSERT INTO SELECT](https://doris.apache.org/docs/4.x/data-operate/import/import-way/insert-into-manual/)
- [Apache Doris: Broker Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/broker-load-manual/)
- [Apache Doris: Data types](https://doris.apache.org/docs/4.x/table-design/data-type/)
