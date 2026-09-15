# Module 7: Updating and Deleting Data in Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 2 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | Approximately 75 minutes, including the guided lab |

## Module goal

This module explains how to keep analytical current state synchronized as
business entities change, correct existing data, remove selected records, and
replace complete lifecycle ranges. Begin with the change contract: what
identifies a row, whether the source supplies a complete state or a patch, how
source order is established, and how much data the operation affects.

Module 4 selected a Table Model from repeated-Key semantics. This module focuses
on current-state workloads, so most examples use Unique Key. It also identifies
operations available to other Table Models and explains why appending another
row to a Duplicate Key table does not update current state.

## Learning objectives

After completing this module, you will be able to:

1. Separate append-only history from current state and define the final visible
   state expected after a sequence of changes.
2. Choose full-row upsert, partial column update, or SQL `UPDATE` from the form,
   frequency, and ownership of incoming changes.
3. Predict whether a Unique Key write inserts a new logical row or replaces an
   existing visible state.
4. Use a Sequence column so source order, rather than arrival order, decides
   which state wins.
5. Distinguish omitted columns in full-row and partial writes from an explicitly
   supplied `NULL`.
6. Use `MERGE INTO` for conditional matched updates/deletes and not-matched
   inserts from a source relation.
7. Choose predicate `DELETE` or Delete Sign from how deleted rows are identified.
8. Choose `TRUNCATE TABLE/PARTITION` or `INSERT OVERWRITE` for complete scopes.
9. Distinguish logical visibility from later physical cleanup by Compaction.
10. Explain why ambiguous source order and repeated single-row transactions are
    operational design problems.

## Scenario-led content outline

An order platform sends complete images, logistics patches, corrections, and
deletion records to Doris. A daily Partition can also expire or require a full
backfill. Each section derives an operation from one need.

| Section | Requirement scenario | Decision developed | Lab 7 evidence |
| --- | --- | --- | --- |
| **7.1 Define the state contract** | History must remain, while reports need one current row per order. | Separate history from state and locate each Table Model's boundary. | Use independent Module 7 tables without changing event data. |
| **7.2 Synchronize complete states** | Full order images may arrive out of order. | Use Unique Key upsert and an explicit Sequence column. | Update `1001`, insert `1004`, and reject an older delayed state. |
| **7.3 Apply field-owned patches** | Logistics owns status but must preserve amount and region. | Use partial update; distinguish omission, defaults, and `NULL`. | Compare full-row and partial writes with omitted columns. |
| **7.4 Correct selected rows** | A small incorrect set is described by a predicate. | Use SQL `UPDATE` for an occasional Value-column correction. | Correct one shipping region. |
| **7.5 Merge staged changes** | One relation contains inserts, updates, and deletes. | Use `MERGE INTO` with deterministic source matching. | Update `4001`, delete `4002`, and insert `4004`. |
| **7.6 Remove selected rows** | A rule selects bad rows; CDC supplies deleted Keys. | Choose predicate `DELETE` or Delete Sign. | Delete `2003` by predicate and `2002` by Key. |
| **7.7 Replace a lifecycle scope** | One date expires; another has a complete correction. | Use `TRUNCATE PARTITION` or `INSERT OVERWRITE`. | Remove `p20260910` and replace `p20260911`. |
| **7.8 Separate visibility from cleanup** | Queries show new state while storage versions remain. | Bound conclusions from queries, hidden markers, and metadata. | Compare visible rows and Tablet versions. |

Lab 7 supplies bounded Doris 4.1.3 evidence. It does not connect to an external
Change Data Capture (CDC) system, benchmark writes, inspect Rowsets or Segments,
display an internal delete bitmap, or wait for Compaction.

---

## 7.1 Define the State Contract Before Choosing an Operation

An event-history table answers **what happened**. A current-state table answers
**what is true now**. An order moving from `created` to `paid` to `shipped` can
produce three history events but one current order row.

| Table Model | Another row with the same Key means | Change-processing role |
| --- | --- | --- |
| Duplicate Key | Preserve another accepted row | History and audit data; another insert does not hide the old row |
| Unique Key | Replace the visible state for that business Key | Current state and primary-key synchronization |
| Aggregate Key | Combine Value columns through declared aggregate functions | Metric contributions or specialized replacement aggregates |

Unique Key is central because full-row upsert, Sequence ordering, SQL `UPDATE`,
Delete Sign, and `MERGE INTO` serve primary-key state maintenance. This does not
make every deletion Unique-only. Predicate `DELETE` can apply across models with
model-specific restrictions, while whole-Partition operations have a different
scope. Aggregate Key can use specialized patterns such as
`REPLACE_IF_NOT_NULL`; that is aggregate-model behavior, not the order-state
contract used here.

Before writing, ask:

1. Which business Key identifies the target state?
2. Does the source carry a full row, selected fields, a predicate, or a complete
   replacement dataset?
3. Which source value establishes order?
4. Can several source rows target the same Key in one batch?
5. Is the scope one Key, a selected set, one Partition, or the table?

