# Real-time Analytics with Apache Doris

This directory contains the course notes, executable Jupyter labs, shared
datasets, and reusable runtime support for the three course levels. Levels 1
and 2 are implemented. Level 3 includes executable Labs 8, 9, and 10; its
course notes and quizzes are still planned.

## Environment

| | |
| --- | --- |
| Platforms | **macOS on Apple silicon** with Docker Desktop: the platform on which every lab of this release was run from start to finish. **Linux on x86_64** with Docker Engine: the labs accept it and use the same images, but this release has not been run on it. **Windows**: run the course inside a WSL 2 Linux distribution on x86_64 with Docker Desktop's WSL 2 integration, and start Jupyter there; inside WSL the labs see Linux on x86_64. This release has not been run on it either. |
| Other platforms | Lab 1 stops at its first step on other combinations, such as an Intel Mac or Linux on arm64. The Doris, Kafka, and HAProxy images exist for both amd64 and arm64, but the course has not been run on those combinations, so Lab 1 does not continue there. |
| Resources | Docker needs at least 4 CPUs, 8 GB of memory, and 20 GB of free disk. With 4 CPUs and 8 GB, the Doris container peaks at about 3.1 GiB during Lab 1's load. Module 9 runs three FEs, three BEs, and HAProxy within the same minimum (6.4 GB in all at its peak in our run); stop the single-node sandbox first. |
| Downloads | Docker images: `apache/doris:all-in-one-4.1.3` (about 1.9 GB to download, 4.5 GB on disk), `apache/kafka:3.9.1` for Module 3 (0.2 GB), `haproxy:3.0-alpine` for Module 9 (20 MB), and `metabase/metabase:v0.59.6.3` for the optional Metabase lab (0.7 GB); a lab reuses an image that Docker already has. The optional Metabase lab also downloads the Doris driver for Metabase (19 KB) from GitHub. Data: 72 MiB of Parquet files from AWS S3 in Lab 1 and again in Lab 3; on its first run, Lab 9 reads a seven-hour slice of the same files, and because those rows are spread over all 40 files, Doris reads about 59 MB to find them; three small files in Lab 3. Python packages from PyPI. |
| Network | Docker Hub for the images; `s3.us-east-1.amazonaws.com` and `doris-courses-public-dataset.s3.us-east-1.amazonaws.com` over HTTPS for the data; PyPI for the packages; GitHub for the optional Metabase lab's driver. From some networks, including mainland China, Docker Hub and AWS `us-east-1` can be slow or unreachable: use the registry mirror or proxy that your network provides. The labs give Doris longer S3 timeouts than its defaults (Module 3 explains them), so a slow connection makes a load slower instead of failing it: the 72 MiB load of Labs 1 and 3 took 11 seconds to 2 minutes over direct connections in our runs, and 22 minutes through a proxy that delivered about 60 KB/s; through the same proxy, Lab 9's first load took 13 minutes. |
| Accounts and keys | None. The dataset bucket is public and is read anonymously. |
| Python | 3.9 to 3.13. If `python3 --version` reports 3.14 or later, create the virtual environment with a supported version, for example `python3.12 -m venv .venv`. |

## Repository structure

