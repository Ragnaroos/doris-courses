# Real-time Analytics with Apache Doris

Build and run a real-time analytics system on Apache Doris with one dataset of
ten million ecommerce events. You start a Doris sandbox and load the events,
see how Doris plans, stores, and scans them, and load data the ways that
production systems do: from a file, from S3, and from Kafka. Then you model
the events into detail and summary tables, analyze them with functions,
windows, and Joins, and keep the current state of orders correct through
updates and deletes. Finally, you accelerate queries without changing their
answers, run a cluster of three FEs and three BEs through failures, and give
the data a lifecycle with a tested way back. Every Lab runs on your own
computer, against a Doris sandbox that the course starts for you, and checks
its results against numbers that you can verify.

## Who this course is for

- Data engineers, analytics engineers, and backend developers who build, or
  are about to build, real-time dashboards or analytical services on Doris.
- You should be able to write SQL with `SELECT`, `WHERE`, `GROUP BY`, and
  `JOIN`; read a short Python cell and change a value in it; and run basic
  Docker commands such as `docker ps` and `docker logs`. Module 3 sends HTTP
  requests with `curl`, and Module 9 stops and starts containers; each Lab
  shows the commands.
- No previous experience with Doris is needed. Module 1 starts the sandbox and
  walks you through your first table.

## What you will learn

- How Doris works: the FE plans a query and the BEs execute it, columnar
  storage and vectorized execution, and the Partitions, Tablets, Rowsets, and
  Segments that decide how much data a query reads.
- How to load data and trust it: Stream Load, the S3 table-valued function with
  `INSERT INTO SELECT`, Routine Load from Kafka, and Group Commit, each with its
  completion evidence and a safe retry.
- How to model and analyze: grain, table models, types, and layout; functions,
  CTEs, and window functions; Joins whose results neither lose nor multiply
  rows; and updates, partial updates, `MERGE INTO`, and deletes for current
  state.
- How to make queries fast and keep them right: views, materialized views,
  indexes, and statistics, checked with `EXPLAIN` and the Query Profile.
- How to run Doris: replicas, FE failover, majority writes, and Join data
  movement across BEs; compression, rolling time windows, and recovery after a
  mistaken drop.

## Course outline

Each module has a lesson (`course.md`), a Lab notebook, and a quiz notebook.
Read the lesson, run the Lab, then take the quiz; the quizzes need no database.
Run the Labs in module order: later Labs read the tables that earlier ones
leave.

| Level | Module | What you will do | Time |
| --- | --- | --- | --- |
| 1 | [Module 1: Introduction to Apache Doris](level1/module01-introduction/course.md) | Start Doris, load 10,158,080 events from S3, and run a first aggregation | 70 min |
| 1 | [Module 2: Deep Dive into Apache Doris Architecture](level1/module02-architecture/course.md) | Change the physical design of the same rows and compare plans and scans | 75 min |
| 1 | [Module 3: Loading Data into Apache Doris](level1/module03-loading-data/course.md) | Load a CSV file, Parquet objects, and Kafka JSON, and retry a batch safely | 85 min |
| 2 | [Module 4: Modeling Data in Apache Doris](level2/module04-modeling/course.md) | Build an event-detail table and a daily summary, and reconcile them | 90 min |
| 2 | [Module 5: Analyzing Data in Apache Doris](level2/module05-analyzing/course.md) | Build a daily-region report in stages with functions, CTEs, and windows | 90 min |
| 2 | [Module 6: Joining Data in Apache Doris](level2/module06-joining/course.md) | Join events with a product dimension, and read Join plans and a Profile | 95 min |
| 2 | [Module 7: Updating and Deleting Data in Apache Doris](level2/module07-updating-deleting/course.md) | Upsert, patch, merge, delete, and replace orders on small tables | 65 min |
| 3 | [Module 8: Accelerating Queries in Apache Doris](level3/module08-query-acceleration/course.md) | Build a view, materialized views, and an index, and read statistics and plans | 120 min |
| 3 | [Module 9: Sharding, Replication, and Distributed Execution in Apache Doris](level3/module09-sharding-replication/course.md) | Expand a cluster, fail an FE, stop a BE during a write, and compare two Joins | 145 min |
| 3 | [Module 10: Controlling Storage Cost and Data Lifecycle in Apache Doris](level3/module10-managing-data/course.md) | Compare compression, expire an hourly Partition, and recover a dropped one | 115 min |

