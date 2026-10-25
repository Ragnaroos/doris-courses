# Module 3: Doris Table Models, Partitioning, and Bucketing

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1 |
| Estimated time | About 60 minutes: reading 25, Lab 25, quiz 10 |

[Course README](../../README.md) · [Open Lab 3](lab03_models_and_pruning.ipynb) · [Open Quiz 3](quiz03_models_and_data_distribution.ipynb)

## Module goal

Choose how a table treats rows with the same key, and where it stores its rows, so that writes keep the right business result and queries read only what they need.

## Learning objectives

After completing this module, you will be able to:

1. Predict the results of the same input in the Duplicate, Unique, and Aggregate Key models.
2. Choose a key model and key columns for detail records, current state, or additive metrics.
3. Distinguish partitions, buckets, sort keys, and business unique keys.
4. Read EXPLAIN to tell partition pruning from bucket pruning.
5. Explain what Merge-on-Write does for a Unique Key table.
6. Tell a smaller plan from a measured speedup.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 3.1 Three Key Models | 7 min | What the same writes leave in each model |
| 3.2 Choose a Model by What a Row Means | 4 min | Keys for details, current state, and metrics |
| 3.3 Merge-on-Write | 3 min | How a Unique Key table keeps only the latest row |
| 3.4 Partitions, Buckets, and Sort Keys | 6 min | Where rows are stored, and why that is not uniqueness |
| 3.5 Read the Plan | 5 min | Partition pruning, bucket pruning, and what a plan does not prove |
| Lab 3 | 25 min | Compare the three models, and three plans of a partitioned table |
| Quiz 3 | 10 min | Six questions on these objectives |

## 3.1 Three Key Models

The key model chosen when a table is created decides what happens to rows with the same key. A raw input table must keep every input, a current-order table the latest amount, and a sales summary must add up its metrics: keeping details, updating by key, and aggregating by function. Decide first what one row means, then choose the model.

WWI order 1 has an amount of 2300.00, and order 2 one of 405.00. In separate Lab tables, simulate correcting order 1 to 2250.00, writing three rows in this order and waiting for each write to finish:

| Write | id | amount | Meaning |
| --- | ---: | ---: | --- |
| 1 | 1 | 2300.00 | The original amount of order 1 |
| 2 | 1 | 2250.00 | The corrected amount of order 1 |
| 3 | 2 | 405.00 | The amount of order 2 |

**Duplicate Key keeps every row.** Its key decides the sort order; it is not a uniqueness constraint.

| id | amount |
| ---: | ---: |
| 1 | 2250.00 |
| 1 | 2300.00 |
| 2 | 405.00 |

**Unique Key keeps the current value of each key.** Written one after another, and without a Sequence column, a later row replaces the earlier one with the same key; Module 7 adds versions for events that arrive out of order.

| id | amount |
| ---: | ---: |
| 1 | 2250.00 |
| 2 | 405.00 |

**Aggregate Key merges values with the declared function**, here `SUM`:

| id | amount |
| ---: | ---: |
| 1 | 4550.00 |
| 2 | 405.00 |

4550.00 is 2300.00 + 2250.00. Doris computed the sum correctly, but it is not an amount that order 1 ever had: two versions of one amount are not two sales.

After Lab 3, check each result:

```sql
SELECT id, amount FROM orders_duplicate ORDER BY id, amount;
SELECT id, amount FROM orders_unique ORDER BY id;
SELECT id, amount FROM orders_aggregate ORDER BY id;
```

## 3.2 Choose a Model by What a Row Means

| What to keep | Its identifier | Model in this course |
| --- | --- | --- |
| Every raw delivery | A delivery ID | Duplicate Key keeps every row |
| The current state of an order | order_id | Unique Key, with business versions in Module 7 |
| Each distinct business event | event_id | Unique Key keeps a redelivered event once |
| Additive metrics by dimension | A combination such as date and product | Aggregate Key, with an explicit function such as SUM |

Current state and history can both use Unique Key, with different keys: a history keyed by `order_id` would overwrite the different events of one order. The References give each model's exact rules.

## 3.3 Merge-on-Write

A Unique Key table must answer queries with only the latest row of each key, although older rows of the same key are still in earlier rowsets (Module 2). **Merge-on-Write** (MoW) settles this when a row is written: Doris finds the older row of the same key and marks it as replaced, so a query reads each key's latest row without merging at read time. It is the default for new Unique Key tables in Doris 4.x, and Lab 3 sets it explicitly:

```text
UNIQUE KEY(id)
"enable_unique_key_merge_on_write" = "true"
```

Marked rows are not removed from the files at once: compaction removes them later. Merge-on-Write changes when the merging happens, not which row wins: here, without a Sequence column, the last write. Module 7 uses it for current order state, with a version column that decides which row is newer.

## 3.4 Partitions, Buckets, and Sort Keys

After deciding how to treat rows with the same key, decide where to store them. For daily order reports, partition by date, so that a query for yesterday reads yesterday's data; then bucket each day by order ID, spreading it over several tablets that can be scanned in parallel.

| Design | The question it answers | Example in Lab 3 |
| --- | --- | --- |
| Partitioning | Which rows belong to one range, and which ranges a query can skip | One partition per day, by order_date |
| Bucketing | How a partition's rows are spread over tablets | HASH(order_id), four buckets per partition |
| Sort key | How rows are sorted in storage | order_date, order_id |
| Business unique key | What identifies one business object | An order's current state by order_id |

The partitioned table is a Duplicate Key table that keeps historical details, sorted by date and order ID. A current-order table needs its own business key: if an order's date can be corrected, a key that includes the date would treat the order before and after the correction as two orders.

**SQL reading example: the table that Lab 3 creates. Do not rerun it after the Lab.**
The Lab creates and resets it; read it first to understand the layout:

