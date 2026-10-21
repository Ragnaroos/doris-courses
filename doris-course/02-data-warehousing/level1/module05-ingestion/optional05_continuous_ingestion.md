# Optional Reading: Continuous Ingestion

| Reading information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 · Module 5 |
| Doris | Apache Doris 4.1.3 |
| Labs | Optional [Lab 5A](optional05_kafka_routine_load.ipynb) (Kafka, 8 GiB of Docker memory) and [Lab 5B](optional05_flink_mysql_cdc.ipynb) (MySQL and Flink CDC, 10 GiB) |
| Estimated time | About 40 minutes: reading 30, quiz 10; the Labs take 30 and 40 minutes more |

[Module 5 lesson](course.md) · [Open the quiz](quiz05_continuous_ingestion.ipynb)

## Goal

Understand how Doris keeps loading data that never stops arriving, from a message stream or from a database's changes, and how such a job resumes without losing or repeating data.

This reading is optional: Modules 6 and 7 and the main quiz do not depend on it. Its quiz checks the objectives below, and Labs 5A and 5B let you run two of the paths, if your machine has the memory.

## Learning objectives

After completing this reading, you will be able to:

1. Explain why a continuous load job keeps its own progress, and how that progress differs from a business version.
2. Read a Routine Load job's state and progress, and choose between pausing, resuming, and stopping it.
3. Explain how a CDC pipeline moves from a snapshot to incremental changes, and what a checkpoint or a savepoint saves.
4. Choose where a new continuous job starts reading: from the beginning, from now, or from a saved position.
5. Explain how a delete in the source database reaches a Unique Key table in Doris.
6. Explain how a continuous file job finds new files, and why a file that arrives with an older name is skipped.

## Structure

| Section | Time | Outcome |
| --- | ---: | --- |
| Progress belongs to the job | 4 min | Offsets and positions, and why they are not versions |
| Kafka and Routine Load | 8 min | A job that consumes a topic, and how to run it |
| Flink CDC and the Doris connector | 7 min | Snapshot, changes, checkpoints, and deletes |
| Where a new job starts | 4 min | From the beginning, from now, or from a saved position |
| Streaming Jobs and CDC_STREAM | 4 min | The same path, run by Doris itself |
| New files in object storage | 3 min | How a job finds new files |
| Quiz | 10 min | Six questions on these objectives |

## Progress belongs to the job

A file is loaded once; a stream never ends. A job that loads a stream must remember how far it has loaded, so that after a pause, a restart, or a failure it continues there: no gap, and nothing twice. That position is the job's **progress**.

In Kafka, a **topic** is a stream of messages, divided into **partitions**; each message has an **offset**, its number within its partition, counted from 0. A Routine Load job's progress is the last offset it loaded in each partition. Offsets of different partitions do not order events against each other. A CDC job's progress is a position in the database's change log, such as a MySQL binlog file and position.

Progress answers "how far has this job read?". It does not answer "which state of this order is newer?": that is the business version, such as `event_version` in Module 7. A delivery confirmation can be read before a late payment event: progress moves forward, and the order's state must not move back. Keep both.

## Kafka and Routine Load

A **Routine Load** job lives in Doris: it reads a Kafka topic, writes what it reads in small batches, each a load transaction, into a table, and records its progress with each commit. It keeps its own progress in Doris, not as the committed offset of an ordinary Kafka consumer group.

```text
Producers ──> Kafka topic (partitions, offsets)
                  │ the job reads continuously
                  ▼
           Routine Load job: a load task every few seconds, progress saved with each commit
                  │
                  ▼
            Doris table
```

`SHOW ROUTINE LOAD FOR <job>` shows the job: `State` (RUNNING, PAUSED, STOPPED, or NEED_SCHEDULE between tasks), `Progress` (the last loaded offset of each partition), `Lag` (how many messages wait in each partition), `Statistic` (rows loaded and rejected), and when it paused on its own, `ReasonOfStateChanged` and `ErrorLogUrls`. Pausing, resuming, and stopping act on the job, not on Doris:

