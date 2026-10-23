# Module 10: Metric Processing and Delivery

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1; the order fact and the case's DWD tables from Lab 9 |
| Estimated time | About 146 minutes: reading 46, Lab 90, quiz 10 |

[Course README](../../README.md) · [Open Lab 10](lab10_metric_processing.ipynb) · [Open Quiz 10](quiz10_metric_processing.ipynb)

## Module goal

Turn "daily orders" and "paid GMV" into written contracts, store their measures at a declared grain, and prove with the detail that the stored numbers are right before you make them faster.

## Learning objectives

After completing this module, you will be able to:

1. Define a metric's population, grain, measures, time rule, and ratio rule before writing its SQL.
2. Build a service table at a declared grain, and rebuild it instead of loading a batch twice.
3. Reconcile a service table with the detail through a full outer join.
4. Use window functions and conditional aggregation without changing the grain of a result.
5. Tell paid GMV, order amount, and net collections apart, and keep each ratio's numerator and denominator.
6. Choose exact or approximate distinct counts, and verify an optimization with equal results and measured work.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 10.1 Write the Metric Contract | 9 min | Population, grain, measures, time, and ratios, in a table |
| 10.2 A Service Table at the Contract's Grain | 8 min | Sums and counts at one grain, rebuilt from the detail |
| 10.3 Reconcile with the Detail | 7 min | A full outer join that notices a lost day |
| 10.4 Windows, Conditions, and Ratios | 8 min | Keep the grain, and divide sums, not averages |
| 10.5 Order Amount Is Not Paid GMV | 8 min | Payments in a window, a created-order cohort, repeat buyers |
| 10.6 Exact Counts, Sketches, and Measured Work | 6 min | Bitmap and HLL, and a Profile before a speedup |
| Lab 10 | 90 min | Build and reconcile the service table, measure the case's payments, compare distinct counts, and measure a smaller table |
| Quiz 10 | 10 min | Six questions on these objectives |

## 10.1 Write the Metric Contract

Three teams report "average order value": one divides the period's amount by its orders, another averages the daily averages, a third leaves cancelled orders in. All three run. Before SQL, write down what the metric is:

| Item | Daily orders and order amount, in this course |
| --- | --- |
| Population | The orders of `orders_fact_l2` that are not CANCELLED |
| Grain | One row per order date and region |
| Measures | `order_count`, the number of orders; `gross_amount`, the sum of `order_amount`, the orders' pre-tax value, not money received |
| Time | `order_date`, the date of the order's version 1 event, in the session's time zone, +08:00 |
| Ratio | Average order amount = `gross_amount` / `order_count`, computed from the sums at the grain asked for |
| Zero and missing | A ratio without orders is `NULL`, not 0; a day without a row is missing, not zero |

Measures add up differently. An amount or a count is **additive**: it adds over days, regions, and customers alike, as long as no join has duplicated it. A balance is **semi-additive**: it adds over customers but not over days, since the same money would count once per day. A ratio is **non-additive**: an average of averages weighs each group the same, whatever its size. Keep a ratio's numerator and denominator, and divide at the grain that you report.

## 10.2 A Service Table at the Contract's Grain

The detail answers every question and costs a scan each time; a **service table** stores the measures that reports ask for, at their grain, in fewer rows. Lab 10's is an Aggregate Key table:

**SQL reading example: the service table of Lab 10. Do not rerun it after the Lab.**

<!-- reading-only-example -->
```sql
CREATE TABLE daily_order_metrics_l2 (
    order_date DATE NOT NULL,
    region VARCHAR(16) NOT NULL,
    order_count BIGINT SUM NOT NULL DEFAULT "0",
    gross_amount DECIMAL(18,2) SUM NOT NULL DEFAULT "0.00"
)
AGGREGATE KEY(order_date, region)
DISTRIBUTED BY HASH(order_date) BUCKETS 1
PROPERTIES ("replication_num"="1");
```

| order_date | region | order_count | gross_amount |
| --- | --- | ---: | ---: |
| 2026-01-01 | EAST | 5 | 720.00 |
| 2026-01-01 | WEST | 4 | 480.00 |
| 2026-01-02 | EAST | 1 | 110.00 |

Together 10 orders and 1310.00, the same as Module 8's view. The `SUM` columns add up rows with the same key, which is right for new orders and wrong for the same batch loaded twice: January 1 EAST would show 10 orders and 1440.00. The table cannot tell a new batch from a repeated one, so the job that fills it must: Lab 10 drops and rebuilds the table from the detail in every run; a production job replaces the affected partitions or loads each batch once, with a record of what it loaded.

