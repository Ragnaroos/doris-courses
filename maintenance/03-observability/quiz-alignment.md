# 测验题与讲义、Lab 的对应关系

每道题考一个学习目标（`objective` 与讲义的学习目标原文相同，`tests/test_lessons.py` 检查）。「讲义」是给出概念的小节，「Lab」是学员亲手得到证据的地方。Level 2（Module 4–8）还没有讲义，B4 补齐后在这里续表。

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
