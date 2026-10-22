# 测验题与讲义、Lab 的对应关系

每道题考一个学习目标（`objective` 与讲义「Learning objectives」的原文相同，`tests/test_lessons.py` 检查）。「讲义」是给出概念的小节，「Lab」是学员亲手得到证据的地方。B8 写成（RT-12），替换了 `former-readmes/level2/quiz_alignment.md`（旧的 Level 2 对照，题目和章节号都已过时）。

答案分布由 `tools/check_quiz_balance.py --strict doris-course/01-real-time-analytics` 检查（CI 中也运行）。B8 完成时：Level 1 共 18 题，正确项最长 17%，同一位置最多 28%；Level 2 共 24 题，17%、33%；Level 3 共 18 题，22%、33%。错误选项不用 always、never、guarantees、proves。

## Module 1: Introduction to Apache Doris

| 题目 id | 学习目标 | 讲义 | Lab 1 中的证据 |
| --- | --- | --- | --- |
| `define_doris` | 1. Define Apache Doris as an open-source, real-time analytics and search database built on an MPP architecture. | 1.1 What Is Apache Doris? | —（概念题） |
| `identify_olap` | 2. Distinguish OLAP from OLTP by the work that a request does, not by the product that runs it. | 1.2 OLAP and OLTP Workloads | 第 7 节按事件类型汇总一千万行 |
| `choose_cdc_reporting` | 3. Recognize workloads that suit Doris, such as real-time dashboards, customer-facing analytics, observability, lakehouse analytics, and CDC-driven reporting. | 1.3 Where Doris Fits（CDC-driven reporting） | —（概念题） |
| `fe_be_responsibilities` | 4. Summarize what the Frontend (FE) and the Backend (BE) each do with a query. | 1.4 A First Look at Doris Architecture | 第 2 节 `SHOW FRONTENDS`、`SHOW BACKENDS` |
| `choose_architecture` | 5. Distinguish the integrated storage and compute architecture from the decoupled storage and compute architecture. | 1.4（两种架构） | 第 1 节：沙箱是单节点的存算一体环境 |
| `check_the_load` | 6. Connect to Doris through its MySQL-compatible protocol, create a table, load data, and check the result with an aggregation query. | Lab 1 小节 | 第 6 节 `verify_baseline`（行数、最早和最晚时间） |

## Module 2: Deep Dive into Apache Doris Architecture

| 题目 id | 学习目标 | 讲义 | Lab 2 中的证据 |
| --- | --- | --- | --- |
| `trace_query_execution` | 1. Trace a query from FE planning, through its plan fragments, to its execution on BE nodes. | 2.1 From SQL to Distributed Pipelines | 第 7 节 `EXPLAIN` |
| `columnar_and_vectorized` | 2. Explain how columnar storage and vectorized execution reduce the work of an analytical scan. | 2.2 Columnar and Vectorized Processing | 第 4 节 `ScanBytes`：只读查询用到的列 |
| `storage_hierarchy_compaction` | 3. Explain the hierarchy from Table to Partition, Tablet, Rowset, and Segment, and why Compaction merges Rowsets. | 2.3、2.4 | 第 2、6 节 `SHOW PARTITIONS`、`SHOW TABLETS` |
| `choose_table_model` | 4. Describe how the Duplicate Key, Unique Key, and Aggregate Key models treat repeated keys. | 2.5 Table Models and Repeated Keys | 第 9 节三种模型的重复 key |
| `choose_physical_design` | 5. Distinguish partitioning, bucketing, the sort key, and the Prefix Index by the problem each one solves. | 2.6 How Doris Skips Work | 第 3、5 节 `events_v2`、`events_v3`；第 10 节练习 |
| `interpret_explain_profile` | 6. Use `EXPLAIN` and the Query Profile to tell planned pruning from the scan work actually done. | 2.6（EXPLAIN 与 Query Profile） | 第 4 节手动取 Profile，第 7 节 `EXPLAIN` 的比例 |

## Module 3: Loading Data into Apache Doris

