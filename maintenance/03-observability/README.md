# Observability 课程维护

学员入口：[课程首页](../../doris-course/03-observability/README.md)。
本目录只供课程作者和评审者使用，不是学员的学习步骤。

| 文件 | 用途 |
| --- | --- |
| [quiz-alignment.md](quiz-alignment.md) | 每道测验题对应的学习目标、讲义小节和 Lab 中的证据（OB-08、OB-17）。改题目、讲义或 Lab 时同步更新 |

## 维护要点

- 全课的故障主线：demo 的 feature flag `paymentFailure` 设为 `50%`（Lab 1 第 5 节由学员在 flag 页面打开）。flag 页面改的是上游检出中的 `doris-opentelemetry-demo/src/flagd/demo.flagd.json`；`lab.teardown()` 用 `git checkout` 恢复，`teardown(keep_data=True)` 不动它。Level 1 的期望值（失败订单约占一半、每分钟 1–2 单失败、访问日志的 HTTP 500、payment span 的异常消息）都建立在这个 flag 上，换故障时要重写 Lab 1–3 和讲义的对应部分。
- Doris App 1.0.5 的 Discover 和 Traces 用浏览器本地时间拼时间条件，表里存的是 UTC：本机不在 UTC 时，相对时间范围查不到最新的行。Lab 3 让 notebook 打印 UTC 的绝对时间范围。插件升级后先确认这个行为是否还在，再决定是否改正文（讲义 3.2 节、Lab 3 第 2 节、quiz03 的 `fix_empty_time_range`）。
- Lab 3 的网页步骤按 Grafana 11.4.0 写。改正文或升级 Grafana 后，用无头 Chrome 按正文逐步走一遍（做法见 plan-doc 的 handoff，脚本按 Lab 3 的节号打印每一步看到的结果）。
- 讲义中引用的数字（失败订单的 span 数、各服务的 error span 数、主机 CPU 的忙碌比例等）来自 2026-10-20 在 Doris 4.1.3、demo 2.0.2 上的实测；升级 demo 或上游 DOG 栈后要重新核对。
