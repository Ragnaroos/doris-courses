# Level 1

Run the modules in order. Module 1 creates the shared `doris_course.events`
baseline, Module 2 compares physical designs, and Module 3 compares load
methods. All notebooks reuse the same persistent single-node integrated Doris
sandbox.

Module 1 also includes
[`quiz1_doris_fundamentals.ipynb`](module01-introduction/quiz1_doris_fundamentals.ipynb),
a five-question interactive knowledge check that runs without Docker or Doris.
Module 2 includes
[`quiz2_doris_architecture_and_physical_design.ipynb`](module02-architecture/quiz2_doris_architecture_and_physical_design.ipynb),
another five-question knowledge check using the same interaction model.
Module 3 includes
[`quiz3_load_methods_and_retry_safety.ipynb`](module03-loading-data/quiz3_load_methods_and_retry_safety.ipynb),
a five-question knowledge check covering load-method selection, quality
evidence, persistence boundaries, and retry safety.

## Level 1 terminology

The course uses the following terms consistently with the Apache Doris 4.x
documentation:

| Course term | Meaning |
| --- | --- |
| Frontend (FE) / Backend (BE) | Use the full name at first mention, then FE and BE. |
| Distributed query plan / plan fragment | FE creates and optimizes a distributed query plan and assigns its plan fragments; BE nodes execute the assigned plan fragments. |
| Physical operator / `PlanNode` | A scan, filter, join, aggregation, Exchange, or other operation inside a plan fragment. |
| Pipeline execution engine | The BE execution engine that schedules operators from assigned plan fragments as parallel Pipeline tasks. |
| MySQL-compatible protocol | The client protocol used to connect to the FE query port. |
| Integrated storage-compute architecture / decoupled storage-compute architecture | The two Doris deployment architectures used throughout the course. |
| Internal table | A table whose data is managed by Doris; `internal-table` is used only as a compound adjective. |
| Duplicate Key model / Unique Key model / Aggregate Key model | The three table models; `DUPLICATE KEY`, `UNIQUE KEY`, and `AGGREGATE KEY` remain SQL keywords in DDL. |
| Partition / Bucket / Tablet / Rowset / Segment | The storage hierarchy; a Bucket corresponds to a physical Tablet within a Partition. |
| Sort key / Prefix Index | The row order and the automatic sparse index over its leading prefix. |
| Partition pruning / bucket (tablet) pruning | FE excludes Partitions or Tablets from the distributed query plan. |
| Query Profile | Runtime evidence collected while BE nodes execute assigned plan fragments; do not rename it “runtime profile” in learner-facing text. |
| Load method | A Doris mechanism such as Stream Load, `INSERT INTO SELECT`, or Routine Load. |
| S3 table-valued function (S3 TVF) | Exposes S3 objects as a temporary relation for SQL queries. |
| Routine Load job | A Doris-managed, long-running Kafka consumer job. |
| Load transaction | The atomic unit that either commits its accepted rows or leaves none of them visible. |
| Stream Load label | A client-supplied batch identity used for duplicate protection and safe retry inspection. |
| Filtered row / unselected row / rejected transaction | A malformed row removed by quality rules / a valid row excluded by `where` / a complete load transaction that does not commit. |
| Kafka topic / Partition / offset | A named message stream / one ordered shard of that stream / a message position within the Partition. |
| Group Commit | A server-side optimization that groups compatible high-frequency small writes into fewer load transactions. |
