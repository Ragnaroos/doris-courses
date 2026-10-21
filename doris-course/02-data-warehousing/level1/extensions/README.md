# Level 1 Extension Labs

These optional notebooks add hands-on work to the main course; they add no modules and replace none of the seven Labs.
Complete Labs 1, 4, 5, 6, and 7 in main-course order before running the extensions; all use the course's single-container sandbox.

| Lab | Related modules | Validation |
|---|---|---|
| [Physical design](extension23_physical_design.ipynb) | Module 2–3 | 100,000 deterministic rows; batches, partitions, execution plans, and Profile, with row-by-row matching results |
| [Files and Group Commit](extension45_files_and_group_commit.ipynb) | Module 4–5 | Standalone Parquet TVF, INSERT SELECT, Broker Load; defaults and generated columns; Group Commit acknowledgment and visibility |
| [Schema and deletion](extension67_schema_and_delete.ipynb) | Module 6–7 | Column additions and type changes, version resolution after load-based deletion, and detection of conflicting content for the same event ID |

## Preparation and Execution

Generating Parquet files for the extensions requires PyArrow. Install it from this course directory:

```bash
.venv/bin/python -m pip install -e '.[extensions]'
.venv/bin/jupyter lab level1/extensions/
```

Run only one notebook at a time in the same lab database. Each extension lists the `ext_*` tables it rebuilds at the beginning;
it does not modify main-course business tables, delete historical files from object storage, or restart other clusters.
Object storage experiments reuse the course object storage from Lab 4 (Silo) and write to an independent random path each time. On failure, preserve job status and output before troubleshooting.
Allow 80–115 minutes in total, in addition to the seven Labs.

## Boundaries

- 100,000 rows and a single node provide only local observations, not proof of production concurrency, failure recovery, or a fixed performance gain.
- The Group Commit extension compares acknowledgment and query visibility request by request, and does not measure sustained throughput; Lab 5 shows ten async_mode loads sharing one transaction.
- Schema changes cover only this lab's column additions and type changes, not every model and change combination.
- Conflict detection runs in an independent staging table; it is not an atomic rejection service for concurrent consumers.
- Kafka and MySQL/Flink CDC have their own optional Labs 5A and 5B, with [their own environment](../../environments/streaming/README.md), outside these three extensions. CDC_STREAM and continuous file ingestion from object storage are covered only in the [optional reading on continuous ingestion](../module05-ingestion/optional05_continuous_ingestion.md).