```text
doris-course/
└── 01-real-time-analytics/
    ├── README.md
    ├── requirements.txt
    ├── pyproject.toml
    ├── .gitignore
    ├── doris_course/
    │   ├── __init__.py
    │   ├── ui.py
    │   ├── docker_runtime.py
    │   ├── doris_client.py
    │   ├── s3.py
    │   ├── profiles.py
    │   ├── kafka.py
    │   └── quiz.py
    ├── datasets/
    │   ├── events.yaml
    │   ├── dimensions.yaml
    │   └── expected_results.yaml
    ├── environments/
    │   └── single-node/
    │       └── README.md
    ├── level1/
    │   ├── README.md
    │   ├── module01-introduction/
    │   │   ├── course.md
    │   │   ├── lab01_start_doris_and_build_baseline.ipynb
    │   │   ├── optional01_metabase_dashboard.ipynb
    │   │   ├── quiz01_doris_fundamentals.ipynb
    │   │   └── quiz01_doris_fundamentals.yaml
    │   ├── module02-architecture/
    │   │   ├── course.md
    │   │   ├── lab02_scan_less_data.ipynb
    │   │   ├── quiz02_doris_architecture_and_physical_design.ipynb
    │   │   └── quiz02_doris_architecture_and_physical_design.yaml
    │   └── module03-loading-data/
    │       ├── course.md
    │       ├── lab03_load_data.ipynb
    │       ├── compose.kafka.yml
    │       ├── quiz03_load_methods_and_retry_safety.ipynb
    │       └── quiz03_load_methods_and_retry_safety.yaml
    ├── level2/
    │   ├── README.md
    │   ├── module04-modeling/
    │   │   ├── course.md
    │   │   ├── lab04_model_data.ipynb
    │   │   ├── quiz04_schema_and_modeling_choices.ipynb
    │   │   └── quiz04_schema_and_modeling_choices.yaml
    │   ├── module05-analyzing/
    │   │   ├── course.md
    │   │   ├── lab05_analyze_data.ipynb
    │   │   ├── quiz05_analytical_query_semantics.ipynb
    │   │   └── quiz05_analytical_query_semantics.yaml
    │   ├── module06-joining/
    │   │   ├── course.md
    │   │   ├── lab06_join_data.ipynb
    │   │   ├── quiz06_join_semantics_and_execution.ipynb
    │   │   └── quiz06_join_semantics_and_execution.yaml
    │   └── module07-updating-deleting/
    │       ├── course.md
    │       ├── lab07_update_delete_data.ipynb
    │       ├── quiz07_state_changes_and_deletion.ipynb
    │       └── quiz07_state_changes_and_deletion.yaml
    └── level3/
        ├── README.md
        ├── module08-query-acceleration/
        │   ├── course.md
        │   └── lab08_accelerate_queries.ipynb
        ├── module09-sharding-replication/
        │   ├── course.md
        │   ├── lab09_observe_sharding_and_replication.ipynb
        │   └── compose.multinode.yml
        └── module10-managing-data/
            ├── course.md
            └── lab10_manage_data.ipynb
```

Course notes, labs, and knowledge checks belong to the module that teaches
them. A Compose file, driver, or fixture used by only one module stays with
that module. Python dependencies, notebook presentation, Docker/Doris access,
S3 access, dataset contracts, and expected results are shared at the course
root.

Generated content is not committed: `.venv/`, notebook checkpoints, downloaded
fixtures, and local JAR files remain local runtime state.

## Python environment and shared helpers

