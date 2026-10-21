# 测验题与讲义、Lab 的对应关系

每道题考一个学习目标（`objective` 与讲义「Learning objectives」的原文相同，`tests/test_lessons.py` 检查，选读材料 `optional05_continuous_ingestion.md` 也一样）。「讲义」是给出概念的小节，「Lab」是学员亲手得到证据的地方。Level 1 在 B5 写成，Level 2–3（Module 8–14）在 B6 写成。

答案分布由 `tools/check_quiz_balance.py --strict doris-course/02-data-warehousing` 检查（CI 中也运行）。B6 完成时：Level 1 共 48 题，正确项最长 25%，同一位置最多 27%（各位置 11 / 12 / 13 / 12）；Level 2 共 24 题，29%、29%（6 / 5 / 6 / 7）；Level 3 共 18 题，17%、28%（4 / 5 / 5 / 4）。Level 2–3 的错误选项不用 always、never、guarantees、proves 这类绝对化的词（B6 最后一次修改）。

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

## Module 8: Views and Materialized Views

| 题目 id | 学习目标 | 讲义 | Lab 8 中的证据 |
| --- | --- | --- | --- |
| `view_or_stored_result` | Distinguish a regular view's saved query from a materialized view's stored result. | 8.2、8.3 | 第 5 节第二单进来后，普通视图 2 单 150.00，手动刷新的物化视图仍是 1 单 100.00 |
| `refresh_scope` | Choose a refresh trigger and scope from the freshness that consumers need and the cost of a refresh. | 8.4 | 第 7 节事实表一天的新订单只重新发布一个分区（PARTIAL）；第 8 节维表改地区后两个分区都重新发布（COMPLETE） |
| `check_after_create` | Check a materialized view's state and rows instead of trusting a successful CREATE. | 8.3 | 第 3 节 `State` NORMAL、`RefreshState` SUCCESS、`SyncWithBaseTables` 1，存储的两行等于定义 |
| `explain_rewrite` | Read in EXPLAIN whether a query was rewritten to use a materialized view, and why it was not. | 8.5 | 第 4 节三个计划：按日被选中；按日和地区 `View dimensions doesn't not cover the query dimensions`；只看 1 月 1 日 `Rewrite compensate predicate by view fail`；练习 9 |
| `stable_contract` | Keep a published view's names and meanings stable when its implementation changes. | 8.6 | 第 4 节查询仍写 `orders_view_l2`，由改写读物化视图；练习 9 新粒度另建 `orders_region_mv_l2` |
| `worth_storing` | Decide whether repeated queries justify storing and maintaining a result. | 8.3 末段 | —（判断题；第 6 节同步物化视图把代价移到写入，Lab 10 第 8 节量出存储省下的扫描） |

扩展题：`refresh_scope` 考分区刷新的范围（事实表的一天对一个分区，维表的变化对全部分区），是 B6 的新内容（DW-16）。

## Module 9: Warehouse Modeling and Joins

| 题目 id | 学习目标 | 讲义 | Lab 9 中的证据 |
| --- | --- | --- | --- |
| `declare_grain` | State the grain of a fact table and a dimension table before joining them. | 9.2 | 第 1 节事实表 11 行 11 单，维表 663 个客户各一行 |
| `model_for_source` | Choose a table model and key from whether a source appends records or replaces current state. | 9.2 的表模型表 | 第 1 节维表 `UNIQUE KEY(customer_id)`；第 6 节 DWD 按业务键和版本 |
| `three_join_checks` | Check a join for lost and duplicated rows with row counts, distinct keys, and amounts. | 9.3、9.5 | 第 2 节 11 行、11 单、1510.00；第 4 节错误维表：左连接 12 / 11 / 1610.00，内连接 11 / 10 / 1410.00；练习 8 |
| `find_missing` | Find facts whose dimension row is missing with a left join or an anti-join. | 9.3 | 第 2 节反连接返回空表；第 4 节左连接有 1 个未匹配订单 |
| `read_join_plan` | Read a join's type and distribution in EXPLAIN without taking a plan for a measurement. | 9.4 | 第 3 节 `INNER JOIN` 与 `BROADCAST`，计划不是测量 |
| `layers_rebuild` | Keep raw deliveries, validated detail, and aggregates in separate layers that can be rebuilt. | 9.1、9.6 | 第 5–7 节：ODS 10 条订单投递、7 条支付投递；DWD 8 单 850.00；DWS / ADS 5 行、7 单 800.00 |

