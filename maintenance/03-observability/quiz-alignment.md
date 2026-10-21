# 测验题与讲义、Lab 的对应关系

每道题考一个学习目标（`objective` 与讲义的学习目标原文相同，`tests/test_lessons.py` 检查）。「讲义」是给出概念的小节，「Lab」是学员亲手得到证据的地方。Level 2（Module 4–8）的讲义和测验在 B4 中写成。

## Module 1: Observability Foundations in the DOG Stack

| 题目 id | 学习目标 | 讲义 | Lab 1 中的证据 |
| --- | --- | --- | --- |
| `choose_signal_for_failing_step` | Choose logs, metrics, or traces for an operational question. | 1.2 Three kinds of telemetry | 第 2 节三类信号分别落库；第 6 节练习按服务统计 error span |
| `join_spans_by_their_ids` | Explain how the trace ID and the parent span ID join the spans of one request. | 1.3 Inside a trace | 第 5 节失败订单的 checkout span；Lab 2 第 5 节按 trace ID 找到一单的全部 span |
| `assign_dog_responsibilities` | Assign collection, storage, and visualization to the parts of the DOG stack. | 1.4 The DOG stack and the demo | 第 1 节启动四个容器，第 4 节打开 Grafana |
| `follow_demo_telemetry_path` | Trace the path that the demo's telemetry takes from a service to a table in Doris. | 1.4（数据路径图和 5 步） | 第 2 节 demo 的数据经两个 Collector 到达三张表 |
| `prove_demo_telemetry_reached_doris` | Judge what evidence shows that telemetry reached Doris. | 1.5 Evidence that telemetry arrived | 第 2 节「Check that the telemetry reached Doris」按最近 5 分钟计数 |
| `confirm_payment_failure` | Start a failure with a feature flag and confirm it in the telemetry. | 1.6 The incident of this course | 第 5 节打开 flag、`wait_for_feature_flag`、等第一单失败、每分钟订单 |

## Module 2: Ingesting Observability Data

| 题目 id | 学习目标 | 讲义 | Lab 2 中的证据 |
| --- | --- | --- | --- |
| `name_the_pipeline_parts` | Describe what the receivers, processors, exporters, and extensions of a Collector pipeline do. | 2.1、2.3 | 第 1 节 `otel_for_logs.yaml` 的各部分，FE 日志行的 `service_name = doris-fe` |
| `distinguish_pull_and_push` | Choose a receiver for a source that pushes its telemetry and for one that must be pulled. | 2.2 Getting telemetry in | 第 2 节 prometheus 抓取 FE / BE；第 3、4 节 OTLP 接收 Python 的 span |
| `predict_batch_export_timing` | Predict when a batch processor sends its data, and what a sending queue and retries guarantee. | 2.3、2.4 | 第 4 节 span 约 20 秒内出现（batch timeout 10 秒）；第 1 节日志批量 1 万条 |
| `table_settings_apply_at_creation` | Explain which settings of the Doris exporter apply only when it creates a table. | 2.4「Creating the tables」 | 第 1 节「Where the table settings come from」（`SHOW DYNAMIC PARTITION TABLES`） |
| `judge_flush_evidence` | Judge what a successful export call shows and what only a query in Doris shows. | 2.6 What proves that a record arrived | 第 4 节 `force_flush()` 后按 trace ID 查询 |
| `explain_missing_payment_logs` | Find the evidence of one request in each signal, and tell which services send which signals. | 2.7 One failed order, three signals | 第 5 节一单失败订单在三张表中的证据，没有 payment、checkout 的日志 |

## Module 3: Visualizing Observability Data

