# Module 1: Introduction to Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris — Level 1 |
| Product baseline | Apache Doris 4.x |
| Lab version | Apache Doris 4.1.3 |
| Estimated time | 60–65 minutes, including the guided lab |

## Module goal

This module explains what Apache Doris is, which problems it is designed to
solve, how analytical workloads differ from transactional workloads, and what
a minimal working Doris workflow looks like.

By the end of the module, you will have a running Doris environment, your first
internal table, and a successful analytical query over a baseline ecommerce
event dataset.

## Learning objectives

After completing this module, you will be able to:

1. Define Apache Doris as an open-source, real-time analytical database.
2. Distinguish OLAP and OLTP by workload characteristics rather than by product
   labels alone.
3. Recognize workloads suited to Doris, including real-time dashboards,
   customer-facing analytics, observability, lakehouse analytics, and
   CDC-driven reporting.
4. Summarize the responsibilities of Frontend (FE) and Backend (BE) nodes.
5. Distinguish the integrated storage-compute architecture from the decoupled
   storage-compute architecture.
6. Connect to Doris through the MySQL protocol, create a basic table, load
   sample data, and execute an aggregation query.

## Module structure

| Section | Format | Time | Outcome |
| --- | --- | ---: | --- |
| 1.1 What Is Apache Doris? | Reading/video | 7 min | Describe Doris in terms of workload, interface, and execution model |
| 1.2 OLAP and OLTP Workloads | Reading/visual | 8 min | Classify workloads using query and write characteristics |
| 1.3 Where Doris Fits | Scenario walkthrough | 7 min | Identify suitable Doris use cases and system boundaries |
| 1.4 A First Look at Doris Architecture | Reading/visual | 9 min | Explain FE, BE, and the two deployment architectures |
| 1.5 Your First Doris Workflow | Guided walkthrough | 5 min | Follow the path from a client connection to an analytical result |
| Lab 1 | Hands-on | 25 min | Start Doris and build the persistent baseline dataset |
| Knowledge check | Quiz | 4 min | Verify the workload and architecture mental models |

---

## 1.1 What Is Apache Doris?

Apache Doris is an **open-source, real-time analytics and search database built
on an MPP architecture**. It exposes SQL through a MySQL-compatible protocol
and is designed to make fresh data available to analytical queries with low
latency.

That definition contains four important ideas.

### Open source

Apache Doris is an Apache Software Foundation top-level project. Its source
code, issue tracker, releases, and development process are public. “Open
source” describes the project and its governance; it does not describe the
workload the database runs.

### Real-time analytics

“Real-time” has two sides:

- **Data freshness:** newly ingested data becomes queryable quickly.
- **Query latency:** analytical results return quickly enough for an
  interactive dashboard, application, or investigation.

A system that refreshes data once a day is not real-time merely because its
queries are fast. A system that receives every event immediately is also not
useful for interactive analytics if each query takes several minutes. A
real-time analytical system must address both parts of the path from ingestion
to insight.

### MPP execution

MPP means **Massively Parallel Processing**. A large query is divided into work
that can run across multiple nodes and CPU cores. The partial results are then
combined into the final answer.

Consider this analytical question:

```sql
SELECT
    region,
    COUNT(*) AS purchase_count,
    SUM(revenue) AS total_revenue
FROM events
WHERE event_type = 'purchase'
GROUP BY region;
```

The answer is small—one row per region—but producing it may require scanning
millions of event rows. Parallel execution makes this shape of work very
different from looking up one order by its primary key.

### Columnar storage and vectorized execution

Analytical queries often read a few columns from many rows. Doris stores
internal-table data by column, so a query can avoid reading unrelated columns.
Its vectorized engine processes batches of column values rather than moving one
row at a time through every operator. Together with MPP execution, this design
supports large scans, filtering, joins, and aggregations.

> **Mental model:** Doris is not “a faster MySQL.” It presents a familiar SQL
> and MySQL-protocol interface, but its storage and execution engine are built
> for analytical workloads.

