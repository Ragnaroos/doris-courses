# Module 9: Warehouse Modeling and Joins

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 2 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1; `customers` from Lab 6; `orders_current` and `order_events` from Lab 7 |
| Estimated time | About 112 minutes: reading 42, Lab 60, quiz 10 |

[Course README](../../README.md) · [Open Lab 9](lab09_modeling_and_joins.ipynb) · [Open Quiz 9](quiz09_modeling_and_joins.ipynb)

## Module goal

Model the orders as a fact and the customers as a dimension, join them without losing or doubling an order, and run a chain of warehouse layers that keeps every delivery and can be rebuilt.

## Learning objectives

After completing this module, you will be able to:

1. State the grain of a fact table and a dimension table before joining them.
2. Choose a table model and key from whether a source appends records or replaces current state.
3. Check a join for lost and duplicated rows with row counts, distinct keys, and amounts.
4. Find facts whose dimension row is missing with a left join or an anti-join.
5. Read a join's type and distribution in EXPLAIN without taking a plan for a measurement.
6. Keep raw deliveries, validated detail, and aggregates in separate layers that can be rebuilt.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 9.1 Give Each Layer a Job | 8 min | ODS, DWD, DWS, and ADS, and what Level 1 already built |
| 9.2 Declare the Grain | 8 min | What one row of a fact and of a dimension means, and which table model keeps it |
| 9.3 Joins That Lose or Double Rows | 8 min | Two failures, and the joins that show or hide them |
| 9.4 How the Plan Joins | 6 min | Broadcast, shuffle, bucket shuffle, and colocate |
| 9.5 Accept a Join | 5 min | Four checks that one total cannot replace |
| 9.6 A Chain on a Case of Its Own | 7 min | From deliveries to a published summary, by rebuilding |
| Lab 9 | 60 min | Build the order fact and the customer dimension, check their join, read its plan, and run the chain |
| Quiz 9 | 10 min | Six questions on these objectives |

## 9.1 Give Each Layer a Job

A damaged amount arrives with a batch of orders. The dashboard must still show valid daily totals, and the data team must keep the bad record to fix and reload it. A warehouse that keeps only the final totals loses the evidence; one that keeps only raw input makes every report repeat the cleaning. Layers give each job its own tables:

| Layer | Question it answers | Also known as | In this course |
| --- | --- | --- | --- |
| ODS, Operational Data Store | What did the sources send? | Raw or staging layer | Lab 6's `orders_raw`, Lab 7's `event_deliveries`, Lab 9's `ods_*` tables |
| DWD, Data Warehouse Detail | Which records passed, at the business grain? | Cleaned or core layer | `orders_clean`, `orders_current`, `order_events`; Lab 9's `orders_fact_l2` and `dwd_*` tables |
| DWS, Data Warehouse Summary | Which aggregates do reports reuse? | Aggregate layer, part of a mart | Lab 10's `daily_order_metrics_l2`, Lab 9's `dws_orders_region_day_l2` |
| ADS, Application Data Service | What does a consumer read? | Serving layer, the mart's interface | Lab 11's `bi_order_metrics_l2`, Lab 9's `ads_orders_region_day_l2` |

```text
Sources → ODS (every delivery) → DWD (valid detail) → DWS (reused aggregates) → ADS (what consumers read)
              │                       │
              └→ rejected records     └→ drill-down to the detail
```

The four names are a modeling convention, not kinds of Doris tables: a layer can be a table or a view, and prefixing four tables does not make a pipeline. What makes one is written down: how each layer is computed from the one before, when it is refreshed, where rejected records go, and how a failed batch is rerun. Level 1 already built the first two layers without naming them; Labs 9 to 11 add the others.

## 9.2 Declare the Grain

A **fact** records a business event or measure: an order, a line of an order, a payment. A **dimension** describes it: the customer's name, a product's category, a region. Before you join them, say what one row of each means, its **grain**:

| Table | One row is | It is not |
| --- | --- | --- |
| `orders_fact_l2` | One order as it is now, dated by the event that created it | Every event of the order |
| `order_events` | One event of an order | The order's current state |
| `payments` | One payment | An order's paid amount |
| `customers_dim_l2` | One customer's current attributes | Every earlier version of the customer |

Lab 9's order fact keeps all 11 orders of Lab 7's current state, the cancelled 900002 too, with their status, amounts, and region, which is the sales region where the order was booked; a report decides with its filter whether a cancelled order counts. Its dimension keeps all 663 WWI customers of Lab 6, one row each.

The table model follows from how the source writes:

| Source | Model and key | Why |
| --- | --- | --- |
| Raw deliveries, an event history | Duplicate Key | Every row is a record to keep, duplicates included |
| A current state, such as a customer's attributes | Unique Key on the business key | A new row for the key replaces the old one |
| Additive measures that only grow | Aggregate Key with `SUM` | Rows with the same key are added up |

