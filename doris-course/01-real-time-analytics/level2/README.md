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

### Module 4 Course 内容大纲（需求场景驱动）

Course 4 从业务需要和 source contract 出发，再推导 Doris schema 选择。正文不以 `CREATE TABLE` 语法或功能清单组织；每一节先说明需要回答的问题、错误选择会造成什么结果，再引出相应的 Table Model、类型或数据布局。Lab 4 随后用 Doris 4.1.3 展示适合直接观察的功能和结果。

#### 4.1 先确定一行代表什么

**需求场景：** 电商平台既要保留每一次浏览、加购和购买事件，又要查询订单或客户的当前状态，还要为 Dashboard 提供每日汇总。这三类数据不能混在同一粒度中。

- 从 source contract 和分析问题定义 grain，而不是从某一列是否看起来唯一来猜测。
- 区分 event history、current state 和 summary metrics：分别是一行一个事件、一行一个业务实体的当前状态、一行一个汇总维度组合。
- 说明混合 detail row 与 summary row 为什么会导致重复计算，以及 summary 丢失哪些明细查询能力。
- 对应 Lab：确认 `events` 的 source contract，并在后续比较 `events_modelled` 与 `daily_event_metrics` 的逻辑行数和 represented event count。

#### 4.2 从 repeated-key semantics 选择 Table Model

**需求场景：** 同一个用户或产品可以连续产生多条日志；同一个订单会收到新的状态；同一天、地区和事件类型还可能收到新的指标贡献。相同 Key 再次出现时，业务希望得到的结果并不相同。

- **Duplicate Key：** 用于 append-style event log、审计记录等需要保留每个 accepted row 的场景；Key columns 主要形成 sort key，相同 Key 不表示去重。
- **Unique Key：** 用于订单、客户画像等 current-state 场景；相同 Key 的新状态执行 upsert，普通查询看到一个当前逻辑行。乱序状态的胜出规则留到 Module 7 的 Sequence column。
- **Aggregate Key：** 用于同一 reporting grain 的新指标贡献需要按声明的聚合方式合并的场景；Key columns 定义聚合组，Value columns 定义 `SUM` 等聚合行为。
- 强调 Table Model 实现的是 grain 和 repeated-key contract，不能仅因某个模型看起来“更快”而选择。
- 对应 Lab：建立 Duplicate Key `events_modelled` 和 Aggregate Key `daily_event_metrics`；Unique Key 的具体更新行为由 Module 7 展示。

#### 4.3 从报表需求推导 summary model

**需求场景：** Dashboard 反复查询每日、地区和事件类型级别的 event count 与 revenue，不需要每次扫描所有事件明细。

- 从报表维度定义 summary grain，再选择能够跨批次正确组合的 additive measures。
- 区分 visible summary rows、这些行代表的 event count 和 revenue total，不能用 summary `COUNT(*)` 代替事件数量。
- 通过 detail 与 summary 的 represented event count、revenue total 对账，并明确 summary 无法回答单个用户或事件的问题。
- 对应 Lab：建立 `daily_event_metrics`，验证 280 个逻辑 groups 仍代表 10,158,080 个 events 和相同 revenue。

#### 4.4 从值的业务含义选择数据类型

**需求场景：** 数据需要按标识符连接、按时间过滤、精确汇总金额，并使用地区和事件类型分组；source landing data 中的金额可能仍是文本。

- 标识符根据取值规则和未来范围选择整数或字符串，并在需要 Join 的表之间保持一致类型。
- 时间字段根据源精度选择 `DATE`、`DATETIME` 或带小数秒精度的 `DATETIME`，同时单独约定时区语义。
- 金额使用满足范围和 scale 的 `DECIMAL`；说明近似浮点和文本金额为何不适合作为最终分析 contract。
- `FLOAT`/`DOUBLE` 适合允许近似误差的传感器测量、科学数据、坐标或模型分数；它们不适合作为要求精确十进制结果的金额或 equality-based Join Key。低精度数值计算可能更便宜，但不能把“`DOUBLE` 一定更快”当成脱离表达式和 workload 的结论。
- 分类字段使用有意义的 `VARCHAR` 上限；区分字符串长度与字段 cardinality。
- 将查询中反复 `CAST`、无法稳定 Join 的标识符和过宽 `VARCHAR` 识别为 schema contract 问题。
- 对应 Lab：比较文本 revenue 与 typed revenue，并观察 `DOUBLE` 与 `DECIMAL` 的表示差异。

#### 4.5 从缺失值含义决定 NULL、NOT NULL 和 DEFAULT

**需求场景：** 某些事件确实没有 product，某些缺失的 region 应归入约定的 `unknown` 类别，而 revenue 文本无法转换则代表坏数据。这三种情况不能统一处理成 `NULL` 或同一个默认值。

- 当“未知、不适用或尚未提供”本身是允许的业务状态时使用 nullable column。
- 当每一行都必须提供有效值时使用 `NOT NULL`，让 schema 明确最低数据质量要求。
- 只有在字段被省略时存在明确替代语义，才使用 `DEFAULT`；默认值不是修复任意非法输入的规则。
- 区分 omitted value、显式 `NULL`、invalid value 和 failed conversion，并说明它们对导入与统计的不同影响。
- 将转换与坏数据处理放在 ingestion boundary，避免每条分析 SQL 重复清洗并静默漏算。
- 对应 Lab：保留允许缺失的 `product_id`、让省略的 `region` 使用 `unknown`，并在加载 typed table 前单独统计非法金额。

#### 4.6 为什么按时间分区，以及何时使用 Auto Partitioning

**需求场景：** 事件查询通常读取最近时间范围，数据按完整日或月保留、替换和过期，新时间段持续到来。

- Partition 是表内按范围划分数据和生命周期管理边界；从常用时间过滤、单个 Partition 数据量和删除/替换范围选择日、月等粒度。
- 解释过细 Partition 带来的 metadata 数量，和过粗 Partition 降低生命周期操作精度的问题。
- 当新时间值持续到达、希望 Doris 按规则创建相应时间范围时考虑 Auto Range Partition；若边界需要严格审批或预先控制，则显式管理 Partition。
- Auto Partitioning 解决的是新 Partition 的创建，不替代 grain、Table Model、Bucket 或 sort-key 设计。
- 对应 Lab：为 `events_modelled` 创建 monthly Auto Range Partitions，并检查实际生成的 Partition。

#### 4.7 为什么每个 Partition 内还需要 Buckets

**需求场景：** 一个月的数据仍然很大，需要在 Backend（BE）节点和执行实例之间分布与并行处理；`region` 只有少量取值且分布倾斜，而 `user_id` 数量多、分布更均匀。