| Statement | What happens | Progress |
| --- | --- | --- |
| `PAUSE ROUTINE LOAD FOR <job>` | The job stops reading; messages wait in Kafka | Kept |
| `RESUME ROUTINE LOAD FOR <job>` | It reads again from its progress | Kept |
| `STOP ROUTINE LOAD FOR <job>` | The job ends for good and cannot be resumed | Gone with the job |

Do not drop and recreate a job to restart it: a new job starts again from its configured offsets and can load old messages a second time.

A job can also pause itself. With `max_error_number` = 0, the first row that does not fit the table pauses the job. Lab 5A shows what that does and does not undo: the valid rows of the same task are loaded, and the job's progress has already moved past the bad message, so `RESUME` continues after it and a corrected message has to be sent again. This differs from a Stream Load batch with `max_filter_ratio` = 0, which loads nothing.

**External environment example; not executed in the lab.** Create a dedicated topic and send two headerless CSV messages, `901001,180.00` and `901002,80.00`. The job maps their first and second values to the order ID and the amount:

<!-- external-service-example -->
```sql
CREATE TABLE orders_kafka_demo (
    order_id BIGINT, order_amount DECIMAL(18,2)
) DUPLICATE KEY(order_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES("replication_num"="1");

CREATE ROUTINE LOAD orders_kafka_job ON orders_kafka_demo
COLUMNS TERMINATED BY ",",
COLUMNS(order_id, order_amount)
PROPERTIES("strict_mode"="true", "max_error_number"="0")
FROM KAFKA(
    "kafka_broker_list"="<broker>:9092",
    "kafka_topic"="<dedicated_topic>",
    "property.kafka_default_offsets"="OFFSET_BEGINNING"
);
SHOW ROUTINE LOAD FOR orders_kafka_job;
SELECT COUNT(*) AS orders, SUM(order_amount) AS amount FROM orders_kafka_demo;
```

Once both messages are loaded, expect 2 rows and 260.00, and `Progress` `{"0":"1"}` for a topic with one partition. The job keeps waiting for new messages; it does not end when the topic runs dry. See [Routine Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/routine-load-manual/).

## Flink CDC and the Doris connector

**CDC**, change data capture, reads the committed inserts, updates, and deletes of a business database from its change log, such as MySQL's binlog. A Flink job with the MySQL CDC connector reads a table, and the Doris connector writes the result into Doris:

```text
MySQL: the table's rows, then its binlog
        │
        ▼
Flink job: MySQL CDC source ── processing ── Doris sink
        │ checkpoints: binlog position and operator state
        ▼
Doris Unique Key table
```

A new job usually first reads the rows that exist, the **snapshot**, and then switches to the binlog for every later change. While it runs, the job saves a **checkpoint** at a fixed interval: its binlog position and the state of its operators. With two-phase commit, the Doris sink commits each checkpoint's rows as a Doris transaction when the checkpoint completes, so a restart from a checkpoint neither loses nor repeats rows. A **savepoint** is a checkpoint that you ask for, for example with `flink stop`, to stop a job and restore it later from exactly that position. Both need the binlog to still hold every change since that position: a binlog that has been purged cannot be replayed.

An update in MySQL becomes a new state of the same key in Doris, which a Unique Key table keeps once. A delete must arrive as a delete: the Doris connector sends it as a row marked for deletion when `sink.enable-delete` is on, and the Unique Key table drops the key. Module 7 shows the same delete mark in a load, and its effect on versions. Check the source's primary key, the target's Unique Key, and the connector's settings together, and test an insert, an update, a delete, and a restart before relying on a pipeline. See the [Flink Doris Connector](https://doris.apache.org/docs/4.x/connection-integration/data-integration/flink-doris-connector/).

`SHOW MASTER STATUS` in MySQL shows the end of the binlog, how far MySQL has written; it is not the position that any reader has reached. Lab 5B runs this whole path: snapshot, changes, a savepoint while the source keeps changing, and a restore that catches up.

