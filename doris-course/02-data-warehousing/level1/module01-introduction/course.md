# Module 1: Meet Doris and Analyze Your First Orders

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox, which Lab 1 starts |
| Estimated time | About 55 minutes: reading 20, Lab 25, quiz 10 |

[Course README](../../README.md) · [Open Lab 1](lab01_connect_and_query.ipynb) · [Open Quiz 1](quiz01_doris_fundamentals.ipynb)

## Module goal

Start Doris, load ten orders into a table, and answer a first business question with SQL: how many orders are there each day, and what do they amount to?

## Learning objectives

After completing this module, you will be able to:

1. Distinguish completing a transaction from analyzing a batch of orders.
2. Explain Doris's role between business databases and analytics users.
3. Explain what the Frontend (FE) and the Backend (BE) do in an integrated storage and compute deployment.
4. Explain what connecting with the MySQL protocol gives you, and what it does not.
5. Write SQL that filters orders and summarizes them by date.
6. Tell what an order's pre-tax amount measures, and what the total of a sample can and cannot show.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 1.1 What Is Apache Doris? | 5 min | Transactions against analytics, and what the FE and BE do |
| 1.2 Doris in an Order Data Warehouse | 5 min | Where Doris sits, and what the MySQL protocol gives you |
| 1.3 The Order Table | 4 min | One row per order, and how the table is defined |
| 1.4 Filter and Summarize Orders | 6 min | WHERE, GROUP BY, and checking the result |
| Lab 1 | 25 min | Start the sandbox, create the table, and summarize ten orders by day |
| Quiz 1 | 10 min | Six questions on these objectives |

The first start of the sandbox downloads the Doris image, which takes several minutes more.

## 1.1 What Is Apache Doris?