- Partition 先决定一行属于哪个逻辑范围，Bucket 再通过 Hash 或 Random distribution 决定它落入该 Partition 的哪个 Tablet；二者解决不同层级的问题。
- Hash Bucket column 应具有足够的分布度，并结合查询和 Join 需求选择；低 cardinality、严重 skew 的字段容易造成数据倾斜。
- Bucket count 由每个 Partition 的数据量、集群规模和期望并行度共同决定，不使用脱离 workload 的固定数字。
- 对应 Lab：使用 `HASH(user_id)` 和每个 Partition 10 Buckets，查看 Tablet 布局；单 BE Lab 不把结果解释为多节点性能证明。

#### 4.8 用 sort key 配合主要查询路径

**需求场景：** 大多数 event 查询先限制时间范围，再按事件、用户或产品进一步分析。

- 在 Doris 中，Table Model 的 Key columns 同时参与排序语义；让常用、具有选择性的过滤前缀与主要访问路径一致。
- 以 `event_time` 开头支持课程的时间范围查询，再根据稳定的明细标识形成后续顺序。
- 说明 sort key、Partition 和 Bucket 各自回答的问题，避免把排序当成分区或去重机制。
- 对应 Lab：检查 `DUPLICATE KEY(event_time, event_id, user_id)`，但不以单次运行时间声称性能差异。

#### 4.9 复杂数据类型从应用结构出发，具体能力查阅官方文档

**需求场景：** 单个事件可能携带标签列表、固定结构的设备信息、动态属性集合或持续演进的文档 payload。

- `ARRAY` 对应同类型的有序集合，例如标签或一次事件中的多个实验编号。
- `STRUCT` 对应字段集合固定的嵌套对象，例如设备信息。
- `MAP` 对应动态的 key-value attributes，例如数量不固定的 campaign properties。
- `JSON`/`VARIANT` 适合保留或分析结构可能变化的文档；稳定且频繁用于过滤、Join、分组和指标计算的字段仍优先建成普通 typed columns。
- Course 只建立“业务结构如何映射到候选类型”的判断框架，并引导学员查阅 Doris 4.x 官方文档确认当前语法、函数、限制和版本差异。
- **Lab 4 不创建复杂类型表，也不演示 ARRAY、MAP、STRUCT、JSON 或 VARIANT。**

官方延伸阅读：[ARRAY](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/ARRAY/)、[MAP](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/MAP/)、[STRUCT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/STRUCT/)、[JSON](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/JSON/)、[VARIANT](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/semi-structured/VARIANT/)。

Course 与 Lab 的职责边界如下：

- **Course：** 从需求场景解释为什么选择某种 grain、Table Model、type、缺失值规则和数据布局，并说明选择的边界与取舍。
- **Lab：** 展示 Doris 4.1.3 中可直接观察的建表、转换、默认值、Table Model、Auto Partition、Hash Bucket 和 detail/summary 对账结果；不承担完整功能目录，也不以单节点运行结果证明性能。

### 模块 4 实验：设计 query-ready event model

基于持久化的 `doris_course.events` 和明确的 analytical requirements，Lab 4 按当前 Notebook 的五个步骤建立模型：

1. **检查 source contract**：确认 baseline 有 10,158,080 行，通过 `SHOW FULL COLUMNS` 查看 type、nullability 和 default。行数用于检查 source availability；grain 来自业务 contract，不依赖全表 `COUNT(DISTINCT ...)` 推断。
2. **观察文本模型的问题**：向 `modeling_raw_events` 写入五行受控样本，用 `TRY_CAST` 计算有效金额并单独统计一行非法金额；以大数值对比 `DOUBLE` 与 `DECIMAL(18,2)` 的精度，不计时比较性能。
3. **建立 typed ingestion boundary**：显式过滤非法 revenue，向 `modeling_typed_events` 写入四行。省略 `region` 的 target column 触发 `DEFAULT "unknown"`；可选 `product_id` 保留为 `NULL`。该步骤不把非法 revenue 写入 typed table 来演示 transaction rejection。
4. **建立并检查完整 event-detail model**：`events_modelled` 使用 Duplicate Key、以 `event_time` 开头的 sort key、monthly Auto Range Partition、`HASH(user_id)` 和每 Partition 10 Buckets。完整模型沿用 baseline 的 `region NOT NULL` 和 `product_id NOT NULL`，不套用受控样本的缺失值规则。与 `events` 核对 10,158,080 行和 39,984,455.64 revenue；再通过 `SHOW PARTITIONS` 和 `SHOW TABLETS` 的紧凑结果检查当前 source values 生成的 2 个月度 Partition、每个 10 Buckets 以及合计 20 Tablets。
5. **从 reporting requirement 推导 summary**：创建 `daily_event_metrics`，以 `(event_date, region, event_type)` 为 Aggregate Key，使用 additive `event_count` 和 `total_revenue`。一次 pre-grouped insert 产生预期 280 个逻辑 groups，仍代表 10,158,080 个 events 和相同 revenue；它不是跨多个批次验证重复 Key merge 的实验。

Notebook 的 `stored_rows` 来自 `COUNT(*)`，表示 SQL 可见逻辑行数，不是物理 Rowset/Segment row inspection。Partition 和 Tablet 数量来自 Doris metadata，只证明当前表已创建的布局。实验不验证 Partition pruning、delete bitmap、Compaction、多节点并行速度或不同 Bucket 设计的性能差异。复杂类型和 Unique Key 在 course 中介绍，不在 Lab 4 中建立对应实验表。

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

### Module 5 Course 内容大纲（分析场景驱动）

Course 5 从“业务问题需要什么形状的结果”出发，再选择函数、SQL clause 和查询阶段。课程不会按字母顺序罗列函数名，而是让学员判断输入是一行、多行、一个窗口还是一个 relation，以及函数会保留、折叠还是扩展行。正文必须覆盖 Doris 4.x SQL Functions 导航中的七类入口：AI Functions、Scalar Functions、Aggregate Functions、Combinators、Analytic (Window) Functions、Table Functions 和 Table-Valued Functions，并解释这些目录并非完全按同一个维度划分。Lab 5 使用 `events_modelled` 展示可直接执行的功能，并通过一个综合分析查询把多个概念连成完整答案。

#### 5.1 先定义分析问题、result grain 和输出方式

**需求场景：** 运营人员想比较每天各地区的流量、购买人数、收入、收入变化和当日排名；结果既要能在 Notebook 中检查，也可能需要导出供下游使用。