## Where a new job starts

A job that resumes continues from its saved position: Routine Load from its progress, a Flink job from a checkpoint or savepoint. A new job needs a starting position, and the choice decides what it loads:

| Start | Routine Load | MySQL CDC in Flink | What the target gets |
| --- | --- | --- | --- |
| From the beginning | `kafka_default_offsets` = `OFFSET_BEGINNING` | `scan.startup.mode` = `initial`: snapshot, then the binlog | Everything that exists, then every change |
| From now | `OFFSET_END` | `latest-offset` | Only what arrives after the start: earlier data is missing |
| From a saved position | The job's own progress | A checkpoint or savepoint, or `specific-offset` with a binlog file and position | Exactly what follows that position |

Starting from a time, such as the CDC connector's `timestamp` mode, finds the first change logged at that time, which does not tell which changes of that second were already loaded: use it to start a new job, not to resume one. A table filled from the beginning by one job must not be filled from the beginning by a second job too, or a Duplicate Key table keeps everything twice.

## Streaming Jobs and CDC_STREAM

**Version and scope:** this section introduces continuous synchronization available from Doris 4.1, which the official documentation marks as Experimental for MySQL and PostgreSQL. The example is not executed in the course; before running it, prepare the source database, the JDBC driver, and the synchronization account for your Doris version. See [MySQL single-table synchronization](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-mysql-table/).

The path is the one of the previous sections, snapshot, changes, and progress, but Doris runs it: a **Streaming Job** created with `CREATE JOB ... ON STREAMING` runs an `INSERT INTO ... SELECT` continuously, and the `CDC_STREAM` table function reads the source's rows and changes:

```text
MySQL rows and binlog ──> CDC_STREAM ──> SELECT maps the columns ──> Doris Unique Key table
                     └──── Streaming Job runs it continuously and records its progress ────┘
```

`"offset"="initial"` reads the existing rows first, then the changes; `"offset"="latest"` reads only later changes. To follow a group of tables with their source structure, evaluate `FROM MYSQL (...) TO DATABASE ...`, which creates the target tables; creating tables and following later schema changes are separate questions. See [CDC_STREAM](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/cdc-stream/) and [MySQL whole-database synchronization](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-mysql-database/).

**External environment example; not executed in the lab.** The source table `demo.orders` has the primary key `order_id` and a `status`, and starts with one row, `(901001, 'CREATED')`:

<!-- external-service-example -->
```sql
CREATE TABLE orders_cdc_demo (
    order_id BIGINT NOT NULL, status VARCHAR(20)
) UNIQUE KEY(order_id)
DISTRIBUTED BY HASH(order_id) BUCKETS 1
PROPERTIES("replication_num"="1");

CREATE JOB orders_mysql_job ON STREAMING DO
INSERT INTO orders_cdc_demo (order_id, status)
SELECT order_id, status FROM CDC_STREAM(
    "type"="mysql", "jdbc_url"="jdbc:mysql://<mysql_host>:3306",
    "driver_url"="<driver_jar_url>", "driver_class"="com.mysql.cj.jdbc.Driver",
    "user"="<sync_user>", "password"="<sync_password>",
    "database"="demo", "table"="orders", "offset"="initial"
);
SELECT * FROM jobs("type"="insert")
WHERE ExecuteType = 'STREAMING' AND Name = 'orders_mysql_job';
SELECT order_id, status FROM orders_cdc_demo ORDER BY order_id;
```

First the row arrives as CREATED. After you change it to PAID in MySQL, the query should show one row, now PAID: the Unique Key keeps one row per order. Read the job's state and progress in `jobs()`, and the business result in the table. Pause the job with `PAUSE JOB WHERE jobName = 'orders_mysql_job'` and resume it with `RESUME JOB WHERE jobName = 'orders_mysql_job'`. See [Continuous load job management](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-overview/).

## New files in object storage

A fixed set of files is loaded once (Module 5); a directory that keeps receiving files needs a job that notices new ones. A Streaming Job over the `S3` table function does that, and finds new files by name: a file is new when its name sorts after the last file it loaded.

