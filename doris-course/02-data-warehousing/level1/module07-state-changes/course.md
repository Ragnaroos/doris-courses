# Module 7: Data Updates, Deletion, and Event Replay

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1; `orders_clean` and `customers` from Lab 6 |
| Estimated time | About 90 minutes: reading 35, Lab 45, quiz 10 |

[Course README](../../README.md) · [Open Lab 7](lab07_current_state_and_replay.ipynb) · [Open Quiz 7](quiz07_state_changes_and_replay.ipynb)

## Module goal

Keep the current state of each order correct while its events arrive twice, out of order, and after an interruption, keep its history, and check both against an independent ledger.

## Learning objectives

After completing this module, you will be able to:

1. Distinguish the keys and purposes of current state, event history, and raw deliveries.
2. Use business versions to resolve duplicate and out-of-order events.
3. Distinguish partial column updates from full-row writes that omit fields.
4. Distinguish soft deletion, SQL DELETE, a load's delete mark, and physical reclamation.
5. Recover from an interrupted multi-table write by replaying the whole batch.
6. Reconcile current state with independent payment, refund, and shipment records.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 7.1 Current State, History, and Deliveries | 5 min | Three tables, three keys, three questions |
| 7.2 Versions Against Arrival Order | 8 min | Why a late event does not undo a newer state |
| 7.3 Partial Column Updates | 6 min | Change a few columns and keep the others |
| 7.4 Four Kinds of Deletion | 6 min | Soft deletion, DELETE, a load's delete mark, and reclamation |
| 7.5 Replay After an Interruption | 5 min | Recover a write that stopped halfway |
| 7.6 Reconcile With an Independent Ledger | 5 min | Prove the amounts with records kept elsewhere |
| Lab 7 | 45 min | Replay events, keep history, reconcile, update one column, and delete on copies |
| Quiz 7 | 10 min | Six questions on these objectives |

## 7.1 Current State, History, and Deliveries

A dashboard needs what is true now; a refund investigation needs what happened. Keeping only the current state loses the story; keeping only the history makes every query find the right version. Lab 7 keeps both, plus the raw deliveries:

| Table | What one row is | Key and purpose |
| --- | --- | --- |
| orders_current | The current state of one order | UNIQUE KEY(order_id), resolved by `event_version` |
| order_events | One distinct business event | UNIQUE KEY(event_id): a redelivered event adds no history |
| event_deliveries | One delivery in one attempt | `attempt_id`, `delivery_id`, and the raw content: every redelivery is kept |

One order has several events, and one event can be delivered several times; `delivery_id` identifies a delivery of a message, not a parcel. Module 6's `orders_clean` gives the ten accepted orders, the first current state and the first history; all are `COURSE_SIMULATION`, and the `wwi_*` tables are not changed.

## 7.2 Versions Against Arrival Order

The business flow of order 900001 is:

```text
Version 1 CREATED → version 2 PAID → version 3 SHIPPED → version 4 DELIVERED
```

Version 1 is the starting state; the later events arrive deliberately out of order, and one twice:

| Position in the first delivery round | event_id | event_version | Event status | Current status after it |
| --- | --- | ---: | --- | --- |
| 1 | E08 | 4 | DELIVERED | DELIVERED, version 4 |
| 2 | E02 | 3 | SHIPPED | Still DELIVERED, version 4 |
| 3 | E01 | 2 | PAID | Still DELIVERED, version 4 |
| 9 | E02 | 3 | SHIPPED, a redelivery | Still DELIVERED, version 4 |

Each event carries the complete state of the order after it (an after-image), not just the fields that changed: version 4 holds DELIVERED and also the amount, the customer, and the payment at that moment, so it can build the current row even before versions 2 and 3 arrive. An event that carries only the changed fields needs a partial update instead (7.3).

The current table names `event_version` as its **Sequence column**: among rows with the same key, Doris keeps the one with the highest sequence value, not the one that arrived last. Find these three settings in the table definition that Lab 7 shows:

```text
UNIQUE KEY(order_id)
"enable_unique_key_merge_on_write"="true"
"function_column.sequence_col"="event_version"
```

