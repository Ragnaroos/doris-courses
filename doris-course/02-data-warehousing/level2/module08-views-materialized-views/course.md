# Module 8: Views and Materialized Views

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1; `orders_current` and `order_events` from Lab 7 |
| Estimated time | About 117 minutes: reading 42, Lab 65, quiz 10 |

[Course README](../../README.md) · [Open Lab 8](lab08_views_and_materialized_views.ipynb) · [Open Quiz 8](quiz08_views_and_materialized_views.ipynb)

## Module goal

Give every team one definition of daily orders, store its result where repeated queries justify it, and prove from metadata, rows, and plans that the stored result is fresh, right, and used.

## Learning objectives

After completing this module, you will be able to:

1. Distinguish a regular view's saved query from a materialized view's stored result.
2. Choose a refresh trigger and scope from the freshness that consumers need and the cost of a refresh.
3. Check a materialized view's state and rows instead of trusting a successful CREATE.
4. Read in EXPLAIN whether a query was rewritten to use a materialized view, and why it was not.
5. Keep a published view's names and meanings stable when its implementation changes.
6. Decide whether repeated queries justify storing and maintaining a result.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 8.1 The Data of Level 2 | 5 min | Which data answers which question, and its amounts |
| 8.2 One Question, Two Definitions | 8 min | Why "daily orders" needs a definition before it needs speed |
| 8.3 Store a Result | 9 min | Regular, synchronous, and asynchronous views, and when to store |
| 8.4 Refresh: When and How Much | 8 min | Manual, scheduled, and partitioned refreshes |
| 8.5 Prove a Rewrite | 8 min | What EXPLAIN shows, and three reasons a query is not rewritten |
| 8.6 Keep the Contract | 4 min | Change the implementation, not the meaning |
| Lab 8 | 65 min | Publish a view, store its daily result, read the plans, and watch three kinds of maintenance |
| Quiz 8 | 10 min | Six questions on these objectives |

## 8.1 The Data of Level 2

Level 1 left a database with a history and a current state. Level 2 builds on them, and on one small case of its own:

| Data | Where it comes from | Used in | Rows and amounts |
| --- | --- | --- | --- |
| Level 1's orders | Lab 7's `orders_current` and `order_events`, from the orders that Lab 6 accepted | The main path of Modules 8–12 | 11 orders and 1510.00 of order amount; without the cancelled order 900002, 10 orders and 1310.00; 250.00 paid and 150.00 refunded |
| The warehouse case | `datasets/warehouse_case.json`, loaded by Lab 9 | Lab 9 sections 5–7, Lab 10 sections 5–6, Lab 11's optional dashboard | 10 order deliveries, 8 orders and 850.00; 7 orders and 800.00 without the cancelled one; 660.00 paid in its reporting window |
| WWI history | Lab 5's ten `wwi_*` tables | Lab 9's customer dimension, through Lab 6's `customers`; nothing else in Level 2 | 701,846 rows of 2013–2016; 663 of them are customers |

Level 1's orders were created on two days and paid twice: enough to define, store, join, and publish daily metrics, too few to measure payments in a reporting window or customers who buy again. The case has those, and Lab 9 says why it exists. Its amounts are its own; do not add them to Level 1's.

A measurement of query speed needs more rows than either has: Lab 10 generates 100,000 orders for it.

## 8.2 One Question, Two Definitions

Operations and Finance both ask for the orders of each day, and both write reasonable SQL. Operations groups the current orders by the date of their `event_time`:

```sql
SELECT DATE(event_time) AS order_date, COUNT(*) AS order_count, SUM(order_amount) AS gross_amount
FROM orders_current
GROUP BY DATE(event_time);
```

Finance groups them by the date of the event that created each order, and leaves cancelled orders out:

```sql
SELECT DATE(e.event_time) AS order_date, COUNT(*) AS order_count, SUM(o.order_amount) AS gross_amount
FROM orders_current o
JOIN order_events e ON e.order_id = o.order_id AND e.event_version = 1
WHERE o.status <> 'CANCELLED'
GROUP BY DATE(e.event_time);
```

| order_date | First query: orders, amount | Second query: orders, amount |
| --- | ---: | ---: |
| 2026-01-01 | 7, 950.00 | 9, 1200.00 |
| 2026-01-02 | 4, 560.00 | 1, 110.00 |

Neither query has an error. `orders_current` keeps the time of each order's latest event: 900001 was delivered, 900002 cancelled, and 900003 refunded on January 2, so the first query counts them on that day, the cancelled one included. The second counts each order once, on the day it was placed. They answer different questions, and a dashboard that shows one under the name of the other is wrong without any SQL error. Before a query is made faster, decide what it means.

This course takes the second definition: an order's date is the date of its version 1 event, and a cancelled order is not counted. A **regular view** saves that query under a name, so that every consumer runs the same one:

**SQL reading example: the view that Lab 8 creates. Do not rerun it after the Lab.**

<!-- reading-only-example -->
```sql
CREATE VIEW orders_view_l2 AS
SELECT o.order_id,
       DATE(e.event_time) AS order_date,
       o.customer_id, o.status, o.order_amount, o.paid_amount, o.refund_amount, o.region
FROM orders_current o
JOIN order_events e ON e.order_id = o.order_id AND e.event_version = 1
WHERE o.status <> 'CANCELLED';
```

