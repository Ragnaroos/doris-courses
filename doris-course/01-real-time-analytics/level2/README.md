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

基于 Level 1 的 `events` dataset 和一组明确的 analytical query requirements，完成供后续模块使用的 `events_modelled`：

- 阅读 dataset contract，确定 event table 的 grain。
- 检查 `event_time`、`event_id`、`user_id`、`event_type`、`region`、`product_id` 和 `revenue` 的业务含义。
- 为每个 column 选择 type、nullability 和 default value。
- 明确选择 Duplicate Key model，并解释为什么 event history 应保留每一条 original event row。
- 显式设计 sort key、time Partition 和 Bucket，避免依赖默认推断。
- 使用一份小型可控数据对比文本金额和 `DECIMAL` 金额：文本模型需要在查询时执行 `CAST`，typed model 可以直接执行 `SUM(revenue)`，非法金额应在 ingestion boundary 被发现，而不是留到分析查询中。
- 对比 detail table 与 summary table 的 stored row count、represented event count 和 total revenue，验证 grain 变化与 additive measures。
- 保留完整的 `events_modelled`，供 Module 5 和 Module 6 使用。

实验重点不是再次验证 Partition pruning，而是让学员能够解释每一项 DDL decision 对应的业务要求。

## 模块 5：使用 Apache Doris 分析数据

### 模块目标

讲清楚 Doris function 如何参与查询，以及如何把 detail event data 逐步转换为可解释的分析结果。

本模块沿用 ClickHouse Module 5 的组织逻辑：先认识 query result 的呈现方式，再区分 scalar function、aggregate function、table-valued function（TVF）和 window function，最后通过 Common Table Expression（CTE）把多个分析阶段组合起来。课程不要求学员记忆完整的 function catalog，而是要求他们根据“逐行转换、跨行聚合、读取外部关系或保留行数进行窗口计算”选择正确的 function category。

ClickHouse 与 Doris 的语法不做机械映射：

- ClickHouse 的 `FORMAT Vertical` 和 `FORMAT JSONEachRow` 属于其 query output syntax。Doris 通过 MySQL-compatible client、Notebook table 等 client surface 呈现结果；MySQL CLI 可用 `\G` 纵向显示一行，`SELECT INTO OUTFILE` 则用于把 query result 导出为 CSV、Parquet 或 ORC。输出形式不会改变 query semantics 或 result grain。
- ClickHouse 的 conditional aggregate combinator（例如 `sumIf`）在本课程中使用 Doris 支持的 conditional expression inside aggregate，例如 `SUM(CASE WHEN ... THEN ... ELSE ... END)`。
- ClickHouse 的 `any` 在 Doris 中对应 `ANY_VALUE`，Doris 也接受 `ANY` alias。它表示从 group 中取任意一个值，不用于掩盖本应加入 `GROUP BY` 的业务维度。
- Doris 支持 Lambda expression，但主要将其作为 `ARRAY_MAP`、`ARRAY_FILTER` 等 higher-order function 的参数；它不等同于注册一个 reusable UDF。
- Doris UDF 用于 built-in function 无法表达的 reusable logic，可实现 scalar、aggregate、window 或 table function。创建 UDF 需要外部实现和部署，不在本模块 Lab 中展开。
- Doris 支持 transaction。单条 query 在 `READ COMMITTED` 下读取 statement 开始时的 committed snapshot；load transaction、Label 和 retry safety 已在 Module 3 讲解，本模块只建立这一衔接，不把 transaction 作为分析 SQL 的主线。

### 学习目标

完成本模块后，学员将能够：