## Module 10: Metric Processing and Delivery

| 题目 id | 学习目标 | 讲义 | Lab 10 中的证据 |
| --- | --- | --- | --- |
| `metric_contract` | Define a metric's population, grain, measures, time rule, and ratio rule before writing its SQL. | 10.1 | 第 1 节指标契约表；第 4 节 132.00 与 133.33 |
| `rebuild_service` | Build a service table at a declared grain, and rebuild it instead of loading a batch twice. | 10.2 | 第 1 节服务表重建后 3 行、10 单 1310.00，只存和与计数 |
| `full_outer_reconcile` | Reconcile a service table with the detail through a full outer join. | 10.3 | 第 3 节去掉 1 月 2 日后，内连接两行都相等，全外连接多出服务表一侧为 `NULL` 的一行 |
| `window_grain` | Use window functions and conditional aggregation without changing the grain of a result. | 10.4 | 第 2 节条件求和；第 4 节 CTE 先按日，累计 1200.00 / 1310.00，`LAG` |
| `paid_gmv` | Tell paid GMV, order amount, and net collections apart, and keep each ratio's numerator and denominator. | 10.5 | 第 5 节 5 单 660.00；第 6 节退款 50.00、净收款 610.00、`cohort_conversion` 0.62500 |
| `distinct_and_proof` | Choose exact or approximate distinct counts, and verify an optimization with equal results and measured work. | 10.6 | 第 7 节精确 20,000 与 HLL 19,834；第 8 节结果相同的 32 行，Profile 读 100,000 行与 32 行 |

扩展题：`paid_gmv` 考支付 GMV、订单金额与净收款的区别（DW-16）；数字来自 `datasets/warehouse_case.json` 的 expected。

## Module 11: Interfaces and Boundaries for BI and AI Consumers

| 题目 id | 学习目标 | 讲义 | Lab 11 中的证据 |
| --- | --- | --- | --- |
| `semantic_view` | Design a semantic view with stable names, one declared grain, and measures whose meaning is written down. | 11.1 | 第 1 节 `bi_order_metrics_l2` 两天、四列 |
| `ratio_over_days` | Tell dimensions, additive measures, and ratios apart in a dashboard. | 11.1 | 第 1 节 `average_order_amount` 由当天的和计算；练习 7 按地区的视图是另一份契约 |
| `checks_fail_on_purpose` | Check an interface's rows, nulls, dates, and totals, and make its contract and freshness checks fail on purpose. | 11.2 | 第 3 节 2 天、0 个空值、10 单 1310.00；第 4 节缺列的副本和 1 月 9 日的新鲜度检查都失败 |
| `calendar_features` | Prepare feature inputs over a calendar without claiming anything about a model's accuracy. | 11.4 | 第 2 节 1 月 3 日 0 单、平均值 `NULL`、`zero_order_flag` 1 |
| `who_checks_what` | State what Doris guarantees and what a BI tool or an AI application must check itself. | 11.3 | —（概念题；选修第 6 节在 Superset 中追溯每个指标的 SQL） |
| `mcp_boundary` | Bound an AI tool's access to Doris with a separate MCP server and a read-only account scoped to published views. | 11.5 | —（只在讲义中，Lab 不启动 MCP Server；选修第 5 节的 Doris 账号只能读 `bi_paid_kpis_l2`） |

## Module 12: Publishing, Permissions, and Audit

