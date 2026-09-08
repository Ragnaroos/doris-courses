# Apache Doris Course Labs

This directory contains the executable Jupyter labs for **Real-time Analytics
with Apache Doris**. Run the notebooks in order: Lab 1 creates the persistent
sandbox and baseline data, Lab 2 explores physical design, and Lab 3 compares
three ingestion paths.

## Setup

The labs support macOS on Apple Silicon with Docker Desktop and Linux on x86_64
with Docker Engine. Use Python 3.9 through 3.13 in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp lab1_secrets.env.example lab1_secrets.env
```

Fill `lab1_secrets.env` with the course read-only S3 credentials. The real
credentials file is ignored by Git and must never be committed.

## Repository organization

The current labs are kept together while Level 1 is being developed. As Levels
2 and 3 are added, use the following course structure. Each module owns its
course notes, notebook, and module-specific runtime files; files used by more
than one module stay at the `01-real-time-analytics` root.

```text
doris-course/
└── 01-real-time-analytics/
    ├── README.md
    ├── requirements.txt
    ├── pyproject.toml
    ├── course_secrets.env.example
    ├── doris_course/                 shared notebook support package
    │   ├── ui.py
    │   ├── docker_runtime.py
    │   ├── doris_client.py
    │   ├── s3.py
    │   ├── profiles.py
    │   └── kafka.py
    ├── datasets/                    shared manifests and expected results
    ├── environments/
    │   └── single-node/          reusable integrated sandbox guidance
    ├── level1/
    │   ├── module01-introduction/
    │   │   ├── course.md
    │   │   ├── lab1_start_doris_and_build_baseline.ipynb
    │   │   └── optional_metabase_dashboard.ipynb
    │   ├── module02-architecture/
    │   │   ├── course.md
    │   │   └── lab2_scan_less_data.ipynb
    │   └── module03-loading-data/
    │       ├── course.md
    │       ├── lab3_load_data.ipynb
    │       └── compose.kafka.yml
    ├── level2/
    │   ├── module04-modeling/
    │   ├── module05-analyzing/
    │   ├── module06-joining/
    │   └── module07-updating-deleting/
    └── level3/
        ├── module08-query-acceleration/
        ├── module09-sharding-replication/
        └── module10-managing-data/
```

This tree is the target organization, not a statement that every listed file
already exists. Moving the current notebooks into it should be a separate,
reviewable change so that notebook behavior does not change at the same time.

### Shared and module-owned files

| Location | Store here | Do not store here |
| --- | --- | --- |
| Course root | Python dependency definitions, shared notebook UI, Docker and Doris clients, S3 access helpers, dataset manifests, and shared expected results | A separate copy of the same helper for every module |
| Module directory | `course.md`, the module notebook, and files used only by that module, such as the Metabase instructions or Kafka Compose file | Secrets or generated downloads |
| Local runtime only | `.venv/`, `course_secrets.env`, downloaded fixtures, notebook checkpoints, and other caches | Files committed to Git or included in a course archive |

Create one local `.venv` at the `01-real-time-analytics` root and reuse it for
all three levels. The virtual environment itself is not portable and must stay
ignored; `requirements.txt` and, after packaging, `pyproject.toml` define the
reproducible environment. Install the shared package once with
`python -m pip install -e .` so notebooks can use the same imports regardless
of their directory depth.

The current `lab_helpers.py` is the transitional shared implementation. As the
course grows, split it by responsibility into the `doris_course/` package shown
above while preserving a small, stable learner-facing API. Do not create an
independent helper file for every module unless the behavior is genuinely
module-specific.

### Doris environment reuse

Levels 1 and 2, plus the query-acceleration material in Level 3, should reuse
the persistent single-node integrated sandbox created in Lab 1. A later
sharding and replication module should use a separately named multi-node
sandbox. Destructive data-management exercises should also use an isolated or
resettable environment instead of risking the shared course data.

Docker named volumes preserve FE metadata and BE data between notebooks.
Stopping a container does not delete those volumes. Module cleanup must remove
only resources owned by that module and must not delete the shared Lab 1
volumes.

### One database with independently named tables

All levels use the same database:

```sql
CREATE DATABASE IF NOT EXISTS doris_course;
USE doris_course;
```

Do not create a database for every level or module. Tables are named by their
role and are independently owned by the lab that creates them:

| Owner | Current tables | Rule |
| --- | --- | --- |
| Module 1 | `events` | Baseline table shared with later modules; later labs treat it as read-only |
| Module 2 | `events_v2`, `events_v3`, `model_dup`, `model_uniq`, `model_agg` | Physical-design and table-model comparisons derived from `events` |
| Module 3 | `events_stream`, `events_s3`, `events_routine` | Independent targets that isolate each ingestion method |

Future modules should continue with descriptive table names rather than new
databases. A notebook may safely `DROP`, `TRUNCATE`, or recreate only the tables
it owns. This keeps reruns predictable while allowing every level to build on
the same `doris_course.events` baseline.

## Lab 1

Start JupyterLab with the prepared environment:

   ```bash
   .venv/bin/jupyter lab lab1_start_doris_and_build_baseline.ipynb
   ```

Use **Run All**, or run the notebook cells from top to bottom. The compact
initialization cell loads the local helpers and styles used by later cells.

## Optional Metabase Lab

After completing Lab 1, open the separate optional notebook:

```bash
.venv/bin/jupyter lab lab1_optional_metabase_dashboard.ipynb
```

The notebook displays the driver download, Docker volume, image, container,
and health-check commands directly. It does not use the former
`lab.start_metabase()` wrapper.

The notebook supports Docker Desktop on macOS Apple Silicon and Docker Engine
on Linux x86_64. Docker selects the native image manifest automatically; do not
add `--platform linux/amd64` on Apple Silicon.

The course S3 dataset contains 10,158,080 ecommerce behavior rows in 40 Parquet
files. Lab 1 loads seven named fields directly into the `events` table. The
notebook contains the schema, validation checks, and expected results needed by
the learner.

## Lab 2

Complete Lab 1 first, then start the architecture and scan-reduction Lab:

```bash
.venv/bin/jupyter lab lab2_scan_less_data.ipynb
```

Lab 2 reuses the persisted `events` table and creates `events_v2` and
`events_v3` with different physical designs. It does not require S3
credentials and does not access or modify the course objects in S3.

Notebook outputs are cleared before release so that learner-visible evidence
always comes from the learner's own environment.

## Lab 3

Complete Lab 1 first, then start the data-loading Lab:

```bash
.venv/bin/jupyter lab lab3_load_data.ipynb
```

Lab 3 compares Stream Load, S3 TVF with `INSERT INTO SELECT`, and Kafka Routine
Load using independent target tables. Group Commit remains in the workload
matching exercise as the server-side optimization for frequent small writes;
it is not presented as a separate source connector. The Kafka sandbox is
defined in `lab3/compose.kafka.yml` and shares the existing `doris-course`
Docker network.

The learner-side CSV and nested JSON fixtures represent the same fixed
1,024-record sample from the Lab 1/2 event dataset. A separate ten-row malformed
CSV is used only for transaction-rejection evidence. Each ingestion section
downloads its fixture from the course S3 bucket with the read-only credentials
in `lab1_secrets.env`, placing it in the ignored `lab3/downloads/` runtime cache.
An existing valid local copy is reused; an incomplete download is never
installed as the active fixture.
