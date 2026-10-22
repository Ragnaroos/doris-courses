# Real-time Analytics 课程维护

学员入口：[课程首页](../../doris-course/01-real-time-analytics/README.md)。
本目录只供课程作者和评审者使用，不是学员的学习步骤。

| 文件 | 用途 |
| --- | --- |
| [quiz-alignment.md](quiz-alignment.md) | 每道测验题对应的学习目标、讲义小节和 Lab 中的证据（RT-12）。改题目、讲义或 Lab 时同步更新 |
| [former-readmes/](former-readmes/) | 课程目录中原来的开发文档（RT-07 移来，只供查阅）：`level1/README.md`（Level 1 的术语约定，已收入 plan-doc 的 conventions.md 第 10 节）、`level2/README.md` 和 `level3/README.md`（中文写作大纲、ClickHouse 对照、开发验证记录）、`level2/quiz_alignment.md`（旧的 Level 2 对照，已过时）、`environments/single-node/README.md`。学员需要的运行信息已并入课程 README（Lab 依赖、端口与 Docker 对象、清理、排错）和各 Lab |

## 维护要点

- 数据的特征写在 M1 讲义的「What the data looks like」和课程 README 的 Dataset 中（2026-10-22 在开发沙箱中查）：26 天（2019-12-01 至 15、2020-03-01 至 11）；每类事件各占一段日子：浏览 13 天（2019-12-05 至 11、2020-03-03 至 08），加购 15 天（2019-12-01 至 04、12-12 至 15、2020-03-01 至 03、03-08 至 11），购买 7 天（2019-12-01 至 04、2020-03-01 至 03），只有 2020-03-03 三类都有；8 个合成 region 各约 127 万事件，1,580,057 个用户，204,231 个商品。很多期望值依赖这些特征：Lab 5 第 7 节 3/4–3/8 收入为 0、Lab 4 练习和 Lab 8、Lab 10 的 2020-03-01 只有加购和购买（75,259 行）、Lab 1 练习的 7 天、M4 4.7 的 region 分桶。按天算浏览到购买的比例在这份数据上没有意义（M1 写明）。换数据时这些地方都要改。
- 依赖 Doris 4.1.3 行为、升级后要重新核对的地方（B7、B8 在 4.1.3 上实测或读源码 `7126cf65d96`）：
  - S3 TVF 的 `"s3.credentials_provider_type" = "ANONYMOUS"` 和两个超时（F-19）；花括号范围去掉前导零，所以 Lab 用 `*`（conventions.md 第 5 节）。
  - 导入或重启后 `SHOW PARTITIONS` / `SHOW TABLETS` 的计数要等 BE 报告（`lab.wait_for_tablet_rows()`）。
  - 动态分区调度器发现间隔变化会提前醒来（F-17），Lab 10 第 3 节的加速路径依赖它。
  - RANDOM 分桶的适用范围（F-03，M4 4.7）。
  - 部分列更新：带列名的 `INSERT` 要 `enable_unique_key_partial_update = true`，Stream Load 用 `partial_columns:true`；新 key 默认 `partial_update_new_key_behavior = APPEND`，ERROR 时报 E-7003 "Can't append new rows in partial update"（M7 7.3、Lab 7 练习）。
  - `MERGE INTO` 只能用于 MoW 的 Unique Key 表，其他表报 "merge into command only support MOW unique key olapTable"（M7 7.5）。
  - Lab 8 第 7 节：手动 `ANALYZE ... WITH SYNC` 是 FULL，没有 hot values，`event_type` 的 ndv 为 2，Join 估计约 37,400 行，实际 17,798 行；后台的自动 ANALYZE（SAMPLE，带 hot values）给出的估计约 17,957，所以这一节在 EXPLAIN 之前先 ANALYZE。计划末尾的 "planned with unknown column statistics" 来自 Unique Key 表 `m08_products` 的隐藏删除标记列（只读 `m08_events` 时没有）。
  - LZ4F、ZSTD 的说法照官网 Data Compression 页（F-02），默认 ZSTD 不写起始版本（F-01）；Auto Range Partition 的 `partition.retention_count`（F-07）。
- 每个 Lab 最后的练习（RT-14）：期望值都是实测值，换数据、换版本后要重跑参考答案（Run All 会执行它们）。参考答案只改练习自己的表，用完即删。
- 测验：objective 必须是讲义学习目标的原文，`tests/test_lessons.py` 检查；改目标时同时改测验和测验 notebook 中列出的目标（`quiz-purpose` 单元）。加题、改 id 会改变显示顺序，改完运行 `check_quiz_balance.py --strict`。
- Lab 9 第一次运行时 S3 切片要读约 59 MB，整本的耗时主要看网络：B8 的干净环境中 263 秒（切片 10.5 秒），B7 经约 60 KB/s 的代理 18 分钟（切片 765 秒）。