| 题目 id | 学习目标 | 讲义 | Lab 12 中的证据 |
| --- | --- | --- | --- |
| `contract_first` | Write a consumer contract and choose the object to publish before granting any privilege. | 12.1 | 第 1 节记录身份、发布对象和角色基线 |
| `role_select` | Grant only the needed object privilege through a role, and tell read privileges from administrative ones. | 12.2 | 第 2 节 `SHOW ROLES` 只有 `TablePrivs` 中的 `Select_priv`；第 3 节普通用户读得到视图、读不到来源 |
| `kinds_of_evidence` | Tell what SHOW GRANTS, SHOW ROLES, a consumer's queries, a change record, and the audit table each prove. | 12.3 | 第 2 节变更记录；第 3 节以消费者身份查询；第 9 节审计表中的 EOF 与 ERR 1105 |
| `retire_one` | Retire access by revoking a membership or a role's privilege, and verify the effect as the consumer. | 12.4 | 第 3 节撤销角色后连库被拒；第 4 节先撤权限再删角色；练习 10（两个仪表盘共用一个角色） |
| `rollback_window` | Release a table with a validated cutover, and say when its rollback stops being safe. | 12.5 | 第 6 节暂停写入、对账、交换、回滚演练；再写一单后保留的旧表缺这一单（3 单 205.00 对 4 单 230.00） |
| `rows_columns` | Choose between table privileges, column privileges, a Row Policy, and masking for a restriction. | 12.6 | 第 7 节 Row Policy：EAST 6 单 830.00，WEST 5 单 680.00；第 8 节列权限：`paid_amount`、`SELECT *`、`COUNT(*)` 被拒 |

扩展题：`kinds_of_evidence` 考审计表与授权证据的区别（DW-16）：`SHOW GRANTS` 说明能做什么，审计表说明做了什么。

## Module 13: Storage and Lifecycle Management

| 题目 id | 学习目标 | 讲义 | Lab 13 中的证据 |
| --- | --- | --- | --- |
| `partition_key` | Choose partition boundaries that match a retention rule and the time that queries filter on. | 13.1 | 第 1 节按月分区；练习 9 从维护日期算出保留的第一个月 2025-02-01 |
| `tablet_count` | Explain how a row belongs to a partition, a tablet, a replica, a rowset, and a segment. | 13.2 | 第 2 节三个分区各一个 tablet、一个副本，`SHOW TABLETS` 每行一个副本 |
| `lagging_count` | Record before-and-after evidence of a maintenance change with SHOW PARTITIONS, SHOW TABLETS, and SHOW CREATE TABLE. | 13.3 | 第 2 节 `VisibleVersion` 2，`RowCount` 在 BE 汇报前为 -1 或 0 |
| `truncate_stages` | Tell query visibility, metadata changes, and reclaimed space apart, and say where compaction fits. | 13.4 | 第 3 节只有 1 月换了 `PartitionId`、`VisibleVersion` 1，剩 2 单 500.00 |
| `recover_by_id` | Recover a dropped or truncated partition from the recycle bin, and say when only a backup or an archive can help. | 13.5 | 第 4 节按名字恢复被拒，删掉替代分区后按 ID 恢复；第 5 节 `DROP` 后按名字恢复；选修第 6–8 节仓库备份与恢复 |
| `runbook` | Write a maintenance runbook with its scope, checks, evidence, and a recovery path tested beforehand. | 13.6 | 练习 9 先算出要删的 `p202411, p202412, p202501`，检查留下 13 单 |

## Module 14: Resource Isolation and Query Protection

| 题目 id | 学习目标 | 讲义 | Lab 14 中的证据 |
| --- | --- | --- | --- |
| `routing_order` | Explain the order in which Doris selects a query's Workload Group. | 14.1 | 第 1 节 root 的会话为空、默认 `normal`；第 6 节普通用户按账号默认组进入 `course_dashboard_l3` |
| `no_queue` | Predict from max_concurrency, max_queue_size, and queue_timeout whether a query runs, waits, or is rejected. | 14.2 | 第 4 节 A 运行、B 排队、C 被拒 `query waiting queue is full`；第 5 节 `query queue timeout` |
| `cpu_cgroup` | Explain where memory and CPU limits apply and what CPU enforcement requires. | 14.3 | 第 3 节沙箱没有 CPU cgroup，`max_cpu_percent` 不生效 |
| `route_and_bypass` | Route an account to a group with USAGE_PRIV and default_workload_group, and explain why bypass_workload_group is not an isolation boundary. | 14.4 | 第 3 节角色只有仪表盘组的 `Usage_priv`；第 4 节 E 绕过队列；第 6 节 H 被拒 |
| `block_before_run` | Tell query_timeout, Workload Policy, and SQL Block Rule apart by when and where they act. | 14.5 | 第 5 节 `query timeout`；第 7 节 `course_scan_guard_l3` 在执行前拒绝全表扫描 |
| `rollback_order` | Write a resource runbook with groups, routing, protection, observations, and a rollback in dependency order. | 14.6 | 第 8 节先查 Workload Policy，再撤权限、删角色、删组；练习 9 |