| 题目 id | 学习目标 | 讲义 | Lab 3 中的证据 |
| --- | --- | --- | --- |
| `choose_load_method` | 1. Select a Doris load method from the source, volume, latency, transformation, and retry requirements of a workload. | 3.1 Select a Load Method from a Workload Contract | 第 1 节把导入方式拖到工作负载上 |
| `choose_group_commit_mode` | 2. Explain the roles of Stream Load, `INSERT INTO SELECT` with the S3 TVF, Routine Load, and Group Commit. | 3.5 Reduce Small-Write Pressure with Group Commit | —（概念题；第 1 节的匹配练习有 Group Commit） |
| `interpret_quality_rejection` | 3. Load a local CSV file with Stream Load and read its synchronous JSON response. | 3.2（过滤行与被拒的事务） | 第 3 节坏行批次被拒；第 6 节练习改 `max_filter_ratio` |
| `distinguish_s3_tvf_insert` | 4. Query Parquet objects with the S3 TVF and persist them with `INSERT INTO SELECT`. | 3.3 Read S3 Objects and Persist a SQL Result | 第 4 节先查 S3 TVF 再 `INSERT INTO SELECT` |
| `reason_about_routine_load` | 5. Explain when a Routine Load job fits continuous Kafka consumption, and how it tracks its progress. | 3.4 Continuously Load Kafka Data with Routine Load | 第 5 节 jsonpaths、暂停与恢复 |
| `retry_stream_load` | 6. Validate loaded and filtered row counts, recognize a rejected load, and retry a batch safely. | 3.2、3.6 | 第 3 节同一 label 重试 |

## Module 4: Modeling Data in Apache Doris

| 题目 id | 学习目标 | 讲义 | Lab 4 中的证据 |
| --- | --- | --- | --- |
| `separate_grains` | 1. Define a table's grain from its source contract, and keep detail and summary grains in separate tables. | 4.1 Define What One Row Represents | 第 5 节两种粒度对账；第 6 节练习 |
| `duplicate_key_columns` | 2. Choose the Duplicate Key, Unique Key, or Aggregate Key model from the behavior that a repeated key requires. | 4.2 Choose a Table Model from Repeated-Key Semantics | 第 4 节 `events_modelled` |
| `additive_summary` | 3. Derive a summary's dimensions and additive measures from a reporting requirement, and reconcile it with the detail. | 4.3 Derive a Summary Model from the Reporting Requirement | 第 5 节 `daily_event_metrics` |
| `decimal_and_varchar` | 4. Choose types for identifiers, time, money, categories, and nested values from their meaning and the operations they need. | 4.4 Choose Data Types from Business Meaning | 第 2 节 `DOUBLE` 与 `DECIMAL`、`TRY_CAST` |
| `omission_and_null` | 5. Distinguish `NULL`, `NOT NULL`, and `DEFAULT` for values that are missing, omitted, or invalid. | 4.5 Give Missing, Omitted, and Invalid Values Different Rules | 第 3 节 typed boundary（`unknown` 默认值、`NULL` 商品） |
| `layout_from_workload` | 6. Design a table's Partitions, Buckets, and sort key from its time filters, lifecycle, distribution, and volume. | 4.6–4.8 | 第 4 节两个月分区 × 10 桶 = 20 个 Tablet |

## Module 5: Analyzing Data in Apache Doris

| 题目 id | 学习目标 | 讲义 | Lab 5 中的证据 |
| --- | --- | --- | --- |
| `table_function_and_tvf` | 1. Choose a function category, such as scalar, aggregate, window, Table Function, or TVF, from its inputs, outputs, and row-count behavior. | 5.2、5.5 | 第 2 节 `EXPLODE` 与 `NUMBERS` |
| `where_and_having` | 2. Define the population of each measure with conditional aggregates, and filter input rows with `WHERE` and groups with `HAVING`. | 5.4（WHERE 与 HAVING） | 第 4、5 节 |
| `any_value_meaning` | 3. Use `ANY_VALUE` only when any representative value satisfies the meaning of the group. | 5.4（ANY_VALUE） | 第 6 节 |
| `cte_and_missing_dates` | 4. Name each stage of an analysis with a CTE and state the grain of its result. | 5.6 Use CTEs to Express the Stages of a Complex Analysis | 第 7 节 `daily` CTE（3/4–3/8 收入为 0） |
| `rank_and_row_number` | 5. Choose window partitions, ordering, frames, and ranking functions for previous-value, cumulative, and ranking questions. | 5.7（tie behavior） | 第 8、9 节；第 13 节练习用 `RANK` |
| `reusable_logic` | 6. Choose between built-in functions, Lambda expressions, Alias Functions, and user-defined functions for missing reusable logic. | 5.8 Choose the Right Extension for Missing Reusable Logic | 第 10 节 Lambda、第 12 节 UDF 家族 |

