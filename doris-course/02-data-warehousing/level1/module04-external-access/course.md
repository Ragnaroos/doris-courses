# Module 4: Querying External Data and Joining Lake Tables

| Course information | Value |
| --- | --- |
| Course | Data Warehousing with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | The course sandbox from Module 1, and a local lake environment that Lab 4 starts |
| Estimated time | About 65 minutes: reading 25, Lab 30, quiz 10 |

[Course README](../../README.md) · [Open Lab 4](lab04_query_iceberg.ipynb) · [Open Quiz 4](quiz04_internal_files_and_lake_tables.ipynb)

## Module goal

Query data where it already is, an Iceberg table and its files in object storage, join it with Doris tables, and decide when to load it into Doris instead.

## Learning objectives

After completing this module, you will be able to:

1. Distinguish Doris internal tables, Parquet files, Iceberg tables, and External Catalogs.
2. Find a lake table through a Catalog and name it as catalog.database.table.
3. Read an Iceberg table's snapshots and files, and explain which files a query of the table reads.
4. Choose between querying external data in place and loading it into an internal table.
5. Read files in object storage with the S3 table function and load them with INSERT INTO SELECT.
6. Find duplicate or missing dimension rows by comparing results before and after a join.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 4.1 Files, Tables, and Catalogs | 5 min | What each of the four objects is |
| 4.2 Connect a Catalog and Find a Table | 6 min | CREATE CATALOG, its two addresses, and catalog.database.table |
| 4.3 Snapshots and Data Files | 4 min | Which files a query of an Iceberg table reads |
| 4.4 Query in Place or Load | 3 min | When each fits, and what loading does not do |
| 4.5 Files Without a Table: the S3 Table Function | 3 min | Read a fixed set of files, and keep their rows |
| 4.6 Check a Join | 4 min | Duplicate and missing dimension rows |
| Lab 4 | 30 min | Walk the Catalog, read snapshots and files, join, and load two ways |
| Quiz 4 | 10 min | Six questions on these objectives |

## 4.1 Files, Tables, and Catalogs

Suppose historical orders are already in a data lake, and the customers are in Doris. Analysts want to query them together without first copying all the history into Doris. Four kinds of objects are involved:

| Object | What it is | How it relates to the others |
| --- | --- | --- |
| Doris internal table | A table whose definition and data Doris stores and manages | What loading writes into |
| Parquet file | A columnar data file | Can be read on its own, or be one of a lake table's files |
| Iceberg table | Metadata, snapshots, and the data files they list | Its metadata decides which files a query reads |
| External Catalog | Doris's entry to another system's metadata and tables | Makes the external tables queryable with Doris SQL |

Parquet describes the columns and rows in one file; Iceberg turns many files into one table that can change. A query of an Iceberg table therefore needs both its metadata and its files.

```text
Files in object storage ── S3 table function ─────┐
                                                 ├─ SQL results ── INSERT INTO ... SELECT ──> Doris internal table
Iceberg metadata and data files ── Catalog ───────┘
```

## 4.2 Connect a Catalog and Find a Table

An External Catalog tells Doris where another system's tables are. For Iceberg with a REST catalog service, it needs two kinds of addresses: the metadata service, to find tables, snapshots, and file lists, and the object store, to read the files. Lab 4's preparation cell creates the Catalog with the course's addresses and shows the statement it ran, which you can copy.

**External environment example; do not run it alongside the Lab.** The same statement, with placeholders for your own services. The Lab names its Catalog after the lab database and queries through it; do not create a second Catalog for the same tables, or their names get mixed up.

<!-- external-service-example -->
```sql
CREATE CATALOG <catalog_name> PROPERTIES (
    "type"="iceberg", "iceberg.catalog.type"="rest",
    "iceberg.rest.uri"="<rest_service_url>",
    "warehouse"="s3://<warehouse_bucket>/",
    "s3.endpoint"="<object_storage_url>", "s3.region"="us-east-1",
    "s3.access_key"="<access_key>", "s3.secret_key"="<secret_key>",
    "use_path_style"="true", "iceberg.rest.view-enabled"="false"
);
```

