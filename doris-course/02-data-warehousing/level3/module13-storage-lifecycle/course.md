# Module 13: Storage and Lifecycle Management

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 3 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1; for the optional backup drill, a local object store that the Lab starts |
| Estimated time | About 108 minutes: reading 38, Lab 60, quiz 10 |

[Course README](../../README.md) · [Open Lab 13](lab13_storage_and_lifecycle.ipynb) · [Open Quiz 13](quiz13_storage_lifecycle.ipynb)

## Module goal

Remove expired months by partition, record what each maintenance step changed, and know before the change how to bring back a month that was removed by mistake.

## Learning objectives

After completing this module, you will be able to:

1. Choose partition boundaries that match a retention rule and the time that queries filter on.
2. Explain how a row belongs to a partition, a tablet, a replica, a rowset, and a segment.
3. Record before-and-after evidence of a maintenance change with SHOW PARTITIONS, SHOW TABLETS, and SHOW CREATE TABLE.
4. Tell query visibility, metadata changes, and reclaimed space apart, and say where compaction fits.
5. Recover a dropped or truncated partition from the recycle bin, and say when only a backup or an archive can help.
6. Write a maintenance runbook with its scope, checks, evidence, and a recovery path tested beforehand.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 13.1 Partition by the Retention Rule | 8 min | Calendar months on the order date, and TRUNCATE against DROP |
| 13.2 Where a Row Lives | 6 min | From a table to a segment, and how many tablets a layout makes |
| 13.3 Evidence Before and After Maintenance | 6 min | What each SHOW statement shows, and which numbers lag |
| 13.4 What TRUNCATE Changes | 6 min | Visibility at once, files later, and the recycle bin between |
| 13.5 Ways Back | 8 min | The recycle bin by name and by ID, a backup, and an archive |
| 13.6 A Maintenance Runbook | 4 min | Scope, checks, change, evidence, and recovery |
| Lab 13 | 60 min | Clear a month, recover it by its partition ID, drop and recover another, and check a retention plan; optionally back up and restore |
| Quiz 13 | 10 min | Six questions on these objectives |

## 13.1 Partition by the Retention Rule

An order table holds two years of data, and the retention rule keeps **the current calendar month and the 12 months before it**. Maintenance in February 2026 keeps February 2025 to February 2026 and removes the months before. A colleague runs `DELETE FROM orders WHERE order_date < '2025-02-01'`: the statement returns quickly, the old orders disappear from queries, and the disk barely changes, because the rows stay in their files until compaction; and if the condition was wrong, there is no way back. Before cleanup SQL, answer four questions:

| Question | Answer for the order table |
| --- | --- |
| What is one row? | One order |
| How long is it kept? | The current month and the 12 months before: February 2025 to February 2026 here |
| Which time decides its expiry? | Its `order_date`, not the time it was loaded |
| How does a removed month come back? | From a backup or an archive that was read back; the recycle bin for a day |

The third answer is the partition key. Partitioned by load time, a January order that arrives in February would sit in February's partition, out of reach of January's cleanup, and a filter on `order_date` would not prune. A rule in calendar months also differs from a rolling window of 365 days: whole months can be removed by partition, a window ending on some day cannot.

| Partitions | Removing January 2025 | What it touches |
| --- | --- | --- |
| Monthly | `ALTER TABLE ... DROP PARTITION p202501` | January's partition alone |
| Yearly | `DELETE ... WHERE order_date < '2025-02-01'` in the 2025 partition | Every query of 2025 applies the delete's condition until compaction |
| None | `DELETE` on the table | Every query of the table applies it |

On a Duplicate Key table, a conditional `DELETE` writes a version with a delete predicate instead of rewriting files; `SHOW DELETE` lists it, and queries filter by it until compaction merges the rowsets. Many predicates slow queries down.

Monthly partitions offer two statements:

| Statement | The partition afterward | Use it to |
| --- | --- | --- |
| `TRUNCATE TABLE ... PARTITION (p202501)` | Still there, empty, with a new ID | Clear a month and load it again |
| `ALTER TABLE ... DROP PARTITION p202501` | Gone, with its definition | Remove a month that expired, after its archive was checked |

Dynamic partitioning can create future partitions and remove historical ones on a schedule; it removes old ones only when `dynamic_partition.start` says how many to keep. Whether the cleanup is manual or scheduled, check the archive of a month before you remove it.

## 13.2 Where a Row Lives

The business speaks of January's orders; Doris stores them in tablets and rowsets. Follow order 130001 of Lab 13, of 2025-01-15:

| Layer | Where order 130001 is | What maintenance looks at |
| --- | --- | --- |
| Table | `ops_orders_l3` | The model, the owner, the privileges |
| Partition | Below 2025-02-01, so in `p202501` | Retention, pruning, the scope of a cleanup |
| Bucket and tablet | `HASH(order_id)` with `BUCKETS 1`: the partition's one tablet | Parallelism, skew, tablet sizes |
| Replica | `replication_num` 1: one copy, on the one BE | How many copies, where, and whether healthy |
| Rowset | The version that its `INSERT` added | Versions, compaction pressure |
| Segment | The column files inside the rowset | Scans and indexes, rarely touched by maintenance |

A cleanup of `p202501` touches January's tablets and leaves February's and March's alone. The layout decides how many tablets there are:

| Table | Partitions | Buckets per partition | Replicas | Tablets | Rows of SHOW TABLETS |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lab 13's `ops_orders_l3` | 3 | 1 | 1 | 3 | 3 |
| A production table of 13 months | 13 | 8 | 3 | 104 | 312 |

Each row of `SHOW TABLETS` is one replica, which is why a partition clause helps on a real table. Too few buckets make large tablets and little parallelism; too many make small tablets and more metadata to schedule. One BE and one replica illustrate the relations; they are not a size for production.

## 13.3 Evidence Before and After Maintenance

A wrong grant can be revoked; a wrong cleanup has no undo statement that always works. Record the state before the change, and run the same checks afterward:

| Evidence | Shows | Does not show |
| --- | --- | --- |
| `SHOW PARTITIONS FROM t` | Each partition's name, range, `PartitionId`, `VisibleVersion`, and `State` | An exact row count now: `RowCount` and `DataSize` wait for the BE's report |
| `SHOW TABLETS FROM t PARTITION (p)` | Each replica's tablet, backend, version, and state | That a removed tablet's files are gone from the disk |
| `SHOW CREATE TABLE t` | The model, the partitions, the bucketing, the replicas | That a month was archived, or compaction finished |
| `SELECT COUNT(*) FROM t PARTITION (p)` | The rows that queries see now | That space was reclaimed |

`VisibleVersion` changes as soon as a load commits; `RowCount` reads -1 or 0 until the BE's next report, about a minute later. `SHOW TABLETS` has no partition column, so name the partition. The sizes mean different things in integrated and in decoupled storage and compute; this course's sandbox is integrated.

## 13.4 What TRUNCATE Changes

**SQL reading example: the step of Lab 13 that clears January. Do not rerun it after the Lab.**

<!-- reading-only-example -->
```sql
TRUNCATE TABLE ops_orders_l3 PARTITION (p202501);
```

| Layer | What changes | When |
| --- | --- | --- |
| Queries | February and March remain: 2 orders, 500.00 | At once |
| Metadata | `p202501` has a new `PartitionId` and `VisibleVersion` 1; the other partitions keep theirs | At once |
| Storage | The old partition and its tablets are in the FE's recycle bin; their files stay | Removed after the recycle bin's retention, then asynchronously on the BE |

`TRUNCATE` replaces the partition with a new, empty one of the same name and range; it neither deletes rows one by one nor records a delete predicate, so it does not wait for compaction. The recycle bin keeps the old partition for `catalog_trash_expire_second`, 86400 seconds by default: one day. `TRUNCATE ... FORCE` skips the recycle bin.

**Compaction** merges a tablet's rowsets into fewer, larger ones in the background, and removes the rows of delete predicates as it goes; that is why the colleague's `DELETE` changed the queries before the disk. It has nothing to do with whether a truncation succeeded. Watch its pressure with `VersionCount` and the load and query rates, not with one small sample.

## 13.5 Ways Back

The recycle bin keeps truncated and dropped partitions, and `RECOVER PARTITION` brings one back while it is there. Lab 13 recovers the truncated January:

1. `SHOW CATALOG RECYCLE BIN WHERE NAME = 'p202501'` lists every dropped `p202501`, of every table and every run; keep the entry whose `PartitionId` you recorded before the truncation.
2. `RECOVER PARTITION p202501 FROM ops_orders_l3` is refused while the empty replacement is in the table: `partition[p202501] already exist in table[ops_orders_l3]`. Check that the replacement is still empty: rows written to it since would be lost.
3. Drop the replacement, which goes to the recycle bin too, and recover by the ID.

**SQL reading example: the recovery of Lab 13. Do not rerun it after the Lab.**

<!-- reading-only-example -->
```sql
ALTER TABLE ops_orders_l3 DROP PARTITION p202501;
RECOVER PARTITION p202501 <the recorded PartitionId> FROM ops_orders_l3;
```

January comes back with its original ID and its order: 3 orders and 600.00. Without the ID, measured on Doris 4.1.3, `RECOVER PARTITION p202501 FROM ops_orders_l3` recovers the newest `p202501` in the recycle bin, the empty replacement, and January stays empty. A `DROP PARTITION` without `FORCE`, as on Lab 13's second table, comes back with a `RECOVER` by name, because only one `p202501` of that table is there.