The times include the lesson, the Lab, and the quiz, but not the first
downloads: Level 1 takes about 4 hours, Level 2 about 6, and Level 3 about
6.5. You have completed a Level when you have run its Labs, with their
practices, and taken its quizzes.

### Optional parts

| Optional part | What it adds | Needs |
| --- | --- | --- |
| [Lab 1 Optional: Connect Metabase and Build a Dashboard](level1/module01-introduction/optional01_metabase_dashboard.ipynb) | A Metabase dashboard on the `events` table of Lab 1 | Lab 1, about 0.7 GB of downloads, and a browser; 20–30 min |
| Lab 10, the end of Section 3 | The same Partition expiry on the real clock instead of the shortcut | Waiting until the next whole hour, up to about an hour |

### Lab dependencies

The single-node sandbox holds one database, `doris_course`, for every Lab
except Lab 9. Each Lab rebuilds only its own tables and checks the tables that
it reads from earlier Labs first; when one is missing, it stops before it
changes anything and names the Lab to run.

| Lab | Needs | Leaves for later Labs |
| --- | --- | --- |
| 1 | Docker | The running sandbox and `events`, 10,158,080 rows |
| 2 | `events` from Lab 1 | Nothing; it builds `events_v2`, `events_v3`, and three small table-model tables |
| 3 | The sandbox; it starts a Kafka broker | Nothing; it builds `events_stream`, `events_s3`, and `events_routine` |
| 4 | `events` from Lab 1 | `events_modelled`, the event table of Modules 5, 6, 8, and 10; it also builds `modeling_raw_events`, `modeling_typed_events`, and `daily_event_metrics` |
| 5 | `events_modelled` from Lab 4 | Nothing |
| 6 | `events_modelled` from Lab 4 | `dim_products`, 204,231 rows, for Module 8; it also builds `join_event_cases` and `join_product_cases` |
| 7 | The sandbox | Nothing; it builds small `order_*` tables |
| 8 | `events_modelled` from Lab 4 and `dim_products` from Lab 6 | Nothing; its objects start with `m08_` |
| 9 | Docker, with the sandbox stopped; it starts its own cluster | Nothing for later Labs; its objects start with `m09_` |
| 10 | `events_modelled` from Lab 4, with the Module 9 cluster stopped | Nothing; its objects start with `m10_` |

## Environment

