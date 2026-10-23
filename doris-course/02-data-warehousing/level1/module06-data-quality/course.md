# Module 6: Data Quality and Schema Validation

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1; `wwi_customers` from Lab 5, or Lab 6 loads it |
| Estimated time | About 70 minutes: reading 30, Lab 30, quiz 10 |

[Course README](../../README.md) · [Open Lab 6](lab06_validate_orders.ipynb) · [Open Quiz 6](quiz06_data_quality_and_rejection.ipynb)

## Module goal

Accept only the new orders that can be trusted, keep every rejected one with its reason and its original text, and prove that the checks catch the errors they claim to catch.

## Learning objectives

After completing this module, you will be able to:

1. Distinguish type checks from business quality rules.
2. Stage raw input as text so that every rejected row can be traced to its source.
3. Route accepted and rejected rows with explicit rules and an independent customer dimension.
4. Check input coverage, uniqueness, amounts, and row-by-row results together.
5. Prove that a check works by making it fail on a known error.
6. Check what a schema change affects before and after you make it.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 6.1 Type Checks and Business Rules | 5 min | Why a value that converts can still be wrong |
| 6.2 Stage the Raw Input | 5 min | Keep every input, as text, with its own ID |
| 6.3 Route With Rules | 7 min | A classification view, two writes, and a trace back to the input |
| 6.4 Check More Than Totals | 5 min | Coverage, uniqueness, amounts, and every field |
| 6.5 Make the Checks Fail on Purpose | 3 min | Known errors that the checks must catch |
| 6.6 When the Schema Changes | 5 min | What a new column or a new type affects |
| Lab 6 | 30 min | Stage 13 inputs, route them 10 and 3, and test the checks |
| Quiz 6 | 10 min | Six questions on these objectives |

## 6.1 Type Checks and Business Rules

Module 5 showed that a load can succeed and still be wrong. Before orders reach reports, two different kinds of checks apply:

| Input | Type check | Business check |
| --- | --- | --- |
| Amount `not-a-number` | Cannot become a DECIMAL | Must not reach the accepted table as an amount |
| Missing order ID | No integer to identify the order | Cannot be an order; reject it |
| Customer ID `999999` | Converts to an integer | No such customer: still reject it |
| A negative amount | A valid decimal | Allowed only if the contract says so; this batch does not |

A column's type, a load's strict mode, and the course's SQL rules work at different levels. A rule such as "the customer exists" is a join against a customer dimension, written in SQL; no column type can express it.

### Agree on a contract for the batch first

A **data contract** is what the sender and the receivers agree each field means and when a row is acceptable. For this batch of new orders: an order ID is required, the amount is not negative, the customer is a known customer, and the source is `COURSE_SIMULATION`. The known customers come from the WWI customer table of Module 5, never from the inputs themselves, or every unknown customer would count as known.

## 6.2 Stage the Raw Input

The raw table `orders_raw` stores every business field as text, plus a stable `input_id`. Lab 6 loads the thirteen inputs from `raw_orders.json` with Stream Load, the method of Module 5: with `format=json` and `strip_outer_array=true`, each object of the file's array becomes a row, its keys matched to the columns named in `columns`. Because every business column is text, the load's strict mode has nothing to reject: `not-a-number` and a missing order ID arrive as they were sent. A typed staging table would reject those rows at the door, and their content would be lost.

Two identifiers do different jobs: `input_id` identifies one arrival in this batch, `order_id` the business order. An input without an order ID still has an `input_id`, and two arrivals of the same order keep two `input_id`s.

| input_id | Raw order_id | Raw order_amount | customer_id | Destination |
| ---: | --- | --- | --- | --- |
| 1–10 | 900001–900010 | Valid amounts, 1400.00 in total | 1–10 | Accepted |
| 11 | 900012 | not-a-number | 1 | INVALID_AMOUNT |
| 12 | NULL | 100.00 | 1 | INVALID_ORDER_ID |
| 13 | 900013 | 100.00 | 999999 | INVALID_CUSTOMER |

## 6.3 Route With Rules

`TRY_CAST` tries a conversion and returns NULL when it fails: `TRY_CAST('not-a-number' AS DECIMAL(18, 2))` is NULL, so a rule can test for that, while the original text stays in `orders_raw` for correcting and reprocessing. See [CAST and TRY_CAST](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/conversion/cast-expr/).

The rules run in a fixed order, order ID, amount, customer, source, and record the first reason that matches; a row with several problems shows its first one, and the others after it is corrected. `CASE WHEN` checks conditions from top to bottom, `THEN` gives the result of the first that matches, and `ELSE` applies when none does. The view keeps the raw fields and adds `reject_reason`:

**SQL reading example: the classification step of Lab 6. Do not rerun it after the Lab.**
The Lab first prepares `orders_raw` and the customer dimension `customers`:

<!-- reading-only-example -->
```sql
CREATE VIEW orders_classified AS
SELECT *, CASE
    WHEN TRY_CAST(order_id AS BIGINT) IS NULL THEN 'INVALID_ORDER_ID'
    WHEN TRY_CAST(order_amount AS DECIMAL(12,2)) IS NULL
      OR TRY_CAST(order_amount AS DECIMAL(12,2)) < 0 THEN 'INVALID_AMOUNT'
    WHEN TRY_CAST(customer_id AS BIGINT) IS NULL THEN 'INVALID_CUSTOMER'
    WHEN TRY_CAST(customer_id AS BIGINT) NOT IN (SELECT customer_id FROM customers) THEN 'INVALID_CUSTOMER'
    WHEN data_source IS NULL OR data_source <> 'COURSE_SIMULATION' THEN 'INVALID_SOURCE'
    ELSE NULL END AS reject_reason
FROM orders_raw;
```

`customers.customer_id` cannot be NULL here; never apply `NOT IN` to a list that might contain NULL: the condition would then be true for no row at all. Input 11 passes the order ID rule and matches the amount rule; input 13 has a valid amount but an unknown customer. The ten normal inputs get a NULL reason.

`orders_classified` is an ordinary view: it stores the query, and every query of it runs the rules again. Creating it moves no data. Two writes route the inputs:

**SQL reading example: the routing step of Lab 6. Do not rerun it after the Lab.**
The Lab first creates the empty `orders_clean` and `orders_rejected`; `orders_clean` is a Duplicate Key table, so running these writes twice would append twice.

<!-- reading-only-example -->
```sql
INSERT INTO orders_clean (
    order_id,customer_id,order_amount,status,event_version,event_id,
    event_time,paid_amount,refund_amount,region,data_source
)
SELECT order_id,customer_id,order_amount,status,event_version,event_id,
       event_time,paid_amount,refund_amount,region,data_source
FROM orders_classified WHERE reject_reason IS NULL;

INSERT INTO orders_rejected (input_id, reason)
SELECT input_id, reject_reason
FROM orders_classified WHERE reject_reason IS NOT NULL;
```

`IS NULL` and `IS NOT NULL` split the same classification into two groups that do not overlap: ten accepted and three rejected. The two writes are not one transaction across both tables: if the work stops between them, the first write's success does not mean the batch is done. To redo the Lab, recreate the result tables and run both writes again.

```text
13 raw inputs in orders_raw
          │ rules, with the independent customer dimension
          ▼
the view orders_classified (with reject_reason)
          ├─ NULL reason → orders_clean: 10 rows
          └─ a reason    → orders_rejected: 3 rows, with their input_id
```

### Trace a rejection back to its input

After the routing:

```sql
SELECT r.input_id, r.order_id, r.order_amount, r.customer_id, x.reason
FROM orders_rejected x
JOIN orders_raw r ON x.input_id = r.input_id
ORDER BY r.input_id;
```

The result is rows 11, 12, and 13 of the table in 6.2. The rejected table keeps identifiers and reasons, the raw table the original text, joined by `input_id`. A load's `ErrorURL` expires; these tables can be queried as long as you keep them. A rule can be tried with a plain `SELECT` with `CASE` before it routes anything: Lab 6's practice does that.

## 6.4 Check More Than Totals

```sql
SELECT reject_reason, COUNT(*) AS input_rows
FROM orders_classified
GROUP BY reject_reason
ORDER BY reject_reason;
```

Expect ten rows without a reason and one for each of the three reasons: every input has exactly one destination, and none is in both tables or in neither.

```sql
SELECT COUNT(*) AS orders,
       COUNT(DISTINCT order_id) AS unique_orders,
       SUM(order_amount) AS amount
FROM orders_clean;
```

Expect 10, 10, and 1400.00. Then compare every field with the expected orders: two wrong amounts, one too high and one too low, would leave the total right.

| Check | What Lab 6 verifies |
| --- | --- |
| Coverage | All 13 inputs have a destination: 10 accepted, 3 rejected |
| Identifiers and references | No duplicate order ID, every customer exists, every source is right |
| Amounts and states | 1400.00 in total, all CREATED, nothing paid or refunded |
| Time | Every event time is set and before the batch's fixed cutoff |
| Every field | Each order equals the expected order |