| 题目 id | 学习目标 | 讲义 | Lab 3 中的证据 |
| --- | --- | --- | --- |
| `search_failed_checkouts` | Search logs in the Discover page of the Doris App with Lucene and with SQL conditions. | 3.3 Searching logs | 第 4 节两个短语的 Lucene 和 SQL 搜索、`TOKENIZE` |
| `explain_quiet_error_search` | Explain why a search by severity misses failures that a service does not log as errors. | 3.4 When failures are not error logs | 第 3 节 `severity_number:>=17` 只有 FE 的错误 |
| `fix_empty_time_range` | Set a time range that matches how Doris stores time. | 3.2 Time ranges and time zones | 第 2 节打印并输入 UTC 的绝对时间范围 |
| `find_error_origin` | Follow a trace from a log line to the span where an error starts. | 3.5 Reading a trace | 第 5 节 trace 面板中 payment 的 Charge span 和它的 `error_message` |
| `measure_host_cpu` | Measure a host's CPU from per-core, per-state samples. | 3.6 Measuring a host's CPU | 第 7 节展开一行看 `cpu`、`state`，按分钟算忙碌比例 |
| `use_time_macros` | Build dashboard panels from SQL with Grafana's time macros. | 3.7 Dashboards | 第 8 节两个面板和 `lab.grafana_dashboard()` 读回 |

## Module 4: Table Models for Observability Data

| 题目 id | 学习目标 | 讲义 | Lab 4 中的证据 |
| --- | --- | --- | --- |
| `choose_model_for_recount` | Choose DUPLICATE, AGGREGATE, or UNIQUE from what must happen to rows that share a key. | 4.1、4.5、4.6 | 第 4 节 exporter 的 `otel_traces_graph`（UNIQUE）和作业重算上一分钟 |
| `keep_spans_with_one_key` | Explain why raw logs, spans, and metric points belong in DUPLICATE tables. | 4.2 DUPLICATE: keep every event | 第 2 节 8 张表的模型，共用 key 的 span（`different_spans` 等于行数） |
| `choose_summary_grain` | Choose the key of an AGGREGATE table at the grain of the questions that it answers. | 4.3 AGGREGATE: keep the counts | 第 3 节 `requests_per_minute` 的 key、按 `end_time` 所在分钟计数 |
| `predict_repeated_load` | Predict the rows of an AGGREGATE table after overlapping or repeated loads. | 4.3（4 + 7 = 11，重复导入会重复计数） | 第 3 节两批导入后边界分钟的行变大、与 `otel_traces` 的 join 核对 |
| `stable_alert_identity` | Build an alert identity that stays the same for every occurrence of an error. | 4.4「A stable identity」 | 第 4 节按告警标识分组，`normalized_message`（recommendation 的流每 10 分钟一次） |
| `read_one_alert_row` | Predict which row a UNIQUE table keeps, and what one row says about occurrences. | 4.4「The row loaded last wins」「One row is not one occurrence」 | 第 4 节再次导入仍是同样的行数、resolved 后再导入变回 open 的说明、sequence 列 |

## Module 5: Partitioning and Bucketing for Observability Data

| 题目 id | 学习目标 | 讲义 | Lab 5 中的证据 |
| --- | --- | --- | --- |
| `count_tablets` | Explain how Doris divides a table into partitions, buckets, and tablets. | 5.1 Partitions, buckets, and tablets | 第 2 节 `SHOW PARTITIONS` 的 5 个分区、10 个桶；第 4 节每个分区的 10 个 tablet |
| `predict_partition_pruning` | Predict which partitions a query reads from its filter on the partition column. | 5.3 Partition pruning | 第 3 节三个计划：`1/5`、昨天没有扫描、不带时间条件也是 `1/5` |
| `predict_dynamic_partitions` | Predict which partitions dynamic partitioning creates and drops. | 5.2 Time partitions for telemetry | 第 2 节 `SHOW DYNAMIC PARTITION TABLES` 的 start、end；创建时的 3 个历史分区 |
| `choose_partitioning` | Choose a partition grain and a partitioning method for a retention period and a query pattern. | 5.4、5.5 | 第 2 节按天分区与保留；第 5 节 AUTO PARTITION 和 `partition.retention_count` |
| `choose_bucketing` | Choose HASH or RANDOM bucketing from a table's filters and the distribution of its data. | 5.6 HASH or RANDOM buckets | 第 4 节 RANDOM 均匀、按服务 HASH 读 1/10 但倾斜；第 6 节练习按 trace ID 分桶 |
| `explain_auto_buckets` | Explain how Doris sets the number of buckets of each partition. | 5.7 How many buckets | 第 2 节 `Buckets` 都是 10 和 Expected 的解释 |

## Module 6: Table Properties, Materialized Views, and Indexes