| | |
| --- | --- |
| Platforms | **macOS on Apple silicon** with Docker Desktop: the platform on which every lab of this release was run from start to finish. **Linux on x86_64** with Docker Engine: the labs accept it and use the same images, but this release has not been run on it. **Windows**: run the course inside a WSL 2 Linux distribution on x86_64 with Docker Desktop's WSL 2 integration, and start Jupyter there; inside WSL the labs see Linux on x86_64. This release has not been run on it either. |
| Other platforms | Lab 1 stops at its first step on other combinations, such as an Intel Mac or Linux on arm64. The Doris, Kafka, and HAProxy images exist for both amd64 and arm64, but the course has not been run on those combinations, so Lab 1 does not continue there. |
| Resources | Docker needs at least 4 CPUs, 8 GB of memory, and 20 GiB of free disk. With 4 CPUs and 8 GB, the Doris container peaks at about 3.1 GiB during Lab 1's load. Module 9 runs three FEs, three BEs, and HAProxy within the same minimum (about 6.4 GiB in all at its peak in the tested run); stop the single-node sandbox first and, with only 8 GB for Docker, the Kafka broker and Metabase too (see [Clean up](#clean-up)). |
| Downloads | Docker images: `apache/doris:all-in-one-4.1.3` (about 1.9 GB to download, 4.5 GB on disk), `apache/kafka:3.9.1` for Module 3 (0.2 GB), `haproxy:3.0.30-alpine3.24` for Module 9 (20 MB), and `metabase/metabase:v0.59.6.3` for the optional Metabase lab (0.7 GB); a lab reuses an image that Docker already has. The optional Metabase lab also downloads the Doris driver for Metabase (19 KB) from GitHub. Data: 72 MiB of Parquet files from AWS S3 in Lab 1 and again in Lab 3; on its first run, Lab 9 reads a seven-hour slice of the same files, and because those rows are spread over all 40 files, Doris reads about 59 MB to find them; three small files in Lab 3. Python packages from PyPI. |
| Doris version | Apache Doris 4.1.3, from the image `apache/doris:all-in-one-4.1.3` with the digest `sha256:82a5cabc7900ebcd3d080412d636c0cebd6602799fffe2605c652b2ea7d42609`. `SHOW FRONTENDS` and `SHOW BACKENDS` report the version as `doris-4.1.3-rc02-7126cf65d96`: the 4.1.3 release is that build. |
| Network | Docker Hub for the images; `s3.us-east-1.amazonaws.com` and `doris-courses-public-dataset.s3.us-east-1.amazonaws.com` over HTTPS for the data; PyPI for the packages; GitHub for the optional Metabase lab's driver. From some networks, including mainland China, Docker Hub and AWS `us-east-1` can be slow or unreachable: use the registry mirror or proxy that your network provides. The labs give Doris longer S3 timeouts than its defaults (Module 3 explains them), so a slow connection makes a load slower instead of failing it: the 72 MiB load of Labs 1 and 3 took 11 seconds to 2 minutes over direct connections in the tested runs, and 22 minutes through a proxy that delivered about 60 KB/s; through the same proxy, Lab 9's first load took 13 minutes. |
| Accounts and keys | None. The dataset bucket is public and is read anonymously. |
| Python | 3.9 to 3.13. If `python3 --version` reports 3.14 or later, create the virtual environment with a supported version, for example `python3.12 -m venv .venv`. |

### Ports and Docker objects

Every Docker resource of the course starts with `doris-rta`, and every host
port is bound to `127.0.0.1`, so the course can run next to the other courses
of this repository. To use another host port, set its variable before you
start Jupyter, and start Jupyter with the same values every time: the
notebooks, their shell cells, and the Compose files read the same variables.

| What | Docker objects | Host ports (variables) |
| --- | --- | --- |
| Single-node sandbox, Modules 1–8 and 10 | Container `doris-rta`, network `doris-rta`, volumes `doris-rta-fe-meta` and `doris-rta-be-storage` | FE query 19030 (`DORIS_RTA_QUERY_PORT`), FE HTTP 18030 (`DORIS_RTA_HTTP_PORT`), BE HTTP 18040 (`DORIS_RTA_BE_HTTP_PORT`) |
| Kafka broker, Module 3 | Compose project `doris-rta-kafka`, container `doris-rta-kafka` | 19092 (`DORIS_RTA_KAFKA_PORT`) |
| Optional Metabase, Module 1 | Container `doris-rta-metabase`, volume `doris-rta-metabase-data` | 13000 (`DORIS_RTA_METABASE_PORT`) |
| Cluster of Module 9 | Compose project `doris-rta-m09`: three FEs, three BEs, and HAProxy | FE query 19130, 19131, 19132 (`DORIS_RTA_M09_FE1_QUERY_PORT`, `DORIS_RTA_M09_FE2_QUERY_PORT`, `DORIS_RTA_M09_FE3_QUERY_PORT`), FE HTTP 18130, 18131, 18132 (`DORIS_RTA_M09_FE1_HTTP_PORT`, `DORIS_RTA_M09_FE2_HTTP_PORT`, `DORIS_RTA_M09_FE3_HTTP_PORT`), BE HTTP 18140 (`DORIS_RTA_M09_BE_HTTP_PORT`), HAProxy 19230 (`DORIS_RTA_M09_PROXY_PORT`) and its statistics page 18230 (`DORIS_RTA_M09_PROXY_STATS_PORT`) |