- 先写清最终一行代表什么、指标分子和分母来自哪些事件，再选择函数。
- 区分计算语义与展示方式：MySQL-compatible client、Notebook table 和 `SELECT INTO OUTFILE` 改变结果如何被消费，不改变 SQL 的 result grain。
- 将复杂问题拆成“筛选输入 → 派生维度 → 聚合指标 → 比较结果行 → 最终筛选与排序”的阶段。
- 对应 Lab：沿用 `events_modelled`，先观察单个 function 对行形状的影响，再构建综合查询。

#### 5.2 为什么 Doris 将 SQL Functions 分成这些类别

**需求场景：** 同一份 event data 可能需要逐行标准化、按组汇总、保留每日行计算趋势、展开集合、生成临时关系，或调用外部模型处理文本。函数分类帮助使用者在写 SQL 前判断其输入、输出和执行依赖。

- **Scalar Functions：** 每个输入行计算一个值，适合日期截取、字符串清洗、数值计算、条件表达式和复杂类型元素处理；通常不自行改变行数。
- **Aggregate Functions：** 对一个 group 的多行计算一个结果，适合 `COUNT`、`SUM`、去重计数和统计量；与 `GROUP BY` 一起改变 result grain。
- **Combinators：** 在已有 aggregate function 上组合额外行为，例如保存/合并 aggregate state，或按数组位置执行聚合。它们面向分阶段聚合、物化中间状态或数组聚合等专门场景，不是普通聚合查询的默认入口。
- **Analytic (Window) Functions：** 在相关行组成的窗口上计算，同时为每个输入结果行返回值，适合排名、累计值、移动窗口和前后行比较。
- **Table Functions：** 将当前输入行中的集合或字符串扩展为零到多行，通常与 `LATERAL VIEW` 使用；例如把一个 event 的 tags 或分隔字符串拆成可分组的行。
- **Table-Valued Functions（TVFs）：** 在 `FROM` 中产生一个可查询 relation，适合读取文件/外部数据、生成 `NUMBERS` 临时行集或查询系统元数据。它们不是对当前表的每一行做 scalar 计算。
- **AI Functions：** 通过 Doris AI Resource 调用外部模型，适合文本分类、抽取、情感分析、脱敏、翻译和摘要。该目录按能力来源分类，并非单一的行形状分类：多数 `AI_*` functions 表现为逐行调用，`AI_AGG` 则跨组聚合文本。
- 使用统一的 row-shape 主线串联后续章节：Scalar Function 可近似理解为“一对一”，为每个 input row 派生一个值；Aggregate Function 是“多对一”，把 group 中的多行折叠为一个结果；Table Function 是“一对多”，把当前一行中的集合展开为零到多行。随后用 CTE 表达这些阶段，再用 Window Function 在读取多行上下文的同时为每个保留行返回一个值。
- 说明“一对一/多对一/一对多”描述的是 function 对查询的贡献，不保证整个 statement 的最终行数；`WHERE`、Join 和 `GROUP BY` 仍会分别过滤、扩展或确定 groups。
- 解释这些类别为什么会有交叉：一个 aggregate function 加 `OVER` 后按 window semantics 工作；AI function 仍可能具有 scalar 或 aggregate 的行形状；Table Function 与 TVF 都返回多行，但前者依附输入行，后者自身提供 relation。
- 对应 Lab：扩展 function matching，使用小型 literal 展示 `EXPLODE` Table Function 与 `NUMBERS` TVF 的行形状；AI Functions 不执行，因为需要外部 AI Resource、网络、凭证并会产生外部调用成本。

官方分类入口：[AI Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/ai-functions/overview/)、[Scalar Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/)、[Aggregate Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/)、[Combinators](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/combinators/)、[Analytic Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/window-functions/overview/)、[Table Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-functions/)、[Table-Valued Functions](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/table-valued-functions/)。

#### 5.3 用 Scalar Functions 派生可解释的分析维度

**需求场景：** 原始 timestamp 需要转成报表日期或小时，region/event type 需要标准化，文本 pattern 需要被筛选，但原始 event grain 应保持不变。

- 使用日期函数表达日、周、月或小时 grain，避免把格式化字符串误当成时间 contract。
- 使用字符串函数完成 normalization、label generation 和 pattern matching，并区分三种目的。
- 说明 scalar expression 为每个输入行生成 derived value；它不会像 `GROUP BY` 一样自动折叠行。
- 不要求记忆完整 catalog，要求能从数据类型、所需变换和返回类型查找官方函数。
- 对应 Lab：并排展示 `TO_DATE`、`DATE_TRUNC`、`EXTRACT`、`REPLACE`、`UPPER`、`LIKE` 和 `REGEXP` 的输入与派生值。

#### 5.4 用 Aggregate Functions 回答定义清楚的指标问题

**需求场景：** 产品经理需要每日 event count、active users、purchase users、purchase revenue 和统计分布，并只保留达到业务阈值的产品或地区。

- 从指标 population 与 grain 选择 `COUNT`、`COUNT(DISTINCT ...)`、`SUM`、`AVG`、`MIN`、`MAX`、variance、covariance 或 correlation。
- 使用 conditional expression inside aggregate，让同一 grouped row 中的不同指标读取各自正确的事件子集。
- `WHERE` 在聚合前筛选 input rows，`HAVING` 在聚合后筛选 groups；把阈值放错位置会改变问题。
- `ANY_VALUE` 只在任意代表值都符合业务语义时使用，不能掩盖遗漏的 grouping dimension。
- Combinator 只在确有 aggregate-state、分阶段合并或数组逐位置聚合需求时引入，普通 event report 优先使用直接可读的 aggregate functions。
- 对应 Lab：展示 grouped metrics、`WHERE`/`HAVING`、合法与不合法的 grouped projection 以及 `ANY_VALUE` 的适用约束。

#### 5.5 用 Table Function 展开当前行中的值

**需求场景：** 一个事件中的 tags、MAP entries 或分隔字符串需要拆成多行，才能按其中的单个元素进行筛选、分组或统计。

- 使用 Table Function 与 `LATERAL VIEW` 展开当前行，例如 `EXPLODE(tags)` 或 `EXPLODE_SPLIT(text, delimiter)`；展开后必须重新确认 result grain 和重复计算风险。
- 在正文中使用 `>` 引用框简要澄清 Table Function 与 TVF：前者为每个当前输入行产生零到多行，后者自身作为 `FROM` 中的 relation source。Module 3 已详细介绍 S3 TVF，本节只用 `NUMBERS` 作最小对照，不重新讲解文件访问和持久化流程。
- 对应 Lab：用无外部依赖的小型值执行 `EXPLODE`，观察行展开、来源关联和 grain 变化；再以 `NUMBERS` 的短例子验证引用框中的 TVF 边界，不访问 S3。

