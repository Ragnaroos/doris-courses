# Real-time Analytics with Apache Doris

This directory contains the course notes, executable Jupyter labs, shared
datasets, and reusable runtime support for the three course levels. Levels 1
and 2 are implemented. Level 3 includes executable Labs 8, 9, and 10; its
course notes and quizzes are still planned.

## Repository structure

```text
doris-course/
└── 01-real-time-analytics/
    ├── README.md
    ├── requirements.txt
    ├── pyproject.toml
    ├── .gitignore
    ├── course_secrets.env.example
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

Generated content is not committed: `.venv/`, `course_secrets.env`, notebook
checkpoints, downloaded fixtures, and local JAR files remain local runtime
state.

## Python environment and shared helpers

Run setup from this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp course_secrets.env.example course_secrets.env
```

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
Lab 9 starts it as the Compose project `doris-course-m09`: three FEs, three
BEs, and HAProxy. Docker needs at least 4 CPUs, 8 GB of memory, and 20 GiB of
free disk space, and the single-node `doris` container must be stopped first
(`docker stop doris`). To reset or remove the Module 9 cluster, run
`docker compose --file level3/module09-sharding-replication/compose.multinode.yml down`
from the course directory.
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

Lab 1 loads 10,158,080 ecommerce event rows from the read-only course S3
dataset. Lab 2 reuses `events` without accessing S3. Lab 3 downloads its CSV and
JSON fixtures into the ignored
`level1/module03-loading-data/downloads/` runtime cache and compares Stream
Load, S3 TVF with `INSERT INTO SELECT`, and Kafka Routine Load.