The first identifies the order, the second turns on Merge-on-Write (Module 3), and the third names the version column. A column that is merely called `event_version` decides nothing. Versions need only be comparable within one order; two different events with the same version would need a rule of their own, which this course does not cover. See [Sequence columns and concurrent update control](https://doris.apache.org/docs/4.x/data-operate/update/unique-update-concurrent-control/).

After Lab 7:

```sql
SELECT order_id, status, event_version, paid_amount, refund_amount
FROM orders_current
WHERE order_id IN (900001, 900003)
ORDER BY order_id;
```

| order_id | status | event_version | paid_amount | refund_amount |
| ---: | --- | ---: | ---: | ---: |
| 900001 | DELIVERED | 4 | 100.00 | 0.00 |
| 900003 | REFUNDED | 4 | 150.00 | 150.00 |

### What counts as a safe duplicate

Processing something **idempotently** means that processing it again leaves a correct result unchanged. The course requires a redelivered `event_id` to carry the same content; the same ID with different content is a conflict, not a duplicate to overwrite. `event_version` is the business's own counter per order, not a Kafka offset or a binlog position: those positions say how far a reader got, not which state is newer.

## 7.3 Partial Column Updates

Suppose order 900001 must be cancelled, and the message carries only its key, the new status, and a version. Whether the other columns keep their values or become defaults or NULL depends on how the row is written, not on leaving columns out of an `INSERT`. A **partial column update** merges the supplied columns into the existing row and keeps the others; it needs a Merge-on-Write Unique Key table and the session setting `enable_unique_key_partial_update`.

Lab 7 tries it on its own copy, `orders_partial_update`, not on the current table:

| Stage | status | event_version | order_amount | region |
| --- | --- | ---: | ---: | --- |
| The starting row | CREATED | 1 | 100.00 | EAST |
| After the partial update of status and version | CANCELLED | 2 | 100.00 | EAST |

**SQL reading example: the partial-update step of Lab 7. Do not rerun it after the Lab.**
The Lab first writes the starting row into its own copy, then runs in the same connection:

<!-- reading-only-example -->
```sql
SET enable_unique_key_partial_update = true;
INSERT INTO orders_partial_update (order_id, status, event_version)
VALUES (900001, 'CANCELLED', 2);
```

`SET` turns on partial updates for this session; the `INSERT` gives the key and the two columns to change. The Lab saves the setting's earlier value and restores it with Python's try/finally, whether the write succeeds or fails; never leave it on in a connection that writes full rows.

```sql
SELECT order_id, status, event_version, order_amount, region
FROM orders_partial_update
ORDER BY order_id;
```

The result is the second row of the table: CANCELLED is not enough on its own; the amount and the region must not be cleared. See [Partial column updates](https://doris.apache.org/docs/4.x/data-operate/update/partial-column-update/).

## 7.4 Four Kinds of Deletion

| Kind | Who uses it | What it does |
| --- | --- | --- |
| A business flag such as `is_deleted` | The business tables and their queries | Keeps the row; every query must filter on the flag |
| SQL `DELETE` | A statement | Removes rows from every later query |
| A load's delete mark, `__DORIS_DELETE_SIGN__` | A load into a Unique Key table: Stream Load with `merge_type` MERGE and a `delete` condition, or a CDC connector | Deletes the key that the loaded row names, as a CDC pipeline does for a source DELETE |
| Physical reclamation | Compaction, inside Doris | Later frees the space of rows that queries no longer see, such as the rows that a Delete Bitmap marks |

A **Delete Bitmap** is how Merge-on-Write marks rows that queries no longer see; it is used for every overwritten row, not only for deletions. Whichever kind you use, a row that queries no longer return does not prove that its space is free. A refund is not a deletion either: order 900003 keeps its payment and its refund, REFUNDED; deleting the payment to show zero net receipts would erase a fact. See [Update and deletion](https://doris.apache.org/docs/4.x/data-operate/update/update-overview/).

Lab 7's copy `orders_delete_demo` starts with orders 900001 and 900002. First a soft delete of 900001: the table still has two rows, and only `WHERE is_deleted=false` hides 900001. Then `DELETE` removes 900002: ordinary queries return only 900001, still flagged.

**SQL reading example: the deletion step of Lab 7. Do not rerun it after the Lab.**
The Lab first rebuilds the copy with 900001 and 900002:

<!-- reading-only-example -->
```sql
UPDATE orders_delete_demo SET is_deleted=true WHERE order_id=900001;
SELECT order_id FROM orders_delete_demo WHERE is_deleted=false ORDER BY order_id;
DELETE FROM orders_delete_demo WHERE order_id=900002;
```

`UPDATE` works only on a Unique Key table such as this copy: on a Duplicate or Aggregate Key table, Doris refuses it with `Only unique table could be updated`. `DELETE` with a condition also works on a Duplicate Key table.

```sql
SELECT order_id, is_deleted, status
FROM orders_delete_demo
ORDER BY order_id;
```

The last query returns 900001, true, CREATED. Lab 7 does not run a load deletion marker experiment: the [schema and deletion extension](../extensions/extension67_schema_and_delete.ipynb) does, in its second section: after a delete at version 2, a replayed version 1 does not bring the order back, and only a new version 3 does.

## 7.5 Replay After an Interruption

Lab 7 interrupts its own steps, not the database:

```text
Record the first delivery → write it to the history → [interruption] → the current table is not written yet
                                              │
                    Redeliver the whole batch ←┘
                         │
                         ├─ record every delivery again
                         ├─ the history keeps each event_id once
                         └─ the current table keeps the highest version per order_id
```

The three tables are written in separate steps, not in one transaction. So recovery must not skip events that are already in the history: that would also skip the current-table writes that never happened. Replaying the whole batch is safe because each table is written idempotently. The three counts after two replays:

| Table | Rows | Why |
| --- | ---: | --- |
| orders_current | 11 | Ten starting orders and one new order |
| order_events | 18 | Ten starting events and eight distinct new events |
| event_deliveries | 19 | One before the interruption and two rounds of nine |

```sql
SELECT 'current' AS record_type, COUNT(*) AS rows_count FROM orders_current
UNION ALL
SELECT 'history' AS record_type, COUNT(*) AS rows_count FROM order_events
UNION ALL
SELECT 'deliveries' AS record_type, COUNT(*) AS rows_count FROM event_deliveries
ORDER BY record_type;
```

Redeliveries add deliveries, not events, and leave the current state as it was.

Lab 7 uses simulated events from a file, replayed after its own steps were interrupted, so it does not require real CDC setup. A CDC pipeline also needs the source's log position, the switch from snapshot to changes, and the connector's own recovery, so that the needed changes can still be read; the [optional reading on continuous ingestion](../module05-ingestion/optional05_continuous_ingestion.md) explains them, and the optional [Lab 5B](../module05-ingestion/optional05_flink_mysql_cdc.ipynb) runs a controlled Savepoint stop and restore with a real MySQL binlog. Neither covers a failed source database or a binlog that was purged.

## 7.6 Reconcile With an Independent Ledger

A replay that leaves the expected counts can still have wrong amounts. `business_events.json` keeps the items, payments, refunds, and shipments separately, as another system would; Lab 7 loads them into their own tables and checks the current state against them: each order's amount equals its items, its paid amount its payments, and its refunded amount its refunds. Each refund must belong to a payment of the same order, each shipment to an order, and every customer and product to the WWI dimensions.

```sql
SELECT SUM(order_amount) AS orders_amount,
       SUM(paid_amount) AS paid,
       SUM(refund_amount) AS refunded,
       SUM(paid_amount - refund_amount) AS net_receipts
FROM orders_current;
```

Expect 1510.00, 250.00, 150.00, and 100.00. Order 900003 keeps 150.00 paid and 150.00 refunded; only its net receipts are zero. These are simulated business records, separate from WWI's account receipts.

## Lab 7: Resolve Out-of-Order Events, Preserve History, and Replay Recoverably

Open [Lab 7: Resolve Out-of-Order Events, Preserve History, and Replay Recoverably](lab07_current_state_and_replay.ipynb). You:

1. Watch a normal update, a duplicate, and a late event on a small table of its own.
2. Build the current, history, and delivery tables from Module 6's accepted orders.
3. Interrupt the steps, replay the whole batch twice, and check 11 orders, 18 events, and 19 deliveries.
4. Reconcile the current state with the independent ledger of items, payments, refunds, and shipments.
5. Update one column of an order, and delete orders, on separate copies.
6. Practice: read the history of the refunded order 900003, and replay a late event twice.

You need the course sandbox from Module 1, and `orders_clean` and `customers` from Lab 6; if `wwi_products` is missing, the Lab loads it from the bundled package. Level 2 starts with [Module 8: Views and Materialized Views](../../level2/module08-views-materialized-views/course.md).

## Summary

- Keep the current state by `order_id`, the history by `event_id`, and every delivery per attempt: three grains for three questions.
- A Sequence column keeps the highest business version of each order, whatever order the events arrive in; a redelivered event must carry the same content, and a reader's position is not a version.
- A partial column update needs a Merge-on-Write Unique Key table and its session setting; check the changed columns and the kept ones, and restore the setting.
- A business flag hides rows only from queries that filter on it, `DELETE` removes rows from every query, a load's delete mark deletes a key, and reclamation frees space later; a refund keeps its payment.
- After an interruption between writes, replay the whole batch: idempotent tables leave 11 orders, 18 events, and 19 deliveries.
- Reconcile with records kept elsewhere: 1510.00 ordered, 250.00 paid, 150.00 refunded, and 100.00 net.

## Quiz 7

Open [Quiz 7: Data Updates, Deletion, and Event Replay](quiz07_state_changes_and_replay.ipynb). It has six single-choice questions and needs no running environment.

Next: this is the last module of Level 1. Level 2 starts with [Module 8: Views and Materialized Views](../../level2/module08-views-materialized-views/course.md).

## References

- [Apache Doris: Unique Key model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/)
- [Apache Doris: Sequence columns and concurrent update control](https://doris.apache.org/docs/4.x/data-operate/update/unique-update-concurrent-control/)
- [Apache Doris: Partial column updates](https://doris.apache.org/docs/4.x/data-operate/update/partial-column-update/)
- [Apache Doris: Update and deletion overview](https://doris.apache.org/docs/4.x/data-operate/update/update-overview/)
- [Apache Doris: DELETE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/DELETE/)
- [Apache Doris: Compaction principles](https://doris.apache.org/docs/4.x/admin-manual/trouble-shooting/compaction-principles/)
