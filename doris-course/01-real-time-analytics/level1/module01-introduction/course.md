# Module 1: Introduction to Apache Doris

| Course information | Value |
| --- | --- |
| Course | Real-time Analytics with Apache Doris · Level 1 |
| Doris | Apache Doris 4.1.3 |
| Environment | Docker with 4 CPUs and 8 GB of memory; Lab 1 starts the course sandbox |
| Estimated time | About 70 minutes: reading 30, Lab 30, quiz 10 |

[Course README](../../README.md) · [Open Lab 1](lab01_start_doris_and_build_baseline.ipynb) · [Open Quiz 1](quiz01_doris_fundamentals.ipynb)

## Module goal

Learn what Apache Doris is and which workloads it is built for, then start a
Doris sandbox and load the event dataset that every later module uses.

## Learning objectives

After completing this module, you will be able to:

1. Define Apache Doris as an open-source, real-time analytics and search database built on an MPP architecture.
2. Distinguish OLAP from OLTP by the work that a request does, not by the product that runs it.
3. Recognize workloads that suit Doris, such as real-time dashboards, customer-facing analytics, observability, lakehouse analytics, and CDC-driven reporting.
4. Summarize what the Frontend (FE) and the Backend (BE) each do with a query.
5. Distinguish the integrated storage and compute architecture from the decoupled storage and compute architecture.
6. Connect to Doris through its MySQL-compatible protocol, create a table, load data, and check the result with an aggregation query.

## Module structure

| Section | Time | Outcome |
| --- | ---: | --- |
| 1.1 What Is Apache Doris? | 7 min | Describe Doris by its workload, interface, and execution model |
| 1.2 OLAP and OLTP Workloads | 8 min | Classify a request by how it reads and changes data |
| 1.3 Where Doris Fits | 7 min | Recognize workloads that suit Doris, and work it should leave to other systems |
| 1.4 A First Look at Doris Architecture | 8 min | Explain the FE, the BE, and the two deployment architectures |
| Lab 1 | 30 min | Start Doris, load 10,158,080 events from S3, and run a first aggregation |
| Quiz 1 | 10 min | Six questions on these objectives |

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
Its vectorized execution engine processes batches of column values rather than moving one
row at a time through every operator. Together with MPP execution, this design
supports large scans, filtering, joins, and aggregations.

> **Mental model:** Doris is not “a faster MySQL.” It presents a familiar SQL
> and MySQL-compatible protocol, but its storage and execution engine are built
> for analytical workloads.