For example: `DORIS_RTA_QUERY_PORT=29030 DORIS_RTA_HTTP_PORT=28030 DORIS_RTA_BE_HTTP_PORT=28040 .venv/bin/jupyter lab`.
Inside the sandbox, the FE still listens on its default ports 9030 and 8030,
and the host ports forward to them. The BE's web server listens on its host
port inside the container too, because the FE redirects Stream Load requests
to the address that the BE registers, and that address must also work from
your computer.

The sandbox is a single-node integrated Doris environment for learning, with
one FE, one BE, and one replica; it is not a production cluster. Its named
volumes keep the FE metadata and the BE data when the container stops. Lab 9
starts the separate Module 9 cluster, which needs the sandbox stopped first
(`docker stop doris-rta`); Lab 10 needs the Module 9 cluster stopped again.

## Get started

1. Create the course's virtual environment and install the requirements. Run
   the commands in the course directory of a complete copy of the repository:
   the requirements also install `doris_labkit`, the notebook runtime that the
   courses share, from `../common`. If `python3 --version` shows 3.14, which
   the course does not support yet, use `python3.12` or `python3.13`:

   ```bash
   cd doris-course/01-real-time-analytics
   python3.12 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

2. Start Docker, wait until `docker info` succeeds, then start Jupyter from the
   same environment and the same directory. If Jupyter offers several
   kernels, choose the one of this `.venv`.

   ```bash
   .venv/bin/jupyter lab
   ```

3. Open the lesson
   [Module 1: Introduction to Apache Doris](level1/module01-introduction/course.md)
   and its Lab, `level1/module01-introduction/lab01_start_doris_and_build_baseline.ipynb`.
   Run **Initialize the Lab**, then the cells in order. Section 2 starts the
   sandbox; the first start downloads the Doris image and takes several
   minutes. The later Labs reuse the same sandbox and start it when it is
   stopped.

### Working through a Lab

- Run the cells in order. The **Expected result** after a step says what you
  should see, then how to read it. A green card is a check that passed; a red
  one stops the Lab and says what differed. If your result differs, look at the
  details and the order in which you ran the cells before you change anything.
- Each Lab ends with a practice: predict the result, write your code in the
  empty cell, then expand the collapsed reference solution after it to compare.
  **Run All** runs the reference solutions too, so run the cells one at a time
  when you want to try first.
- After a kernel restart, run **Initialize the Lab** again; Labs 2 to 8 and 10
  then start or reconnect to the sandbox in their first steps. When you finish
  a Lab, shut down its kernel to release its connections; the tables stay in
  the sandbox.

## Dataset

The labs use a transformed copy of
[eCommerce behavior data from multi category store](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store/data),
published by Michael Kechinov and provided by the
[REES46 Marketing Platform](https://rees46.com/en/datasets). The course copy keeps
`event_time`, `event_type`, `product_id`, and `user_id`, adds a stable
`event_id`, assigns each user one of eight synthetic `region` values, and keeps
the price as `revenue` only for purchases. Module 1 describes the
transformation and attribution in full.

| | |
| --- | --- |
| Rows | 10,158,080 events from 2019-12-01 00:00:12 to 2020-03-11 04:53:08 (26 days in December 2019 and March 2020) |
| Files | 40 Parquet files, about 72 MiB, in the public bucket `doris-courses-public-dataset` (AWS `us-east-1`): `s3://doris-courses-public-dataset/doris-course/events/v1/events-*.parquet` |
| Lab 3 samples | Three small files (about 250 KB in total) under `https://doris-courses-public-dataset.s3.us-east-1.amazonaws.com/doris-course/lab3/v2/`, downloaded into `level1/module03-loading-data/downloads/` |
| Access | Public and read-only. Doris reads the bucket with the S3 TVF and `"s3.credentials_provider_type" = "ANONYMOUS"`; no AWS account or key is needed. |