| Option | When | What you must control |
| --- | --- | --- |
| A service table that a job builds | Cleaning, quality gates, and publication are steps of a pipeline | Reruns, the scope of each rebuild, reconciliation |
| An asynchronous materialized view (Module 8) | A stable query whose refresh Doris can manage | Refresh state, freshness, which queries it answers |
| A regular view | The definition must be shared, the cost is acceptable | The cost of every query |

Keep the detail when the service table exists: it is what finds the service table's errors.

## 10.3 Reconcile with the Detail

A service table is right when the detail, computed again by an independent query, gives the same numbers. Read the service table on one side only:

```sql
WITH detail AS (
    SELECT order_date, region, COUNT(*) AS order_count, SUM(order_amount) AS gross_amount
    FROM orders_fact_l2
    WHERE status <> 'CANCELLED'
    GROUP BY order_date, region
), serving AS (
    SELECT order_date, region, SUM(order_count) AS order_count, SUM(gross_amount) AS gross_amount
    FROM daily_order_metrics_l2
    GROUP BY order_date, region
)
SELECT COALESCE(d.order_date, s.order_date) AS order_date,
       COALESCE(d.region, s.region) AS region,
       d.order_count AS detail_orders, s.order_count AS serving_orders,
       d.gross_amount AS detail_amount, s.gross_amount AS serving_amount
FROM detail d
FULL OUTER JOIN serving s ON s.order_date = d.order_date AND s.region = d.region
ORDER BY order_date, region;
```

Join on the service table's grain, date and region. A `FULL OUTER JOIN` keeps a row that only one side has. Lab 10 compares a service table that lost January 2, as if that day's load had failed: an inner join shows the two rows of January 1, EAST and WEST, both equal, and the comparison passes; the full outer join shows 2026-01-02 EAST with 1 order and 110.00 in the detail and `NULL` in the service table. Keep the `NULL` until you know why it is there: a missing row is not a day with no orders. Check rows, amounts, dates, and the important dimensions before you tune anything: a faster query that returns the wrong answer only returns it sooner.

## 10.4 Windows, Conditions, and Ratios

`GROUP BY` folds rows into groups. A **window function** computes over related rows and keeps each row: `SUM(...) OVER (ORDER BY order_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` adds up from the first row to the current one, and `LAG(...) OVER (ORDER BY order_date)` takes the previous row's value. Give the window the grain that you want first:

```sql
WITH daily AS (
    SELECT order_date, SUM(order_count) AS order_count, SUM(gross_amount) AS gross_amount
    FROM daily_order_metrics_l2
    GROUP BY order_date
)
SELECT order_date, order_count, gross_amount,
       SUM(gross_amount) OVER (ORDER BY order_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_amount,
       LAG(gross_amount) OVER (ORDER BY order_date) AS previous_day_amount
FROM daily
ORDER BY order_date;
```

The CTE makes one row per day, so the result has one row per day: 1200.00 and then 1310.00 so far, and 1200.00 the day before January 2. A window on the service rows instead would run per region; summing a daily window that was repeated on each order would count the day once per order. `LAG` takes the previous row: here the previous day, because no day is missing; with a gap it would be an older day, and a comparison with yesterday needs a calendar of all dates. A ranking needs a rule for ties, and a moving window explicit bounds.

A **conditional aggregate** puts slices of a group side by side: `SUM(CASE WHEN region = 'EAST' THEN order_count ELSE 0 END)` counts the EAST orders of each day next to all of them, 5 of 9 on January 1. `WHERE` filters rows before they are grouped, `HAVING` filters the groups afterward.

The ratio rule matters on real data. On January 1, EAST has 5 orders and 720.00, an average of 144.00, and WEST 4 orders and 480.00, an average of 120.00. The average of the two averages is 132.00; the day's average order amount is 1200.00 / 9 = 133.33. The first weighs WEST's 4 orders as much as EAST's 5. With larger differences, such as one order of 100 against 100 orders worth 1000, the error grows: 55.00 against 10.89.

## 10.5 Order Amount Is Not Paid GMV

Order amount says what was ordered. **Gross merchandise value (GMV)** here means the value of the paid orders, from the payments themselves, not from an order status: a refunded order was still paid once. The warehouse case of Module 9 has the payments, and Lab 10 writes their contract:

| Metric | Contract |
| --- | --- |
| Paid GMV | The deduplicated successful payments with a time in `[2026-01-01, 2026-01-04)`, Asia/Shanghai; refunds are separate |
| Paid orders and customers | The distinct orders and customers of those payments |
| Created-order cohort conversion | The orders created in the window and paid before the cutoff, divided by all orders created in the window |
| Repeat-buyer rate | The customers with at least two paid orders in the window, divided by the paying customers |
| Net collections | Paid GMV minus the refunds of the window; not profit |

