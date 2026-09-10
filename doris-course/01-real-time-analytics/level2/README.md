# Level 2

Level 2 延续 Level 1 创建的 `doris_course` Database 和 `events` baseline dataset，按照以下路径组织学习内容：

```text
设计 schema → 编写分析 SQL → 连接事实与维度 → 维护 current state
```

课程结构对应 ClickHouse Level 2 的 Modeling、Analyzing、Joining、Deleting and Updating 四个模块，但具体内容使用 Apache Doris 4.x 的数据类型、Table Model、Join execution strategy 和 Unique Key Merge-on-Write 机制。

## 模块 4：在 Apache Doris 中建模数据

### 模块目标

讲清楚如何把 source data 和 analytical workload 转换成适合 Doris 的 Table schema。

重点包括数据粒度、Table Model、Key columns、数据类型、`NULL`/default value，以及 Partition、Bucket 和 sort key 如何共同构成完整的数据模型。Module 2 解释这些机制如何工作，本模块进一步解决面对真实业务需求时应该如何选择。

ClickHouse Module 4 重点介绍数据类型、Nullable、default value 和 Partition；Doris 版本保留这些设计问题，但使用 Doris 自己的类型系统和 Table Model。

### 学习目标

完成本模块后，学员将能够：

- 从 source contract 和查询需求中确定一张表的 grain，即一行数据代表什么。
- 根据 repeated-key semantics，在 Duplicate Key、Unique Key 和 Aggregate Key model 之间进行选择。
- 为标识符、时间、金额、分类字段和半结构化字段选择合适的 Doris data type。
- 说明为什么金额通常使用 `DECIMAL`，而不是 `FLOAT` 或文本类型。
- 区分 `NULL`、`NOT NULL` 和 `DEFAULT` 所表达的数据语义，并说明它们对导入和查询的影响。
- 说明 Key columns 在三种 Table Model 中分别承担的排序、去重或聚合职责。
- 根据时间范围、数据生命周期、过滤模式和数据分布设计 Partition、Bucket 和 sort key。
- 识别过宽的 `VARCHAR`、运行时反复 `CAST`、不必要的 nullable column 和粒度混合等常见建模问题。
- 说明 ARRAY、MAP、STRUCT、JSON/VARIANT 等复杂类型适合解决什么问题，以及何时更应该使用普通 typed columns。

Doris 官方推荐的建表流程也是先确定 Table Model，再选择数据类型、Partition/Bucket 和索引；Table Model 创建后不能直接转换为另一种模型：