| Property | Purpose in this course |
| --- | --- |
| type, iceberg.catalog.type | The Iceberg table format, with a REST metadata service |
| iceberg.rest.uri | Where Doris finds tables, snapshots, and file lists |
| warehouse | Where the tables' files are in object storage; it must match the REST service's setting |
| s3.endpoint, s3.region, keys | Let the BEs read the files |
| use_path_style | Put the bucket name into the URL's path, which the course's Silo expects |
| iceberg.rest.view-enabled | Turn off Iceberg views, which the course does not use |

On the course's Docker network, the services are `http://course-lake-rest:8181` and `http://course-lake-silo:9000`: names that Doris resolves, not localhost on the machine of your notebook. The object store is [Silo](https://github.com/pgsty/silo), an open-source fork of the MinIO server maintained by the Pigsty project; it speaks the S3 API, so Doris reaches it with the same properties as Amazon S3. The course uses Silo because MinIO no longer publishes community container images. When Doris finds a table's definition but cannot read its rows, check the two addresses separately. Use real credentials only in the environment, never in notes or notebooks. See [Iceberg Catalog](https://doris.apache.org/docs/4.x/lakehouse/catalogs/iceberg-catalog/).

### catalog.database.table

Doris's own tables are in the Catalog `internal`. A table in another Catalog has a three-part name, `catalog.database.table`: for example `wwi_lake.sales.orders`, where `wwi_lake` is the Catalog in Doris, `sales` the external database, and `orders` the lake table. It is a name, not a file path. `SHOW CATALOGS`, `SHOW DATABASES FROM <catalog>`, and `SHOW TABLES FROM <catalog>.<database>` walk down the three parts, and `SHOW CREATE TABLE` shows a lake table's kind and location: `ENGINE=ICEBERG_EXTERNAL_TABLE` and its `LOCATION` in object storage.

```sql
SELECT order_date, COUNT(*) AS sample_orders, SUM(order_amount) AS amount
FROM wwi_lake.sales.orders
GROUP BY order_date
ORDER BY order_date;
```

With the course's ten orders, expect five orders and 3944.20 on the first day and five orders and 8276.40 on the second. The query reads the lake table; nothing is stored in Doris. The Lab keeps its table's full name in the variable `source`.

## 4.3 Snapshots and Data Files

Each commit to an Iceberg table, such as an `INSERT`, writes new data files and a new **snapshot**: the list of files that make up the table at that moment. A query of the table reads the files of its current snapshot. Doris exposes Iceberg's metadata as tables named after the table with a suffix:

| Metadata table | What it lists |
| --- | --- |
| `<table>$snapshots` | Each snapshot: its time, its parent, and its operation, such as `append` |
| `<table>$files` | The data files of the current snapshot, with their format and record counts |
| `<table>$history` | Which snapshot was current when |

In the course, **Doris writes the lake table**: Lab 4's preparation inserts the ten orders, which makes one `append` snapshot and one Parquet file. In a real data lake, other engines such as Spark or Flink usually write the tables, and Doris reads them through the same Catalog. When a query plans a scan of an Iceberg table, Doris also passes its filters to Iceberg, which can skip files whose column statistics rule them out: the plan shows them as `icebergPredicatePushdown`.

## 4.4 Query in Place or Load

| Situation | First choice | What to weigh |
| --- | --- | --- |
| Exploring history for the first time | Query in place through the Catalog | The external services' availability, network, permissions |
| Joining lake history with Doris's customers | A query across Catalogs | Whether the join keys are unique, and whether customers are missing |
| The same snapshot queried again and again | Load it into an internal table | How often to refresh, the storage, and how changes are applied |
| A fixed set of files, without a table | The S3 table function (4.5) | The files' format, columns, and access |

Querying in place is a choice of where the data stays, not a promise that every external query is fast. Loading with `INSERT INTO ... SELECT` stores the rows that one query returned: it is a copy of that moment, and it does not follow later changes in the lake unless you load again.

## 4.5 Files Without a Table: the S3 Table Function

A **table function** returns rows like a table. `S3(...)` reads files in S3-compatible object storage: it takes the path of a file, or of several with a `*`, the format, and the store's address and keys, and reads exactly those files. `DESC FUNCTION S3(...)` shows the columns that it finds in a Parquet file. `SELECT` alone stores nothing; `INSERT INTO <table> SELECT ... FROM S3(...)` writes the rows into an internal table in the same statement.

Lab 4 points the function at the lake table's own data file, which `$files` lists, and loads it into `orders_from_file`. The function does not read Iceberg snapshots: if the table later deleted rows in a new snapshot, the old file would still contain them, while a query through the Catalog reads only the current snapshot's files. Use the function for a fixed set of files, and the Catalog for a table. Module 5 compares it with Broker Load. See the [S3 table function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/).

## 4.6 Check a Join

If a customer has two rows in a dimension table, an order of 100.00 joins twice and sums to 200.00: a correct join can give a wrong amount. A customer missing from the dimension makes an order disappear from an inner join.

```text
Order: order_id=1, customer_id=832, amount=2300.00
          │ join on customer_id
          ├─ customer row A → one result row
          └─ customer row B → a second result row (a duplicate)
```

Lab 4's customer table is a Unique Key table, so each order matches at most one customer. Check row counts and amounts before and after a join, and compare loaded tables field by field.

`LEFT JOIN` keeps every order on the left, with `NULL` customer fields when no customer matches; `INNER JOIN` keeps only the matched orders. To reconcile all orders, use a `LEFT JOIN` and count the missing customers, so that fewer rows after a join are not mistaken for fewer orders. After Lab 4, in the lab database:

```sql
SELECT COUNT(*) AS missing_customers
FROM orders_from_lake o
LEFT JOIN customers_sample c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
```

Expect 0; otherwise check the customer keys and the data's scope before trusting a total. After loading, the internal table must give the lake table's result:

```sql
SELECT order_date, COUNT(*) AS sample_orders, SUM(order_amount) AS amount
FROM orders_from_lake
GROUP BY order_date
ORDER BY order_date;
```

## Lab 4: Query an Iceberg Table and Its Files

Open [Lab 4: Query an Iceberg Table and Its Files](lab04_query_iceberg.ipynb). You:

1. Start the lake services, create the Catalog, and read the SQL that the preparation ran.
2. Find the table with `SHOW CATALOGS`, `SHOW DATABASES FROM`, and `SHOW CREATE TABLE`, and read its `$snapshots` and `$files`.
3. Query the ten orders in the lake, join them with `customers_sample`, and load them into `orders_from_lake`.
4. Read the table's data file with the S3 table function and load it into `orders_from_file`.
5. Practice: the second day's orders, with missing customers counted, and the plans of the lake and the internal table.

You need the course sandbox from Module 1. The Lab starts Silo and an Iceberg REST Catalog on 127.0.0.1:51900 and 51818; the first start downloads their images. The course README's [Environment](../../README.md#environment) section lists the ports and their variables, and its [Clean up](../../README.md#clean-up) section says how to stop and remove the lake. The sample is the ten orders of Module 1, under the WWI data's MIT license.

## Summary

- A Parquet file is columnar data, an Iceberg table is metadata and snapshots over such files, and an External Catalog is Doris's entry to another system's tables; none of them copies data into Doris.
- A Catalog needs the metadata service's address and the object store's address; `SHOW CATALOGS`, `SHOW DATABASES FROM`, and `SHOW TABLES FROM` walk down to a `catalog.database.table` name.
- A query of an Iceberg table reads the files of its current snapshot; `$snapshots` and `$files` show them.
- Query in place to explore and join; load into an internal table for repeated analysis, knowing that the copy does not follow later changes.
- The S3 table function reads exactly the files it is given, ignoring any table's snapshots, and `INSERT INTO ... SELECT` keeps its rows in Doris.
- A duplicate dimension key multiplies joined rows and a missing key drops them from an inner join: count rows and amounts before and after, and count missing matches with a `LEFT JOIN`.

## Quiz 4

Open [Quiz 4: Querying External Data and Joining Lake Tables](quiz04_internal_files_and_lake_tables.ipynb). It has six single-choice questions and needs no running environment.

Next module: [Module 5: Batch and Continuous Data Ingestion](../module05-ingestion/course.md).

## References

- [Apache Doris: Catalog overview](https://doris.apache.org/docs/4.x/lakehouse/catalog-overview/)
- [Apache Doris: Iceberg Catalog](https://doris.apache.org/docs/4.x/lakehouse/catalogs/iceberg-catalog/)
- [Apache Doris: S3 table function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/)
- [Apache Doris: INSERT INTO SELECT](https://doris.apache.org/docs/4.x/data-operate/import/import-way/insert-into-manual/)