| Measure | Value |
| --- | ---: |
| Order amount of the case's orders, without the cancelled one | 800.00 |
| Paid GMV in the window | 660.00 from 5 paid orders and 3 customers |
| Refunds in the window | 50.00 |
| Net collections | 610.00 |
| Cohort conversion | 5 of 8 created orders: 0.62500 |
| Repeat-buyer rate | 2 of 3 customers: 0.66666 |

A payment ID that arrives twice counts once, and the payment of January 5 is outside the window. The cohort counts the cancelled order as created and not converted, which is why its contract says so: the order metrics leave cancelled orders out, the cohort does not. Distinct counts do not add up either: the paying customers of each day add up to 4, but the window has 3, because one customer paid on two days. Each ratio keeps its numerator and denominator in the published row, so a reader can check it.

## 10.6 Exact Counts, Sketches, and Measured Work

A count of distinct customers needs a promise of accuracy before a function:

| Method | Result | Fits | Costs |
| --- | --- | --- | --- |
| `COUNT(DISTINCT id)` | Exact | Reconciliations, moderate sizes | Keeps every distinct ID while it counts |
| Bitmap (`BITMAP_UNION_COUNT(TO_BITMAP(id))`) | Exact | Non-negative integer IDs, distinct counts reused at scale | Integer IDs only, bitmap functions |
| HLL (`HLL_UNION_AGG(HLL_HASH(id))`) | Approximate | Scale matters more than the last unit | An error that the consumers must know about |

On 100,000 IDs with 20,000 distinct, Lab 10's exact methods give 20,000 and HLL 19,834, an error of 0.0083 in this run: one observation, not a bound. Do not call HLL exact because it matched a small example.

To show that a service table helps, prove first that it answers like the detail: Lab 10 compares every one of 32 daily rows. Then read what each execution did: `EXPLAIN` shows the plan, a **Query Profile** the measured work of one execution, here 100,000 rows scanned for the detail against 32 for the service table. Last come timings, taken under stated conditions: 20 runs of each query, one at a time, after a warm-up, with the result cache off; their empirical 95th percentile (P95) was a few milliseconds for both. Fewer rows read does not always mean a faster query, and a timing on one computer is not a service level for a dashboard.

## Lab 10: Build and Reconcile a Service Table, and Measure Payments

Open [Lab 10: Build and Reconcile a Service Table, and Measure Payments](lab10_metric_processing.ipynb). You:

1. Write the contract of daily orders, and build `daily_order_metrics_l2` from Lab 9's order fact.
2. Roll it up for a dashboard, with averages computed from the sums.
3. Reconcile it with the detail, and see an inner join miss a lost day that a full outer join shows.
4. Compute a cumulative window and both averages of January 1 on the real days and regions.
5. Measure the case's payments: paid GMV, cohort conversion, repeat buyers, and net collections.
6. Compare exact and approximate distinct counts, and measure a 32-row table against 100,000 detail rows.
7. Practice: compute orders per customer and day from the detail.

You need the course sandbox and Lab 9's `orders_fact_l2` and the case's DWD tables. Module 11 publishes `daily_order_metrics_l2`.

## Summary

- A metric is its contract: population, grain, measures, time, and the rule for ratios, zeros, and missing rows; amounts and counts add up, balances only over some keys, ratios not at all.
- A service table stores sums and counts at one grain; rebuild it from the detail, because its `SUM` columns cannot tell a repeated batch from a new one.
- Reconcile on the service grain with a full outer join, which keeps rows that one side lacks; an inner join drops them from the comparison.
- Make the grain first, then window over it; compute a ratio from the sums at the grain you report, not as an average of averages.
- Paid GMV comes from deduplicated payments in a window, order amount from orders, net collections from both minus refunds; distinct counts per day do not add up to the window.
- Use exact counts for reconciliation and HLL where its error is accepted; prove equal results, then read the Profile's measured work, then time it.

## Quiz 10

Open [Quiz 10: Metric Processing and Delivery](quiz10_metric_processing.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 11: Interfaces and Boundaries for BI and AI Consumers](../module11-bi-and-ai/course.md).

## References

- [Apache Doris: Window functions](https://doris.apache.org/docs/4.x/query-data/window-function/)
- [Apache Doris: Aggregate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/aggregate/)
- [Apache Doris: Bitmap precise deduplication](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/bitmap-precise-deduplication/)
- [Apache Doris: HLL approximate deduplication](https://doris.apache.org/docs/4.x/query-acceleration/distinct-counts/hll-approximate-deduplication/)
- [Apache Doris: Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)