| A file arrives | What the job does |
| --- | --- |
| `orders-001.parquet` at 09:00 | Loads it and records it as its progress |
| `orders-002.parquet` at 09:05 | Its name sorts after the progress: loads it |
| `orders-000.parquet` at 09:10 | Its name sorts before the progress: skips it; load it separately |

So publish files with names that increase, such as fixed-width batch numbers, also for late data: an order from yesterday arriving today goes into today's file. Overwriting a file under an old name is not a new batch. The job's `CurrentOffset` names the last file it processed and `EndOffset` the end of the current batch; when a file arrived but its rows did not, compare its name with these first. See [Continuous loading from object storage](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-s3/).

**External environment example; not executed in the lab.** Reuse the two-column table of the Routine Load example, and a directory that holds only the new files:

<!-- external-service-example -->
```sql
CREATE TABLE orders_files_demo LIKE orders_kafka_demo;
CREATE JOB orders_files_job ON STREAMING DO
INSERT INTO orders_files_demo (order_id, order_amount)
SELECT order_id, order_amount FROM S3(
    "uri"="s3://<bucket>/incremental/orders-*.parquet",
    "s3.endpoint"="<endpoint>", "s3.region"="<region>",
    "s3.access_key"="<access_key>", "s3.secret_key"="<secret_key>",
    "format"="parquet"
);
SELECT * FROM jobs("type"="insert")
WHERE ExecuteType = 'STREAMING' AND Name = 'orders_files_job';
SELECT order_id, order_amount FROM orders_files_demo ORDER BY order_id;
```

Publish `orders-001.parquet` with `(901001, 180.00)`, wait for the row, then `orders-002.parquet` with `(901002, 80.00)`: expect two rows and 260.00, without running any `INSERT` yourself. Pause the job with `PAUSE JOB WHERE jobName = 'orders_files_job'` when you are done, so that it stops picking up files.

## Summary

- A continuous job keeps its own progress, offsets in Kafka or a binlog position in a database, so that it resumes without gaps or repeats; business versions decide which state of a record is newer, a separate question.
- Read a Routine Load job's `State`, `Progress`, `Lag`, and `Statistic`; pause and resume it to keep its progress, and stop it only to end it; a job paused by a bad row has already moved past that row.
- A CDC job reads a snapshot and then the change log; a checkpoint or savepoint saves its position and operator state, and a restore needs the log to still hold every change since then.
- A new job starts from the beginning, from now, or from a saved position; starting from now leaves out what came before, and a time is no substitute for a saved position.
- A source delete reaches Doris only as a delete: the connector marks the row for deletion and the Unique Key table drops the key.
- A continuous file job loads files whose names sort after its progress; a file with an earlier name is skipped and needs a separate load.

## Quiz

Open the [Continuous Ingestion quiz](quiz05_continuous_ingestion.ipynb). It has six single-choice questions and needs no running environment.

Return to the [Module 5 lesson](course.md), or continue to [Module 6: Data Quality and Schema Validation](../module06-data-quality/course.md).

## References

- [Apache Doris: Routine Load](https://doris.apache.org/docs/4.x/data-operate/import/import-way/routine-load-manual/)
- [Apache Doris: Flink Doris Connector](https://doris.apache.org/docs/4.x/connection-integration/data-integration/flink-doris-connector/)
- [Flink CDC 3.4: MySQL connector](https://nightlies.apache.org/flink/flink-cdc-docs-release-3.4/docs/connectors/flink-sources/mysql-cdc/)
- [Apache Doris: Continuous load overview](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-overview/)
- [Apache Doris: CREATE STREAMING JOB](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/job/CREATE-STREAMING-JOB/)
- [Apache Doris: CDC_STREAM table function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/cdc-stream/)
- [Apache Doris: Continuous loading from object storage](https://doris.apache.org/docs/4.x/data-operate/import/import-way/streaming-job/continuous-load-s3/)