- 说明 MySQL-compatible client、Notebook table 和 `SELECT INTO OUTFILE` 分别面向交互查询、课程展示和 result export；不把 result presentation 与 SQL 计算逻辑混为一谈。
- 按作用区分 scalar function、aggregate function、TVF 和 window function。
- 使用 `TO_DATE`、`DATE_TRUNC`、`DATE_FORMAT` 和 `EXTRACT` 完成日期转换、时间粒度归一和时间维度提取。
- 使用 `LOWER`、`UPPER`、`TRIM`、`REPLACE`、`LIKE` 和 `REGEXP` 完成字符串标准化与 pattern matching。
- 使用 `COUNT`、`COUNT(DISTINCT ...)`、`SUM`、`AVG`、`MIN`、`MAX` 以及 variance、covariance、correlation 等 aggregate function 计算指标，并根据业务问题选择有意义的统计量。
- 使用 conditional expression inside aggregate 在同一 grouped row 中计算多个条件指标。
- 区分 `WHERE` 对 input rows 的过滤和 `HAVING` 对 aggregated groups 的过滤。
- 在确定 functionally dependent 或任意代表值确实符合业务语义时使用 `ANY_VALUE`，并解释它为什么不能替代正确的 grouping design。
- 说明 Module 3 使用的 S3 TVF 为什么属于 table-valued function：它产生可被 `SELECT` 查询的 temporary relation，而不是对单行返回一个 scalar value。
- 使用 CTE 将复杂查询拆分为命名清晰的中间 result set。
- 区分 aggregate function 和 window function：aggregate function 将多行折叠为较少的 grouped rows；window function 保留 result rows，并为每一行计算排名、累计值或前后行比较结果。
- 使用 `ROW_NUMBER`、`RANK`、`LAG` 和 `SUM() OVER (...)` 完成排名、趋势和累计分析。
- 为 window function 提供确定性的 `PARTITION BY` 和 `ORDER BY`。
- 使用一个小型 ARRAY literal 和 Lambda expression 理解 higher-order function 如何逐元素转换或过滤 array；复杂类型的 schema 选择仍以 Module 4 为准。
- 说明何时优先使用 built-in function，以及何时才需要部署 reusable UDF。

Doris 官方文档说明：CTE 是一条 statement 内可复用的 temporary result set；window function 不减少 result row 数量；TVF 将外部数据暴露为 relation；`ANY_VALUE` 返回 group 中任意一个非 `NULL` value；Lambda expression 可用于 ARRAY higher-order function：