The [Apache Doris project README](https://github.com/apache/doris) and
[Apache Doris overview](https://doris.apache.org/docs/4.x/getting-started/what-is-apache-doris/)
are the source of truth for the current product definition and capabilities.

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
return one number while scanning millions of rows. On the course data, this
query reads the 4,768,620 events of December 2019 and returns one value,
18,134,559.98:

```sql
SELECT SUM(revenue)
FROM events
WHERE event_time >= '2019-12-01 00:00:00'
  AND event_time <  '2020-01-01 00:00:00';
```

The course data comes from 2019 and 2020, so the course's queries use fixed
dates; a query relative to `NOW()` would find no rows.

Conversely, returning many rows is not automatically analytical. Exporting
1,000 orders by their known identifiers can still be an operational access
pattern.

### One business process, two workloads

Imagine an ecommerce checkout:

1. A customer confirms an order.
2. The application validates inventory and payment.
3. The operational database commits the order and updates its status.
4. The change is delivered to Doris through a stream or change data capture
   (CDC) pipeline. CDC continuously copies committed changes from the
   operational database to downstream systems without moving analytical reads
   onto the transactional database.
5. A dashboard recalculates revenue, conversion, and regional demand.

The order commit is OLTP. The dashboard queries are OLAP. They are connected,
but they optimize for different units of work.

```text
Customer request
      |
      v
OLTP database ---- change stream / CDC pipeline ----> Apache Doris
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
CDC-oriented integrations such as Flink CDC; the available load methods
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

## 1.4 A First Look at Doris Architecture

The first workflow depends on two component boundaries: FE accepts and plans
SQL, while BE executes the assigned work and manages internal-table data in an
integrated storage and compute deployment.

### Frontend (FE)

The FE is the SQL entry point and coordination layer. Its responsibilities
include:

- accepting MySQL-compatible client connections;
- authenticating users and checking privileges;
- parsing and analyzing SQL;
- creating and optimizing a distributed query plan, then assigning its plan
  fragments to BE nodes for execution;
- managing SQL-layer metadata such as databases, tables, and schemas;
- coordinating distributed execution and node management.

FE accepts MySQL-protocol connections on its query port, `9030` by default. In
the course sandbox, host port `19030` forwards to that port, so a MySQL client
that connects to `127.0.0.1:19030` is talking to the FE. “Frontend” does not
mean a graphical web interface.

### Backend (BE)

The BE executes the assigned plan fragments using the vectorized execution
engine. In the integrated storage and compute architecture, it also stores
internal-table data on local storage. Across a production cluster, multiple
BEs can scan and aggregate different pieces of a table in parallel.

```text
MySQL-compatible client
          |
          | SQL over the FE query port (9030; host port 19030 in the sandbox)
          v
Frontend (FE)
  parse -> analyze -> optimize -> coordinate
          |
          | assigned plan fragments
          v
Backend (BE)
  scan -> filter -> aggregate -> return partial results
```

The official [system architecture documentation](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)
provides the complete FE and BE responsibility model.

### Integrated storage and compute architecture

In the integrated storage and compute architecture, a BE is stateful: it executes
queries and stores internal-table data on local disks. Storage capacity and
compute capacity therefore scale together as BE nodes are added.

This architecture is a strong fit when:

- operational simplicity is important;
- local I/O and predictable low latency are priorities;
- data and workload scale are manageable without independent elasticity.

The Lab 1 All-in-One environment uses this architecture, but with only one FE,
one BE, and one replica. It is a **single-node integrated Doris sandbox**, not a
production-ready cluster.

### Decoupled storage and compute architecture

In the decoupled storage and compute architecture, which some Doris
documentation calls Shared Storage, persistent table data lives in shared
storage such as object storage or HDFS. BE nodes act as stateless compute nodes
and use local storage as a cache. Compute Groups can scale and
isolate workloads without creating a full independent copy of the persistent
data.

The architecture also introduces a Meta Service for data-layer metadata such
as tablets, Rowsets, and load transactions. FE remains the SQL entry,
planning, and SQL-metadata layer.

This architecture is a strong fit when:

- compute demand changes independently from stored data volume;
- multiple workloads need isolated compute pools over shared data;
- cloud-native elasticity is more important than the simplest deployment.

### Compare the two architectures

| Question | Integrated storage and compute architecture | Decoupled storage and compute architecture |
| --- | --- | --- |
| Where is persistent table data stored? | BE local storage | Shared storage layer |
| What does a BE do? | Stores data and executes queries | Executes queries and caches hot data |
| How does capacity scale? | Storage and compute scale together | Storage and compute scale independently |
| Main operational advantage | Simpler component model and local I/O | Elastic compute and workload isolation |
| Example deployment | Single-node integrated sandbox | Compute Groups over shared storage |

Both architectures expose the same SQL interface. They differ in where data is
stored and whether storage and compute resources scale together or
independently.

## Lab 1: Start Doris and Build a Baseline Dataset

Lab 1 creates the persistent environment and baseline dataset used by the next
modules. You need Docker with at least 4 CPUs, 8 GB of memory, and 20 GiB of free
disk; the course README lists the platforms and downloads. Plan about 30
minutes; the first run also downloads the Doris image, about 1.9 GB.

You will:

1. Start the official All-in-One image as a reusable single-node integrated
   Doris sandbox.
2. Connect to FE through the MySQL-compatible query port.
3. Use `SHOW FRONTENDS` and `SHOW BACKENDS` to verify the two components.
4. Query a remote Parquet sample with the S3 table-valued function (S3 TVF).
5. Create `doris_course.events` as the baseline internal table.
6. Load and validate 10,158,080 ecommerce event rows.
7. Run a grouped event and revenue query.
8. Optionally, stop and restart the container to confirm that Docker named
   volumes preserve FE metadata and BE table data.

Open the notebook:

[Lab 1 — Start Doris and Build a Baseline Dataset](lab01_start_doris_and_build_baseline.ipynb)

The Lab ends with a practice: find the day with the most purchase revenue.
Predict the result first, then write the code in the empty cell; the collapsed
reference solution after it also runs with Run All and leaves the Lab's tables
as they were.

### Dataset source and attribution

The lab uses a transformed course copy of **eCommerce behavior data from
multi-category store**, published by Michael Kechinov and provided by the
REES46 Marketing Platform.

- [Original dataset on Kaggle](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store/data)
- [REES46 public datasets](https://rees46.com/en/datasets)
- [Firebolt E-Commerce Analytics Primer](https://www.firebolt.io/free-sample-datasets/e-commerce)

The transformation preserves `event_time`, `event_type`, `product_id`,
and `user_id`; creates a stable `event_id`; assigns each user to a synthetic
`region`; and records price as `revenue` only for purchase events. Synthetic
regions do not represent real user locations.

The course copy is 40 Parquet files (about 72 MiB, 10,158,080 rows) in the
public bucket `doris-courses-public-dataset` in AWS `us-east-1`. The bucket
allows anonymous reads, so the lab needs no AWS account or credentials.

### What the data looks like

A few features of the data explain results that you will see in later
modules:

| Feature | Value |
| --- | --- |
| Time range | 26 days in two months: 2019-12-01 to 2019-12-15 and 2020-03-01 to 2020-03-11; January and February 2020 have no events |
| Event types | 9,437,184 `view`, 589,824 `cart`, and 131,072 `purchase` events |
| Days with purchases | Seven: 2019-12-01 to 2019-12-04 and 2020-03-01 to 2020-03-03; the other 19 days have a revenue of 0.00 |
| Days with views | Thirteen: 2019-12-05 to 2019-12-11 and 2020-03-03 to 2020-03-08 |
| Days with cart events | Fifteen: 2019-12-01 to 2019-12-04, 2019-12-12 to 2019-12-15, 2020-03-01 to 2020-03-03, and 2020-03-08 to 2020-03-11 |
| Regions | Eight synthetic values, `region_01` to `region_08`, each with about 1.27 million events |
| Users and products | 1,580,057 users and 204,231 products |

The course copy is a subset of the original publication, so its counts are not
those of the original dataset, and its event types barely overlap in time:
only 2020-03-03 has views, cart events, and purchases, and the purchase days
before it have no views. A daily ratio from views to purchases therefore
means nothing in this data; the Labs compare event types, regions, and days
without such a ratio.

## Summary

- Apache Doris is an open-source database for real-time analytics and search:
  it makes fresh data queryable quickly and answers analytical queries with low
  latency, using MPP execution, columnar storage, and vectorized processing.
- OLTP and OLAP are workload patterns. A small transaction on one business
  entity is OLTP; a scan and aggregation over many rows is OLAP, whichever
  product runs it and however many rows it returns.
- Doris suits fresh, interactive analysis: real-time dashboards,
  customer-facing analytics, observability, lakehouse analytics, and
  CDC-driven reporting. It does not replace the transactional database, raw
  object storage, or the visualization layer.
- The FE accepts and analyzes SQL, creates and optimizes the distributed query
  plan, and assigns its plan fragments; the BE nodes execute those fragments
  and, in the integrated architecture, store the table data.
- In the integrated storage and compute architecture, BEs store the data
  locally and storage and compute grow together; in the decoupled
  architecture, the data lives in shared storage and compute groups scale
  independently.
- Lab 1 connected to the FE over the MySQL protocol, read Parquet files in S3
  with the S3 TVF, loaded 10,158,080 events into an internal table, and checked
  them with a count, a time range, and an aggregation.

## Quiz 1: Introduction to Apache Doris

Open [Quiz 1: Introduction to Apache Doris](quiz01_doris_fundamentals.ipynb).
It has six single-choice questions and needs no running environment.

Next module: [Module 2: Deep Dive into Apache Doris Architecture](../module02-architecture/course.md).

## References

- [Apache Doris source repository and project overview](https://github.com/apache/doris)
- [What is Apache Doris?](https://doris.apache.org/docs/4.x/getting-started/what-is-apache-doris/)
- [System Architecture](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)
- [Customer-Facing Analytics](https://doris.apache.org/use-cases/customer-facing-analytics/)
- [Observability with Doris](https://doris.apache.org/docs/4.x/observability/overview/)
- [Load Overview](https://doris.apache.org/docs/4.x/data-operate/import/load-manual/)
- [S3 table-valued function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/s3/)
- [All-In-One image](https://doris.apache.org/community/developer-guide/all-in-one-image/)