`datasets/events.yaml` records the same locations, the schema, and the expected
row count and time range.

Module 1 describes the shape of the data: 26 days in December 2019 and March
2020, event types that cover different days (purchases on only seven of them),
and eight synthetic regions.

## Clean up

To pause, stop the sandbox and keep its data; the next Lab starts it again, or
run `docker start doris-rta`:

```bash
docker stop doris-rta
```

Stop the Kafka broker, the optional Metabase container, and the Module 9
cluster the same way, from the course directory:

```bash
docker compose --file level1/module03-loading-data/compose.kafka.yml stop
docker stop doris-rta-metabase
docker compose --file level3/module09-sharding-replication/compose.multinode.yml stop
```

To remove everything that the course created, run these commands in the course
directory. They delete the course data:

```bash
docker compose --file level3/module09-sharding-replication/compose.multinode.yml down --volumes
docker compose --file level1/module03-loading-data/compose.kafka.yml down --volumes
docker rm -f doris-rta doris-rta-metabase
docker volume rm doris-rta-fe-meta doris-rta-be-storage doris-rta-metabase-data
docker network rm doris-rta
```

A command that names something you never created, such as the optional
Metabase container, reports that it does not exist; the others still run.
Afterward, `docker ps -a --filter name=doris-rta` and
`docker volume ls --filter name=doris-rta` show nothing. Optionally, remove
the images that the course downloaded with `docker image rm`, and delete
`.venv/`, the files that Lab 3 downloaded to
`level1/module03-loading-data/downloads/`, and the Metabase driver in
`level1/module01-introduction/assets/`.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Lab 1 stops at its first step with "Unsupported host" | The course runs on macOS on Apple silicon and on Linux on x86_64, and on Windows inside WSL 2; see [Environment](#environment). |
| A cell says that a host port is in use | It names the port and shows the program that holds it, and it has started nothing. Stop that program, or restart Jupyter with the port's variable set to a free port, as in [Ports and Docker objects](#ports-and-docker-objects). |
| A Lab says that another Lab must run first | Run the Lab that it names, then rerun the cell. [Lab dependencies](#lab-dependencies) lists what each Lab needs. |
| `pip install` fails, or a notebook cannot import `doris_labkit` or `doris_course` | Use Python 3.9 to 3.13, install in `doris-course/01-real-time-analytics` of a complete repository, and choose the kernel of its `.venv`. |
| The connection is refused, or the sandbox is stopped or unhealthy | Check `docker info`, then `docker ps -a --filter name=doris-rta` and `docker logs --tail 200 doris-rta`. Give Docker at least 8 GB of memory and rerun the Lab's first steps, which start the sandbox. Do not remove the volumes to retry: they hold the tables of every Lab. |
| An image cannot be downloaded | Docker Hub is slow or unreachable from your network. Use the registry mirror or proxy of your network, then rerun the cell; a Lab reuses an image that Docker already has. |
| A load from S3 fails with `curlCode: 28, Timeout was reached` | Doris could not reach `s3.us-east-1.amazonaws.com` even within the longer timeouts that the Labs set. Check that your computer reaches it, then rerun the cell; the cells empty their target first, so a rerun is safe. |
| Lab 9 stops before it starts the cluster | It needs 4 CPUs, 8 GB of Docker memory, 20 GiB of free disk, and the sandbox stopped (`docker stop doris-rta`); its message says which. If the cluster gets into a state that the Lab cannot recover from, remove it with `docker compose --file level3/module09-sharding-replication/compose.multinode.yml down` and rerun the Lab from Section 1.1. |
| Lab 10 stops at its first cell | The Module 9 cluster is still running; stop it with the command that the cell shows. |