## Module 6: Joining Data in Apache Doris

| 题目 id | 学习目标 | 讲义 | Lab 6 中的证据 |
| --- | --- | --- | --- |
| `predict_multiplication` | 1. Predict a Join's result grain and multiplicity from the grain and key cardinality of both inputs. | 6.1 Establish the Relationship Before Adding Attributes | 第 4 节重复的商品 key |
| `return_missing_relationships` | 2. Choose Inner, Outer, Semi, Anti, Cross, or ASOF Join from the rows that the answer must retain. | 6.2 Choose the Logical Join Operator | 第 2 节 Inner、Left Outer、Semi、Anti |
| `on_or_where` | 3. Decide how `NULL` keys match and whether a right-side condition belongs in `ON` or `WHERE`. | 6.3（Outer Join 的条件位置） | 第 8 节练习 |
| `hash_or_nested_loop` | 4. Explain when Doris uses a Hash Join or a Nested Loop Join, and what the build and probe sides do. | 6.4 Connect the Join Condition to Its Physical Implementation | 第 6 节等值与纯非等值的计划 |
| `choose_distribution` | 5. Compare Broadcast, Partition Shuffle, Bucket Shuffle, and Colocate Join by the data each moves and the layout each needs. | 6.5–6.8 | 第 7 节 Broadcast 与 Bucket Shuffle 的计划 |
| `runtime_filter_plan` | 6. Read the Join strategy and Runtime Filters in `EXPLAIN` separately from what the Query Profile records. | 6.9、6.10 | 第 7 节 Runtime Filter 的 Profile 计数 |

## Module 7: Updating and Deleting Data in Apache Doris

| 题目 id | 学习目标 | 讲义 | Lab 7 中的证据 |
| --- | --- | --- | --- |
| `merge_staged_changes` | 1. Choose full-row upsert, partial column update, SQL `UPDATE`, or `MERGE INTO` from the form and ownership of incoming changes. | 7.5 Apply Conditional Actions with MERGE INTO | 第 4 节 |
| `sequence_order` | 2. Use a Sequence column so that source order, not arrival order, decides which state wins. | 7.2 Synchronize Complete States with Unique Key Upsert | 第 1 节较小的 Sequence 不覆盖 |
| `omitted_columns` | 3. Predict what full-row and partial writes do to omitted columns, and how omission differs from `NULL`. | 7.3 Preserve Unowned Fields with Partial Column Update | 第 2 节；第 7 节练习（Stream Load `partial_columns`） |
| `identify_deleted_rows` | 4. Choose predicate `DELETE` or the Delete Sign from how the deleted rows are identified. | 7.6 Choose How Deleted Rows Are Identified | 第 5 节谓词 DELETE 与 Delete Sign |
| `replace_partition` | 5. Choose `TRUNCATE` or `INSERT OVERWRITE` to remove or replace a complete Partition. | 7.7 Match the Operation to a Complete Lifecycle Scope | 第 6 节 `TRUNCATE` 与 `INSERT OVERWRITE` |
| `visibility_and_cleanup` | 6. Separate the visibility of a published change from the later physical cleanup by Compaction. | 7.8 Separate Logical Visibility from Physical Cleanup | 第 5 节 tablet 版本与隐藏的删除标记 |

## Module 8: Accelerating Queries in Apache Doris