#### 5.6 用 CTE 表达复杂分析的阶段

**需求场景：** 运营人员要查看每天各地区的全部事件、活跃用户、购买用户和收入，同时比较上一天收入、累计收入以及同一天的地区收入排名。

- 第一个 CTE 只选择目标时间范围并派生 `event_date`，让 input population 可检查。
- 第二个 CTE 按 `(event_date, region)` 聚合，使用 conditional aggregates 生成 event、user、purchase 和 revenue measures。
- 第三个阶段在 daily-region rows 上使用 `LAG`、累计 `SUM() OVER (...)` 和 `RANK`/`ROW_NUMBER`，保持 daily-region grain。
- 最外层只负责业务筛选和展示顺序，避免在同一层混合 detail filtering、aggregation 和 window filtering。
- 说明 CTE 提供可读的命名边界，并不自动物化，也不保证单独的性能收益。
- **Lab 可行性与落实：** `events_modelled` 已包含完成该场景所需的 `event_time`、`user_id`、`event_type`、`region` 和 `revenue`，且有 10,158,080 条 event rows；无需增加数据表。Lab 5 Section 9 已加入并实际运行这条多阶段 SQL，针对 2020-03-01 至 2020-03-03 产生 3 个日期 × 8 个地区的 24 行 daily-region 结果，并同时显示 event count、active users、purchase users、purchase revenue、previous revenue、cumulative revenue 和 daily rank。Section 7–8 的八行 daily query 作为 CTE 与 window semantics 铺垫，Section 9 再展示最终结果和每个阶段的 grain。
- **Course 写作要求：** 综合 SQL 应服务于同一个运营问题，并逐阶段标注 input/result grain；正文解释为什么分阶段以及如何选择 aggregate/window semantics，Lab 提供实际 SQL 与 24 行结果，不在 Course 重复整段可运行 Notebook 内容。

#### 5.7 用 Window Functions 比较行而不丢失行

**需求场景：** 已得到 daily-region metrics 后，还要回答“比昨天多多少”“截至今天累计多少”“当天该地区排第几”。这些问题仍要保留每个 daily-region row。

- 用 `PARTITION BY` 定义独立分析序列，用 window `ORDER BY` 定义前后关系，用 frame 定义当前行读取的范围。
- 用 `LAG`/`LEAD` 比较相邻结果行，用 aggregate-over-window 计算累计或移动指标，用 `ROW_NUMBER`/`RANK` 表达不同 tie semantics。
- 为需要确定顺序的窗口提供稳定 tie-breaker，并区分 window 内排序与最终 result ordering。
- 对应 Lab：在已聚合的结果上增加 previous、cumulative 和 rank columns，并验证窗口计算没有再次折叠行数。

#### 5.8 何时使用 UDF、UDAF、UDWF 或 UDTF

**需求场景：** 企业拥有 Doris built-in functions 无法表达的可复用规则，例如专有风险评分、跨行行业指标、自定义窗口状态或复杂文本拆分；也可能需要迁移已有 Hive Java functions。

- **User-Defined Function（UDF）：** 一行输入产生一个值，适合不可用内置函数表达的可复用逐行变换、验证或评分。
- **User-Defined Aggregate Function（UDAF）：** 多行维护并合并 state、每组产生一个结果，适合 Doris 无内置实现的行业聚合指标。
- **User-Defined Window Function（UDWF）：** 在窗口范围内为每行产生结果，适合需要自定义窗口 state/reset 逻辑的计算。
- **User-Defined Table Function（UDTF）：** 一个输入行产生零到多行并与 `LATERAL VIEW` 使用，适合自定义解析、拆分和展开。
- 先检查 built-in function、清晰的 SQL expression、Lambda/higher-order function 或 Alias Function；只有逻辑确实缺失且需要跨查询复用时才承担代码打包、部署、权限、资源和升级维护成本。
- Course 解释四种扩展与调用场景；Lab 保留非执行的 Java registration/lifecycle 模板，不构建 JAR，也不部署外部代码。Python UDF family 在 Doris 4.1.3 文档中标为 experimental，不作为本课程的默认生产路径。