The cutoff `2026-01-02 12:00:00` checks this offline batch. A pipeline that keeps running also needs the time of the business event, the time it was loaded, and the time it was checked, to tell late events from slow transport or a backlog.

## 6.5 Make the Checks Fail on Purpose

A check that has never failed may not check anything. Lab 6 breaks the accepted table twice, on purpose, and calls the uniqueness check directly each time, so that the totals do not fail first and hide whether that rule works:

1. Append a copy of an existing order: the uniqueness check must fail.
2. Restore, then change the second order's ID to the first order's ID: still ten rows and 1400.00, but one order twice and another missing. The uniqueness check must fail again.

```text
Correct input → checks pass
A duplicate, or a duplicate with the same totals → the uniqueness check fails, as expected
Restore from the classified input → checks pass again → Module 7
```

The expected values come from the fixed input and the rules, and the restore reclassifies the raw input, so the checks have an independent reference even after the accepted table was written wrongly.

## 6.6 When the Schema Changes

Validating input against a schema is different from changing the schema itself. Adding a nullable column `order_channel` leaves it NULL in the old rows, but a load that maps columns by position, or an `INSERT INTO ... VALUES` without a column list, no longer fits the table, and a `SELECT *` downstream returns one more column. Changing what a column means, such as an amount that becomes tax-inclusive, needs a new agreement even when the type stays the same.

| Kind of change | What Doris does | What to check |
| --- | --- | --- |
| Lightweight Schema Change | Some operations, such as adding a value column, change only metadata | Defaults, column mappings, and the downstream queries |
| Heavyweight Schema Change | Other operations, such as some type changes, rewrite the data files in the background | The job's state, resources, and the converted data |

Whether a change is light or heavy depends on the operation, the table model, and the version, not on its name. Try it on a separate copy, never on `orders_clean`:

```text
ALTER TABLE <separate_copy_table> ADD COLUMN order_channel VARCHAR(20) NULL;
DESC <separate_copy_table>;
SHOW ALTER TABLE COLUMN;
```

Before the change, find the writes and queries that depend on the column order; after it, check the definition, the new column in old rows, a new load, and the downstream results. A background change is done when `SHOW ALTER TABLE COLUMN` reports `FINISHED`, not when the `ALTER` returns. The [schema and deletion extension](../extensions/extension67_schema_and_delete.ipynb) adds a column and changes a type on a copy of the orders; Level 3 covers rolling changes out. See [Schema Change](https://doris.apache.org/docs/4.x/table-design/schema-change/).

## Lab 6: Preserve Input, Route Rejections, and Automate Validation

Open [Lab 6: Preserve Input, Route Rejections, and Automate Validation](lab06_validate_orders.ipynb). You:

1. Stage the thirteen inputs with Stream Load, including an invalid amount, a missing order ID, and an unknown customer.
2. Route them into ten accepted and three rejected rows, and trace each rejection to its raw text by `input_id`.
3. Check the accepted orders, break them twice on purpose to see the uniqueness check fail, and restore them.
4. Practice: try a new amount-review rule with `CASE` before using it.

You need the course sandbox from Module 1 and `wwi_customers` from Lab 5; if it is missing, the Lab loads that one table from the bundled package. Module 7 reads the accepted orders. The course README's [Dataset](../../README.md#dataset) section lists the inputs.

## Summary

- A type check asks whether a value converts; a business rule asks whether it belongs in reports: an integer customer ID does not make the customer real.
- Stage raw input as text with its own `input_id`, so that nothing is rejected at the door and every rejection keeps its original text; an expired `ErrorURL` is no substitute.
- Route with explicit rules against an independent customer dimension: 13 inputs, 10 accepted and 3 rejected, each with one reason.
- Coverage, uniqueness, amounts, and a comparison of every field complement each other; a total that matches cannot prove that the details are right.
- A check is proven when a known error makes it fail and the restored data passes again; a fixed cutoff is not a freshness measure for a running pipeline.
- Before a schema change, find the writes and queries that depend on the columns; after it, check old rows, new loads, and the change's job until it is FINISHED.

## Quiz 6

Open [Quiz 6: Data Quality and Schema Validation](quiz06_data_quality_and_rejection.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 7: Data Updates, Deletion, and Event Replay](../module07-state-changes/course.md).

## References

- [Apache Doris: Stream Load, including strict mode and filtering](https://doris.apache.org/docs/4.x/data-operate/import/import-way/stream-load-manual/)
- [Apache Doris: CAST and TRY_CAST](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/conversion/cast-expr/)
- [Apache Doris: Schema Change](https://doris.apache.org/docs/4.x/table-design/schema-change/)
