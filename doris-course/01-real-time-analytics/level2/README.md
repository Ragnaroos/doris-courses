# Level 2

Level 2 延续 Level 1 创建的 `doris_course` Database 和 `events` baseline dataset，按照以下路径组织学习内容：

```text
设计 schema → 编写分析 SQL → 连接事实与维度 → 维护 current state
```

课程结构对应 ClickHouse Level 2 的 Modeling、Analyzing、Joining、Deleting and Updating 四个模块，但具体内容使用 Apache Doris 4.x 的数据类型、Table Model、Join execution strategy 和 Unique Key Merge-on-Write 机制。

## 模块 4：在 Apache Doris 中建模数据

英文正文：[Module 4: Modeling Data in Apache Doris](module04-modeling/course4_modeling_data_in_apache_doris.md)

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
- 从 reporting requirement 推导 summary grain 和 additive measures，使用逻辑行数、represented event count 和 revenue total 对齐 detail 与 summary，并识别 summary 无法回答的问题。

Doris 官方推荐的建表流程也是先确定 Table Model，再选择数据类型、Partition/Bucket 和索引；Table Model 创建后不能直接转换为另一种模型：

- [Apache Doris Table Design Guide](https://doris.apache.org/docs/4.x/table-design/overview/)
- [Table Model Best Practices](https://doris.apache.org/docs/4.x/table-design/data-model/tips/)

### 模块 4 实验：设计 query-ready event model

基于持久化的 `doris_course.events` 和明确的 analytical requirements，Lab 4 按当前 Notebook 的五个步骤建立模型：

1. **检查 source contract**：确认 baseline 有 10,158,080 行，通过 `SHOW FULL COLUMNS` 查看 type、nullability 和 default。行数用于检查 source availability；grain 来自业务 contract，不依赖全表 `COUNT(DISTINCT ...)` 推断。
2. **观察文本模型的问题**：向 `modeling_raw_events` 写入五行受控样本，用 `TRY_CAST` 计算有效金额并单独统计一行非法金额；以大数值对比 `DOUBLE` 与 `DECIMAL(18,2)` 的精度，不计时比较性能。
3. **建立 typed ingestion boundary**：显式过滤非法 revenue，向 `modeling_typed_events` 写入四行。省略 `region` 的 target column 触发 `DEFAULT "unknown"`；可选 `product_id` 保留为 `NULL`。该步骤不把非法 revenue 写入 typed table 来演示 transaction rejection。
4. **建立完整 event-detail model**：`events_modelled` 使用 Duplicate Key、以 `event_time` 开头的 sort key、monthly Auto Range Partition、`HASH(user_id)` 和每 Partition 10 Buckets。完整模型沿用 baseline 的 `region NOT NULL` 和 `product_id NOT NULL`，不套用受控样本的缺失值规则。与 `events` 核对 10,158,080 行和 39,984,455.64 revenue。
5. **从 reporting requirement 推导 summary**：创建 `daily_event_metrics`，以 `(event_date, region, event_type)` 为 Aggregate Key，使用 additive `event_count` 和 `total_revenue`。一次 pre-grouped insert 产生预期 280 个逻辑 groups，仍代表 10,158,080 个 events 和相同 revenue；它不是跨多个批次验证重复 Key merge 的实验。

Notebook 的 `stored_rows` 来自 `COUNT(*)`，表示 SQL 可见逻辑行数，不是物理 Rowset/Segment row inspection。实验不验证 Partition pruning、delete bitmap、Compaction 或性能差异。复杂类型和 Unique Key 在 course 中介绍，不在 Lab 4 中建立对应实验表。

Lab 4 重建前只清空自身四张 target tables，保留 `events` baseline。完成后保留 `events_modelled`，供 Module 5 和 Module 6 使用；可选 stop/restart 验证 Docker named volumes 中的数据持久化。

## 模块 5：使用 Apache Doris 分析数据

英文正文：[Module 5: Analyzing Data in Apache Doris](module05-analyzing/course5_analyzing_data_in_apache_doris.md)

### 模块目标

讲清楚 Doris function 如何参与查询，以及如何把 detail event data 逐步转换为可解释的分析结果。

本模块沿用 ClickHouse Module 5 的组织逻辑：先认识 query result 的呈现方式，再区分 scalar function、aggregate function、table-valued function（TVF）和 window function，最后通过 Common Table Expression（CTE）把多个分析阶段组合起来。课程不要求学员记忆完整的 function catalog，而是要求他们根据“逐行转换、跨行聚合、读取外部关系或保留行数进行窗口计算”选择正确的 function category。

ClickHouse 与 Doris 的语法不做机械映射：

- ClickHouse 的 `FORMAT Vertical` 和 `FORMAT JSONEachRow` 属于其 query output syntax。Doris 通过 MySQL-compatible client、Notebook table 等 client surface 呈现结果；MySQL CLI 可用 `\G` 纵向显示一行，`SELECT INTO OUTFILE` 则用于把 query result 导出为 CSV、Parquet 或 ORC。输出形式不会改变 query semantics 或 result grain。
- ClickHouse 的 conditional aggregate combinator（例如 `sumIf`）在本课程中使用 Doris 支持的 conditional expression inside aggregate，例如 `SUM(CASE WHEN ... THEN ... ELSE ... END)`。
- ClickHouse 的 `any` 在 Doris 中对应 `ANY_VALUE`，Doris 也接受 `ANY` alias。它表示从 group 中取任意一个值，不用于掩盖本应加入 `GROUP BY` 的业务维度。
- Doris 支持 Lambda expression，但主要将其作为 `ARRAY_MAP`、`ARRAY_FILTER` 等 higher-order function 的参数；它不等同于注册一个 reusable UDF。
- Doris Alias Function 可通过 SQL 为已有 function expression 注册 reusable signature；需要外部算法时，可以使用 Java UDF 等扩展。Lab 介绍 Java UDF lifecycle 和非执行注册模板，不构建 JAR 或部署 UDF。
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
- 为 window function 选择符合业务含义的 `PARTITION BY`、`ORDER BY` 和适用的 frame；为 `ROW_NUMBER` 提供确定性的 tie-breaker，并保留 `RANK` 所需的并列语义。
- 使用一个小型 ARRAY literal 和 Lambda expression 理解 higher-order function 如何逐元素转换或过滤 array；复杂类型的 schema 选择仍以 Module 4 为准。
- 区分 built-in function、array Lambda expression、SQL Alias Function 和需要外部实现与部署的 UDF。

Doris 官方文档说明：CTE 是一条 statement 内可复用的 temporary result set；window function 不减少 result row 数量；TVF 将外部数据暴露为 relation；`ANY_VALUE` 返回 group 中任意一个非 `NULL` value；Lambda expression 可用于 ARRAY higher-order function：

- [Common Table Expressions](https://doris.apache.org/docs/4.x/query-data/cte/)
- [Analytic Functions (Window Functions)](https://doris.apache.org/docs/4.x/query-data/window-function/)
- [ANY_VALUE](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/any-value/)
- [FILE Table-Valued Function](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/file/)
- [ARRAY_MAP](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/array-functions/array-map/)
- [Java UDF, UDAF, UDWF and UDTF](https://doris.apache.org/docs/4.x/query-data/udf/java-user-defined-function/)
- [Transactions](https://doris.apache.org/docs/4.x/data-operate/transaction/)

### 模块 5 实验：使用 function 回答 event analytics questions

继续使用 Module 4 的 `events_modelled`。Lab 提供可直接运行的 SQL，并通过 function matching 和 guided query builder 增加互动；其他步骤以固定 SQL 和 expected results 解释概念，不要求学员从空白开始编写完整 SQL。

实验按以下路径组织：

1. **建立 function category mental model**：用一组可交互的 matching cards，把 `LOWER`、`SUM`、S3 TVF 和 `ROW_NUMBER` 分别匹配到 scalar、aggregate、TVF 和 window function，并根据“输入一行还是多行、输出 scalar 还是 relation、是否保留 result rows”解释选择。
2. **转换时间与字符串字段**：固定 SQL 使用 `TO_DATE`、按小时 `DATE_TRUNC`、`EXTRACT`、`REPLACE`、`UPPER`、`LIKE` 和 `REGEXP`，在八行样本中并列展示原始值与 derived values。日/周/月选择放在后面的 query builder 中。
3. **从 detail rows 得到 grouped metrics**：按 date 和 region 计算 event count、minimum/maximum purchase value 与 purchase revenue；conditional expression 区分所有 event 与 purchase-only measures。本步骤不分别计算 view/cart 指标，active users 可在后面的 builder 中选择。
4. **区分 input-row filter 与 group filter**：用一条同时包含 `WHERE` 和 `HAVING` 的查询，先筛选当天 purchase events，再保留达到 revenue threshold 的 product groups。
5. **理解合法与不合法的 grouped projection**：先展示“选择了未 grouping、未 aggregation 的 column”产生的错误，再使用 `ANY_VALUE` 得到一个任意代表值；同时通过结果说明，只有当 group 内具体取哪个值不影响业务含义时才应这样做。
6. **用 CTE 表达一个命名阶段**：固定 SQL 使用 `daily` CTE 把 event rows 聚合到八行 daily results，先单独展示这些行。本步骤没有排序 CTE stages 或 expression 补全交互。
7. **比较 aggregate function 与 window function**：下一条 SQL 复用相同 `daily` CTE 定义，在外层使用 `LAG`、`SUM() OVER (...)` 和 `ROW_NUMBER`，为八行 daily results 增加 previous revenue、cumulative revenue 和确定性排名；没有单独执行 `RANK`。
8. **体验 Lambda 和 higher-order function**：使用独立的小型 ARRAY literal 运行 `ARRAY_MAP(x -> ...)` 和 `ARRAY_FILTER(x -> ...)`。该演示不修改 `events_modelled` schema，也不重复 Module 4 的复杂类型建模内容。
9. **完成受引导的 business question challenge**：从 date grain、event filter 和 metric 中作出有限选择，由 Notebook 生成并展示最终 SQL；学员根据关键 value 和 result grain 验证结果。
10. **识别 UDF boundary**：用需求对照表与 Java UDF lifecycle 解释何时需要扩展 built-in functions。提供非执行的注册模板，不构建 JAR 或部署 UDF。

Module 3 已详细执行 S3 TVF，本 Lab 不再次读取完整 remote dataset，只在 function category 中引用它。Level 1 optional Lab 已展示 Metabase dashboard，因此本模块不重复安装 BI environment；完成挑战后，可选地把最终 query 保存到已有 Metabase dashboard。

## 模块 6：在 Apache Doris 中连接数据

英文正文：[Module 6: Joining Data in Apache Doris](module06-joining/course6_joining_data_in_apache_doris.md)

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
- 说明 Join Runtime Filter 如何由 build-side values 动态产生并在 Join semantics 允许时下推到 probe-side Scan，以及它可能减少的 probe rows、I/O 和 network transfer；区分计划中的 producer/consumer 与实际过滤效果。
- 使用 `EXPLAIN` 识别 Join type、Join condition、build/probe relationship、Runtime Filter 和 data-distribution strategy。
- 理解 optimizer 通常会自动选择 Join order 和 distribution strategy，只在有运行证据时才考虑使用 hint。
- 识别 ASOF JOIN 的 point-in-time semantics：为每条 event 在相同 equi-key 范围内寻找指定时间方向上最近的 dimension/state row，而不是要求 timestamp 完全相等。

Doris 官方文档将 Broadcast、Partition Shuffle、Bucket Shuffle 和 Colocate 定义为四种主要 Join distribution strategy；对数据布局的要求越严格，潜在 network transfer 通常越少：

- [Doris Joins](https://doris.apache.org/docs/4.x/query-data/join/)
- [ASOF JOIN for Time-Series Nearest-Neighbor Matching](https://doris.apache.org/docs/4.x/query-data/asof-join/)
- [Runtime Filter](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/runtime-filter/)
- [Adjusting Join Shuffle Mode](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/adjusting-join-shuffle/)

### 模块 6 实验：丰富 event data 并观察 Join execution

从 `events_modelled` 的 product identifiers 在本地生成 204,231 行的 `dim_products`，以 Unique Key 保持一行一个 product。Category 和 brand 是确定性生成的教学属性；刻意省略 `1005115` 并加入 dimension-only `999999999`，不读取额外 remote dataset：

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
- 在 Join type 演示后完成一条按 category 和 region 聚合 revenue 的 fact-dimension query，再使用小表和 execution plan 深入理解 Join execution。

## 模块 7：在 Apache Doris 中更新和删除数据

英文正文：[Module 7: Updating and Deleting Data in Apache Doris](module07-updating-deleting/course7_updating_and_deleting_data_in_apache_doris.md)

### 模块目标

讲清楚如何根据变更对象、数据规模、写入频率和恢复要求，在 Doris 中选择合适的 update/delete path。

本模块以 current-state data 为主线，对比 load-based full-row upsert、partial column update 和 SQL `UPDATE`，再根据删除粒度选择 predicate `DELETE`、Delete Sign、`TRUNCATE` 或 atomic overwrite。Module 2 建立存储层级基础，Module 4 解释模型选择并简述 Unique Key Merge-on-Write（MoW）的文档机制；Lab 4 不观察 delete bitmap、Rowset 或 Compaction。本模块进一步用这些机制解释变更操作结果与取舍。

ClickHouse Module 7 从 immutable Part、mutation、lightweight delete 和 replacing/collapsing engine 出发；Doris 对应设计应围绕 Unique Key Merge-on-Write 展开，不能沿用 ClickHouse 的 mutation 或 `FINAL` semantics。

### 学习目标

完成本模块后，学员将能够：

- 根据 workload 选择 update path：高频或批量 change events 使用 load-based upsert，低频条件修正使用 SQL `UPDATE`，只提供部分 value columns 时使用 partial column update。
- 使用 Unique Key model 的 full-row upsert，并说明相同 Key columns 表示覆盖现有 logical row，不存在的 Key 表示插入新 row。
- 说明 full-row upsert 中未提供的 columns 按 schema 使用 default/允许的 `NULL`，而 partial column update 保留现有 row 中未提供的 columns；区分已有 Key 与新 Key 的行为，以及遗漏字段与显式 `NULL`。
- 使用 Sequence column 处理乱序到达的 Change Data Capture（CDC）events，使较大的 sequence value 决定同一 Key 的可见版本。
- 说明 SQL `UPDATE` 只支持 Unique Key model、只能修改 value columns，并理解它需要先扫描匹配 rows、再写回更新结果。
- 说明修改 Key column 不是普通 `UPDATE`；业务主键变化应表达为删除旧 Key 并插入新 Key。
- 根据删除范围和数据来源选择 predicate `DELETE`、Delete Sign、`TRUNCATE TABLE/PARTITION` 或 `INSERT OVERWRITE`/temporary partition replacement。
- 说明 predicate `DELETE` 可用于所有 Table Model，但 Aggregate Key model 对 delete condition 有 Key-column restrictions；Delete Sign 则用于 Unique Key model 的批量主键删除和 CDC delete events。
- 说明 MoW write 发布可见后，后续普通查询读取获胜状态或排除删除 Key，无需等待 Compaction；区分 Delete Sign 与 delete bitmap，以及 statement snapshot 与后台物理清理。
- 说明高频 single-row `UPDATE`/`DELETE` 会产生 transaction 和 Rowset pressure，应尽量批量提交；大范围 partition rewrite 应优先使用 metadata-level truncate 或 atomic overwrite，而不是 massive predicate delete。

Doris 4.x 的 Unique Key model 默认使用 Merge-on-Write。官方文档按操作目的区分 load-based update、SQL `UPDATE`、partial column update、conditional delete、Delete Sign、`TRUNCATE` 和 atomic overwrite：

- [Unique Key](https://doris.apache.org/docs/4.x/key-features/unique-key/)
- [Data Update and Delete](https://doris.apache.org/docs/4.x/key-features/data-update-delete/)
- [Load-Based Updates for the Unique Model](https://doris.apache.org/docs/4.x/data-operate/update/update-of-unique-model/)
- [UPDATE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/UPDATE/)
- [Delete Operation](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/)
- [INSERT OVERWRITE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/INSERT-OVERWRITE/)

### 模块 7 实验：维护 current order state

使用 `doris_course` 中三个独立的小表，保留 Module 1–6 的 `events`、`events_modelled` 和 `dim_products`。当前 Notebook 按五个主体步骤组织：

1. **建立 current-state contract 并执行 upsert**：创建 `order_state`，以 `order_id` 为 Unique Key、`updated_at` 为 Sequence column。已有 `1001` 更新为 `shipped`，新 Key `1004` 插入；晚到的较小 Sequence 不覆盖新状态，阶段结束有四个逻辑订单。
2. **比较遗漏列的含义**：重置两行后，full-row upsert 让 `1002` 的 amount/region 使用默认值；partial column update 只提供 `1003` 的 Key、status、updated_at，保留其他已有值。结束后恢复 partial-update session variable 为 false。
3. **进行 SQL correction**：再次恢复两行，修改 `1001` 的 `shipping_region`，对比前后值。该阶段不改变 `updated_at`；不执行 Key-column UPDATE 或非 Unique Key target 的失败案例。
4. **删除并观察可见性**：独立 `order_deletions` 不配置 Sequence。分别对 `2003` 执行 predicate DELETE、向 `2002` 写入 Delete Sign，普通查询只剩 `2001`。同节展示 Tablet Version/VersionCount/RowCount 和隐藏标记；不直接展示 delete bitmap、物理 Rowset/Segment 或 Compaction 空间回收。标记不保证在后台清理后仍可查询。
5. **选择 Partition lifecycle operation**：`order_lifecycle` 仅演示 `TRUNCATE TABLE ... PARTITION(...)` 和 `INSERT OVERWRITE`，不在此表执行 predicate DELETE。先清空 `p20260910`，再把 `p20260911` 替换为 `3003`、`3005`。Notebook 展示前后结果，不运行并发读验证 atomic switch。

可选 restart 检查的 `order_state` 保留第 3 节恢复的两行。Temporary Partition、恢复、new-key partial-update policy、并发和相同 Sequence 冲突由 course 说明边界，不作为当前 Lab 的已执行步骤。

实验结束时，学员应能针对“订单状态更新、晚到 CDC event、单列修正、批量主键删除、过期 Partition 清理和 Partition backfill”分别说明选择哪一种 path，以及为什么不使用其他 path。所有修改均限制在 Module 7 专用 tables 中。

## Interactive quizzes

Each quiz contains six independent English single-choice questions and uses the shared `doris_course.quiz` interface. No running Lab or external service is required.

- Module 4: [Notebook](module04-modeling/quiz4_schema_and_modeling_choices.ipynb) · [Question YAML](module04-modeling/quiz4_schema_and_modeling_choices.yaml)
- Module 5: [Notebook](module05-analyzing/quiz5_analytical_query_semantics.ipynb) · [Question YAML](module05-analyzing/quiz5_analytical_query_semantics.yaml)
- Module 6: [Notebook](module06-joining/quiz6_join_semantics_and_execution.ipynb) · [Question YAML](module06-joining/quiz6_join_semantics_and_execution.yaml)
- Module 7: [Notebook](module07-updating-deleting/quiz7_state_changes_and_deletion.ipynb) · [Question YAML](module07-updating-deleting/quiz7_state_changes_and_deletion.yaml)

[Question alignment and course review notes](quiz_alignment.md)