The view names the date `order_date`, keeps the filter in one place, and shows only the columns that reports use: 10 orders and 1310.00. It stores no rows: each query of the view runs the saved query on the current tables, so it is always as fresh as they are, and costs what they cost. It is not an access grant either: Module 12 grants access to a view.

`order_amount` is the order's pre-tax value, not money received: 900003 keeps its 150.00 in the view although it was refunded. Payments and refunds are measures of their own. A view's contract says such things: what each column means, its unit, its time zone, the meaning of `NULL`, and who changes it.

## 8.3 Store a Result

A dashboard that opens the daily totals every few minutes runs the same join and aggregation again and again, and gets the same answer until the orders change. A **materialized view** stores that answer: it has a query, like a view, and a result, like a table.

| Object | What it stores | When it computes | What to watch |
| --- | --- | --- | --- |
| Regular view | The query | At every query | The cost of every query |
| Synchronous materialized view | An aggregate or a different column order of one table, kept with the table | At every load into the table | The load's extra work; only one table, and on a Unique Key table no aggregation |
| Asynchronous materialized view | The result of a query over one or several tables | At each refresh | Freshness and the cost of each refresh |

**SQL reading example: the materialized view that Lab 8 creates. Do not rerun it after the Lab.**
It stores the daily totals, with the same tables, join, and filter as the view:

<!-- reading-only-example -->
```sql
CREATE MATERIALIZED VIEW orders_daily_mv_l2
BUILD IMMEDIATE
REFRESH AUTO ON MANUAL
AS
SELECT DATE(e.event_time) AS order_date,
       COUNT(*) AS order_count,
       SUM(o.order_amount) AS gross_amount
FROM orders_current o
JOIN order_events e ON e.order_id = o.order_id AND e.event_version = 1
WHERE o.status <> 'CANCELLED'
GROUP BY DATE(e.event_time);
```

`BUILD IMMEDIATE` starts the first build when the view is created; `REFRESH AUTO` lets Doris decide how much to recompute; `ON MANUAL` means that only a `REFRESH MATERIALIZED VIEW` statement starts a refresh. The build runs as a task after `CREATE` returns. A successful `CREATE` only accepted the definition, so check four things afterward, each with its own question:

| Check | Where | Question |
| --- | --- | --- |
| `State` | `mv_infos('database'='<db>')` | Can the materialized view be used at all? NORMAL |
| `RefreshState` | the same | Did its last refresh succeed? SUCCESS |
| `SyncWithBaseTables` | the same | Does its result still match the base tables? 1 |
| The rows | `SELECT` from the materialized view | Are they the definition's answer? 9 / 1200.00 and 1 / 110.00 |

When a refresh fails or takes too long, `tasks('type'='mv')` lists the view's refresh tasks with their `Status` and `ErrorMsg`; the Lab's waits show them when they time out.

A stored result pays when the same costly query is asked often, its answer may be minutes old, and someone watches the refreshes. It does not pay for one-off exploration, for a query shape that keeps changing, or for data that changes faster than a refresh can follow. On ten orders nothing needs storing; the Lab stores them to show how a stored result behaves, and Lab 10 measures what storing saves on 100,000 rows.

## 8.4 Refresh: When and How Much

A refresh answers two questions: when it runs, and how much it recomputes.

**When.** `ON MANUAL` refreshes when a statement says so, for example at the end of the job that loads a batch, which is the right trigger when consumers need the completed batch. `ON SCHEDULE EVERY 10 MINUTE` refreshes on a clock, whether or not anything changed, which suits data that arrives continuously and a consumer who accepts a known delay. A refresh on a clock does not know whether a late batch has arrived yet.

**How much.** "Incremental" here means that Doris recomputes only the affected partitions, not that it adds new rows to the previous sum. A materialized view `PARTITION BY` a date column of its base table maps each of its partitions to that table's partitions, so a change in one day's partition refreshes one day:

| Change | What Doris can map | What `REFRESH ... AUTO` recomputes, in Lab 8 |
| --- | --- | --- |
| A new order in February 2's partition of the fact table | February 2 | One partition: `RefreshMode` PARTIAL |
| Customer 1's region in an unpartitioned customer table | No date | Both partitions: `RefreshMode` COMPLETE |

The second refresh recomputed February 2 although nothing in it changed: equal values before and after do not show how much was recomputed. The task's `NeedRefreshPartitions` does, and a partition that was published again gets a new `PartitionId`. If a day's amount changes from 200.00 to 180.00, a refresh recomputes the day from its current rows; it never adds 180.00 to 200.00.

Lab 8 also shows the other side: a manual-refresh result after a write. Its regular view shows 2 orders and 150.00 at once; its materialized view keeps 1 order and 100.00 until the refresh. A synchronous materialized view has no such gap: the load updates it, and its cost moves into every load.

## 8.5 Prove a Rewrite

