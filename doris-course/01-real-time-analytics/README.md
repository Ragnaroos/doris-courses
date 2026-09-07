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