## 7.2 Synchronize Complete States with Unique Key Upsert

When a source emits a complete current image, loading into a Unique Key table
provides upsert behavior:

```text
new Key       -> insert a current row
existing Key  -> replace its visible current state
```

This fits batched full images from CDC or a producer that owns every target
Value column. It does not preserve every historical version in ordinary query
results.

### Make source order explicit

Arrival order is unreliable. A delayed `paid` message can arrive after a newer
`shipped` message. A Sequence column makes source version, timestamp, or offset
part of the table contract:

```text
09:00 created
10:10 shipped  -> visible winner
10:05 paid     -> arrives last but has a smaller Sequence
```

Lab 7 declares `"function_column.sequence_col" = "updated_at"`. Merely naming a
column `updated_at` would not create ordering semantics. Choose a value monotonic
for each business Key and supplied by the authoritative source. Equal Sequence
values need an additional source policy; do not assume arrival order is a safe
tie-breaker.

Continuous changes should normally be batched. A tight loop of individual
writes creates many transactions and storage versions. Freshness, batch size,
failure recovery, and retry safety remain part of the ingestion contract.

## 7.3 Preserve Unowned Fields with Partial Column Update

A logistics feed may own `status` and `updated_at` but not `amount` or
`shipping_region`. Reconstructing a complete row could overwrite other systems'
values.

| Mode | Existing Key receives only status and time | Omitted Value columns |
| --- | --- | --- |
| Full-row upsert | Construct a complete replacement | Use schema defaults or permitted `NULL` |
| Partial column update | Patch the existing state | Preserve visible values |

Lab 7 shows a full-row write changing omitted amount and region to `0.00` and
`UNASSIGNED`, while a partial update preserves `88.00` and `CN-WEST`.

Omission is different from explicitly supplying `NULL`. An explicit `NULL` is
a requested value for a nullable column and is invalid for a `NOT NULL` column
unless transformed before the write. A default is not a universal repair for a
supplied invalid value.

