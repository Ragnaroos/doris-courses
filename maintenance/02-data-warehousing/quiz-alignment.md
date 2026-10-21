# 测验题与讲义、Lab 的对应关系（Level 1）

每道题考一个学习目标（`objective` 与讲义「Learning objectives」的原文相同，`tests/test_lessons.py` 检查，选读材料 `optional05_continuous_ingestion.md` 也一样）。「讲义」是给出概念的小节，「Lab」是学员亲手得到证据的地方。B5 写成，Level 2–3（Module 8–14）在 B6 补上。

答案分布由 `tools/check_quiz_balance.py --strict doris-course/02-data-warehousing/level1` 检查（CI 中也运行）：B5 完成时 48 题，正确项最长 25%（12 题），同一位置最多 27%（各位置 11 / 12 / 13 / 12）。

## Module 1: Meet Doris and Analyze Your First Orders

| 题目 id | 学习目标 | 讲义 | Lab 1 中的证据 |
| --- | --- | --- | --- |
| `transaction_or_analysis` | Distinguish completing a transaction from analyzing a batch of orders. | 1.1 | 第 7 节按日汇总（分析） |
| `doris_between_systems` | Explain Doris's role between business databases and analytics users. | 1.2 | — （概念题） |
| `fe_and_be_roles` | Explain what the Frontend (FE) and the Backend (BE) do in an integrated storage and compute deployment. | 1.1 | 第 2 节 `SHOW FRONTENDS` / `SHOW BACKENDS` |
| `what_the_mysql_protocol_gives` | Explain what connecting with the MySQL protocol gives you, and what it does not. | 1.2「What the MySQL protocol gives you」 | 第 2 节 `SELECT VERSION()` 返回 5.7.99，Version 列是 4.1.3 |
| `filter_and_group_by_date` | Write SQL that filters orders and summarizes them by date. | 1.4 | 第 7 节按日汇总；两个练习（≥1000.00、第二天 ≥300） |
| `what_an_amount_shows` | Tell what an order's pre-tax amount measures, and what the total of a sample can and cannot show. | 1.3、1.4「Check the result, and what it means」 | 第 6 节 10 单、12220.60 与逐字段比对 |

## Module 2: Doris Storage Architecture and Write Mechanisms

| 题目 id | 学习目标 | 讲义 | Lab 2 中的证据 |
| --- | --- | --- | --- |
| `planning_then_execution` | Trace a query to explain FE planning and BE execution. | 2.1 | 第 5 节 EXPLAIN 与 Profile |
| `tablets_rowsets_segments` | Explain the hierarchy of table, partition, tablet, rowset, and segment. | 2.2 | 第 3、4 节分区、tablet、rowset |
| `visibility_and_compaction` | Explain when loaded rows become visible, and what compaction changes afterward. | 2.3 | 第 2 节写完即可查询；第 4 节 compaction 后结果不变 |
| `compare_one_thing_at_a_time` | Compare batch and row-by-row writes with everything else held constant. | 2.4 | 第 1 节两张表只差写法 |
| `versions_and_rowsets` | Read a tablet's versions and rowsets, and explain what they show about write batches and compaction. | 2.4「What versions and rowsets show」 | 第 3 节 Version 2 与 11；第 4 节 `[2-2]` … `[11-11]` 合并为 `[2-11]` |
| `plan_and_profile` | Use EXPLAIN for what a query plans and the Query Profile for what its scan read. | 2.5 | 第 5 节三个查询的 ScanRows、RowsKeyRangeFiltered、RowsVectorPredFiltered；练习的日期过滤 |

## Module 3: Doris Table Models, Partitioning, and Bucketing