官方延伸阅读：[Java UDF, UDAF, UDWF and UDTF](https://doris.apache.org/docs/4.x/query-data/udf/java-user-defined-function/)、[Python UDF family](https://doris.apache.org/docs/4.x/query-data/udf/python-user-defined-function/)。

Course 与 Lab 的职责边界如下：

- **Course：** 从结果 grain、输入/输出行形状、数据来源和复用需求解释函数类别以及 SQL 分阶段方法。
- **Lab：** 执行 built-in functions、Table Function、TVF、aggregation、CTE 和 window examples，并用 `events_modelled` 完成综合 SQL；不连接外部 AI provider，也不部署 UDF artifact。

### 模块 5 实验：使用 function 回答 event analytics questions

继续使用 Module 4 的 `events_modelled`。Lab 提供可直接运行的 SQL，并通过 function matching 和 guided query builder 增加互动；其他步骤以固定 SQL 和 expected results 解释概念，不要求学员从空白开始编写完整 SQL。

实验按以下路径组织：

1. **建立 function category mental model**：用一组可交互的 matching cards，根据输入、输出、行数变化和外部依赖匹配 Scalar、Aggregate、Combinator、Analytic (Window)、Table Function、TVF 和 AI Function。
2. **区分 Table Function 与 TVF**：使用小型 ARRAY literal 和 `LATERAL VIEW EXPLODE` 把一个 input row 展开成两行；使用 `NUMBERS` TVF 在没有 input table 的情况下生成四行 relation。
3. **转换时间与字符串字段**：固定 SQL 使用 `TO_DATE`、按小时 `DATE_TRUNC`、`EXTRACT`、`REPLACE`、`UPPER`、`LIKE` 和 `REGEXP`，在八行样本中并列展示原始值与 derived values。
4. **从 detail rows 得到 grouped metrics**：按 date 和 region 计算 event count、minimum/maximum purchase value 与 purchase revenue；conditional expression 区分所有 event 与 purchase-only measures。
5. **区分 input-row filter 与 group filter**：用一条同时包含 `WHERE` 和 `HAVING` 的查询，先筛选当天 purchase events，再保留达到 revenue threshold 的 product groups。
6. **理解合法与不合法的 grouped projection**：先展示“选择了未 grouping、未 aggregation 的 column”产生的错误，再在业务约束成立时使用 `ANY_VALUE`。
7. **用 CTE 表达一个命名阶段**：固定 SQL 使用 `daily` CTE 把 event rows 聚合到八行 daily results，先单独展示这些行。
8. **比较 aggregate function 与 window function**：复用相同 `daily` CTE，使用 `LAG`、`SUM() OVER (...)` 和 `ROW_NUMBER` 为八行 daily results 增加 previous revenue、cumulative revenue 和确定性排名。
9. **完成 daily-region 综合分析**：三个 CTE stages 从三天 event detail 生成 24 行 daily-region result，同时展示 event count、active users、purchase users、purchase revenue、previous revenue、cumulative revenue 和 daily rank，并标明每阶段 grain。
10. **体验 Lambda 和 higher-order function**：使用独立的小型 ARRAY literal 运行 `ARRAY_MAP(x -> ...)` 和 `ARRAY_FILTER(x -> ...)`，不修改 `events_modelled` schema。
11. **完成受引导的 business question challenge**：从 date grain、event filter 和 metric 中作出有限选择，由 Notebook 生成并展示最终 SQL。
12. **识别 user-defined function family boundary**：对比 UDF、UDAF、UDWF 和 UDTF 的行形状与场景，并保留非执行的 Java scalar UDF 注册模板；不构建 JAR 或部署外部代码。

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

### Module 6 Course 内容大纲（Join 场景驱动）

Course 6 先从“哪些业务对象需要被关联、哪些 unmatched rows 必须保留、关联后的一行代表什么”选择 logical Join，再从过滤后的输入大小、Join condition 和现有数据布局解释 Doris 如何让 matching keys 在同一执行位置相遇。正文先用业务保留要求覆盖 Doris 支持的 Inner、Left/Right/Full Outer、Left/Right Semi、Left/Right Anti、NULL-aware Left Anti、Cross 和 ASOF Join，再将 logical result 与 Hash/Nested Loop physical implementation 分开。Broadcast、Partition Shuffle、Bucket Shuffle 和 Colocate 分别用独立场景说明，避免只背策略名称。

#### 6.1 先确认业务关系与 Join 后的 grain

**需求场景：** event fact 需要补充 product category 和 brand，但维表可能缺失 product，也可能意外包含重复 product definitions。

- 在写 Join 前确认 Join key、左右表 grain 和 one-to-one、one-to-many 或 many-to-many relationship。
- 预测一条 fact row 能匹配多少 dimension rows；duplicate dimension keys 会放大 result rows，并可能重复计算 revenue。
- 把“补充属性”和“只检查是否存在”区分开，避免为 existence question 引入不需要的右表 columns 和 row multiplication。
- 对应 Lab：创建一行一个 product 的 `dim_products`，再用受控重复 Key 案例观察 row multiplication。

#### 6.2 从 unmatched-row requirement 选择 logical Join operator

**需求场景：** 分析人员可能只要已知产品的事件、要保留所有事件以发现缺失维度、要找孤儿 Key，或要完整盘点两侧所有对象。

- `INNER JOIN`：只保留两侧匹配的组合，用于仅分析已成功 enrichment 的事件。
- `LEFT`/`RIGHT OUTER JOIN`：保留指定一侧的 unmatched rows；另一侧 columns 对未匹配行表现为 `NULL`。
- `FULL OUTER JOIN`：两侧 unmatched rows 都属于答案时使用，例如双向 reconciliation。
- `LEFT`/`RIGHT SEMI JOIN`：只返回指定一侧存在匹配的行，适合 eligibility/existence 检查。
- `LEFT`/`RIGHT ANTI JOIN`：只返回指定一侧没有匹配的行，适合 orphan detection 或排除名单。
- `CROSS JOIN`：明确需要 Cartesian product 时使用，输出规模等于组合数量。
- `ASOF JOIN`：event 需要匹配相同业务 Key 下某个时间方向最近的状态，而不是要求时间戳完全相等。
- 对应 Lab：执行 Inner、Left Outer、Left Semi 和 Left Anti；其他类型由 Course 场景解释，避免为了目录完整而重复大表操作。

#### 6.3 明确 NULL 和过滤条件的业务语义

**需求场景：** 两张表的关联字段都可能为 `NULL`；有时 `NULL` 表示同一个“未知组”，有时表示根本没有可比较的 Key。

- 普通 `=` 不让两侧 `NULL` 相互匹配；只有业务明确要求把两侧缺失值视为同组时才使用 NULL-safe `<=>`。
- 区分 Anti Join 与含 `NULL` 的 `NOT IN`，并说明 NULL-aware Anti Join 解决的语义问题。
- Outer Join 中右表条件放在 `ON` 还是 `WHERE` 会改变 unmatched rows 是否被保留。
- 对应 Lab：用小表对比 `=` 与 `<=>`，并观察 Left Outer Join 的 unmatched row。

#### 6.4 从 Join condition 进入 physical Join implementation

**需求场景：** product enrichment 使用等值 product Key，而价格区间或时间范围匹配可能只有 non-equi condition。

- Equi-condition 可让 Doris 从一侧建立 hash table，再让另一侧 probe matching key；build/probe 是 Join operator 的执行角色，不等于表永久属性。
- 只有 range/non-equi condition 或 Cartesian relationship 时，可能使用 Nested Loop Join 比较候选组合。
- 先过滤和投影，再比较实际进入 Join 的 build/probe 数据量；原表总大小不是唯一依据。
- 对应 Lab：用 `EXPLAIN SHAPE PLAN` 对比 equi Hash Join 与小规模 non-equi Nested Loop Join。

**从逻辑语义到分布式执行的串联：** 6.2–6.3 先确定 logical result，回答哪些 matched/unmatched rows 被保留、`NULL` 如何匹配以及 predicate 在哪个阶段生效。6.4 开始回答两个 physical questions：单个 Join instance 用 Hash Join 还是 Nested Loop Join 寻找候选；多 BE 上 matching rows 如何到达同一个 Join instance。Broadcast、Partition Shuffle、Bucket Shuffle 和 Colocate 是第二个问题的数据分布策略，不是新的 logical Join type。

- 只有在数据和执行实例分布于多个 BE 时，跨节点 data movement 才成为这些策略的核心取舍；single-BE Lab 可以观察 plan label 和 local Exchange，但不能证明真实跨 BE network cost。
- 以三 BE 上 event rows 与 product rows 分散存放为例：如果相同 `product_id` 位于不同 BE，本地 Join 会漏掉匹配，因此必须复制一侧、按 Key 重分布，或复用预先对齐的 Bucket placement。
- Broadcast 保留大 probe side，只复制过滤和投影后足够小的 build side；每个参与实例都必须容纳完整 build copy，所以它不适合解决 large build side 的内存不足。
- Partition Shuffle 面向两侧都大且不能复制的 equi-Join：两侧按 Join Key 路由，每个实例只处理一个 Key partition，从而把 Hash Join state 分散到集群；代价是两侧网络传输，skewed Key 仍可能产生热点。
- Bucket Shuffle 复用一侧已有布局，只移动另一侧；Colocate 通过持久化布局契约让两侧 matching Buckets 预先同置。这两种策略比 general Partition Shuffle 更直接地减少 Join-time movement，但需要更严格的起始布局。

#### 6.5 Broadcast：小型 build side 到每个参与 Join 的执行位置

**需求场景：** 千万级 event fact 要关联经过过滤后只有少量 rows 的 product category dimension。

- 保持大型 probe side 在原位置，将完整的较小 build-side relation 发送到参与 Join 的 probe-side execution instances。
- 适合 build side 足够小，或 Shuffle key 严重倾斜而复制成本可接受的情况；广播成本会随参与实例增加。
- 不能把“dimension table”当成永久 Broadcast 规则：应看过滤、投影后的大小、Join type 支持和内存容量。
- 对应 Lab：默认计划对筛选后的 `dim_products` 使用 Broadcast，并在单 BE 中读取 plan shape；不声称测得多节点网络性能。

#### 6.6 Partition Shuffle：两侧按 Join key 重新分布

**需求场景：** 两张大表按不同方式存储，任何一侧都不适合复制，但相同 Join key 的 rows 必须在同一个执行分区相遇。

- 对两侧 Join input 计算相同的 Join-key hash 并通过 Exchange 重新分布，使相同 Key 路由到同一目标 partition。
- 适合 large-to-large equi-Join 且没有可直接复用的兼容布局；网络传输涉及两侧输入。
- Join-key skew 会让某些目标分区承受更多 rows，需要结合 statistics 和 Profile 判断，而不能只看平均值。
- 对应 Lab：Course 用多 BE 数据移动图和小型 Key 路由例子解释；single-BE Lab 只从计划对照说明 general Partition Shuffle，不模拟真实跨节点流量。

#### 6.7 Bucket Shuffle：保留一侧 Bucket 布局，只重分布另一侧

**需求场景：** 大型 event table 已按 `product_id` 的兼容 Hash 规则分桶，另一张表需要与这些既有 Bucket 对齐。

- 保留可用一侧的 Bucket/Tablet placement，将另一侧按 Join key 路由到对应 Bucket 的执行位置。
- 相比 general Partition Shuffle，只需要重新分布一侧，但要求保留侧的 Bucket column 与 Join key 满足策略条件。
- 对直接扫描的物理表场景，还要核对当前输入是否落在单个 Partition；Doris 4.x Join 文档的物理表适用条件不是“只要两表都 Hash 分桶”这么简单。若上游已有 `GROUP BY` 等 operator，则应根据该 operator 输出的实际 distribution 判断。
- “两表都按某列 Hash”不足以自动说明计划一定是 Bucket Shuffle；仍要检查 Join 方向、类型、Bucket 数、数据位置和 optimizer plan。
- 对应 Lab：`dim_products` 按 `product_id` Hash bucket；查询的时间 predicate 只读取 `events_modelled` 的一个月度 Partition；`[shuffle]` 对照计划在测试的 Doris 4.1.3 sandbox 中显示 `shuffleBucket`，用于读取计划证据。

#### 6.8 Colocate：通过建表契约让 matching Buckets 预先同置

**需求场景：** 两张经常 large-to-large Join 的表具有稳定的共同 Join key，值得在数据布局阶段承担更严格约束，以减少每次查询的数据移动。

- 两表加入同一 Colocation Group，并满足兼容的 bucket key、Bucket count、replica allocation 和稳定 placement，matching Buckets 才能在本地 Join。
- Colocate 的收益来自预先对齐的数据位置；它是持续 workload 的物理设计选择，不是单条 SQL 的通用 hint。
- 检查 group `IsStable` 和实际 plan；rebalance 或不满足契约时不能假定始终使用 colocated execution。
- 对应 Lab：Course 展示完整场景和布局要求；当前 Lab 不创建 Colocation Group，只说明为何单次 Broadcast/Bucket Shuffle plan 不能证明 Colocate。

#### 6.9 用 Runtime Filter 在 Scan 阶段减少 Probe candidates

**需求场景：** 千万级 `events_modelled` 只需关联 `category_1` 中的产品；dimension predicate 过滤后只剩部分 `product_id`，大量 event Keys 不可能产生 Join match。

- Doris 可以在执行时从过滤后的 build-side Join Keys 生成 Join Runtime Filter，并在 Join semantics 允许时将它应用到 probe-side Scan，让不可能匹配的候选 rows 不再进入后续 Hash Join。
- 适合 probe input 大、build-side predicate 具有选择性、Runtime Filter 能及时到达 Scan，且减少的 Scan/Exchange/probe work 足以抵消 filter 创建、合并、分发和应用成本的场景。
- 当 probe input 已很小、build Keys 覆盖大多数 probe Keys、filter 到达太晚，或 Bloom Filter 因近似匹配让部分不匹配候选通过时，收益可能有限；optimizer 也可能裁剪缺乏选择性的 Runtime Filter。
- Runtime Filter 不改变 Join result semantics，也不是第五种 Join distribution strategy。Broadcast、Partition Shuffle、Bucket Shuffle 和 Colocate 决定数据在哪里相遇；Runtime Filter 尝试减少到达这些 operator 的候选 rows，同一个计划可以同时包含 Broadcast 与 Runtime Filter。
- 对应 Lab：`d.category = 'category_1'` 先限定 build-side product Keys；Profile 随后显示 `events_modelled` Scan 上具体 RF 的 input/filtered rows，以及有多少 rows 到达 Hash Join probe path。

#### 6.10 从 EXPLAIN 和 Profile 区分计划与实际效果

**需求场景：** optimizer 选择了某种 distribution，并计划从 build-side Keys 生成 Runtime Filter；需要判断这是计划安排，还是运行时确实减少了 probe rows。

- FE creates and optimizes a distributed query plan and assigns plan fragments；BE nodes execute the assigned plan fragments。
- `EXPLAIN SHAPE PLAN` 用于识别 Join type、condition、distribution、Exchange 和 Runtime Filter producer/consumer。
- Query Profile 用于查看实际 build/probe rows、数据移动与 Runtime Filter counters；计划中 `apply RFs` 不能证明过滤比例。
- Runtime Filter 从 build-side values 生成，可在语义允许时下推到 probe-side Scan；它用于减少候选 rows，不能代替最终 Join equality check。
- `[broadcast]`、`[shuffle]` 等 hint 只用于有计划与运行证据的比较，不作为业务 SQL 的默认配方。
- 对应 Lab：执行当前 Join，裁剪展示 `events_modelled` Scan 的 RF input/filtered rows、`RowsProduced` 与 Join `ProbeRows`，同时明确 `ScanRows` 不等于避免读取的行数。

Course 与 Lab 的职责边界如下：

- **Course：** 用明确的数据规模、布局、匹配语义和保留要求解释 logical Join 与四种 distribution strategy 的适用场景。
- **Lab：** 执行主要 Join semantics，观察重复 Key 和 NULL 行为，并读取 Doris 4.1.3 的 Broadcast、Bucket Shuffle、Runtime Filter 计划与 Profile；不把单 BE 时间用于排名多节点策略。

### 模块 6 实验：Joining Data in Apache Doris

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
- [MERGE INTO](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/MERGE-INTO/)
- [Delete Operation](https://doris.apache.org/docs/4.x/data-operate/delete/delete-manual/)
- [INSERT OVERWRITE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/INSERT-OVERWRITE/)

### Module 7 Course 内容大纲（状态变化与生命周期场景驱动）

Course 7 先回答为什么分析系统仍然需要更新和删除：订单、客户、库存和权限等业务实体会变化，Change Data Capture（CDC）会持续同步这些变化，纠错与合规请求也会改变已经写入的数据。课程再根据变化由什么数据表达、影响多少 Key 或 Partition、发生频率以及是否需要原子切换，选择 Doris 的写入路径。

#### 7.1 为什么实时分析需要 current-state 更新和删除

**需求场景：** event history 要保留每次行为，但运营报表还必须看到订单的最新状态、客户当前等级、取消记录以及合规删除后的结果。

- 区分 append-only history 与 current-state table：前者回答发生过什么，后者回答现在是什么。
- 上游 OLTP insert/update/delete 通过 CDC 到达 Doris 时，需要明确 target Key、操作类型和 source ordering contract。
- 更新场景包括持续状态同步、晚到/乱序事件、批量字段补丁和一次性数据纠错；删除场景包括 CDC delete、条件删除、数据过期和 Partition backfill。
- 先定义期望的最终可见状态，再选择 DML 或 load path；不能把所有变化都建模成重复日志后要求查询自行猜测最新行。
- 对应 Lab：使用独立的 order current-state tables，不修改 `events`、`events_modelled` 或 `dim_products`。

#### 7.2 用 Unique Key upsert 同步完整状态

**需求场景：** 上游每次发送订单的一条完整当前状态；已有 `order_id` 应更新，不存在的 Key 应插入。

- Unique Key 的 full-row upsert 根据 Key 自动区分 insert 和 replacement，适合批量完整状态或 CDC full image。
- 当变化可能乱序到达时，用 Sequence column 表达 source order；较大的 source version/timestamp 决定同一 Key 的可见状态，而不是简单按到达顺序。
- Sequence column 是显式 schema contract；普通 timestamp column 不会自动产生版本胜出语义。
- 对应 Lab：`order_state` 以 `order_id` 为 Unique Key、`updated_at` 为 Sequence column，展示新 Key 插入、已有 Key 更新和晚到旧状态不生效。

#### 7.3 当来源只拥有部分字段时使用 partial column update

**需求场景：** 物流系统只拥有 `status` 和 `updated_at`，不应覆盖支付系统维护的 amount 或客户系统维护的 region。

- Full-row upsert 中省略的 value columns 按 schema 使用 default 或允许的 `NULL`，不会自动保留旧值。
- Partial column update 对已有 Key 保留未提供的 columns，只更新输入包含的字段；遗漏字段与显式写入 `NULL` 含义不同。
- 单独决定 new Key 在 partial update 中应报错还是按配置补齐后插入，不能把 existing-key semantics 套到不存在的 Key。
- 对应 Lab：并排比较 full-row upsert 与 partial update 对省略 amount/region 的不同结果。

#### 7.4 用 SQL UPDATE 修正由 predicate 选出的少量数据

**需求场景：** 一小批客户或订单的分类值错误，可以用 SQL condition 找到，但没有外部 replacement records。

- SQL `UPDATE ... SET ... WHERE ...` 直接表达一次性、低频、predicate-based correction，并保留未在 `SET` 中指定的 value columns。
- `UPDATE` 面向 Unique Key target 且只能修改 value columns；业务 Key 变化应表达为删除旧 Key、插入新 Key。
- 高频逐行 `UPDATE` 会引入重复 transaction/write 开销，持续变化应优先批量 load-based update。
- 对应 Lab：用 `WHERE order_id = 1001` 修正一个 `shipping_region`，并检查其他 value columns 与其他 Key 不受影响。

#### 7.5 用 MERGE INTO 统一处理来自 source relation 的多种变化

**需求场景：** 一个 staging table 或 source subquery 同时包含新增、修改和删除标记，希望按 target/source matching condition 在一条 statement 中分别处理。

- `MERGE INTO target USING source ON ...` 以 Join 结果选择 action：`WHEN MATCHED` 可 `UPDATE` 或 `DELETE`，`WHEN NOT MATCHED` 可 `INSERT`；可用附加 predicate 区分不同 change types。
- Target 必须是 Unique Key table；source 可以是 table 或 subquery。它适合已有 source relation 且需要 set-based matched/not-matched logic 的批处理同步。
- 它与简单 upsert 的区别在于可以根据 match 与业务条件选择不同 action；与流式 load-based CDC 的区别在于它是一条基于 source relation 的 DML statement。
- 必须保证一次 Merge 中 source matching 对 target Key 是确定的。Doris 4.x 文档指出 duplicate join rows 不会被检测，发生时行为未定义；应在 source stage 先按业务顺序去重或拒绝冲突。
- **Course 写作要求：** 使用一组很小的 target/source rows 先预测 matched update、matched delete 和 not-matched insert 的最终状态，再给出一条紧凑的 `MERGE INTO` 示例；重点解释 action selection 与 source uniqueness，避免把它写成单纯的语法目录。
- **Lab 衔接：** `lab7_update_delete_data.ipynb` 使用 Module 7 专用的本地 target 和 staging tables，先验证 source 对 target Key 唯一，再执行 matched update、matched delete 和 not-matched insert；不接入外部 CDC 系统。

官方参考：[MERGE INTO](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/data-modification/DML/MERGE-INTO/)。

#### 7.6 根据删除信息的来源选择 predicate DELETE 或 Delete Sign

**需求场景：** 维护任务要求删除所有 `category = 'test'` 的 rows；另一条 CDC stream 直接带来被删除的 customer Keys。

- Predicate `DELETE` 适合 SQL condition 定义目标 rows 的场景；Table Model 不同会有相应 condition restrictions。
- Delete Sign 适合 Unique Key batch/CDC 输入已经携带 deleted Keys 的场景，让删除与其他输入记录通过 load path 同步。
- 写 `NULL`、省略所有 value columns 或普通 full-row upsert 都不等于删除 logical row。
- `__DORIS_DELETE_SIGN__` 是输入可携带的 hidden marker，不是内部 delete bitmap。
- 对应 Lab：分别用 predicate `DELETE` 和 incoming Delete Sign 删除两个受控订单，再用普通查询和 hidden column view 观察结果。

#### 7.7 根据变化范围选择 TRUNCATE 或 INSERT OVERWRITE

**需求场景：** 一整个旧日期 Partition 已过期；另一个日期 Partition 有一份完整修正数据，需要在读者持续看到一致内容的情况下整体替换。

- `TRUNCATE TABLE/PARTITION` 适合完整 scope 不再需要的生命周期删除，避免为每行生成 predicate delete work。
- `INSERT OVERWRITE` 适合用完整 replacement dataset 原子替换 table 或指定 Partitions；未出现在 replacement 中的旧 rows 不会保留。
- 先 truncate/delete 再 reload 是多个操作，中间可能出现 empty 或 partial interval；普通 `INSERT INTO` 对 Duplicate Key table 只是追加。
- 对应 Lab：清空过期 `p20260910`，再用 `INSERT OVERWRITE` 替换 `p20260911` 并展示前后结果；atomic reader guarantee 来自官方机制，当前 Lab 不执行并发读取测试。

#### 7.8 区分逻辑可见性与物理清理

**需求场景：** 删除或 upsert 已发布，新的普通查询已看到新状态或不再返回旧 Key，但磁盘使用量没有立即下降。

- Merge-on-Write（MoW）发布新版本后改变后续查询的 logical visibility；无需等待 Compaction 才能看到获胜状态。
- 旧 row versions 可以继续占用存储，之后由 background Compaction 回收；查询结果不能证明物理空间已经释放。
- 区分 ordinary query、hidden Delete Sign、Tablet metadata、internal delete bitmap 和 physical Rowset/Segment，各自能支持的结论不同。
- 高频小事务会增加 transaction、version 与 Rowset pressure；持续变化应批量化，整 Partition 变化应使用对应 lifecycle operation。
- 对应 Lab：观察 visible rows、Tablet Version/VersionCount/RowCount 和 Delete Sign；不声称 Notebook 直接展示 delete bitmap 或 Compaction 回收。

Course 与 Lab 的职责边界如下：

- **Course：** 从同步 contract、source ordering、字段所有权、选择方式和变化范围解释 upsert、partial update、`UPDATE`、`MERGE INTO` 与删除/替换路径。
- **Lab：** 在 Doris 4.1.3 专用小表中展示状态胜出、省略列、predicate correction、基于 staging relation 的 `MERGE INTO`、key-based deletion 和 Partition lifecycle；不连接外部 CDC。

### 模块 7 实验：维护 current order state

使用 `doris_course` 中五个独立的小表，保留 Module 1–6 的 `events`、`events_modelled` 和 `dim_products`。当前 Notebook 按六个主体步骤组织：

1. **建立 current-state contract 并执行 upsert**：创建 `order_state`，以 `order_id` 为 Unique Key、`updated_at` 为 Sequence column。已有 `1001` 更新为 `shipped`，新 Key `1004` 插入；晚到的较小 Sequence 不覆盖新状态，阶段结束有四个逻辑订单。
2. **比较遗漏列的含义**：重置两行后，full-row upsert 让 `1002` 的 amount/region 使用默认值；partial column update 只提供 `1003` 的 Key、status、updated_at，保留其他已有值。结束后恢复 partial-update session variable 为 false。
3. **进行 SQL correction**：再次恢复两行，修改 `1001` 的 `shipping_region`，对比前后值。该阶段不改变 `updated_at`；不执行 Key-column UPDATE 或非 Unique Key target 的失败案例。
4. **合并 staging change set**：创建 `order_merge_target` 和 `order_merge_changes`。先比较 source row count 与 distinct `order_id`，确认每个 target Key 只有一个 source row；随后用一条 `MERGE INTO` 更新 `4001`、删除 `4002`、保留未匹配的 `4003` 并插入 `4004`。
5. **删除并观察可见性**：独立 `order_deletions` 不配置 Sequence。分别对 `2003` 执行 predicate DELETE、向 `2002` 写入 Delete Sign，普通查询只剩 `2001`。同节展示 Tablet Version/VersionCount/RowCount 和隐藏标记；不直接展示 delete bitmap、物理 Rowset/Segment 或 Compaction 空间回收。标记不保证在后台清理后仍可查询。
6. **选择 Partition lifecycle operation**：`order_lifecycle` 仅演示 `TRUNCATE TABLE ... PARTITION(...)` 和 `INSERT OVERWRITE`，不在此表执行 predicate DELETE。先清空 `p20260910`，再把 `p20260911` 替换为 `3003`、`3005`。Notebook 展示前后结果，不运行并发读验证 atomic switch。

可选 restart 检查的 `order_state` 保留第 3 节恢复的两行。Temporary Partition、恢复、new-key partial-update policy、并发和相同 Sequence 冲突由 course 说明边界，不作为当前 Lab 的已执行步骤。

实验结束时，学员应能针对“订单状态更新、晚到 CDC event、单列修正、批量主键删除、过期 Partition 清理和 Partition backfill”分别说明选择哪一种 path，以及为什么不使用其他 path。所有修改均限制在 Module 7 专用 tables 中。

## Interactive quizzes

Each quiz contains six independent English single-choice questions and uses the shared `doris_course.quiz` interface. No running Lab or external service is required.

- Module 4: [Notebook](module04-modeling/quiz4_schema_and_modeling_choices.ipynb) · [Question YAML](module04-modeling/quiz4_schema_and_modeling_choices.yaml)
- Module 5: [Notebook](module05-analyzing/quiz5_analytical_query_semantics.ipynb) · [Question YAML](module05-analyzing/quiz5_analytical_query_semantics.yaml)
- Module 6: [Notebook](module06-joining/quiz6_join_semantics_and_execution.ipynb) · [Question YAML](module06-joining/quiz6_join_semantics_and_execution.yaml)
- Module 7: [Notebook](module07-updating-deleting/quiz7_state_changes_and_deletion.ipynb) · [Question YAML](module07-updating-deleting/quiz7_state_changes_and_deletion.yaml)

[Question alignment and course review notes](quiz_alignment.md)