| 题目 id | 学习目标 | 讲义 | Lab 6 中的证据 |
| --- | --- | --- | --- |
| `read_missing_compression` | Read the storage properties of a table from `SHOW CREATE TABLE`, including the ones that it leaves out. | 6.1、6.3 | 第 2 节 `lab.show_create_table("otel_logs")` 没有 compression |
| `fair_compression_test` | Design a comparison of compression algorithms that changes only the algorithm. | 6.3 Compression | 第 5 节两张只差 compression 的表、等 BE 报告大小、LZ4 约 1.6 倍 |
| `match_phrase_tokens` | Explain how the inverted index of a text column answers `MATCH_ANY`, `MATCH_ALL`, and `MATCH_PHRASE`. | 6.4 Inverted indexes for log search | 第 3 节两个短语的搜索；Module 3 Lab 的 `TOKENIZE` |
| `read_scan_counters` | Interpret the row counters of a Query Profile without claiming more than they show. | 6.5 Measuring a search with a Query Profile | 第 3 节有无索引两次 Profile 的五个计数 |
| `view_lifecycle` | Explain how a synchronous materialized view is built, kept up to date, and stored. | 6.6 Synchronous materialized views | 第 4 节等构建作业 FINISHED、`DESC otel_traces ALL` 的 AGG_KEYS 索引 |
| `predict_view_rewrite` | Predict whether Doris can answer a query from a materialized view. | 6.7 When Doris uses a view | 第 4 节命中与三种不能用的计划及原因；第 6 节练习 |

## Module 7: Trace Analysis and Litefuse

| 题目 id | 学习目标 | 讲义 | Lab 7 中的证据 |
| --- | --- | --- | --- |
| `break_down_by_operation` | Compute the failure rate and the latency of each operation from server spans. | 7.1 From one trace to all of them | 第 2 节各操作的失败率和 P50 / P99（ingress 0.0%） |
| `read_p99` | Interpret latency percentiles without claiming more than they show. | 7.2 Percentiles | 第 2 节 P50 / P99；失败与成功订单的耗时 |
| `find_failure_start` | Find with SQL the service in which each failure of many traces starts. | 7.3 Where failures start | 第 2 节 `NOT EXISTS` 的查询只剩 payment |
| `rolling_share` | Use a window function to compute a value for each row from the rows related to it. | 7.4 Window functions | 第 2 节最近十单的失败比例（`ROWS BETWEEN 9 PRECEDING AND CURRENT ROW`） |
| `llm_trace_contents` | Explain what the trace of an LLM application records that service spans do not. | 7.5 Traces of an LLM application | 第 5–7 节 generation 的 prompt、模型、token、成本，Litefuse 网页 |
| `locate_litefuse_traces` | Find an LLM application's traces in Doris, and query them with SQL. | 7.6 Litefuse on Doris | 第 6 节 `litefuse.spans_llm_app`；第 9 节练习按用户统计 |

## Module 8: Alerting with Grafana

| 题目 id | 学习目标 | 讲义 | Lab 8 中的证据 |
| --- | --- | --- | --- |
| `choose_alert_expression` | Write an alert query that measures what the alert is about. | 8.2 The alert query | 第 2–3 节来源、一个核的一次采样、按状态统计，告警查询 |
| `predict_pending_states` | Predict how an alert instance moves between Normal, Pending, and Alerting, and back. | 8.3 Rules, evaluation, and states | 第 7 节 Normal → Pending → Alerting 和恢复；第 10–11 节失败订单的告警 |
| `find_the_routing_problem` | Separate what a contact point, a notification policy, and an alert rule each decide. | 8.4 Contact points and notification policies | 第 4 节联系点和 Test、第 5 节子策略；第 10 节新规则带同样的标签 |
| `preserve_host_dimension` | Keep the labels that an alert needs to be acted on. | 8.2「One row per instance」、8.4 | 第 6 节 `GROUP BY host`、邮件中的 `host` |
| `distinguish_missing_data_from_low_value` | Decide how a rule treats missing data, and detect a source that stops reporting. | 8.5 When data stops | 第 8 节停掉 Collector 后的 NoData；第 12 节练习；失败订单规则的 `noDataState: OK` |
| `provision_rule_with_uid` | Keep alert rules as code, and send them to Grafana. | 8.6 Rules as code | 第 9 节导出 YAML；第 10 节 `lab.provision_alert_rule_group()`（先 POST 再 PUT） |