| 题目 id | 学习目标 | 讲义 | Lab 3 中的证据 |
| --- | --- | --- | --- |
| `same_writes_three_models` | Predict the results of the same input in the Duplicate, Unique, and Aggregate Key models. | 3.1 | 第 1 节三张表的结果 |
| `model_and_keys` | Choose a key model and key columns for detail records, current state, or additive metrics. | 3.2 | 练习 4（选模型表示当前金额） |
| `four_design_choices` | Distinguish partitions, buckets, sort keys, and business unique keys. | 3.4 | 第 2 节 `orders_partitioned` 的定义 |
| `partition_and_bucket_pruning` | Read EXPLAIN to tell partition pruning from bucket pruning. | 3.5 | 第 2 节三个计划：2/2、8/8；1/2、4/4；1/2、1/4 |
| `merge_on_write` | Explain what Merge-on-Write does for a Unique Key table. | 3.3 | 第 1 节 `orders_unique` 的 MoW 属性（Module 7 再用） |
| `smaller_plan_not_speedup` | Tell a smaller plan from a measured speedup. | 3.5「Pruning must not change the answer, and is not yet a speedup」 | 第 2 节检查第一天仍是 5 单、3944.20 |

## Module 4: Querying External Data and Joining Lake Tables

| 题目 id | 学习目标 | 讲义 | Lab 4 中的证据 |
| --- | --- | --- | --- |
| `files_tables_catalogs` | Distinguish Doris internal tables, Parquet files, Iceberg tables, and External Catalogs. | 4.1 | 第 1 节 `ENGINE=ICEBERG_EXTERNAL_TABLE`；第 4 节 ENGINE iceberg / Doris |
| `catalog_database_table` | Find a lake table through a Catalog and name it as catalog.database.table. | 4.2 | 第 1 节 `SHOW CATALOGS`、`SHOW DATABASES FROM`、`SHOW TABLES FROM` |
| `snapshots_and_files` | Read an Iceberg table's snapshots and files, and explain which files a query of the table reads. | 4.3 | 第 2 节 `$snapshots`、`$files` |
| `query_in_place_or_load` | Choose between querying external data in place and loading it into an internal table. | 4.4 | 第 3 节直接查湖表；第 4 节装入 `orders_from_lake` |
| `s3_function_and_load` | Read files in object storage with the S3 table function and load them with INSERT INTO SELECT. | 4.5 | 第 5 节 `DESC FUNCTION S3(...)`、`INSERT INTO orders_from_file` |
| `join_fanout_and_missing` | Find duplicate or missing dimension rows by comparing results before and after a join. | 4.6 | 第 4 节 join 后仍 10 单；练习的 LEFT JOIN 缺失客户数 |

## Module 5: Batch and Continuous Data Ingestion

| 题目 id | 学习目标 | 讲义 | Lab 5 中的证据 |
| --- | --- | --- | --- |
| `choose_a_load_method` | Choose a load method for a local file, files in object storage, a message stream, a database's changes, or many small writes. | 5.1、5.5 | 第 1 节 Stream Load；第 4 节 Group Commit（对象存储在 Lab 4 第 5 节） |
| `map_fields_to_columns` | Map CSV positions, Parquet fields, and default values to the columns of a target table. | 5.2 | 第 1 节 `columns`；第 5 节 Parquet；练习 6（列顺序不同的 CSV） |
| `judge_a_load` | Judge a load from its response and from the rows, relationships, and amounts in the target table. | 5.3「The response, then the table」 | 第 1 节响应与表；第 5 节 join 检查 |
| `retry_with_the_label` | Retry a load batch safely with its label, and tell a batch retry from business deduplication. | 5.3「A label makes a retry safe, for a while」 | 第 2 节 `Label Already Exists` |
| `group_commit_visibility` | Explain what Group Commit changes for many small loads, and when their rows become visible. | 5.4 | 第 4 节 off_mode 10 个事务、版本 11；async_mode 1 个事务、版本 2、约 2 秒后可见 |
| `grains_and_definitions` | Distinguish the grain and amount definitions of WWI historical orders, account receipts, and the simulated new orders. | 5.6 | 第 5 节按日 `COUNT(DISTINCT OrderID)`；练习 7（产品排名，每行只计一次） |

### 选读材料 Continuous Ingestion（`quiz05_continuous_ingestion.yaml`）

