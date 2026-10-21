# Observability 课程维护

学员入口：[课程首页](../../doris-course/03-observability/README.md)。
本目录只供课程作者和评审者使用，不是学员的学习步骤。

| 文件 | 用途 |
| --- | --- |
| [quiz-alignment.md](quiz-alignment.md) | 每道测验题对应的学习目标、讲义小节和 Lab 中的证据（OB-08、OB-17）。改题目、讲义或 Lab 时同步更新 |
| [dog-stack.md](dog-stack.md) | `environments/dog-stack/` 中各 override 文件的作用，改上游提交 `STACK_COMMIT` 后的核对方法，Litefuse 与 private endpoint（OB-15 从课程目录移来；学员需要的部分已并入课程 README） |

## 维护要点

- 全课的故障主线：demo 的 feature flag `paymentFailure` 设为 `50%`（Lab 1 第 5 节由学员在 flag 页面打开）。flag 页面改的是上游检出中的 `doris-opentelemetry-demo/src/flagd/demo.flagd.json`；`lab.teardown()` 用 `git checkout` 恢复，`teardown(keep_data=True)` 不动它。Level 1 的期望值（失败订单约占一半、每分钟 1–2 单失败、访问日志的 HTTP 500、payment span 的异常消息）都建立在这个 flag 上，换故障时要重写 Lab 1–3 和讲义的对应部分。
- Doris App 1.0.5 的 Discover 和 Traces 用浏览器本地时间拼时间条件，表里存的是 UTC：本机不在 UTC 时，相对时间范围查不到最新的行。Lab 3 让 notebook 打印 UTC 的绝对时间范围。插件升级后先确认这个行为是否还在，再决定是否改正文（讲义 3.2 节、Lab 3 第 2 节、quiz03 的 `fix_empty_time_range`）。
- Lab 3 的网页步骤按 Grafana 11.4.0 写。改正文或升级 Grafana 后，用无头 Chrome 按正文逐步走一遍（做法见 plan-doc 的 handoff，脚本按 Lab 3 的节号打印每一步看到的结果）。
- 讲义中引用的数字（失败订单的 span 数、各服务的 error span 数、主机 CPU 的忙碌比例等）来自 2026-10-20 在 Doris 4.1.3、demo 2.0.2 上的实测；升级 demo 或上游 DOG 栈后要重新核对。
- Level 2 也建立在这个 flag 上（B4）：Lab 4 的汇总和告警、Lab 5–7 的故障时间窗（从第一单失败开始）都要求 flag 开过；Lab 8 第 11 节由学员在 flag 页面把它关掉，故事到此结束。之后重跑 Lab 8 第 10 节会等不到 Alerting（等待单元的提示说 flag 要是 50%）；Lab 4–7 仍能用之前的失败数据（B4 干净环境关 flag 后重跑 Lab 4、5、7 通过），只是故障时间窗中失败的比例会越来越低。
- 讲义和 Lab 中依赖 Doris 4.1.3 行为、升级后要重新核对的地方（B4 在 4.1.3 上实测或读源码 `7126cf65d96`）：`UTC_DATE()` 在规划时不折叠，不能做分区裁剪（讲义 5.3）；BUCKETS AUTO 估算低于上一分区一半时沿用上一分区的桶数（`DynamicPartitionScheduler.checkAndFixAutoBucketCalcNumIsValid`，讲义 5.7、Lab 5 第 2 节、quiz05）；同步物化视图的列名不能与基表或其他视图的列重名，`CREATE MATERIALIZED VIEW IF NOT EXISTS` 不跳过已有视图（Lab 6 第 4 节先 DROP）；不走索引的 `MATCH_PHRASE` 和 `LIKE` 过滤掉的行记在 `RowsExprPredFiltered`（`SegmentIterator::_execute_common_expr`，`SCAN_FILTER_COUNTERS`）；`ALTER TABLE ... SET ("compression" = ...)` 报 Unknown table property；`group_commit_mode` 表属性自 4.1 起有。
- Lab 5 的分桶倾斜（按 `service_name` 分 10 桶时最大的 tablet 约 38%，有一两个几乎为空）取决于各服务名的哈希值和 demo 的流量构成，换 demo 版本后要重新跑一遍再改数字（讲义 5.6）。RANDOM 表每个 tablet 的占比在数据少时是 7%–13%，数据多了才接近 10%：4.1.3 的导入按批轮流写各个 tablet（`VTabletFinder` 的 `FIND_TABLET_EVERY_BATCH`，起点由 FE 的 `TabletLoadIndexRecorderMgr` 按分区轮转）。
- Level 2 的 Expected 按数据最少的情况写（B4 干净环境：Lab 1 之后直接做 Lab 2–8，Lab 4 开始时只有 5 单）：数量写成「tens of thousands or more」这类下限，失败比例在单数少时加了「chance can put the share far from half」。改正文时用干净环境的输出再核对一遍。
- Lab 8 第 10 节用 Grafana 的 provisioning API 建规则：带固定 uid 的规则第一次要先 POST `/api/v1/provisioning/alert-rules`，组的 PUT 只更新已有 uid 的规则（否则 500 "could not find alert rule"），`lab.provision_alert_rule_group()` 已处理；`X-Disable-Provenance: true` 让规则在网页中可改。升级 Grafana 后先核对这两点。
- demo 的 jaeger（`/tmp`）、kafka（3 个）、prometheus（`/prometheus`）镜像声明了 demo 的 Compose 文件没有挂载的卷，Docker 为它们建匿名卷。下次启动不会复用这些卷，所以 `stop_demo()` 和 `teardown()` 删除 demo 时都加 `--volumes`（OB-20），`keep_data=True` 也一样。之前不带 `--volumes`，demo 每启动一次就留下 5 个卷。检查清理后有没有残留时，按名字过滤查不到匿名卷，要用 `docker volume ls -f dangling=true` 按创建时间比对；升级 demo 后照此再查一次。
- Linux（OB-21）：课程只在 macOS 的 Docker Desktop 上跑过。下面是 2026-10-21 读代码、并在本机模拟后核对过的情况：
  - FE 的日志目录以 bind mount 挂到 `.runtime/doris-logs/fe`。FE 以 root 写日志，还会建 `profile/` 子目录。在 Linux 的 Docker Engine 上，这些文件在宿主机上也属于 root，学员不用 sudo 就删不掉 `.runtime/`。Docker Desktop 把属主映射成当前用户，所以 Mac 上看不到这个问题。
  - 修正：`teardown()` 第 6 步在删除 DOG 之后，用 Doris 镜像执行 `chown -R --reference=/logs /logs`，把文件交还给目录的属主（`prepare_environment()` 以学员身份建的这个目录）。用 `--reference` 而不是学员的 uid，是因为在 rootless Docker 下这个目录在容器里显示为 root 的，用 `--reference` 不会把属主改错。
  - 验证：在 Docker Desktop 的命名卷上模拟过。命名卷放在虚拟机的 ext4 上，与 Linux 一样检查属主。修正前学员对 `profile/` 没有写权限，修正后所有文件都归学员。
  - 容器的打开文件数：Docker Engine 29（containerd 2.1.5 起）在 Linux 上把容器默认的 `ulimit -n` 设为 1024，Docker Desktop 是 1048576。用 `--ulimit nofile=1024:524288` 起 Doris 实测，BE、FE 进程都是 524288：内嵌的 JVM 把软上限提到硬上限，`start_be.sh` 只在 macOS 上关掉 MaxFDLimit。BE 空闲时已打开 764 个文件。
  - `vm.max_map_count`：Doris 要求至少 2000000，镜像设了 `SKIP_CHECK_ULIMIT=true`，启动时不检查。Docker Desktop 的虚拟机是 262144；Linux 默认 65530（Ubuntu 22.04、Debian 12），Ubuntu 24.04 和 Fedora 39 起是 1048576。BE 空闲时有 3,959 个映射，没有在课程的负载下测过。有人在 Linux 上跑课程时，先看这一项：BE 日志中有没有 mmap 失败。
  - 已核实没有问题：
    - 34 个镜像都同时发布了 linux/amd64 和 linux/arm64（用 `docker buildx imagetools inspect` 查过）。
    - Grafana 的 Doris App 只有前端，没有按架构编译的程序。
    - flagd-ui 以 root 运行，能写 flag 文件。
    - Module 2 的日志 Collector 用 `--user` 以学员的 uid 运行。
  - 没有考虑的环境：
    - rootless Docker 和 Podman：demo 的 Collector 挂载 `/var/run/docker.sock`。
    - 开启 SELinux 的系统：bind mount 都没有加 `:z`。
    - M4 Mac 上的 Linux 虚拟机：`.env.arm64` 只在 Darwin 上添加。
- 网页步骤的核对脚本（无头 Chrome）：Lab 1 第 5 节和 Lab 8 第 11 节的 flag 页面、Lab 3 第 2–8 节、Lab 8 第 4–6 节，用法见 plan-doc 的 handoff。