All Key columns must be available so Doris can locate the row. Also define what
happens when a partial record carries a new Key: there is no old row from which
to preserve missing values. Current behavior depends on update mode, defaults,
nullability, and settings. Consult the current [Column Update](https://doris.apache.org/docs/4.x/data-operate/update/partial-column-update/)
contract for production loading and flexible column sets.

## 7.4 Correct a Small Selected Set with SQL UPDATE

When no replacement records exist and a SQL predicate identifies the problem,
use a direct correction:

```sql
UPDATE order_state
SET shipping_region = 'CN-NORTH'
WHERE order_id = 1001;
```

`WHERE` selects target rows; `SET` names changed Value columns. SQL `UPDATE`
targets a Unique Key table and cannot modify Key columns. A business-Key change
should delete the old Key and insert the new one.

This path fits occasional corrections. It is a poor shape for a high-frequency
application loop because each statement finds rows and publishes a transaction.
When incoming records already identify Keys, use batched full-row or partial
loads.

## 7.5 Apply Conditional Actions with MERGE INTO

A staging relation may contain mixed change types:

| `order_id` | `change_type` | Required action |
| ---: | --- | --- |
| 4001 | UPSERT | Update an existing order |
| 4002 | DELETE | Delete an existing order |
| 4004 | UPSERT | Insert a new order |

`MERGE INTO` joins that relation to a Unique Key target:

```sql
MERGE INTO order_merge_target AS t
USING order_merge_changes AS s
ON t.order_id = s.order_id
WHEN MATCHED AND s.change_type = 'DELETE' THEN DELETE
WHEN MATCHED AND s.change_type = 'UPSERT' THEN UPDATE SET
    status = s.status,
    amount = s.amount,
    shipping_region = s.shipping_region,
    updated_at = s.updated_at
WHEN NOT MATCHED AND s.change_type = 'UPSERT' THEN INSERT
    (order_id, status, amount, shipping_region, updated_at)
VALUES
    (s.order_id, s.status, s.amount, s.shipping_region, s.updated_at);
```

This fits a set-based batch already represented as a table or subquery. It adds
conditional matched and not-matched actions that a simple upsert cannot express.
It is a Data Manipulation Language statement, not a substitute for a continuous
high-throughput streaming load.

### Require deterministic source matching

Doris 4.x does not detect duplicate Join rows for `MERGE INTO`; multiple source
rows driving one target row can yield undefined behavior. Deduplicate by an
authoritative sequence or reject the batch first. Lab 7 compares total source
rows with distinct source Keys before executing the merge.

## 7.6 Choose How Deleted Rows Are Identified

Use predicate `DELETE` when SQL defines the target set, such as
`status = 'test'`. It can apply to Duplicate, Unique, and Aggregate Key tables,
although Aggregate Key delete conditions are restricted to Key columns.

Use Delete Sign when a batch or CDC record already carries a deleted Unique
Key. Setting hidden `__DORIS_DELETE_SIGN__ = 1` lets deleted Keys use a load
path. Writing `NULL`, omitting Value columns, or sending an ordinary upsert does
not mean delete.

Delete Sign is an input-facing hidden column, not the internal per-Rowset delete
bitmap described by Merge-on-Write. Lab 7 deletes `2003` by predicate and
`2002` by Delete Sign, after which an ordinary query returns only `2001`.

## 7.7 Match the Operation to a Complete Lifecycle Scope

| Requirement | Starting operation |
| --- | --- |
| A complete table or Partition is obsolete | `TRUNCATE TABLE/PARTITION` |
| A complete corrected dataset replaces a scope | `INSERT OVERWRITE` |
| Only a bounded predicate-selected set disappears | Predicate `DELETE` |

`TRUNCATE PARTITION` fits retention of complete calendar ranges.
`INSERT OVERWRITE` fits a backfill containing the complete desired contents;
rows absent from the replacement do not remain. Ordinary `INSERT INTO` on a
Duplicate Key table would append and can duplicate the old scope.

Doris documents overwrite as atomic replacement. Lab 7 observes the final
contents but does not run concurrent readers, so it does not claim to observe
the switch itself. Always verify the target scope: a complete dataset written
to the wrong Partition is still a complete replacement of the wrong data.

## 7.8 Separate Logical Visibility from Physical Cleanup

After publication, new ordinary queries see the winning Unique Key state and
exclude logically deleted rows. They need not wait for Compaction. Superseded
physical versions can remain until background Compaction reclaims them.

```text
transaction publishes
        +-- new queries see the new logical state
        +-- old physical versions may remain
                    +-- later Compaction can reclaim them
```

| Evidence | Supported conclusion | Unsupported conclusion |
| --- | --- | --- |
| Ordinary `SELECT` | Current visible rows and values | Whether old bytes were reclaimed |
| Hidden Delete Sign | Current hidden delete markers | Internal delete-bitmap contents |
| `SHOW TABLETS` versions | A later Tablet version was published | Exact visible row count or future version count |
| Official documentation | Designed MoW and Compaction behavior | Direct Notebook observation of internals |

`VersionCount` can change during the lab because background work is independent.
Tablet `RowCount` is not `COUNT(*)`. Frequent tiny writes can also create
transaction, version, and Rowset pressure, so batch continuous changes and use
Partition-level operations for whole ranges.

---

## Lab 7: Maintain Current State and Remove Data Safely

Open [Lab 7 — Maintain Current State and Remove Data Safely](lab7_update_delete_data.ipynb).
It creates only Module 7 tables:

- `order_state` for upsert, Sequence, partial update, and SQL correction;
- `order_merge_target` and `order_merge_changes` for local `MERGE INTO`;
- `order_deletions` for predicate DELETE and Delete Sign;
- `order_lifecycle` for Partition truncate and overwrite.

| Step | Observation |
| --- | --- |
| 1 | New and existing Keys follow upsert; the larger Sequence wins |
| 2 | Full-row omission uses defaults; partial update preserves values |
| 3 | SQL `UPDATE` changes only the selected Value column |
| 4 | One merge performs matched update, matched delete, and not-matched insert |
| 5 | Predicate and incoming-Key deletes produce the intended visible state |
| 6 | Truncate removes an expired range and overwrite replaces a backfill scope |

No external CDC system, object store, or downloaded dataset is involved.

## Module summary

Choose a change path from the source contract. Full-row upsert fits complete
primary-key images; Sequence protects source order. Partial update fits
field-owned patches; SQL `UPDATE` fits predicate corrections; `MERGE INTO` fits
a staged relation requiring conditional actions.

Predicate DELETE fits a SQL-defined set, Delete Sign fits incoming Unique Keys,
and `TRUNCATE` or `INSERT OVERWRITE` fits complete lifecycle scopes. Published
changes affect query visibility before Compaction necessarily reclaims storage.

## Official references

- [Data Update and Delete](https://doris.apache.org/docs/4.x/key-features/data-update-delete/) and [Unique Key](https://doris.apache.org/docs/4.x/key-features/unique-key/)
- [Load-Based Updates for the Unique Model](https://doris.apache.org/docs/4.x/data-operate/update/update-of-unique-model/) and [Column Update](https://doris.apache.org/docs/4.x/data-operate/update/partial-column-update/)
- [`UPDATE`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/UPDATE/) and [`MERGE INTO`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/MERGE-INTO/)
- [Delete Operation](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/) and [Load-Based Batch Delete](https://doris.apache.org/docs/4.x/data-operate/delete/batch-delete-manual/)
- [Truncate Operation](https://doris.apache.org/docs/4.x/data-operate/delete/truncate-manual/) and [`INSERT OVERWRITE`](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/INSERT-OVERWRITE/)
- Doris 4.1.3 terminology: [`OlapTable.java`](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/catalog/OlapTable.java) and [`InternalCatalog.java`](https://github.com/apache/doris/blob/4.1.3/fe/fe-core/src/main/java/org/apache/doris/datasource/InternalCatalog.java)