- [Common Table Expressions](https://doris.apache.org/docs/4.x/query-data/cte/)
- [Analytic Functions (Window Functions)](https://doris.apache.org/docs/4.x/query-data/window-function/)
- [ANY_VALUE](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/any-value/)
- [FILE Table-Valued Function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/file/)
- [ARRAY_MAP](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/array-functions/array-map/)
- [Java UDF, UDAF, UDWF and UDTF](https://doris.apache.org/docs/4.x/query-data/udf/java-user-defined-function/)
- [Transactions](https://doris.apache.org/docs/4.x/data-operate/transaction/)

### 模块 5 实验：使用 function 回答 event analytics questions

继续使用 Module 4 的 `events_modelled`。Lab 保持即插即用：每一步提供可直接运行的 SQL，但通过小范围参数选择、function matching、结果预测和局部 expression 补全增加互动，不要求学员从空白开始编写完整 SQL。

实验按以下路径组织：

1. **建立 function category mental model**：用一组可交互的 matching cards，把 `LOWER`、`SUM`、S3 TVF 和 `ROW_NUMBER` 分别匹配到 scalar、aggregate、TVF 和 window function，并根据“输入一行还是多行、输出 scalar 还是 relation、是否保留 result rows”解释选择。
2. **转换时间与字符串字段**：使用完整 query template，通过选择日/周/月 reporting grain 切换 `TO_DATE` 或 `DATE_TRUNC`；组合 `LOWER`、`TRIM`、`LIKE` 或 `REGEXP` 观察标准化和 pattern matching 如何改变匹配结果。Module 4 已解释 column type，本步骤只关注 query-time transformation。
3. **从 detail rows 得到 grouped metrics**：计算每天和每个 region 的 event count、active user count、minimum/maximum purchase value 与 purchase revenue；使用 conditional expression inside aggregate，在一行中分别计算 view、cart 和 purchase 指标。
4. **区分 input-row filter 与 group filter**：在同一 business question 中对比 `WHERE` 和 `HAVING`，找出达到 revenue threshold 的 product groups，并让学员先预测 filter 发生在 aggregation 前还是后。
5. **理解合法与不合法的 grouped projection**：先展示“选择了未 grouping、未 aggregation 的 column”产生的错误，再使用 `ANY_VALUE` 得到一个任意代表值；同时通过结果说明，只有当 group 内具体取哪个值不影响业务含义时才应这样做。
6. **用 CTE 表达多个分析阶段**：使用 `daily` CTE 先把 event rows 聚合到 daily grain，再由后续 CTE 计算 daily change 和 cumulative revenue。Learner 通过排序 CTE stages 或选择缺失的 expression 完成查询结构，而不是手写整条 SQL。
7. **比较 aggregate function 与 window function**：在相同 daily result 上对比 grouped `SUM` 与 `SUM() OVER (...)`，并使用 `LAG`、`ROW_NUMBER` 或 `RANK` 观察 window function 如何增加计算列但保留 input result rows。
8. **体验 Lambda 和 higher-order function**：使用独立的小型 ARRAY literal 运行 `ARRAY_MAP(x -> ...)` 和 `ARRAY_FILTER(x -> ...)`。该演示不修改 `events_modelled` schema，也不重复 Module 4 的复杂类型建模内容。
9. **完成受引导的 business question challenge**：从 date grain、filter、metric 和 ranking rule 中作出有限选择，由 Notebook 生成并展示最终 SQL；学员根据 expected row count、关键 value 和 result grain 验证结果。

Module 3 已详细执行 S3 TVF，本 Lab 不再次读取完整 remote dataset，只在 function category 中引用它。Level 1 optional Lab 已展示 Metabase dashboard，因此本模块不重复安装 BI environment；完成挑战后，可选地把最终 query 保存到已有 Metabase dashboard。

## 模块 6：在 Apache Doris 中连接数据

### 模块目标

讲清楚 Join 的 logical semantics，以及 Doris 在 MPP execution architecture 中如何选择 physical Join implementation、移动数据并减少 probe-side work。

学员需要先根据业务关系、unmatched-row requirement、Join condition 和 expected result grain 选择正确的 Join type，再理解 FE 如何根据 table statistics、Join condition 和 data distribution 创建并优化 distributed query plan，BE nodes 如何执行 assigned plan fragments。课程区分 equi-Join 通常采用的 Hash Join 与 non-equi condition 可能采用的 Nested Loop Join，并说明 Broadcast、Partition Shuffle、Bucket Shuffle 和 Colocate 分别会产生什么 data movement。

ClickHouse Module 6 通过不同 Join algorithm 和 Dictionary lookup 比较执行效果；Doris 版本重点使用 Doris optimizer、Shuffle strategy 和 colocated data distribution，不引入 ClickHouse Dictionary。

### 学习目标

完成本模块后，学员将能够：

- 根据需要保留哪一侧的 unmatched rows，在 `INNER JOIN`、`LEFT/RIGHT OUTER JOIN` 和 `FULL OUTER JOIN` 之间进行选择，并说明 `CROSS JOIN` 为什么会产生 Cartesian product。
- 使用 Semi Join 和 Anti Join 表达“是否存在匹配记录”，避免不必要地返回另一侧 columns。
- 识别 one-to-one、one-to-many 和 many-to-many relationship，并预测 Join 后的 result grain。
- 解释 duplicate Join keys 为什么可能放大 result row count。
- 说明普通 equality operator `=` 不会匹配 `NULL`，并在确实需要把两侧 `NULL` 视为相等时识别 NULL-safe equality operator `<=>`；区分普通 Anti Join 与 NULL-aware Anti Join 所解决的问题。
- 说明 Hash Join 的 build side 和 probe side 各自承担的职责。
- 根据 Join condition 区分 Hash Join 与 Nested Loop Join：equi-condition 可以构建 hash table，只有 range/non-equi condition 或 Cartesian product 时可能需要 Nested Loop Join。
- 区分 Doris 的主要 Join data-distribution strategy：Broadcast Join、Partition Shuffle Join、Bucket Shuffle Join 和 Colocate Join。
- 说明 small dimension table 为什么通常适合作为 Broadcast side，以及 large-to-large Join 为什么通常需要 Shuffle。
- 说明 Join Runtime Filter 如何由 build-side values 动态产生并下推到 probe-side Scan，从而减少 probe rows、I/O 和 network transfer。
- 使用 `EXPLAIN` 识别 Join type、Join condition、build/probe relationship、Runtime Filter 和 data-distribution strategy。
- 理解 optimizer 通常会自动选择 Join order 和 distribution strategy，只在有运行证据时才考虑使用 hint。
- 识别 ASOF JOIN 的 point-in-time semantics：为每条 event 在相同 equi-key 范围内寻找指定时间方向上最近的 dimension/state row，而不是要求 timestamp 完全相等。

Doris 官方文档将 Broadcast、Partition Shuffle、Bucket Shuffle 和 Colocate 定义为四种主要 Join distribution strategy；对数据布局的要求越严格，潜在 network transfer 通常越少：

- [Doris Joins](https://doris.apache.org/docs/4.x/query-data/join/)
- [ASOF JOIN for Time-Series Nearest-Neighbor Matching](https://doris.apache.org/docs/4.x/query-data/asof-join/)
- [Runtime Filter](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/runtime-filter/)
- [Adjusting Join Shuffle Mode](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/adjusting-join-shuffle/)

### 模块 6 实验：丰富 event data 并观察 Join execution

为 baseline events 增加一张课程提供的小型 product dimension table：

- 创建 `dim_products`，包含 `product_id`、category、brand 等属性。
- 使用 `INNER JOIN` 返回具有有效 product match 的 event。
- 使用 `LEFT OUTER JOIN` 保留没有 dimension match 的 event，并观察右表 columns 为 `NULL` 的结果。
- 使用 Left Semi Join 找出存在 product definition 的 event。
- 使用 Left Anti Join 找出 orphan product IDs。
- 比较 Join 前后的 row count，识别 duplicate dimension keys 导致的 row multiplication。
- 用一组包含 `NULL` Join key 的小型 rows 对比 `=` 与 `<=>`；RIGHT、FULL、CROSS 和 NULL-aware Anti Join 在课程中解释，不要求逐一建立大表演示。
- 使用一个 equi-Join 与一个小型 non-equi Join 的 `EXPLAIN`，分别识别 Hash Join 与 Nested Loop Join；避免对千万级数据执行无约束 Cartesian product。
- 使用 `EXPLAIN` 检查 FE 创建并优化的 distributed query plan，并识别 Join condition、Runtime Filter 以及 small dimension table 对应的 Broadcast Join。
- 使用按 Join key Hash bucketing 的 `dim_products`，通过 `EXPLAIN` 对比 Broadcast 与可复用现有 Bucket layout 的 Bucket Shuffle plan evidence，并说明 Partition Shuffle 的 data movement。
- 在 single-node sandbox 中不以 elapsed time 判断 Join strategy；实验重点是读取 execution plan 和解释 data movement。
- 最后完成一条按 category 和 region 聚合 revenue 的 fact-dimension query。

## 模块 7：在 Apache Doris 中更新和删除数据

### 模块目标

讲清楚如何根据变更对象、数据规模、写入频率和恢复要求，在 Doris 中选择合适的 update/delete path。

本模块以 current-state data 为主线，对比 load-based full-row upsert、partial column update 和 SQL `UPDATE`，再根据删除粒度选择 predicate `DELETE`、Delete Sign、`TRUNCATE` 或 atomic overwrite。Unique Key model、Merge-on-Write（MoW）、delete bitmap、Rowset 和 Compaction 已在 Module 2 和 Module 4 建立基础，本模块只用这些机制解释操作结果与性能取舍，不重复讲解 Table Model 分类或完整存储层级。

ClickHouse Module 7 从 immutable Part、mutation、lightweight delete 和 replacing/collapsing engine 出发；Doris 对应设计应围绕 Unique Key Merge-on-Write 展开，不能沿用 ClickHouse 的 mutation 或 `FINAL` semantics。

### 学习目标

完成本模块后，学员将能够：

- 根据 workload 选择 update path：高频或批量 change events 使用 load-based upsert，低频条件修正使用 SQL `UPDATE`，只提供部分 value columns 时使用 partial column update。
- 使用 Unique Key model 的 full-row upsert，并说明相同 Key columns 表示覆盖现有 logical row，不存在的 Key 表示插入新 row。
- 说明 full-row upsert 中未提供的 columns 会使用 `NULL` 或 default value，而 partial column update 会保留现有 row 中未提供的 columns。
- 使用 Sequence column 处理乱序到达的 Change Data Capture（CDC）events，使较大的 sequence value 决定同一 Key 的可见版本。
- 说明 SQL `UPDATE` 只支持 Unique Key model、只能修改 value columns，并理解它需要先扫描匹配 rows、再写回更新结果。
- 说明修改 Key column 不是普通 `UPDATE`；业务主键变化应表达为删除旧 Key 并插入新 Key。
- 根据删除范围和数据来源选择 predicate `DELETE`、Delete Sign、`TRUNCATE TABLE/PARTITION` 或 `INSERT OVERWRITE`/temporary partition replacement。
- 说明 predicate `DELETE` 可用于所有 Table Model，但 Aggregate Key model 对 delete condition 有 Key-column restrictions；Delete Sign 则用于 Unique Key model 的批量主键删除和 CDC delete events。
- 说明 MoW update/delete 提交后，delete bitmap 立即使旧 row version 对查询不可见；旧 Segment 空间通常要等 Compaction 才被回收。
- 说明高频 single-row `UPDATE`/`DELETE` 会产生 transaction 和 Rowset pressure，应尽量批量提交；大范围 partition rewrite 应优先使用 metadata-level truncate 或 atomic overwrite，而不是 massive predicate delete。

Doris 4.x 的 Unique Key model 默认使用 Merge-on-Write。官方文档按操作目的区分 load-based update、SQL `UPDATE`、partial column update、conditional delete、Delete Sign、`TRUNCATE` 和 atomic overwrite：

- [Unique Key](https://doris.apache.org/docs/4.x/key-features/unique-key/)
- [Data Update and Delete](https://doris.apache.org/docs/4.x/key-features/data-update-delete/)
- [Load-Based Updates for the Unique Model](https://doris.apache.org/docs/4.x/data-operate/update/update-of-unique-model/)
- [UPDATE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/UPDATE/)
- [Delete Operations Overview](https://doris.apache.org/docs/4.x/data-operate/delete/delete-overview.html/)
- [INSERT OVERWRITE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/INSERT-OVERWRITE/)

### 模块 7 实验：维护 current order state

使用独立的小型 `order_state` dataset，避免修改 Module 1–6 保存的 event history 和 modeled tables。实验按“识别变更 → 选择操作 → 验证 visible state”的路径组织：

1. **建立 current-state contract**：创建以 `order_id` 为 Key、以 `updated_at` 为 Sequence column 的 Unique Key table，写入少量初始订单，并明确一行代表一个订单的当前状态。
2. **执行 full-row upsert**：同时写入一个已有 `order_id` 和一个新 `order_id`，观察前者被替换、后者被插入；再发送较早的 out-of-order event，验证较小 Sequence value 不能覆盖较新的状态。
3. **比较 full-row 与 partial column semantics**：在受控 row 上展示普通 `INSERT` 未提供 column 时采用 default/`NULL` 的行为，再启用 partial column update 只修改 `status` 或配送字段，验证其他 value columns 保持不变。
4. **使用 SQL `UPDATE` 进行低频条件修正**：通过 `WHERE` 更新少量 value columns，并展示尝试修改 Key column 或对 Duplicate Key table 执行 `UPDATE` 为什么不符合该操作的约束。
5. **匹配删除方法与删除粒度**：使用 predicate `DELETE` 删除受控 rows；随后用一组独立的小型 cases 说明 Delete Sign 如何把 CDC delete event 作为批量 Key write 处理，并核对提交前后的 visible rows。
6. **比较 row deletion 与 lifecycle operation**：在独立的 partitioned sandbox table 上，对比 conditional `DELETE`、`TRUNCATE PARTITION` 和 `INSERT OVERWRITE`。前者按 row predicate 删除；后两者分别用于整 Partition 清理和原子重建，不对主课程 table 执行破坏性操作。
7. **解释提交后的 storage state**：通过查询结果确认 update/delete 已立即改变 visible state，并结合一份简短的 execution diagram 说明旧 row version 由 delete bitmap 隐藏、空间由后续 Compaction 回收；不重复 Module 2 的 Tablet/Rowset inspection。

实验结束时，学员应能针对“订单状态更新、晚到 CDC event、单列修正、批量主键删除、过期 Partition 清理和 Partition backfill”分别说明选择哪一种 path，以及为什么不使用其他 path。所有修改均限制在 Module 7 专用 tables 中。
