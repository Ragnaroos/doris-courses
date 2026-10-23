# Data Warehousing with Apache Doris

Build an order warehouse on Apache Doris that the business can trust. You load
orders and their history in batches, keep only the inputs that pass their
checks, follow every change of an order, model the orders as facts and
dimensions, turn them into metrics with written contracts, and publish those
metrics to dashboards and models. Then you run the warehouse: access through
roles, a data lifecycle with a tested way back, and separate resources for each
workload. Every Lab runs on your own computer, against a Doris sandbox that the
course starts for you, and checks its results against numbers that you can
verify.

## Who this course is for

- Data engineers and analytics engineers who build, or are about to build, a
  data warehouse on Doris.
- You should be able to write SQL with `SELECT`, `WHERE`, `GROUP BY`, and
  `JOIN`; read a short Python function, including `try` / `finally`, and change
  a value in a dictionary or a function call; recognize the parts of an HTTP
  request, its method, URL, headers, and status code, because Lab 5 sends one;
  and run basic Docker commands such as `docker ps` and `docker logs`.
- No previous experience with Doris is needed. Module 1 starts the sandbox and
  walks you through your first table.

## What you will learn

- How Doris plans, stores, and loads data: the FE and the BE, tablets and
  rowsets, the three key models, partitions and buckets, lake tables through a
  Catalog, and batch loads that you can retry without loading anything twice.
- How to keep data right as it arrives: stage the raw input, route rejections
  with their reasons, keep the current state and the history of each order with
  business versions, and replay a batch after a failure.
- How to model and measure: facts and dimensions with declared grains, joins
  that neither lose nor double an order, metrics with written contracts, and
  materialized views and service tables that you reconcile with the detail.
- How to publish to consumers: semantic views for dashboards and models, and
  the line between what Doris guarantees and what a BI or AI tool must check.
- How to operate the warehouse: grants through roles and the evidence that
  proves them, partitions that follow a retention rule with a tested way back,
  and Workload Groups and query limits that keep one workload from slowing
  another.

## Course outline

Each module has a lesson (`course.md`), a Lab notebook, and a quiz notebook.
Read the lesson, run the Lab, then take the quiz; the quizzes need no database.
Run the Labs in module order: later Labs read the tables that earlier ones
leave.

| Level | Module | What you will do | Time |
| --- | --- | --- | --- |
| 1 | [Module 1: Meet Doris and Analyze Your First Orders](level1/module01-introduction/course.md) | Start Doris, load ten orders, and count and total them by day | 55 min |
| 1 | [Module 2: Doris Storage Architecture and Write Mechanisms](level1/module02-architecture/course.md) | Follow a query from the FE to the BE, and read the versions and rowsets that two ways of writing leave | 55 min |
| 1 | [Module 3: Doris Table Models, Partitioning, and Bucketing](level1/module03-table-design/course.md) | Compare the three key models on the same rows, and read in plans how partitions and buckets narrow a scan | 60 min |
| 1 | [Module 4: Querying External Data and Joining Lake Tables](level1/module04-external-access/course.md) | Query an Iceberg table and its files in a local lake, join it with a Doris table, and load it | 65 min |
| 1 | [Module 5: Batch and Continuous Data Ingestion](level1/module05-ingestion/course.md) | Load files with Stream Load, check each response, retry safely, and load the WWI history | 90 min |
| 1 | [Module 6: Data Quality and Schema Validation](level1/module06-data-quality/course.md) | Stage thirteen new orders, route the three bad ones with their reasons, and break the checks on purpose | 70 min |
| 1 | [Module 7: Data Updates, Deletion, and Event Replay](level1/module07-state-changes/course.md) | Keep each order's current state and history while its events arrive twice and out of order, and replay after an interruption | 90 min |
| 2 | [Module 8: Views and Materialized Views](level2/module08-views-materialized-views/course.md) | Publish one definition of daily orders as a view, store its result in materialized views, and read in `EXPLAIN` which queries use them | 117 min |
| 2 | [Module 9: Warehouse Modeling and Joins](level2/module09-modeling-and-joins/course.md) | Join an order fact with a customer dimension without losing or doubling an order, and run an ODS → DWD → DWS → ADS chain | 112 min |
| 2 | [Module 10: Metric Processing and Delivery](level2/module10-metric-processing/course.md) | Write metric contracts, reconcile a service table with the detail, and measure paid GMV | 146 min |
| 2 | [Module 11: Interfaces and Boundaries for BI and AI Consumers](level2/module11-bi-and-ai/course.md) | Publish a semantic view and its features, and check them before anyone reads them | 120 min |
| 3 | [Module 12: Publishing, Permissions, and Audit](level3/module12-publishing-permissions-audit/course.md) | Grant a view to a role, test it as an ordinary user, audit who read what, and release a table with a rollback | 123 min |
| 3 | [Module 13: Storage and Lifecycle Management](level3/module13-storage-lifecycle/course.md) | Clear and drop monthly partitions, and bring one back from the recycle bin | 108 min |
| 3 | [Module 14: Resource Isolation and Query Protection](level3/module14-resource-isolation/course.md) | Give dashboards and ad hoc queries their own Workload Groups, route accounts to them, and reject excessive scans | 100 min |