The [Apache Doris project README](https://github.com/apache/doris) and
[Apache Doris overview](https://doris.apache.org/docs/4.x/gettingStarted/what-is-apache-doris/)
are the source of truth for the current product definition and capabilities.

### Check your understanding

Which statement best defines Doris?

1. A dashboard application that stores chart definitions
2. A row-oriented OLTP database with an analytics plugin
3. An open-source, MPP-based database for real-time analytics and search
4. An object-storage service for Parquet files

**Answer:** 3. BI tools can query Doris, and Doris can query object storage, but
neither of those integrations defines the database itself.

---

## 1.2 OLAP and OLTP Workloads

OLTP and OLAP describe **workload patterns**. They are not reliable labels for
classifying a product by name alone.

- **OLTP** stands for Online Transaction Processing.
- **OLAP** stands for Online Analytical Processing.

### Compare the unit of work

| Characteristic | Typical OLTP workload | Typical OLAP workload |
| --- | --- | --- |
| Business purpose | Record an operational action | Understand patterns across many actions |
| Rows touched by one request | Usually one or a small number | Often thousands, millions, or more |
| Columns touched | Often most columns in a row | Often a selected subset of columns |
| Query shape | Key lookup, small insert, point update | Filter, scan, join, group, aggregate, rank |
| Write pattern | Many small concurrent transactions | Batch, micro-batch, stream, or CDC ingestion |
| Result size | One record or a small operational response | A summary, time series, cohort, or drill-down |
| Latency expectation | Fast commit for an individual action | Interactive response despite much more work |
| Example | Place order `91827` | Revenue by region during the last 24 hours |

The number of result rows is not the deciding factor. An analytical query may
return one number while scanning millions of rows:

```sql
SELECT SUM(revenue)
FROM events
WHERE event_time >= NOW() - INTERVAL 1 DAY;
```

Conversely, returning many rows is not automatically analytical. Exporting
1,000 orders by their known identifiers can still be an operational access
pattern.

### One business process, two workloads

Imagine an ecommerce checkout:

1. A customer confirms an order.
2. The application validates inventory and payment.
3. The operational database commits the order and updates its status.
4. The change is delivered to Doris through a stream or CDC pipeline.
5. A dashboard recalculates revenue, conversion, and regional demand.

The order commit is OLTP. The dashboard queries are OLAP. They are connected,
but they optimize for different units of work.

```text
Customer request
      |
      v
OLTP database ---- change stream / CDC ----> Apache Doris
      |                                         |
operational truth                         analytical serving
                                                |
                                                v
                                      dashboard / application
```

Doris supports transactions, updates, and deletes, but those capabilities do
not turn every operational workload into a good Doris workload. The right
question is: **Does the application primarily need to commit small operational
transactions, or analyze many records together?**

### Workload classification practice

| Request | Classification | Reason |
| --- | --- | --- |
| Update the shipping address for order `91827` | OLTP | Small, state-changing transaction for one business entity |
| Count purchases by region and hour | OLAP | Large scan and grouped aggregation |
| Return one customer’s current password-reset token | OLTP | Point lookup on sensitive operational state |
| Show 30-day conversion trends for 5,000 merchants | OLAP | Time-range scan, grouping, and high-concurrency analytical serving |

> **Decision rule:** classify the request by how it reads and changes data—not
> by whether it happens to use SQL.

---

## 1.3 Where Doris Fits

Doris works best when fresh or large datasets must support interactive SQL,
especially when many users or applications query the data concurrently.

### Real-time dashboards

A dashboard may continuously show order volume, conversion rate, inventory
risk, or revenue. The underlying data changes every second, while each panel
executes filters and aggregations over a recent time range.

**Fit signal:** new data must become visible quickly, and repeated aggregations
must remain interactive.

### Customer-facing analytics

In customer-facing analytics, query results appear inside a product rather
than only inside an internal BI tool. Examples include merchant portals,
advertising platforms, usage dashboards, and partner reporting APIs.

This workload adds two requirements to ordinary reporting:

- many customers may query at the same time;
- latency becomes part of the product experience.

The Doris [customer-facing analytics overview](https://doris.apache.org/use-cases/customer-facing-analytics/)
describes this combination of fresh data, interactive latency, and high
concurrency.

### Observability

Logs, traces, metrics, and application events arrive continuously. Engineers
need both search and analytics: locate a specific error, group failures by
service, calculate latency percentiles, and compare behavior before and after a
deployment.

**Fit signal:** the workload combines high-throughput event ingestion with
filters, full-text search, and aggregations. See the official
[observability architecture](https://doris.apache.org/docs/4.x/observability/overview/).

### Lakehouse analytics

Data may already live in object storage and open table formats. Doris can query
external data through catalogs and table-valued functions, or load selected
data into internal tables for predictable analytical serving.

```text
Object storage / lakehouse
          |
          | federated query or selected load
          v
     Apache Doris --------> BI, SQL clients, analytical applications
```

**Fit signal:** teams want one SQL layer across external lakehouse data and
fresh internal tables, or they need to accelerate queries over open formats.

### CDC-driven reporting

An operational database remains the system of record while change data capture
continuously delivers inserts, updates, and deletes to Doris. Reports then use
fresh operational changes without running large analytical scans against the
transactional database.

**Fit signal:** the source system must remain optimized for transactions, but
the business needs near-real-time analysis of its changing data. Doris supports
CDC-oriented integrations such as Flink CDC; the available ingestion choices
are introduced in Module 3 and summarized in the official
[load overview](https://doris.apache.org/docs/4.x/data-operate/import/load-manual/).

### When Doris is not the first component to choose

Doris is not normally the system that should:

- authorize a payment as a short, isolated business transaction;
- coordinate a multi-step checkout workflow across operational services;
- act only as raw object storage for files;
- replace a visualization layer that already provides charts and dashboards.

It can serve the analysis behind those systems. Good architecture gives each
component a clear responsibility.

---

## 1.4 A First Look at Doris Architecture

This section introduces only the component boundaries needed for the first
workflow. Module 2 follows query execution and storage organization in greater
detail.

### Frontend (FE)

The FE is the SQL entry point and coordination layer. Its responsibilities
include:

- accepting MySQL-compatible client connections;
- authenticating users and checking privileges;
- parsing and analyzing SQL;
- creating and optimizing query plans;
- managing SQL-layer metadata such as databases, tables, and schemas;
- coordinating distributed execution and node management.

When a MySQL client connects to port `9030` in the course sandbox, it connects
to the FE. “Frontend” does not mean a graphical web interface.

### Backend (BE)

The BE executes query-plan fragments using the vectorized execution engine. In
the integrated architecture, it also stores internal-table data on local
storage. Across a production cluster, multiple BEs can scan and aggregate
different pieces of a table in parallel.

```text
MySQL-compatible client
          |
          | SQL over port 9030
          v
Frontend (FE)
  parse -> analyze -> optimize -> coordinate
          |
          | distributed plan fragments
          v
Backend (BE)
  scan -> filter -> aggregate -> return partial results
```

The official [system architecture documentation](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)
provides the complete FE and BE responsibility model.

### Integrated storage-compute architecture

In the integrated architecture, a BE is stateful: it executes queries and
stores internal-table data on local disks. Storage capacity and compute
capacity therefore scale together as BE nodes are added.

This architecture is a strong fit when:

- operational simplicity is important;
- local I/O and predictable low latency are priorities;
- data and workload scale are manageable without independent elasticity.

The Lab 1 All-in-One environment uses this architecture, but with only one FE,
one BE, and one replica. It is a **single-node integrated Doris sandbox**, not a
production-ready cluster.

### Decoupled storage-compute architecture

In the decoupled architecture, persistent table data lives in shared storage
such as object storage or HDFS. BE nodes act as stateless compute nodes and use
local storage as a cache. Compute Groups can scale and isolate workloads
without creating a full independent copy of the persistent data.

The architecture also introduces a Meta Service for data-layer metadata such
as tablets, Rowsets, and ingestion transactions. FE remains the SQL entry,
planning, and SQL-metadata layer.

This architecture is a strong fit when:

- compute demand changes independently from stored data volume;
- multiple workloads need isolated compute pools over shared data;
- cloud-native elasticity is more important than the simplest deployment.

### Compare the two architectures

| Question | Integrated storage-compute | Decoupled storage-compute |
| --- | --- | --- |
| Where is persistent table data stored? | BE local storage | Shared storage layer |
| What does a BE do? | Stores data and executes queries | Executes queries and caches hot data |
| How does capacity scale? | Storage and compute scale together | Storage and compute scale independently |
| Main operational advantage | Simpler component model and local I/O | Elastic compute and workload isolation |
| Course use | Lab 1 single-node sandbox | Conceptual introduction only |

Neither architecture changes the SQL goal of this module. The choice changes
where data is stored and how resources are scaled—not whether learners can
connect with SQL and query a table.

---

## 1.5 Your First Doris Workflow

A minimal Doris workflow has six stages:

```text
Connect -> inspect -> create database -> create table -> load -> query
```

### 1. Connect to FE

Doris supports the MySQL protocol, so many MySQL-compatible clients and drivers
can connect to it. In the course sandbox:

```bash
mysql -h 127.0.0.1 -P 9030 -u root
```

MySQL protocol compatibility does not mean every MySQL feature or storage
behavior is identical. It means existing client libraries and tools can use a
familiar connection protocol and SQL interface.

### 2. Inspect the environment

```sql
SELECT VERSION();
SHOW FRONTENDS;
SHOW BACKENDS;
```

These statements answer three different questions:

- Which Doris build accepted the connection?
- Is an FE available to plan and coordinate SQL?
- Is a BE available to execute queries and, in this sandbox, store data?

### 3. Create a database and table

The following small example mirrors the schema used in the lab:

```sql
CREATE DATABASE IF NOT EXISTS doris_course;
USE doris_course;

CREATE TABLE IF NOT EXISTS events_demo (
    event_time DATETIME NOT NULL,
    event_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    region VARCHAR(16) NOT NULL,
    product_id BIGINT NOT NULL,
    revenue DECIMAL(12, 2) NOT NULL DEFAULT "0.00"
)
PROPERTIES (
    "replication_num" = "1"
);
```

The one-replica setting is specific to the single-BE teaching sandbox. Table
models, sort keys, partitions, buckets, and production replica design belong to
Module 2.

### 4. Load a few rows

```sql
INSERT INTO events_demo VALUES
    ('2026-01-01 09:00:00', 1, 101, 'view',     'region_01', 7001,  0.00),
    ('2026-01-01 09:02:00', 2, 101, 'cart',     'region_01', 7001,  0.00),
    ('2026-01-01 09:05:00', 3, 101, 'purchase', 'region_01', 7001, 29.95);
```

This is enough to demonstrate the workflow. It is not a recommendation to send
millions of individual SQL statements. Module 3 compares Doris loading methods
for local files, object storage, applications, and Kafka.

### 5. Run an analytical query

```sql
SELECT
    event_type,
    COUNT(*) AS event_count,
    SUM(revenue) AS total_revenue
FROM events_demo
GROUP BY event_type
ORDER BY event_count DESC;
```

The result contains one row for each event type. The query reads detail events
but returns a grouped summary—the fundamental shape of an analytical query.

### 6. Read the workflow as a system

```text
Client sends SQL
      |
      v
FE parses and plans
      |
      v
BE stores/scans data and executes aggregation
      |
      v
Client receives the grouped result
```

The SQL interface is intentionally simple. The distributed planning, storage,
and vectorized execution behind it are what allow the same workflow to scale to
larger analytical datasets.

---

## Lab 1: Start Doris and Build a Baseline Dataset

The lab turns the conceptual workflow into a persistent environment used by
Modules 2 and 3.

You will:

1. Start the official All-in-One image as a reusable single-node integrated
   Doris sandbox.
2. Connect to FE through the MySQL-compatible query port.
3. Use `SHOW FRONTENDS` and `SHOW BACKENDS` to verify the two components.
4. Query a remote Parquet sample with the S3 table-valued function (S3 TVF).
5. Create `doris_course.events` as the baseline internal table.
6. Load and validate 10,158,080 ecommerce event rows.
7. Run a grouped event and revenue query.
8. Stop and restart the container to confirm that Docker named volumes preserve
   FE metadata and BE table data.

Open the notebook:

[Lab 1 — Start Doris and Build a Baseline Dataset](lab1_start_doris_and_build_baseline.ipynb)

### Dataset source and attribution

The lab uses a transformed teaching copy of **eCommerce behavior data from
multi-category store**, published by Michael Kechinov and provided by the
REES46 Marketing Platform.

- [Original dataset on Kaggle](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store/data)
- [REES46 public datasets](https://rees46.com/en/datasets)
- [Firebolt E-Commerce Analytics Primer](https://www.firebolt.io/free-sample-datasets/e-commerce)

The course transformation preserves `event_time`, `event_type`, `product_id`,
and `user_id`; creates a stable `event_id`; assigns each user to a synthetic
`region`; and records price as `revenue` only for purchase events. Synthetic
regions are teaching data and do not represent real user locations.

---

## Knowledge check

1. A request reads five columns from 20 million events, groups by region, and
   returns eight rows. Which characteristic makes it analytical?
2. Why can an OLTP database remain the system of record when Doris is added to
   an architecture?
3. Which component accepts a MySQL-protocol connection and creates the query
   plan?
4. In the integrated architecture, which component stores internal-table data
   and executes query fragments?
5. What is the main resource-scaling difference between the integrated and
   decoupled architectures?
6. Does querying a Parquet file through a TVF automatically persist those rows
   in an internal Doris table?

<details>
<summary>Answers</summary>

1. The query scans and aggregates a large set of records; the small result does
   not make the work transactional.
2. The OLTP system continues to commit operational transactions, while a
   stream or CDC pipeline copies changes to Doris for analytics.
3. Frontend (FE).
4. Backend (BE).
5. Integrated BEs scale storage and compute together; decoupled deployments
   keep persistent data in shared storage and can scale compute independently.
6. No. A TVF exposes external data as a temporary relational result. An
   explicit load such as `INSERT INTO ... SELECT` is required to persist it in
   an internal table.

</details>

## Module summary

- Apache Doris is an open-source, MPP-based database for real-time analytics
  and search.
- OLTP and OLAP are workload patterns. Small operational transactions and large
  analytical scans solve different problems even when both use SQL.
- Doris is suited to fresh, interactive analytical workloads such as
  dashboards, customer-facing analytics, observability, lakehouse analytics,
  and CDC-driven reporting.
- FE accepts requests, manages SQL metadata, and plans and coordinates queries.
- BE executes queries; in the integrated architecture it also stores internal
  table data.
- Integrated storage-compute favors a simple stateful FE/BE deployment, while
  decoupled storage-compute enables shared persistent storage and independently
  scalable compute.
- A first Doris workflow is straightforward: connect, inspect, create, load,
  query, and validate.

## Official references

- [Apache Doris source repository and project overview](https://github.com/apache/doris)
- [What is Apache Doris?](https://doris.apache.org/docs/4.x/gettingStarted/what-is-apache-doris/)
- [System Architecture](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)
- [Customer-Facing Analytics](https://doris.apache.org/use-cases/customer-facing-analytics/)
- [Observability with Doris](https://doris.apache.org/docs/4.x/observability/overview/)
- [Load Overview](https://doris.apache.org/docs/4.x/data-operate/import/load-manual/)
- [All-In-One image](https://doris.apache.org/community/developer-guide/all-in-one-image/)