| 题目 id | 学习目标 | 讲义 | Lab 8 中的证据 |
| --- | --- | --- | --- |
| `reuse_a_definition` | 1. Distinguish a regular view, a manually populated summary table, a synchronous materialized view, and an asynchronous materialized view. | 8.2 Reuse Query Logic with a Regular View | 第 2 节 |
| `choose_materialization` | 2. Choose synchronous or asynchronous materialization from the SQL scope, the freshness requirement, and the write or refresh cost. | 8.3、8.4 | 第 3、4 节 |
| `stored_grain` | 3. Determine whether a materialized result preserves the dimensions and measure state needed to answer another query. | 8.5 Decide Whether a Materialized Result Can Answer the Query | 第 5 节；第 8 节练习（只按地区） |
| `choose_an_index` | 4. Choose an inverted index, a BloomFilter index, or an NGram BloomFilter index from the predicate it must serve. | 8.6 Narrow Selective Detail Lookups with a Secondary Index | 第 6 节 |
| `estimates_and_actuals` | 5. Separate build state, plan selection, statistics, and runtime evidence when you check an acceleration structure. | 8.7 Give the Optimizer Reliable Inputs | 第 7 节统计信息与 Join 的估计 |
| `worth_the_cost` | 6. Decide whether the read savings of a structure justify its storage, write, and refresh cost. | 8.8 Decide Whether the Read Savings Justify the Cost | —（概念题） |

## Module 9: Sharding, Replication, and Distributed Execution in Apache Doris

| 题目 id | 学习目标 | 讲义 | Lab 9 中的证据 |
| --- | --- | --- | --- |
| `tablets_and_replicas` | 1. Explain how Partitions, Buckets, Tablets, and replicas relate, and count them for a table. | 9.2 Relate Partitions, Buckets, Tablets, and Replicas | 1.2 的 12 个 Tablet、24 个副本；第 4 节练习 |
| `expansion_moves_replicas` | 2. Explain why adding a BE moves existing replicas without changing the table's Partitions or Buckets. | 9.2（扩容不重新分片） | 1.2 加入 be-3 后副本迁移 |
| `fe_failure_and_reconnect` | 3. Separate FE metadata election from the client connection that must be reopened after its FE fails. | 9.3 Separate FE Election from Client Load Balancing | 1.3、1.4 |
| `replicas_and_scan_tasks` | 4. Trace a query from Tablet selection to the BE scan tasks that a Query Profile records. | 9.4 Follow a Query from SQL to BE Scan Tasks | 2.2 |
| `majority_and_recovery` | 5. Apply the default majority-write rule, and tell a live BE from a current replica after an outage. | 9.5 Commit Through a Majority and Recover the Lagging Replica | 2.3、2.4 |
| `bucket_shuffle_or_colocate` | 6. Explain how Bucket Shuffle and Colocate Join reduce the data that a distributed Join moves. | 9.6 Compare Bucket Shuffle and Colocate Join Data Movement | 3.1、3.2 |

## Module 10: Controlling Storage Cost and Data Lifecycle in Apache Doris

| 题目 id | 学习目标 | 讲义 | Lab 10 中的证据 |
| --- | --- | --- | --- |
| `compression_goal` | 1. Explain the separate roles of column encoding and Page compression, and choose a compression algorithm from the constrained resource. | 10.2 Understand Where Doris Compresses Data | 第 1 节算法特点表 |
| `fair_comparison` | 2. Design a fair compression comparison that keeps the input, layout, loads, and replicas equal. | 10.3 Compare Compression Choices with Controlled Input | 第 1 节三张对照表 |
| `partition_modes` | 3. Choose Manual, Auto, or Dynamic Partitioning from what creates and what removes Partitions. | 10.4 Choose How Partitions Are Created and Removed | 第 2 节（Dynamic）、第 4 节（Manual） |
| `hourly_window` | 4. Read a Dynamic Partition window from its time unit, offsets, and time zone, and predict what happens to late data. | 10.5 Define a Rolling Window and Its Late-Data Policy | 第 2 节小时窗口；第 5 节练习（按天的窗口） |
| `expiry_evidence` | 5. Separate an accepted configuration, scheduler action, SQL visibility, and storage reclamation when a Partition expires. | 10.6 Separate Configuration, Scheduling, Visibility, and Reclamation | 第 3 节缩小 start 后等调度器 |
| `recovery_boundary` | 6. Decide when the recycle bin is enough and when an independent backup or a replay from the source is needed. | 10.8 Establish the Recovery Boundary Before Data Is Removed | 第 4 节不带 FORCE 删除后按名字恢复 |