Dashboards query the view, not the materialized view. When a query asks for something that a materialized view stores, Doris can rewrite the query to read the stored rows instead of the base tables: **transparent rewriting**. Four things are easily confused: the view was created, its refresh finished, a direct query of it returns the right rows, and a query of the base tables or the view was rewritten to use it. The first three do not prove the fourth.

`EXPLAIN` shows the plan of a query without running it. Each scan names the table or materialized view that it reads, and a section lists the materialized views that Doris tried: chosen, usable but not chosen, or not usable, with the reason. Lab 8 explains three queries of `orders_view_l2`:

| Query of the view | What the plan reads | `orders_daily_mv_l2` |
| --- | --- | --- |
| The daily totals | `orders_daily_mv_l2` | Chosen |
| The totals per day and region | `orders_current` and `order_events` | Not usable: `View dimensions doesn't not cover the query dimensions` |
| The totals of January 1 alone | `orders_current` and `order_events` | Not usable: `Rewrite compensate predicate by view fail` |

The second one cannot be answered: the stored rows have no region, and no rewrite can bring back a column that the materialized view did not keep. The third one surprises: the stored rows have `order_date`, yet a filter on it stopped the rewrite. Doris 4.1.3 turns `DATE(event_time) = '2026-01-01'` into a range on `event_time`, `event_time >= '2026-01-01 00:00:00' AND event_time <= '2026-01-01 23:59:59'`, before it looks for a materialized view, and the stored rows do not keep `event_time`. Over a table with a real `DATE` column, such as Module 9's order fact, the same filter can be applied to the stored rows: measured on 4.1.3, the rewrite then succeeds, although on tiny tables the optimizer may still prefer to read the base table.

When a query is not rewritten, look in this order: is the materialized view ready (`State`, `RefreshState`); does it keep the grain, the columns, and the filters that the query needs; and did the cost-based optimizer simply prefer the base tables, which it may do on tiny tables, listing the view as usable but not chosen? A rewritten plan still says nothing about whether the answer is right: compare the stored rows with the definition, as section 8.3 did.

## 8.6 Keep the Contract

Consumers depend on a view's names and meanings, not on how it is computed. That lets the implementation change underneath: a view's query can start reading a materialized view, or another table, as long as each column keeps its name, its type, and what it means, and the change is checked by comparing the old and the new answer for the same data. Renaming `gross_amount` to `revenue`, or adding `customer_id` to a view whose row is a day, changes the contract, and its consumers must hear about it first.

A new question at a new grain gets a new interface. When a regional dashboard asks for the orders of each day and region, `orders_daily_mv_l2` cannot answer; a second materialized view at that grain can, and Lab 8's practice builds it. It stores more rows than the daily one, and it is one more refresh to schedule and check.

## Lab 8: Share One Definition, Store Its Result, and Check the Rewrite

Open [Lab 8: Share One Definition, Store Its Result, and Check the Rewrite](lab08_views_and_materialized_views.ipynb). You:

1. Compare two answers to "daily orders": 7 or 9 orders on January 1.
2. Publish the course's definition as the regular view `orders_view_l2`: 10 orders, 1310.00.
3. Store its daily totals in `orders_daily_mv_l2`, and check its state and rows.
4. Explain three queries of the view, and see which ones the materialized view answers.
5. On small tables of their own: watch a manual-refresh result go stale and catch up, a synchronous materialized view that a load updates, and a partitioned refresh of one day against a refresh of both.
6. Practice: store the totals per day and region, and see the query per region rewritten.

You need the course sandbox from Module 1 and Lab 7's `orders_current` and `order_events`; the Lab changes neither, and its own objects end in `_l2`.

## Summary

- A regular view saves a query and stores nothing, so it is always as fresh and as costly as its tables; a materialized view stores a result, which a load or a refresh keeps up to date.
- Refresh on the event that consumers wait for, such as a completed batch, or on a schedule they accept; a partitioned materialized view recomputes the partitions that Doris can map to a change, and all of them when it cannot.
- After `CREATE`, check `State`, `RefreshState`, and `SyncWithBaseTables`, then compare the stored rows with the definition; `tasks('type'='mv')` says why a refresh failed.
- `EXPLAIN` lists the materialized views that Doris tried and why one was not used: a missing column or grain, a filter that it cannot apply to the stored rows, or a cheaper base table.
- Change a view's implementation freely, its names and meanings only with its consumers; a new grain is a new interface.
- Store a result when the same costly query is asked often and its consumers accept a monitored delay, not for one-off questions or tiny tables.

## Quiz 8

Open [Quiz 8: Views and Materialized Views](quiz08_views_and_materialized_views.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 9: Warehouse Modeling and Joins](../module09-modeling-and-joins/course.md).

## References

- [Apache Doris: CREATE VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/view/CREATE-VIEW/)
- [Apache Doris: Synchronous materialized views](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/sync-materialized-view/)
- [Apache Doris: Asynchronous materialized views, overview](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/overview/)
- [Apache Doris: Asynchronous materialized views, best practices](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/use-guide/)
- [Apache Doris: CREATE ASYNC MATERIALIZED VIEW](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/async-materialized-view/CREATE-ASYNC-MATERIALIZED-VIEW/)