<!-- reading-only-example -->
```sql
CREATE TABLE orders_partitioned (
    order_date DATE, order_id BIGINT, amount DECIMAL(18,2)
) DUPLICATE KEY(order_date, order_id)
PARTITION BY RANGE(order_date) (
    PARTITION p_day1 VALUES [('2013-01-01'), ('2013-01-02')),
    PARTITION p_day2 VALUES [('2013-01-02'), ('2013-01-03'))
)
DISTRIBUTED BY HASH(order_id) BUCKETS 4
PROPERTIES("replication_num"="1");
```

- `DUPLICATE KEY(order_date, order_id)` sorts the rows by date and order ID; it does not make order IDs unique.
- `PARTITION BY RANGE` partitions by date; each range includes its left end and excludes its right end.
- `DISTRIBUTED BY HASH(order_id) BUCKETS 4` gives each partition four buckets, by a hash of the order ID: four tablets per partition, not four BEs.
- `replication_num=1` keeps one copy, which suits the one-BE sandbox, not production.

So the orders of 2013-01-02 belong to `p_day2`, and the hash of each order ID picks one of that partition's buckets. The table has only its own data, its **base index**, with no rollup or synchronous materialized view that would store another copy in more tablets:

```text
orders_partitioned
├── p_day1: 2013-01-01 ≤ order_date < 2013-01-02
│   └── HASH(order_id), 4 tablets
└── p_day2: 2013-01-02 ≤ order_date < 2013-01-03
    └── HASH(order_id), 4 tablets
```

More buckets give more shards to scan in parallel, and more tablets to manage: choose the number from the data's size. See [Partitioning and bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/basic-concepts/).

## 3.5 Read the Plan

A hash bucket is computed from the bucketing column's value, so within a partition the same order ID always lands in the same bucket. A query that fixes both the date and the order ID can therefore read one partition, and in it one bucket. Lab 3 compares three plans:

```sql
EXPLAIN SELECT * FROM orders_partitioned;
EXPLAIN SELECT * FROM orders_partitioned WHERE order_date = '2013-01-01';
EXPLAIN SELECT * FROM orders_partitioned
WHERE order_date = '2013-01-01' AND order_id = 1;
```

| Query | `partitions=` | `tablets=` | Why |
| --- | --- | --- | --- |
| No filter | 2/2 | 8/8 | Nothing rules out a day or an order |
| Date | 1/2 | 4/4 | The second day cannot match: **partition pruning** |
| Date and order ID | 1/2 | 1/4 | Only one bucket can hold order 1: **bucket pruning** |

In the scan node `VOlapScanNode`, `tablets=` counts the tablets of the partitions that remain, so the denominator drops from 8 to 4. Field names can change between versions; look for the scan node and these two lines.

### Pruning must not change the answer, and is not yet a speedup

```sql
SELECT COUNT(*) AS sample_orders, SUM(amount) AS order_amount
FROM orders_partitioned
WHERE order_date = '2013-01-01';
```

The date filter returns five orders and 3944.20. Adding `order_id = 1` narrows the answer to one order and its original 2300.00, not the 2250.00 of the model experiment, which used separate tables. Pruning must preserve the answer to the same SQL predicates; adding a business filter can change the answer.

A plan that reads a quarter of the tablets will not necessarily run four times faster: the time also depends on how much each tablet holds, caching, and fixed costs, and on ten orders all three queries take about the same time. A smaller plan is a reason to expect less work; a speedup is something you measure, with the same data and machine, and the Query Profile of Module 2 shows what each scan read.

## Lab 3: Model Semantics, Partitioning, and Bucketing

Open [Lab 3: Model Semantics, Partitioning, and Bucketing](lab03_models_and_pruning.ipynb). You:

1. Write the same three rows into a Duplicate, a Unique, and an Aggregate Key table and compare what each keeps.
2. Create the partitioned table and compare the plans of a query without a filter, with a date filter, and with a date and an order ID.
3. Practice: decide which model answers "what is order 1's amount now", then choose a model for two orders' current amounts.

You need the course sandbox from Module 1. The optional [extension Lab on batches, partitions, and Profile](../extensions/extension23_physical_design.ipynb) compares the same designs on 100,000 rows.

## Summary

- From the same three writes, Duplicate Key keeps three rows, Unique Key the current value of each key, and Aggregate Key with SUM 4550.00 for order 1, which is not an amount the order ever had.
- Decide what one row means before choosing a model: order_id for current state, event_id for distinct events, a dimension combination for additive metrics.
- Partitions divide rows into ranges, buckets spread a partition over tablets, and the sort key orders rows; none of them makes a business key unique.
- In EXPLAIN, a date filter cuts `partitions=` to 1/2, and an equality filter on the bucketing column cuts `tablets=` to 1/4.
- Merge-on-Write marks an older row of the same key as replaced when the new row is written, so queries read only the latest row.
- A plan that reads fewer tablets predicts less work, not a measured speedup: check the result first, then measure on the same data and machine.

## Quiz 3

Open [Quiz 3: Doris Table Models, Partitioning, and Bucketing](quiz03_models_and_data_distribution.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 4: Querying External Data and Joining Lake Tables](../module04-external-access/course.md).

## References

- [Apache Doris: Duplicate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/duplicate/)
- [Apache Doris: Unique Key model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/)
- [Apache Doris: Aggregate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/)
- [Apache Doris: Partitioning and bucketing basics](https://doris.apache.org/docs/4.x/table-design/data-partitioning/basic-concepts/)
- [Apache Doris: Data bucketing](https://doris.apache.org/docs/4.x/table-design/data-partitioning/data-bucketing/)
- [Apache Doris: EXPLAIN](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/EXPLAIN/)