The recycle bin is a short way back. The durable ones are prepared before the change:

| Way back | What it holds | Limits |
| --- | --- | --- |
| The recycle bin | Truncated and dropped partitions and tables | One day by default; nothing after `FORCE` |
| A repository backup, `BACKUP SNAPSHOT` / `RESTORE SNAPSHOT` | A snapshot of tables in a remote repository, such as S3-compatible storage | The snapshot's time: later writes are not in it |
| An archive | A copy of a month's data that you exported and read back, for example as Parquet files in object storage | Whatever the export kept; it is reloaded, not restored |
| The source | A replayable batch or a change stream upstream | The source's own retention |

Lab 13's optional sections run a repository backup: they start a small local object store, the Silo of Module 4, register it as a repository, back up a table, drop it with `FORCE`, and restore its snapshot under another name in another database, where every row is compared. Doris and the object store share one computer there, so losing the computer would lose both copies: a backup for disaster recovery needs another failure domain, a tested recovery point and recovery time, and managed credentials and retention. The drill covers an ordinary table of an integrated storage and compute deployment, not decoupled storage and compute, the cluster's configuration, or external lake tables.

## 13.6 A Maintenance Runbook

The next operator needs more than "clear January". Write the runbook before the change:

| Part | Lab 13's example |
| --- | --- |
| Scope | `ops_orders_l3.p202501` alone |
| Checks before | The partition exists and holds 1 order of 100.00; the table holds 3; each partition's `PartitionId` and `VisibleVersion`; in production, an archive read back and an approval |
| Change | `TRUNCATE TABLE ops_orders_l3 PARTITION (p202501)` |
| Evidence after | 2 orders and 500.00 remain; only January has a new ID |
| Recovery | Within a day, check that the empty replacement has received no rows, drop it, and run `RECOVER PARTITION p202501 <recorded id> FROM ops_orders_l3`; afterward, reload from the archive |

Test the recovery before the change: read the archive back and compare its rows with the partition, instead of finding out after a mistake that it cannot be read. Lab 13's practice checks a retention plan in SQL before it removes anything: from the maintenance date 2026-02-15 it computes the first month to keep, 2025-02-01, lists the partitions that end on or before it, drops them without `FORCE`, and checks that 13 months remain.

## Lab 13: Partition Maintenance and Recovery

Open [Lab 13: Partition Maintenance and Recovery](lab13_storage_and_lifecycle.ipynb). You:

1. Create `ops_orders_l3` with three monthly partitions, one order each.
2. Record its partitions, tablets, and definition.
3. Clear January with `TRUNCATE`, and compare the IDs before and after.
4. Recover the truncated January by its partition ID.
5. Drop and recover January on a second table.
6. Optionally, back up a table to a repository, drop it with `FORCE`, and restore it in another database.
7. Practice: check a retention plan for 13 calendar months, then apply it.

You need only the course sandbox. The optional drill starts the object store and keeps its snapshot; the Lab says how to remove it.

## Summary

- Partition by the time that decides expiry, the order date, in the rule's units, calendar months; drop an expired month, truncate one that you will reload.
- A row lives in a partition, a tablet of it, a replica of the tablet, a rowset, and its segments; a partition's cleanup touches only its tablets.
- Record each partition's ID and version, its tablets, and the table's definition before a change, and count rows per partition: `RowCount` lags.
- Queries change at once, metadata gets new IDs, and space comes back after the recycle bin's retention; compaction merges rowsets and removes deleted rows, apart from truncation.
- Recover a truncated partition by its recorded ID, after removing its empty replacement; only a backup, an archive, or the source can help after `FORCE` or the retention.
- A runbook names the scope, the checks, the change, the evidence, and a recovery that was tested before the change.

## Quiz 13

Open [Quiz 13: Storage and Lifecycle Management](quiz13_storage_lifecycle.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 14: Resource Isolation and Query Protection](../module14-resource-isolation/course.md).

## References

- [Apache Doris: Partitioning and bucketing](https://doris.apache.org/docs/4.x/key-features/partitioning-and-bucketing/)
- [Apache Doris: Dynamic partitioning](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning)
- [Apache Doris: Delete](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/)
- [Apache Doris: Truncate](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/)
- [Apache Doris: Recycle bin](https://doris.apache.org/docs/4.x/admin-manual/data-admin/recyclebin/)
- [Apache Doris: Backup](https://doris.apache.org/docs/4.x/admin-manual/data-admin/backup-restore/backup/)
- [Apache Doris: Restore](https://doris.apache.org/docs/4.x/admin-manual/data-admin/backup-restore/restore/)
- [Apache Doris: Data compaction](https://doris.apache.org/docs/4.x/key-features/data-compaction/)