Run setup from this directory with Python 3.9 to 3.13 (see [Environment](#environment)):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` also installs `doris_labkit`, the notebook runtime shared by the
courses, from `../common`. Run the command from this directory and keep the
repository together.

Use the same `.venv` for all levels. The environment itself is not portable;
`pyproject.toml` and `requirements.txt` are the reproducible definitions.

Each notebook initialization cell finds the course root before importing one
stable learner-facing entry point. This supports both JupyterLab launched from
the course root and VS Code opened directly on a module notebook:

```python
from doris_course import DorisLab
```

The package separates notebook UI, Docker lifecycle, Doris access, S3,
profiles, and Kafka concerns. `DorisLab` remains the small façade used in
notebook cells, so implementation changes do not add setup code to the learner
experience.

## Doris environment reuse

Level 1, Level 2, and Level 3 query-acceleration exercises reuse the persistent
single-node integrated sandbox created by Module 1. Docker named volumes retain
FE metadata and BE data when the container stops.

Sharding and replication require a separately named multi-node environment.
Lab 9 starts it as the Compose project `doris-rta-m09`: three FEs, three
BEs, and HAProxy. Docker needs at least 4 CPUs, 8 GB of memory, and 20 GiB of
free disk space, and the single-node `doris-rta` container must be stopped first
(`docker stop doris-rta`). To reset or remove the Module 9 cluster, run
`docker compose --file level3/module09-sharding-replication/compose.multinode.yml down`
from the course directory.

## Container names and host ports

Every Docker resource of this course starts with `doris-rta`, and every host
port is bound to `127.0.0.1` in the 1xxxx range, so this course can run next to
the other courses in this repository. To use a different host port, set its
variable before starting Jupyter; the notebooks, shell cells, and Compose files
read the same variables.

| What | Name | Host port (variable) |
| --- | --- | --- |
| Single-node sandbox, Modules 1-8 and 10 | container `doris-rta`, network `doris-rta`, volumes `doris-rta-fe-meta` and `doris-rta-be-storage` | FE query 19030 (`DORIS_RTA_QUERY_PORT`), FE HTTP 18030 (`DORIS_RTA_HTTP_PORT`), BE HTTP 18040 (`DORIS_RTA_BE_HTTP_PORT`) |
| Kafka broker, Module 3 | Compose project `doris-rta-kafka`, container `doris-rta-kafka` | 19092 (`DORIS_RTA_KAFKA_PORT`) |
| Optional Metabase, Module 1 | container `doris-rta-metabase`, volume `doris-rta-metabase-data` | 13000 (`DORIS_RTA_METABASE_PORT`) |
| Multi-node cluster, Module 9 | Compose project `doris-rta-m09` | FE query 19130-19132, FE HTTP 18130-18132, BE HTTP 18140, HAProxy 19230 and stats 18230 (`DORIS_RTA_M09_*`, see `doris_course/environment.py`) |

Inside the sandbox, FE still listens on its default ports 9030 and 8030; the
host ports forward to them. BE's web server listens on 18040 inside the
container as well, because FE redirects Stream Load requests to the address BE
registers, and that address must also work from your computer.

To remove everything this course created (this deletes the course data):

```bash
docker compose --file level3/module09-sharding-replication/compose.multinode.yml down --volumes
docker compose --file level1/module03-loading-data/compose.kafka.yml down --volumes
docker rm -f doris-rta doris-rta-metabase
docker volume rm doris-rta-fe-meta doris-rta-be-storage doris-rta-metabase-data
docker network rm doris-rta
```

A command that names something you never created, such as the optional
Metabase container, reports that it does not exist; the others still run.

Destructive management exercises should also use an isolated or resettable
environment. A module may clean up only the containers, volumes, topics, jobs,
and tables it owns.

## One database and independently owned tables

Every level uses one database:

```sql
CREATE DATABASE IF NOT EXISTS doris_course;
USE doris_course;
```

Do not create a database for each level or module. Tables use descriptive,
independent names:

| Owner | Current tables | Responsibility |
| --- | --- | --- |
| Level 1, Module 1 | `events` | Persistent baseline shared with later modules |
| Level 1, Module 2 | `events_v2`, `events_v3`, `model_dup`, `model_uniq`, `model_agg` | Physical-layout and table-model comparisons |
| Level 1, Module 3 | `events_stream`, `events_s3`, `events_routine` | Independent targets for each load method |

Later modules treat `doris_course.events` as read-only and create their own
descriptively named derived tables. Rerunnable notebooks may `DROP`, `TRUNCATE`,
or recreate only their owned tables.

## Run Level 1

Start JupyterLab from this directory so all module-relative commands share the
same course root:

```bash
.venv/bin/jupyter lab level1/module01-introduction/lab01_start_doris_and_build_baseline.ipynb
```

Then run:

```text
level1/module02-architecture/lab02_scan_less_data.ipynb
level1/module03-loading-data/lab03_load_data.ipynb
```

The optional Metabase lab is:

```text
level1/module01-introduction/optional01_metabase_dashboard.ipynb
```

The Level 1 knowledge checks are independent of Docker, Doris, Kafka, and S3:

```text
level1/module01-introduction/quiz01_doris_fundamentals.ipynb
level1/module02-architecture/quiz02_doris_architecture_and_physical_design.ipynb
level1/module03-loading-data/quiz03_load_methods_and_retry_safety.ipynb
```

Lab 1 loads 10,158,080 ecommerce event rows from the course's public S3
bucket (see [Dataset](#dataset)); no AWS account or credentials are needed.
Lab 2 reuses `events` without accessing S3. Lab 3 downloads its CSV and JSON
fixtures into the ignored `level1/module03-loading-data/downloads/` runtime
cache and compares Stream Load, S3 TVF with `INSERT INTO SELECT`, and Kafka
Routine Load.

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