- [Apache Doris Table Design Guide](https://doris.apache.org/docs/dev/table-design/overview/)
- [Table Model Best Practices](https://doris.apache.org/docs/4.x/table-design/data-model/tips/)

### 模块 4 实验：设计 query-ready event model

基于 Level 1 的 `events` dataset 和一组明确的 analytical query requirements，完成一张面向后续分析的 Doris table：

- 阅读 dataset contract，确定 event table 的 grain。
- 检查 `event_time`、`event_id`、`user_id`、`event_type`、`region`、`product_id` 和 `revenue` 的业务含义。
- 为每个 column 选择 type、nullability 和 default value。
- 明确选择 Duplicate Key model，并解释为什么 event history 应保留每一条 original event row。
- 显式设计 sort key、time Partition 和 Bucket，避免依赖默认推断。
- 使用一份小型可控数据对比文本金额和 `DECIMAL` 金额：文本模型需要在查询时执行 `CAST`，typed model 可以直接执行 `SUM(revenue)`，非法金额应在 ingestion boundary 被发现，而不是留到分析查询中。
- 使用 `DESC`、`SHOW CREATE TABLE` 和简单 Query Profile 验证最终设计。
- 保留建模后的 table，供 Module 5 和 Module 6 使用。

实验重点不是再次验证 Partition pruning，而是让学员能够解释每一项 DDL decision 对应的业务要求。

## 模块 5：使用 Apache Doris 分析数据

### 模块目标

教会学员使用 Doris SQL 把 detail event data 转换为可解释的分析结果。

重点包括 filtering、scalar function、aggregate function、conditional aggregation、Common Table Expression（CTE）和 window function。学员不只是写出能够执行的 `SELECT`，还要理解不同 SQL operator 如何改变 result grain，以及如何构造可验证、可维护的分析查询。

### 学习目标

完成本模块后，学员将能够：

- 使用 `WHERE`、`GROUP BY`、`HAVING` 和 `ORDER BY` 构造基本分析查询。
- 使用日期时间、字符串、条件和数值 scalar function 转换业务字段。
- 使用 `COUNT`、`COUNT(DISTINCT ...)`、`SUM`、`MIN`、`MAX` 和 conditional aggregation 计算分析指标。
- 区分 `WHERE` 对 input rows 的过滤和 `HAVING` 对 aggregated groups 的过滤。
- 使用 CTE 将复杂查询拆分为命名清晰的中间 result set。
- 区分 aggregate function 和 window function：aggregate function 将多行折叠为较少的 grouped rows；window function 保留 result rows，并为每一行计算排名、累计值或前后行比较结果。
- 使用 `ROW_NUMBER`、`RANK`、`LAG` 和 `SUM() OVER (...)` 完成排名、趋势和累计分析。
- 为 window function 提供确定性的 `PARTITION BY` 和 `ORDER BY`。
- 根据 event sequence 说明 funnel analysis 的输入条件和结果含义。

Doris window function 在 `WHERE`、`JOIN` 和 `GROUP BY` 之后计算，并且不会像普通 aggregation 一样减少 result row 数量：

- [Window Functions Overview](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/window-functions/overview/)
- [Common Table Expressions](https://doris.apache.org/docs/4.x/query-data/cte/)

### 模块 5 实验：回答 event analytics business questions

继续使用 Module 4 的 modelled event table，以一组业务问题驱动 SQL 编写：

- 计算每天和每个 region 的 event count、active user count 与 purchase revenue。
- 使用 conditional aggregation，在一行结果中同时计算 view、cart 和 purchase 指标。
- 使用 `HAVING` 找出达到指定交易规模的 region 或 product。
- 使用 CTE 将“先按天聚合、再计算变化率”的查询拆成多个阶段。
- 使用 `RANK` 或 `ROW_NUMBER` 找出每个 region revenue 最高的 product。
- 使用 `LAG` 计算 daily revenue 与前一天的差值。
- 使用 `SUM() OVER (...)` 计算 cumulative revenue。
- 可选：使用 `WINDOW_FUNNEL` 分析 view → cart → purchase 的 event sequence。
- 每道任务都提供 expected row count 或关键 expected value，帮助学员验证 SQL semantics，而不是只判断 statement 是否成功。

## 模块 6：在 Apache Doris 中连接数据

### 模块目标

讲清楚 Join 的 logical semantics，以及 Doris 在 MPP execution architecture 中如何执行 Join。

学员需要先根据业务关系选择正确的 Join type，再理解 FE 如何根据 table statistics、Join condition 和 data distribution 创建并优化 distributed query plan，BE nodes 如何执行 assigned plan fragments，以及 Broadcast、Partition Shuffle、Bucket Shuffle 和 Colocate 分别会产生什么 data movement。

ClickHouse Module 6 通过不同 Join algorithm 和 Dictionary lookup 比较执行效果；Doris 版本重点使用 Doris optimizer、Shuffle strategy 和 colocated data distribution，不引入 ClickHouse Dictionary。

### 学习目标

完成本模块后，学员将能够：

- 根据是否需要保留 unmatched rows，在 `INNER JOIN` 和 `LEFT OUTER JOIN` 之间进行选择。
- 使用 Semi Join 和 Anti Join 表达“是否存在匹配记录”，避免不必要地返回右表 columns。
- 识别 one-to-one、one-to-many 和 many-to-many relationship，并预测 Join 后的 result grain。
- 解释 duplicate Join keys 为什么可能放大 result row count。
- 说明 Hash Join 的 build side 和 probe side 各自承担的职责。
- 区分 Doris 的主要 Join data-distribution strategy：Broadcast Join、Partition Shuffle Join、Bucket Shuffle Join 和 Colocate Join。
- 说明 small dimension table 为什么通常适合作为 Broadcast side，以及 large-to-large Join 为什么通常需要 Shuffle。
- 使用 `EXPLAIN` 识别 Join type、Join condition、build/probe relationship 和 data-distribution strategy。
- 理解 optimizer 通常会自动选择 Join order 和 distribution strategy，只在有运行证据时才考虑使用 hint。

Doris 官方文档将 Broadcast、Partition Shuffle、Bucket Shuffle 和 Colocate 定义为四种主要 Join distribution strategy；对数据布局的要求越严格，潜在 network transfer 通常越少：

- [Doris Joins](https://doris.apache.org/docs/4.x/query-data/join/)
- [Adjusting Join Shuffle Mode](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/adjusting-join-shuffle/)

### 模块 6 实验：丰富 event data 并观察 Join execution

为 baseline events 增加一张课程提供的小型 product dimension table：

- 创建 `dim_products`，包含 `product_id`、category、brand 等属性。
- 使用 `INNER JOIN` 返回具有有效 product match 的 event。
- 使用 `LEFT OUTER JOIN` 保留没有 dimension match 的 event，并观察右表 columns 为 `NULL` 的结果。
- 使用 Left Semi Join 找出存在 product definition 的 event。
- 使用 Left Anti Join 找出 orphan product IDs。
- 比较 Join 前后的 row count，识别 duplicate dimension keys 导致的 row multiplication。
- 使用 `EXPLAIN` 检查 FE 创建并优化的 distributed query plan。
- 观察 small dimension table 对应的 Broadcast Join。
- 创建一个与 event table 具有兼容 Hash bucketing 的实验表，通过 `EXPLAIN` 对比 Broadcast、Partition Shuffle 或 Bucket Shuffle 的 plan evidence。
- 在 single-node sandbox 中不以 elapsed time 判断 Join strategy；实验重点是读取 execution plan 和解释 data movement。
- 最后完成一条按 category 和 region 聚合 revenue 的 fact-dimension query。

## 模块 7：在 Apache Doris 中更新和删除数据

### 模块目标

讲清楚 analytical table 中的 update/delete 与 OLTP row-in-place modification 有什么区别，并教会学员根据数据规模和变更模式选择正确的 Doris 操作。

重点包括 Unique Key model、upsert、Merge-on-Write（MoW）、delete bitmap、Sequence column、partial column update、predicate `DELETE` 和 Partition-level data replacement。

ClickHouse Module 7 从 immutable Part、mutation、lightweight delete 和 replacing/collapsing engine 出发；Doris 对应设计应围绕 Unique Key Merge-on-Write 展开，不能沿用 ClickHouse 的 mutation 或 `FINAL` semantics。

### 学习目标

完成本模块后，学员将能够：

- 区分 append-only event history 和 current-state table，并为两者选择不同的 Table Model。
- 说明 Duplicate Key model 保留 repeated keys，而 Unique Key model 对相同 Key columns 执行 upsert。
- 说明 Unique Key Merge-on-Write 如何写入新 Rowset，并通过 delete bitmap 使旧 row version 对查询不可见。
- 说明 logical delete 已生效并不代表旧 Segment 所占空间已经立即释放；实际清理由后续 Compaction 完成。
- 使用完整 row upsert 更新一条 current-state record。
- 使用 Sequence column 处理乱序到达的 change events，防止旧状态覆盖新状态。
- 区分 SQL `UPDATE`、partial column update 和 full-row upsert 的适用场景。
- 使用 predicate `DELETE` 删除一组匹配 rows。
- 根据删除范围选择 row-level `DELETE`、delete sign、`TRUNCATE PARTITION`、`TRUNCATE TABLE` 或 Partition replacement。
- 说明高频 single-row update/delete 会产生 transaction 和 Rowset 压力，应优先使用 batch ingestion。

Doris 4.x 的 Unique Key model 默认使用 Merge-on-Write；Sequence column 可为乱序 Change Data Capture（CDC）events 决定哪个版本生效：

- [Unique Key Model](https://doris.apache.org/docs/4.x/table-design/data-model/unique/)
- [Data Update and Delete](https://doris.apache.org/docs/4.x/key-features/data-update-delete/)
- [Delete Operations Overview](https://doris.apache.org/docs/4.x/data-operate/delete/delete-overview.html/)

### 模块 7 实验：维护 current order state

使用独立的小型 `order_state` dataset，避免修改 Level 1 保存的 immutable event history：

- 创建以 `order_id` 为 Key 的 Unique Key table。
- 使用 `updated_at` 作为 Sequence column。
- 写入订单的初始状态。
- 写入相同 `order_id` 的新状态，验证查询只返回最新 logical row。
- 故意写入一条较早的 out-of-order change event，验证它不会覆盖具有更高 Sequence value 的状态。
- 使用 SQL `UPDATE` 修正一条小范围业务数据。
- 使用 partial column update 只更新订单状态或配送字段，并验证其他 columns 保持不变。
- 使用 predicate `DELETE` 删除一条受控测试记录。
- 查询更新和删除前后的结果，并观察 row count、status 和 `updated_at`。
- 检查 Tablet version 或相关 storage evidence，把 upsert/delete 与新 Rowset、delete bitmap 和后续 Compaction 联系起来。
- 可选：在实验 Partition 上使用 `TRUNCATE PARTITION`，对比 row-level delete 与 Partition-level lifecycle operation。
- 所有修改均使用课程专用 table，不破坏 Module 1–6 的 baseline dataset。