| 题目 id | 学习目标 | 选读材料 | 选做 Lab 中的证据 |
| --- | --- | --- | --- |
| `progress_or_version` | Explain why a continuous load job keeps its own progress, and how that progress differs from a business version. | Progress belongs to the job | 5A 第 2、4 节 Progress `{"0":"1"}`、`{"0":"4"}` |
| `pause_resume_or_stop` | Read a Routine Load job's state and progress, and choose between pausing, resuming, and stopping it. | Kafka and Routine Load | 5A 第 3–4、6 节 |
| `what_a_savepoint_keeps` | Explain how a CDC pipeline moves from a snapshot to incremental changes, and what a checkpoint or a savepoint saves. | Flink CDC and the Doris connector | 5B 第 2–5 节 |
| `where_a_new_job_starts` | Choose where a new continuous job starts reading: from the beginning, from now, or from a saved position. | Where a new job starts | 5A `OFFSET_BEGINNING`；5B `scan.startup.mode` = `initial`、从 savepoint 恢复 |
| `deletes_reach_doris` | Explain how a delete in the source database reaches a Unique Key table in Doris. | Flink CDC and the Doris connector | 5B 第 3 节 MySQL 删除 920002 |
| `files_found_by_name` | Explain how a continuous file job finds new files, and why a file that arrives with an older name is skipped. | New files in object storage | —（只在阅读材料中，没有 Lab） |

## Module 6: Data Quality and Schema Validation

| 题目 id | 学习目标 | 讲义 | Lab 6 中的证据 |
| --- | --- | --- | --- |
| `type_check_or_business_rule` | Distinguish type checks from business quality rules. | 6.1 | 第 2 节 999999 能转成整数仍被拒 |
| `stage_raw_text_with_input_id` | Stage raw input as text so that every rejected row can be traced to its source. | 6.2 | 第 1 节 Stream Load 13 行全部进入 `orders_raw` |
| `route_with_independent_dimension` | Route accepted and rejected rows with explicit rules and an independent customer dimension. | 6.3 | 第 2 节 10 + 3，按 `input_id` 追溯 |
| `totals_are_not_details` | Check input coverage, uniqueness, amounts, and row-by-row results together. | 6.4 | 第 3 节质量报告；第二个反例总数不变 |
| `break_the_checks_on_purpose` | Prove that a check works by making it fail on a known error. | 6.5 | 第 3 节两个反例与恢复 |
| `schema_change_effects` | Check what a schema change affects before and after you make it. | 6.6 | —（ext67 第 1 节在副本上加列、改类型） |

本课只保留这一道「总数一致不代表明细正确」的题（DW-16：原来 quiz1 Q5、quiz3 Q5、quiz4 Q5、quiz6 Q4 都考它），其余三处换成 MySQL 协议（M1）、计划与实测（M3）、S3 表函数（M4）；Group Commit、CDC 起始位点、Schema Change 分别在 quiz5、选读测验、quiz6 中。

## Module 7: Data Updates, Deletion, and Event Replay

| 题目 id | 学习目标 | 讲义 | Lab 7 中的证据 |
| --- | --- | --- | --- |
| `three_grains` | Distinguish the keys and purposes of current state, event history, and raw deliveries. | 7.1 | 第 1 节三张表；第 3 节 11 / 18 / 19 |
| `versions_decide` | Use business versions to resolve duplicate and out-of-order events. | 7.2 | 开头的小例子；第 3 节 900001 仍是 DELIVERED v4；练习 7 |
| `partial_update` | Distinguish partial column updates from full-row writes that omit fields. | 7.3 | 第 4 节 CANCELLED、金额和地区不变 |
| `kinds_of_deletion` | Distinguish soft deletion, SQL DELETE, a load's delete mark, and physical reclamation. | 7.4 | 第 5 节软删除与 DELETE（导入删除标记在 ext67 第 2 节） |
| `replay_after_interruption` | Recover from an interrupted multi-table write by replaying the whole batch. | 7.5 | 第 2–3 节中断后重放两次 |
| `reconcile_with_ledger` | Reconcile current state with independent payment, refund, and shipment records. | 7.6 | 第 3 节之后的业务流水核对；练习 6（900003 的历史与流水） |