Apache Doris is an open-source real-time analytical database. You use SQL to query details, join data, and calculate summaries.
In this course, it answers a simple question first: **how many orders are there each day, and what is their total amount?**
[Product introduction](https://doris.apache.org/docs/4.x/getting-started/what-is-apache-doris/)

### How do transactions differ from analytics?

| Work | Example | Focus |
| --- | --- | --- |
| Transaction processing (OLTP) | A customer submits an order | Whether that one order is saved correctly |
| Analytical processing (OLAP) | Count orders and total their amounts by day | The picture across a set of orders |

Both kinds of work may use `SELECT`. Looking up an order's address so that a customer can change it serves a transaction;
summarizing order amounts by date is analysis, even when the result is only two rows.

### What do the FE and the BE do?

The course's single-container sandbox runs one **Frontend** (FE) and one **Backend** (BE). It uses the **integrated storage and compute** architecture: the BE both stores the data and computes on it. (Doris also has a decoupled storage and compute architecture, in which the data lives in shared storage; the course does not use it.)

| Component | Main responsibilities |
| --- | --- |
| Frontend (FE) | Receives SQL, manages metadata such as table definitions, and plans and coordinates queries |
| Backend (BE) | Stores the tables' data, and scans, filters, and aggregates it |

Think of a query as: **the client submits SQL → the FE plans the work → the BE reads and computes → the result returns.**
Module 2 follows this path in more detail.

## 1.2 Doris in an Order Data Warehouse

In this course, a business system handles transactions such as placing orders, and Doris receives copies of the order data for analysts and reports to query.
An order data warehouse brings orders and the data needed to analyze them together, so that queries and summaries are easy to run again and again.

```text
Orders in the business system → loading → Doris → SQL analysis and reports
```

For order analysis, Doris helps you:

- **Query details**: find an order and its customer, date, and amount.
- **Summarize**: count orders and total their amounts by date or customer.
- **Join**: query orders together with customers, products, and other data.

This module uses one order table for the first two; loading, external data, quality checks, and state changes follow in Modules 4–7.

### What the MySQL protocol gives you

Doris speaks the MySQL protocol: a MySQL client, a BI tool with a MySQL driver, or Python's `pymysql`, which the Labs use, can connect to the FE and send SQL. That is all the protocol gives you:

- **It is not MySQL.** Doris's SQL, table models, and settings are its own; a statement that works in MySQL may not work in Doris, and the reverse. `SELECT VERSION()` returns `5.7.99`, the protocol version that Doris reports to MySQL clients; the Doris version is in the `Version` column of `SHOW FRONTENDS` and `SHOW BACKENDS`, `doris-4.1.3-rc02-7126cf65d96` in the sandbox.
- **It moves no data.** Connecting a tool does not copy anything from a business database into Doris; loading or synchronization does that, from Module 5 on.

## 1.3 The Order Table

This course starts with ten historical orders from Wide World Importers (WWI), a simulated wholesale business that Microsoft publishes.
The sample is the table `orders_sample`, with **one row per order**:

| Field | Meaning |
| --- | --- |
| order_id | Order ID |
| customer_id | Customer ID |
| order_date | Order date |
| order_amount | Sum of quantity × unit price over the order's item lines: the pre-tax order amount |
| line_count | Number of item lines in the order |
| data_source | Data source, WWI here |

An order can contain several item lines but takes one row in this table.
The amount is what the customer ordered, before tax; it is not money received. Whether an order is paid needs payment or account data, which this table does not have.

### The table definition in the Lab

Lab 1 shows and runs the complete `CREATE TABLE` and `INSERT` statements. Recognize these parts:

| Syntax | Meaning in this Lab |
| --- | --- |
| BIGINT, DATE, DECIMAL(18,2) | Integers, dates, and amounts with two decimal places |
| NOT NULL | The field cannot be empty |
| DUPLICATE KEY(order_id) | Keep every inserted row; the same order ID is not deduplicated |
| BUCKETS 1 | Store the table's data in one tablet; ten orders need no more |
| replication_num=1 | Keep one copy: each replica needs its own BE, and the sandbox has one |

Module 3 covers models, partitions, and buckets. After creating the table, you can view its definition with:

```sql
SHOW CREATE TABLE orders_sample;
```

## 1.4 Filter and Summarize Orders

**Run these queries after Lab 1 has created the table and inserted the ten rows**, in the same lab database.

### View one order

```sql
SELECT order_id, customer_id, order_date, order_amount, line_count
FROM orders_sample
WHERE order_id = 4;
```

`FROM` names the table, `WHERE` selects order 4, and `SELECT` names the fields to show. Expect one row:

| order_id | customer_id | order_date | order_amount | line_count |
| --- | --- | --- | --- | --- |
| 4 | 57 | 2013-01-01 | 445.20 | 3 |

Customer 57 placed this order on 2013-01-01, with three item lines and a pre-tax amount of 445.20.

### Filter higher-value orders

Find the orders of at least 1000:

```sql
SELECT order_id, order_date, order_amount
FROM orders_sample
WHERE order_amount >= 1000.00
ORDER BY order_id;
```

`>=` means greater than or equal to, and `ORDER BY` sorts the result by order ID. Expect three orders:

| order_id | order_date | order_amount |
| --- | --- | --- |
| 1 | 2013-01-01 | 2300.00 |
| 80 | 2013-01-02 | 1138.00 |
| 83 | 2013-01-02 | 6220.40 |

The three orders total 9658.40. Lab 1's first practice asks you to write this query yourself.

### Count orders and total their amounts by day

```sql
SELECT order_date,
       COUNT(*) AS sample_orders,
       SUM(order_amount) AS order_amount
FROM orders_sample
GROUP BY order_date
ORDER BY order_date;
```

The result changes from one row per order to one row per date:

- `GROUP BY` puts the orders of the same day into one group.
- `COUNT(*)` counts the rows of a group; because the table has one row per order, that is the number of orders.
- `SUM` adds the group's amounts, and `AS` names the result column.
- `ORDER BY` sorts the dates; it only sorts and does not aggregate.

| Date | Sample order count | Pre-tax order amount |
| --- | ---: | ---: |
| 2013-01-01 | 5 | 3944.20 |
| 2013-01-02 | 5 | 8276.40 |
| Total | 10 | 12220.60 |

The SQL returns the two daily rows; the "Total" row is for checking by hand. This answers the question of 1.1.

### Check the result, and what it means

```sql
SELECT COUNT(*) AS order_count,
       SUM(order_amount) AS total_amount
FROM orders_sample;
```

After a normal run, expect **10 rows and 12220.60**. Lab 1 also compares every field with the sample: two wrong amounts, one too high and one too low, could leave the total unchanged, so a matching total is a first check, not proof.

Two limits of what this total means: it is the pre-tax amount of ten sampled orders, not the business's total for those days, and it says nothing about payments.

Do not rerun the ten-row `INSERT` on its own: a Duplicate Key table keeps appending, and you would see twenty rows and an amount of 24441.20.
To start over, run the Lab's create-table step again, which resets `orders_sample`, then the insert. Retries and deduplication come in later modules.

## Lab 1: Connect to Doris and Query Your First Orders

Open [Lab 1: Connect to Doris and Query Your First Orders](lab01_connect_and_query.ipynb). You:

1. Load the Lab tools, then start the course's single-container sandbox and connect to the lab database.
2. Check that the FE and the BE are alive, and read the Doris version.
3. Create `orders_sample`, insert the ten orders, and compare them with the sample field by field.
4. Summarize the orders by day.
5. Practice: filter the orders of at least 1000.00, then the second day's orders of at least 300.

You need Docker with about 8 GB of memory for the sandbox. The sample comes from the [official Microsoft release](https://github.com/microsoft/sql-server-samples/releases/tag/wide-world-importers-v1.0), under its MIT license; the [data notes](../../datasets/README.md) describe it.

## Summary

- A transaction completes one business operation; analysis summarizes a set of data, even when it returns few rows.
- In this course, the business system handles transactions, and Doris receives the data and answers analytical queries.
- In the integrated storage and compute sandbox, the FE plans and coordinates queries, and the BE stores the data and computes on it.
- The MySQL protocol lets MySQL tools send SQL to Doris; it does not make Doris MySQL, and it does not load any data.
- `WHERE` filters rows, `GROUP BY` with `COUNT` and `SUM` summarizes them by date, and `ORDER BY` sorts the result.
- The ten sample orders have a pre-tax total of 12220.60: an amount ordered by a sample, not payments received and not the whole business; check details as well as totals.

## Quiz 1

Open [Quiz 1: Meet Doris and Analyze Your First Orders](quiz01_doris_fundamentals.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 2: Doris Storage Architecture and Write Mechanisms](../module02-architecture/course.md).

## References

- [Apache Doris: What is Apache Doris](https://doris.apache.org/docs/4.x/getting-started/what-is-apache-doris/)
- [Apache Doris: System architecture](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)
- [Apache Doris: SELECT](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-query/SELECT/)
- [Apache Doris: Duplicate Key model](https://doris.apache.org/docs/4.x/table-design/data-model/duplicate/)
- [Apache Doris: Data types](https://doris.apache.org/docs/4.x/table-design/data-type/)
- [Apache Doris: The all-in-one image](https://doris.apache.org/community/developer-guide/all-in-one-image/)