A Duplicate Key table organizes rows by its key; it does not stop a second row for an order. The order fact is rebuilt from the current state in each run, and its grain is checked with `COUNT(*)` against `COUNT(DISTINCT order_id)`. A Unique Key dimension cannot hold two current rows for one customer; a Duplicate Key one can, as soon as a load appends a changed customer instead of replacing it.

When reports need the customer's attributes at the time of each order, not today's, keep versions with validity boundaries, `valid_from` and `valid_to`, that do not overlap for a customer, and join each order to the version valid at its event time. Taking the rows with `valid_to IS NULL` answers a different question: the customer's current attributes. This course's dimension keeps only the current ones.

## 9.3 Joins That Lose or Double Rows

Two different faults break a join. A dimension row that matches twice doubles the fact's measures; a dimension row that is missing drops the fact, or leaves it without attributes. A self-contained example: customer 1 has two rows in the dimension, customer 2 one.

```sql
WITH facts AS (
    SELECT 1 AS order_id, 1 AS customer_id, 100 AS amount
    UNION ALL SELECT 2, 2, 200
), dim AS (
    SELECT 1 AS customer_id, 'Tailspin Toys (Head Office)' AS customer_name
    UNION ALL SELECT 1, 'Tailspin Toys, head office'
    UNION ALL SELECT 2, 'Tailspin Toys (Sylvanite, MT)'
)
SELECT COUNT(*) AS joined_rows, COUNT(DISTINCT f.order_id) AS orders, SUM(f.amount) AS joined_amount
FROM facts f
JOIN dim d ON f.customer_id = d.customer_id;
```

The result is 3 rows, 2 orders, and 400 for orders worth 300: order 1 counts twice. `COUNT(DISTINCT order_id)` still says 2, so it alone misses the inflation, and `SUM(DISTINCT amount)` is no repair: two orders of the same amount would count once. Compare rows, distinct orders, and the amount before and after the join, and check the dimension's key separately.

The join type decides what happens to a fact without a match:

| Join | Which facts it keeps | Use it to |
| --- | --- | --- |
| `INNER JOIN` | Only the matched ones | Analyze facts whose dimension is known; a missing customer's orders disappear |
| `LEFT JOIN` | All of them; the dimension's columns are `NULL` without a match | Keep every order and see which lack a customer |
| `FULL OUTER JOIN` | The unmatched rows of both sides too | Reconcile two sets (Module 10) |
| `LEFT SEMI JOIN` | Each fact once, if a match exists | Filter facts by a set of dimension rows |
| `LEFT ANTI JOIN` | Only the facts without a match | Find missing dimension rows |

After Lab 9, this anti-join, written as a left join, finds the orders without a customer:

```sql
SELECT f.customer_id, COUNT(*) AS orders_without_customer
FROM orders_fact_l2 f
LEFT JOIN customers_dim_l2 d ON d.customer_id = f.customer_id
WHERE d.customer_id IS NULL
GROUP BY f.customer_id;
```

An empty result means that every order has its customer. An inner join cannot do this check: it removes exactly the rows that you are looking for. Both faults can happen at once and hide each other in a total, which Lab 9 shows.

## 9.4 How the Plan Joins

The logical join says which rows appear; the physical join says how Doris brings the matching rows together:

| Distribution | What moves | When it fits |
| --- | --- | --- |
| `BROADCAST` | One side, usually the smaller, is sent to every instance that scans the other | A small dimension and a large fact |
| `PARTITIONED`, a shuffle | Both sides are redistributed by the join key | Two large sides |
| `BUCKET_SHUFFLE` | Only one side moves, to the buckets of the other | The join key is the other side's bucketing key |
| `COLOCATE` | Nothing: matching buckets are already together | Tables that share a colocation group and its bucketing |

`EXPLAIN` shows the choice on the join node: in Lab 9, `join op: INNER JOIN(BROADCAST)[]` with the condition on `customer_id`, and an exchange that sends the customers to the scan of the orders. `HASH(customer_id)` in two tables' definitions does not make them colocated: that needs a colocation group. The plan is Doris's choice for this data and its statistics; a Query Profile records what an execution actually did. With one BE and one bucket, the sandbox teaches how to read a plan, not how the strategies compare on a cluster.

A **Runtime Filter** is another part of a join plan: during execution, Doris builds a filter from the join keys of one side and applies it to the scan of the other, so rows that cannot match are skipped early. It changes how much is read, never which rows the join returns, and it does not fix a duplicated dimension key.

## 9.5 Accept a Join

Lab 9 compares the order fact before and after its left join with the customers:

| Stage | Rows | Distinct orders | Amount |
| --- | ---: | ---: | ---: |
| Before the join | 11 | 11 | 1510.00 |
| After the left join | 11 | 11 | 1510.00 |

The dimension's key is unique (663 rows, 663 customers) and the anti-join is empty. Then a faulty copy of the dimension, without customer 2 and with customer 1 twice, shows what each check catches:

| Join with the faulty dimension | Rows | Distinct orders | Amount | Unmatched orders |
| --- | ---: | ---: | ---: | ---: |
| `LEFT JOIN` | 12 | 11 | 1610.00 | 1 |
| `INNER JOIN` | 11 | 10 | 1410.00 | 0 |

The inner join returns 11 rows, the fact's own number, which looks right; only the distinct orders and the amount show that an order is missing and another counted twice. Accept a join when the dimension's key is unique, no fact lacks its dimension row, and rows, distinct keys, and amounts agree before and after.

## 9.6 A Chain on a Case of Its Own

Level 1's orders were created on two days and paid twice, too few for the payment metrics of Module 10. The warehouse case in `datasets/warehouse_case.json` has 8 orders of 5 customers over three days, with a delivery that repeats, an older version that arrives late, a malformed amount, a payment after the reporting cutoff, and a partial refund. Lab 9 runs it through all four layers:

| Layer | Tables | Rows | What happens |
| --- | --- | ---: | --- |
| ODS | `ods_order_deliveries_l2`, `ods_payment_deliveries_l2` | 10 and 7 | Every delivery kept as it came, the bad amount as text |
| DWD | `dwd_orders_l2`, `dwd_payments_l2` | 8 and 6 | One current order per order ID, by version; one payment per payment ID |
| DWS | `dws_orders_region_day_l2` | 5 | Orders and order amount per day and region, without the cancelled order: 7 orders, 800.00 |
| ADS | `ads_orders_region_day_l2` | 5 | The summary under the names that a dashboard reads |

The DWD step keeps the latest version of each order with a window function, `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY event_version DESC, input_id DESC)`: it numbers the deliveries of each order from the highest version down, and the query keeps number 1. Module 10 explains window functions. So the late delivery of order 2102 with version 1 does not turn it back from `PARTIALLY_REFUNDED` to `CREATED`. A payment ID that arrives twice is one payment, because the case declares that a repeated ID carries the same content; the same ID with a different amount would be a conflict to resolve, not a duplicate to drop.

The counts differ from layer to layer, 10, 8, and 5, because each layer has its own grain; the amount ties them together: the 800.00 of the summary is the DWD orders' 850.00 without the cancelled order's 50.00. The chain is rebuilt from ODS in each run, and the rebuild gives the same rows again. Inserting the summary a second time would count every order twice: an aggregate is reproducible when it is rebuilt from its detail, not when it is appended. The chain runs as a batch in the Lab; it implies no scheduler, no change-data capture, and no transaction across the layers.

## Lab 9: Order Facts, Customer Dimensions, and a Warehouse Chain

Open [Lab 9: Order Facts, Customer Dimensions, and a Warehouse Chain](lab09_modeling_and_joins.ipynb). You:

1. Build `orders_fact_l2`, 11 orders and 1510.00, and `customers_dim_l2`, 663 customers, and check their grain.
2. Join them, look for missing customers, and compare rows, orders, and the amount before and after.
3. Add up the orders per region, and read the join's type and distribution in the plan.
4. Join the orders with a faulty dimension, and read what each check shows.
5. Run the case through ODS, DWD, DWS, and ADS, and reconcile its published rows.
6. Practice: repair the faulty dimension.

You need the course sandbox and the tables of Labs 6 and 7. Module 10 reads the order fact and the case's DWD tables.

## Summary

- Say what one row of each table means before you join them: an order as it is now, a customer's current attributes, a delivery, a summary per day and region.
- Duplicate Key keeps every record, Unique Key replaces a key's row, Aggregate Key adds up measures; only a check of `COUNT(*)` against distinct keys shows that a Duplicate Key fact kept its grain.
- A duplicated dimension key doubles measures and a missing one drops or blanks facts; compare rows, distinct keys, and amounts before and after the join.
- Find facts without a dimension row with a left join and `IS NULL`, an anti-join; an inner join hides them.
- `EXPLAIN` shows a join's type and its distribution, such as `INNER JOIN(BROADCAST)`; it is Doris's plan, not a measurement of the execution.
- Keep ODS, DWD, DWS, and ADS apart and rebuild each from the layer before it; the counts differ by grain, and the amounts reconcile.

## Quiz 9

Open [Quiz 9: Warehouse Modeling and Joins](quiz09_modeling_and_joins.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 10: Metric Processing and Delivery](../module10-metric-processing/course.md).

## References

- [Apache Doris: Join](https://doris.apache.org/docs/4.x/query-data/join/)
- [Apache Doris: Table Model Overview](https://doris.apache.org/docs/4.x/table-design/data-model/intro/)
- [Apache Doris: Colocation Join](https://doris.apache.org/docs/4.x/query-acceleration/colocation-join/)
- [Apache Doris: Runtime Filter](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/runtime-filter/)
- [Apache Doris: Query Profile](https://doris.apache.org/docs/4.x/query-acceleration/query-profile/)