The times include the lesson, the Lab, and the quiz, but not the first
downloads: Level 1 takes about 8 hours, Level 2 about 8, and Level 3 about 5.5.
You have completed a Level when you have run its Labs, with their practices,
and taken its quizzes.

### Optional parts

Nothing in the main path depends on these:

| Optional part | What it adds | Needs |
| --- | --- | --- |
| [Reading: Continuous Ingestion](level1/module05-ingestion/optional05_continuous_ingestion.md), with its own quiz | Kafka and Routine Load, Flink CDC, Streaming Jobs and CDC_STREAM, and continuous file loads | Module 5 |
| [Further reading: WWI invoices and account receipts](level1/module05-ingestion/optional05_invoice_and_receipts.md) | The three kinds of amounts in the WWI history | Lab 5 |
| [Lab 5A: Kafka → Routine Load → Doris](level1/module05-ingestion/optional05_kafka_routine_load.ipynb) | A Routine Load job that consumes a real Kafka topic | Docker with 8 GiB of memory and 4 CPUs; 30 min |
| [Lab 5B: MySQL → Flink CDC → Doris](level1/module05-ingestion/optional05_flink_mysql_cdc.ipynb) | A Flink CDC job from MySQL, stopped with a savepoint and restored | Docker with 10 GiB of memory and 4 CPUs; 40 min |
| [Module 2–3 Extension Lab: Batches, Partitions, and Profile](level1/extensions/extension23_physical_design.ipynb) | Modules 2 and 3 again, on 100,000 rows | Labs 2 and 3; 25–35 min |
| [Module 4–5 Extension Lab: Direct File Queries, Batch Loading, and Group Commit Acknowledgments](level1/extensions/extension45_files_and_group_commit.ipynb) | Broker Load, default and generated columns, and the three Group Commit modes | Labs 4 and 5, and PyArrow (see [Get started](#get-started)); 30–45 min |
| [Module 6–7 Extension Lab: Schema Changes, Load-Based Deletion, and Conflict Detection](level1/extensions/extension67_schema_and_delete.ipynb) | Schema changes, a load's delete mark, and conflicting events | Labs 6 and 7; 25–35 min |
| Lab 11, sections 5 and 6 | A three-chart Superset dashboard on the payment contract of Lab 10 | About 2 GiB more Docker memory, and internet access for the first build; 15 min |
| Lab 13, sections 6 to 8 | A backup to an object store, and a restore into another database | 512 MiB more Docker memory; 15 min |

Run the extensions after the main Labs that they name, one at a time; each one
rebuilds only its own `ext_*` tables. Labs 11 and 13 run their optional
sections only when you switch them on in the Lab. Labs 5A and 5B recreate the
Doris container with a 6 GiB memory limit, which leaves its BE 2.4 GiB: before
you go back to the main Labs, run Lab 1's **Start and Connect**, which recreates
the container without the limit and keeps its data.

### Lab dependencies

All Labs use one database in the sandbox, `dw_course_l1_demo` unless you set
`DW_DATABASE`, and each Lab rebuilds only its own tables. A Lab that reads
another Lab's tables checks them first; when one is missing, it stops before it
changes anything and names the Lab to run.

| Lab | Needs | Leaves for later Labs |
| --- | --- | --- |
| 1 | Docker | The running sandbox and the database |
| 2, 3 | The sandbox | Nothing |
| 4 | The sandbox; it starts the lake environment | Nothing; the Module 4–5 extension uses the same lake |
| 5 | The sandbox | The ten `wwi_*` history tables |
| 6 | `wwi_customers` from Lab 5, which it loads from the bundled package when it is missing | `orders_clean` and `customers` |
| 7 | `orders_clean` and `customers` from Lab 6; `wwi_products` from Lab 5, loaded when it is missing | `orders_current`, `order_events`, and the payments, refunds, and shipments |
| 8 | `orders_current` and `order_events` from Lab 7 | Nothing |
| 9 | `customers` from Lab 6; `orders_current` and `order_events` from Lab 7 | `orders_fact_l2`, `customers_dim_l2`, and the warehouse case's tables |
| 10 | `orders_fact_l2` and the case's `dwd_*` tables from Lab 9 | `daily_order_metrics_l2` and the case's payment metrics |
| 11 | `daily_order_metrics_l2` from Lab 10 | `bi_order_metrics_l2` |
| 12 | `orders_fact_l2` from Lab 9 and `bi_order_metrics_l2` from Lab 11 | Nothing |
| 13, 14 | The sandbox | Nothing |

If Lab 4's lake cannot start, for example because its images cannot be
downloaded, continue with Labs 5 to 7 and return to Lab 4 later.

Level 1's tables are named for what they hold: `sample` is a small sample,
`raw` keeps the input as it arrived, and `current` is the current state. The
tables of Level 2 end in `_l2`, those of Level 3 in `_l3`, and those of the
extensions start with `ext_`.

## Environment

- **Supported platforms.** macOS on Apple Silicon, where every Lab was run end
  to end. Linux on x86-64 uses the same images but was not run end to end. On
  Windows, use WSL 2. Docker and Jupyter must run on the same computer: the
  notebooks start the containers and connect to Doris on `127.0.0.1`. Your
  browser can be on another computer.
- **Resources.** Docker with 4 CPUs and 8 GB of memory, and about 20 GB of free
  disk. The optional parts need more: Lab 5A 8 GiB and Lab 5B 10 GiB of Docker
  memory, with 4 CPUs, because both run Doris with a 6 GiB memory limit next to
  their services; the dashboard of Lab 11 about 2 GiB more; the backup of
  Lab 13 512 MiB more.
- **Doris version.** Apache Doris 4.1.3, from the image
  `apache/doris:all-in-one-4.1.3` with the digest
  `sha256:82a5cabc7900ebcd3d080412d636c0cebd6602799fffe2605c652b2ea7d42609`.
  `SHOW FRONTENDS` and `SHOW BACKENDS` report the version as
  `doris-4.1.3-rc02-7126cf65d96`: the 4.1.3 release is that build.
- **Downloads.** The images below, the first time that a Lab needs them. Silo
  is an open-source (AGPLv3) fork of the MinIO server, maintained by the Pigsty
  project, with MinIO's S3 API; the course uses it because MinIO no longer
  publishes community container images.

  | Image | Used by | Download | On disk |
  | --- | --- | --- | --- |
  | `apache/doris:all-in-one-4.1.3` | Every Lab: one FE and one BE in one container | 1.9 GB | 4.5 GB |
  | `pgsty/silo:RELEASE.2026-10-18T00-00-00Z` | Lab 4's lake, the Module 4–5 extension, and Lab 13's backup | 60 MB | 210 MB |
  | `apache/iceberg-rest-fixture:1.10.0` | Lab 4's lake | 300 MB | 820 MB |
  | `apache/kafka:3.9.0` | Lab 5A | 220 MB | 630 MB |
  | `mysql:8.0.33` | Lab 5B | 170 MB | 800 MB |
  | `flink:1.20.1-scala_2.12-java11` and three connector JARs from Maven Central, built into `doris-course-flink` | Lab 5B | 650 MB | 1.5 GB |
  | `apache/superset:4.1.2` and its Doris driver from PyPI, built into `doris-course-superset` | Lab 11's dashboard | 310 MB and the packages | 1.7 GB |

  The Python packages, including JupyterLab, take about 470 MB. The WWI data is
  in the repository, about 10 MiB, and Lab 5 unpacks it to `.runtime/wwi/`.
- **Accounts and keys.** None: no cloud account and no paid data service. The
  sandbox's `root` user has no password, and the lake, the backup store, and the
  dashboard use fixed credentials written in their files under `environments/`.
  They are for this local sandbox only, which listens on `127.0.0.1`: do not
  reuse them anywhere else, and do not write passwords into notebooks. The
  Doris accounts that Labs 11, 12, and 14 create get generated passwords, which
  the Labs do not show.
- **Ports.** All of them on `127.0.0.1`. To use other ports, set the variables
  before you start Jupyter, and start it with the same values every time: each
  Lab reads them, and so does Docker Compose.

  | Port | Purpose | Variable |
  | --- | --- | --- |
  | 52030 | FE MySQL protocol | `DW_FE_QUERY_PORT` |
  | 51030 | FE HTTP | `DW_FE_HTTP_PORT` |
  | 51040 | BE HTTP, for Stream Load | `DW_BE_HTTP_PORT` |
  | 51900 | Lab 4's object store | `DW_LAKE_S3_PORT` |
  | 51818 | Lab 4's Iceberg REST Catalog | `DW_LAKE_REST_PORT` |
  | 51888 | Lab 11's optional Superset | `DW_BI_PORT` |
  | 51910 | Lab 13's optional backup store | `DW_BACKUP_S3_PORT` |

  For example:
  `DW_FE_QUERY_PORT=62030 DW_FE_HTTP_PORT=61030 DW_BE_HTTP_PORT=61040 .venv/bin/jupyter lab`.
  Lab 5B's Flink web UI gets a free port that Docker chooses; the Lab prints it.
- **Docker objects.** Each part of the environment is its own Compose project,
  so the course runs next to your other containers and touches none of them.
  Each project also has a network, `<project>_default`; the Labs attach the
  Doris container to the networks of the lake, the dashboard, and the backup
  store.

  | Compose project | Started by | Services | Volumes |
  | --- | --- | --- | --- |
  | `doris-warehousing-course` | Lab 1 | `doris` | `fe-meta`, `be-storage` |
  | `doris-warehousing-lake` | Lab 4 | `silo`, `rest` | `lake-data`, `lake-catalog` |
  | `doris-warehousing-streaming` | Labs 5A and 5B | `kafka`; `mysql`, `jobmanager`, `taskmanager` | `kafka-data`, `mysql-data`, `flink-state` |
  | `doris-warehousing-bi` | Lab 11, section 5 | `superset` | `bi-metadata` |
  | `doris-warehousing-backup` | Lab 13, section 6 | `silo` | `backup-objects` |

  Docker names the containers and volumes after the project, such as the
  container `doris-warehousing-course-doris-1` and the volume
  `doris-warehousing-course_fe-meta`.
- **Databases and cluster objects.** To give several people one sandbox, set a
  different `DW_DATABASE` for each before they start Jupyter; the name must
  start with `dw_course_l1_`. Labs 5A and 5B use `dw_course_l1_streaming`, and
  Lab 13's optional restore creates `<your database>_restore_l3`. Roles, users,
  Row Policies, Workload Groups, and SQL Block Rules belong to the whole
  sandbox. Labs 12 and 14 remove theirs again. Only the optional dashboard of
  Lab 11 keeps two: its account, `course_bi_<suffix>`, and the role
  `course_bi_dashboard_l3`, to which Lab 12 moves the account's grant.

## Get started

1. Create the course's virtual environment with Python 3.10 to 3.13, and
   install the requirements. Run the commands in the course directory of a
   complete copy of the repository: the requirements install the notebook
   runtime that the courses share from `../common`. If `python3 --version`
   shows 3.14, which the course does not support yet, use `python3.12` or
   `python3.13`:

   ```bash
   cd doris-course/02-data-warehousing
   python3.12 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

   For the Module 4–5 extension, also install PyArrow:
   `.venv/bin/python -m pip install -e '.[extensions]'`.

2. Start Docker, wait until `docker info` succeeds, then start Jupyter from the
   same environment. If Jupyter offers several kernels, choose the one of this
   `.venv`.

   ```bash
   .venv/bin/jupyter lab
   ```

3. Open the lesson
   [Module 1: Meet Doris and Analyze Your First Orders](level1/module01-introduction/course.md)
   and its Lab, `level1/module01-introduction/lab01_connect_and_query.ipynb`.
   Run **Initialize the Lab Tools**, read the reset notice, then run **Start
   and Connect**. The first start downloads the Doris image and takes several
   minutes; continue when it shows `connection_ok` 1. The later Labs connect to
   the same sandbox.

### Working through a Lab

- Run the cells in order. The **Expected result** after a step says what you
  should see, then how to read it. A green card is a check that passed; a red
  one stops the Lab and says what differed. If your result differs, look at
  the details and the order in which you ran the cells before you change
  anything.
- Each Lab ends with a practice: write your code in the blank cell, then expand
  the collapsed reference solution after it to compare. **Run All** runs the
  reference solutions too, so run the cells one at a time when you want to try
  first.
- Each Lab says at its start which tables it rebuilds. After a kernel restart,
  rerun the Lab's first cells, which connect again; they do not start Docker,
  which Lab 1 does. When you finish a Lab, shut down its kernel to release its
  connections; the tables stay in the sandbox.

## Dataset

The course keeps two kinds of data apart by their source:

- **WWI history.** Microsoft's
  [Wide World Importers sample database v1.0](https://github.com/microsoft/sql-server-samples/releases/tag/wide-world-importers-v1.0),
  a simulated wholesale business, under the MIT license
  (`datasets/wwi/LICENSE.txt`). Module 1 starts with ten of its orders, worth
  12220.60 before tax; Lab 5 loads ten of its tables, 701,846 rows from 2013 to
  2016 with only the columns that the course uses. The dates are not shifted to
  today. WWI's customer receipts belong to accounts, not to orders, so the
  course does not count them as order payments.
- **Simulated new orders.** Orders 900001 to 900011 from 2026, written for the
  course and labeled `COURSE_SIMULATION`. They reference WWI customers and
  products 1 to 11; their prices, their EAST and WEST regions, and their events
  in Asia/Shanghai time are teaching assumptions. After Lab 7, the 11 orders
  are worth 1510.00, and 1310.00 without the cancelled one; Level 2 starts from
  them. Lab 9 adds a small case of its own, with 8 orders of 5 customers, their
  deliveries, payments, and a partial refund.

| File in `datasets/` | What it holds | Used by |
| --- | --- | --- |
| `wwi/sample.json` | Ten WWI orders and the customers and products that they reference | Labs 1 to 4 |
| `wwi/wwi-core.tar.gz`, `wwi/manifest.json` | Ten WWI tables as Parquet files, and their hashes and row counts | Lab 5; Labs 6 and 7 read its customers and products |
| `orders.csv`, `orders.json` | Ten simulated new orders, 900001 to 900010, worth 1400.00 | Labs 5 to 7, the Module 4–5 extension |
| `malformed_orders.csv`, `orders_reordered.csv` | A batch with one bad row, and two orders whose columns come in another order | Lab 5 |
| `raw_orders.json` | The ten orders and three bad ones: an amount that is not a number, an empty order ID, and an unknown customer | Lab 6 |
| `deliveries.json`, `business_events.json`, `expected_current.json` | Order events delivered twice and out of order; an independent ledger of items, payments, refunds, and shipments; the expected current state | Lab 7 |
| `warehouse_case.json` | The case of Labs 9 to 11, with its expected results | Labs 9 to 11 |

Lab 5 unpacks the WWI tables to `.runtime/wwi/` and checks every file against
the manifest. To use files that you unpacked before, set `DW_WWI_DATA_DIR` to
their directory before you start Jupyter. Lab 10 and the Module 2–3 extension
generate their 100,000 rows from fixed rules.

## Clean up

To pause, stop the sandbox and keep its data, then start it again later:

```bash
docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml stop
docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml start --wait
```

The lake, the streaming services, the dashboard, and the backup store stop the
same way: use the project and file of their commands below, with `stop`
instead of `down --volumes`. Lab 4 starts its lake again when you run it.

To remove everything that the course created, run these commands in the course
directory, in this order:

1. Remove the streaming services of Labs 5A and 5B. They come first, because
   they are attached to the sandbox's network; their jobs end with them:

   ```bash
   docker compose --project-name doris-warehousing-streaming --file environments/streaming/compose.yml --profile kafka --profile cdc down --volumes
   ```

2. Remove the sandbox, with its databases, users, roles, and groups:

   ```bash
   docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml down --volumes
   ```

3. Remove the lake, the dashboard, and the backup store. They come after the
   sandbox, because the Doris container is attached to their networks until it
   is removed:

   ```bash
   docker compose --project-name doris-warehousing-lake --file environments/lakehouse/compose.yml down --volumes
   docker compose --project-name doris-warehousing-bi --file environments/bi/compose.yml down --volumes
   docker compose --project-name doris-warehousing-backup --file environments/backup/compose.yml down --volumes
   ```

4. Optionally, remove the images that the course built,
   `doris-course-superset:4.1.2-pydoris1.1.0` and
   `doris-course-flink:1.20.1-cdc3.4.0-doris25.0.0`, and the ones that it
   downloaded, with `docker image rm`; then delete `.runtime/` and `.venv/` in
   the course directory.

Afterward, `docker ps -a --filter name=doris-warehousing` and
`docker volume ls --filter name=doris-warehousing` show nothing.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| A cell says that a port is in use | It names the port and its variable, such as `52030 (DW_FE_QUERY_PORT)`, and has started nothing. Find the program with `lsof -nP -iTCP:52030 -sTCP:LISTEN`; stop it if it is yours, or restart Jupyter with the variable set to a free port. |
| A Lab says that another Lab must run first | Run the Lab that it names, in the same database, then rerun the cell. [Lab dependencies](#lab-dependencies) lists what each Lab needs. |
| `pip install` fails, or a notebook cannot import `doris_labkit` or `dw_course` | Use Python 3.10 to 3.13, install in `doris-course/02-data-warehousing` of a complete repository, and choose the kernel of its `.venv`. |
| The connection is refused, or Doris stops or restarts | Check `docker info`, then `docker compose --project-name doris-warehousing-course --file environments/single-node/compose.yml ps` and the same command with `logs --tail 100 doris`. Give Docker at least 8 GB of memory, and run Lab 1's **Start and Connect** again: it starts or reuses the sandbox. Do not remove the volumes to retry: they hold the tables of every Lab. |
| A main Lab fails with `MEM_ALLOC_FAILED` | After Lab 5A or 5B, Doris still has their 6 GiB memory limit. Run Lab 1's **Start and Connect**, which recreates the container without it and keeps the data, then rerun the cell. |
| The lake, the dashboard, or the backup store does not start | The message says whether an image could not be downloaded, which needs internet access, Docker ran out of memory, or the service did not become healthy. Read its log with `docker compose --project-name <project> --file environments/<directory>/compose.yml logs --tail 80`. |
| Every scan of more than two partitions fails with `sql hits sql block rule: course_scan_guard_l3` | Lab 14 was interrupted and left its rule behind. Rerun Lab 14 from its first cell through step 2, which removes it. |
