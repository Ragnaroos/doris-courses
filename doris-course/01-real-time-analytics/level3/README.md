# Level 3：分析数据的查询加速、分布与生命周期管理

本大纲供课程开发者参考，使用中文编写；后续面向学员的课程正文（Course）、实验（Lab）和测验（Quiz）仍使用英文。Doris 官方术语、SQL 标识符、配置项和文件名保留原文，以便与前两级课程及官方文档对照。

Course 大纲只保留可迁移的业务问题、选择条件、机制和证据边界；固定表名、事件 ID、行数、金额、容器地址及某次运行的计划或 Profile 数值只写在对应 Lab 大纲中。课程可以沿用 `event_time`、`user_id`、`product_id` 等统一业务字段举例，但不能让通用结论依赖某一批实验数据。

Level 3 延续 Level 1–2 已建立的电商分析流程：

```text
在保持分析结果正确的前提下减少查询工作量
    → 分布数据并维持可用副本
    → 随时间演进、保留和恢复数据
```

**当前状态：Module 8–10 的 Course、Lab 与 Quiz 均已实现；Lab 关键路径已在本地 Doris 4.1.3 验证。** [Module 8 Course](module08-query-acceleration/course.md)、[Module 9 Course](module09-sharding-replication/course.md)、[Module 10 Course](module10-managing-data/course.md)、[Lab 8](module08-query-acceleration/lab08_accelerate_queries.ipynb)、[Lab 9](module09-sharding-replication/lab09_observe_sharding_and_replication.ipynb) 与 [Lab 10](module10-managing-data/lab10_manage_data.ipynb) 使用英文；每个 Module 另有一个英文交互式 Quiz Notebook 和一份本地 YAML 题库。本文件保留中文开发大纲，并以实际 Lab 顺序记录目的、预期结果和证据边界。Lab 10 跨整点的自然过期步骤仍取决于运行时钟和 Dynamic Partition 调度周期，不能把局部验证写成每次都已完成整本回归。

技术基线为 Apache Doris 4.x，实验目标版本为 4.1.3。所有版本敏感行为必须通过后文列出的验证，才能写成实验的预期结果。

## 与 Level 1–2 的衔接

| 已有基础 | Level 3 新增内容 |
| --- | --- |
| 模块 2：存储层级、排序键、Prefix Index、Partition/Tablet 裁剪 | 选择额外的加速结构，分别验证构建完成、计划选用和运行收益 |
| 模块 3：导入事务、重试安全、Group Commit | 在选择加速方案和诊断运行状态时考虑写入与维护成本 |
| 模块 4：数据粒度、Table Model、类型化明细、汇总、Auto Partitioning | 比较手动填充的汇总表与自动维护的物化视图，把布局设计连接到实际放置和保留策略 |
| 模块 5：分析粒度、聚合、公共表表达式（Common Table Expression，CTE）、窗口函数 | 在复用计算时保持查询语义 |
| 模块 6：逻辑 Join、物理实现、分布策略、Runtime Filter | 检查多 BE 放置、稳定的 Colocation Group 和实际分布式执行 |
| 模块 7：更新、删除、清空、覆盖、逻辑可见性 | 管理结构演进、时间范围、可恢复的对象删除及恢复边界 |

所有环境统一使用 Database 名称 `doris_course`。隔离集群中的 `doris_course` 是该集群自己的数据库，同名不表示共享数据。

Frontend（FE）负责创建和优化分布式查询计划，并分配计划片段；Backend（BE）节点执行分配到的计划片段。沿用前两级课程中的 Table Model、Duplicate Key model、Unique Key model、Aggregate Key model、Partition、Bucket、Tablet、Runtime Filter、Query Profile、build side / probe side、Broadcast、Partition Shuffle、Bucket Shuffle 和 Colocate 等术语。Key columns 的职责按 Table Model 解释，不能一概视为传统主键约束。

## 场景驱动的课程写作约定

Level 3 不按“功能定义→语法清单”组织 Course。每个 Module 使用一条连续的电商分析业务主线：前一阶段的结果或限制引出下一个决策，不为每个小节重新编造一个无关故事。每章优先按以下顺序展开：

```text
业务或运维状态发生变化
    → 明确新的正确性、新鲜度、性能或可用性约束
    → 比较候选方案及成本
    → 解释 Doris 的相关机制
    → 说明 metadata、EXPLAIN、Query Profile 或业务结果各能回答什么
    → 限定当前证据不能支持的结论
    → 由尚未解决的问题进入下一节
```

- Course 负责让学员知道“为什么现在需要做选择”、“用什么条件选择”和“当前证据允许什么结论”。
- Lab 使用可重复的 Doris 操作提供证据，不重复 Course 的长段机制说明，也不把一次实验的固定数字写成通用结论。
- Quiz 换用新场景检查学员能否迁移决策方法，不要求记忆 Lab 的表名、行数、金额、Tablet ID 或 Profile 计数。
- Partition、Bucket、Tablet、Replica 的数量关系，Fragment 层次，列编码与 Page 压缩等内容可以作为主线中的直接技术解释，不必为每个概念另造场景。

## 模块 8：在 Apache Doris 中加速查询

已实现课程：[Module 8 Course](module08-query-acceleration/course.md)。

### 模块目标

从重复计算、选择性访问和数据新鲜度要求出发，选择查询加速方案。同时解释减少的查询工作量，以及额外的存储、写入、刷新和运维成本。

### 场景与逻辑主线

电商分析团队需要在同一份事件历史上同时提供收入面板和产品明细调查。课程不把 View、Materialized View 和索引并列成功能清单，而是让报表工作量逐步变化：

| 主线阶段 | 业务变化 | 当前决策 | 证据与下一步 |
| --- | --- | --- | --- |
| 8.1 | 面板结果正确，但运行频率和计算成本上升 | 先固定人口、粒度、指标和新鲜度，不先选功能 | 建立可对账的 baseline，才能判断后续加速是否改变语义 |
| 8.2 | 多个面板重复书写同一 purchase 定义 | 用 regular View 共享逻辑，但不把它当成结果存储 | 结果一致后仍观察到底表工作，从而引出预计算结果 |
| 8.3 | 单表地区汇总重复执行，且写入后必须立即可见 | 在受支持的 SQL scope 内选择 synchronous MV | 分开检查构建、计划选用和写入后答案，再进入多表计算 |
| 8.4 | 品类报表需要重复 Join 事件和产品属性，业务接受明确的 refresh lag | 使用 asynchronous MV，显式定义刷新和陈旧边界 | 源答案、存储答案、Task 状态和透明改写分开验证 |
| 8.5 | 新面板改变粒度或要求 distinct buyers | 判断已保存的维度和可加指标是否足以推导目标查询 | 一个改写成功、一个因状态缺失而回到明细，说明 MV 不是通用缓存 |
| 8.6–8.7 | 用户从汇总下钻到非主要排序列的选择性明细，或可用结构未被选中 | 按谓词选索引，并先检查统计信息和谓词形态 | metadata 说明结构存在，`EXPLAIN` 说明计划，Profile 说明实际过滤 |
| 8.8 | 加速结构已能减少部分读工作，但写入、刷新和存储成本持续存在 | 按查询频率、延迟目标、新鲜度和维护成本决定是否保留 | 记录决策假设；本地加速不回答多节点容量和可用性，进入 Module 9 |

### 学习目标

完成本模块后，学员应能够：

1. 在选择加速功能前，明确结果正确性、新鲜度、查询频率和资源限制。
2. 区分普通视图、显式维护的汇总表、同步物化视图和异步物化视图。
3. 根据查询形态与新鲜度选择物化方案，并考虑维护和存储成本。
4. 解释为什么创建了某个结构，并不能证明查询实际使用了它。
5. 根据谓词语义和选择性选择 Inverted Index 或 BloomFilter Index，并区分它们与内置裁剪结构。
6. 区分持久化的 BloomFilter Index 与 Join Runtime Filter。
7. 使用结果核对、`EXPLAIN` 和明确算子范围的 Query Profile 证据评估受控变化。
8. 识别在增加存储结构前，是否应先处理查询形态、统计信息或数据分布问题。

### 课程内容大纲

#### 8.1 先定义正确答案和需要减少的工作

**需求场景：** 仪表板结果正确，但查询频率增加后成本不断上升。

- 明确输入数据范围、输出粒度、指标、新鲜度和负载频率。
- 先定义报表人口：直接读取事实表与通过维度表 Inner Join 的报表可能覆盖不同记录。无法匹配维度的事实行会被 Inner Join 排除，因此比较结果前必须先确认两条查询是否使用同一输入范围；不能把查询人口差异误判为加速结构丢失数据。
- 使用模块 2、6 已介绍的概念，定位可能需要减少的扫描、Join、聚合和 Exchange 工作。
- 区分结果错误、计划不合理、实际工作量过大，以及受噪声影响的总耗时；建立“完整结果对账 → `EXPLAIN` 选择 → Query Profile 实际计数”的证据顺序，不以配置项清单或单次耗时开场。
- **实验衔接：** 建立结果可核对的基线，在修改本模块对象之前保留计划和 Query Profile。

#### 8.2 复用查询逻辑，不把逻辑复用当成结果存储

**需求场景：** 多个面板需要共享同一个购买收入定义。

- 普通视图用于复用查询逻辑，CTE 用于单条语句内部的逻辑组织；定义本身不代表持久化计算结果。
- 解释普通 View 展开后通常仍访问其底层表：View 名称出现在 SQL 中，不表示 Doris 读取了另一份已计算数据。应以实际计划和扫描 Profile 判断它复用的是查询定义，还是确有其他物化访问路径。
- 与模块 4 手动填充的汇总表对照：它存储预计算数据，但现有填充过程没有建立自动刷新关系。
- 在明确重复计算需求后，再引入需要持续维护的预计算结果。
- **实验衔接：** 比较本模块普通视图与其定义查询的结果；结果相同不能证明发生了缓存或物化。

#### 8.3 让受支持的单表汇总与写入保持一致

**需求场景：** 反复执行的聚合必须反映基表已经提交的变化。

- 从新鲜度要求引入同步物化视图。
- 明确视图定义受到表达式、聚合函数和 Table Model 支持范围的限制，不承诺任意 SQL 或 Join 都适用。
- 区分初始构建、后续写入维护和优化器选择 rollup/index；同步物化视图作为基表下的物化索引参与计划选择，并不是查询 SQL 显式改成了另一张独立表。同时说明额外存储与导入维护开销。
- 用一条带唯一业务标识、可安全重跑的已知写入解释同步维护：业务结果的预期增量证明提交后的答案改变，计划继续选择物化索引证明访问路径没有退回基表；两项证据必须分开陈述，具体标识和增量留给 Lab。
- **实验衔接：** 在本模块的 Duplicate Key 表上创建受支持的视图，等待构建完成，检查计划选中的扫描索引，并在追加本模块数据后核对基表查询结果。

官方参考：[同步物化视图](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/sync-materialized-view/)。

#### 8.4 用明确的新鲜度取舍复用多表计算

**需求场景：** 品类收入需要反复连接事件和产品属性，报表允许一定刷新延迟。

- 引入异步物化视图，并明确刷新约定。
- 区分直接查询视图中的存储数据，与对基表查询进行透明改写；关闭 rewrite 后比较源 Join 与存储结果，避免查询视图时又被优化器改写而形成循环论证。
- 比较手动与定时刷新、全量与满足条件的分区增量刷新；维度变化同样会影响新鲜度。
- 用维度属性重分类说明陈旧性：源查询已经把相关事实移动到新的分类，但手动 COMPLETE refresh 前，异步视图仍保存旧分类结果；refresh Task 成功后再用全部分组对账确认追平。Task 成功、数据新鲜和透明改写是三个不同状态，具体分类名、行数和金额留给 Lab。
- **实验衔接：** 使用本模块的事实表和维度表副本，演示手动刷新、源数据变化及刷新后的对账。核实一致性配置之前，不预先规定过期视图的改写行为。

官方参考：[物化视图选型](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/overview/)、[异步物化视图概述](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/overview/)、[管理与查询](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/functions-and-demands/)。

#### 8.5 验证预计算结果能否回答当前查询

**需求场景：** 物化视图已经存在，但仪表板仍然执行原有工作。

- 检查请求的粒度、维度、谓词以及指标是否能够从视图推导。
- 复用此前的语义区分：若异步视图保存分类、地区、`COUNT(*)` 与 `SUM(revenue)`，优化器可以把可加指标继续汇总到更高粒度；若它没有保存 `user_id` 或可合并的去重状态，就不能从该视图推导 `COUNT(DISTINCT user_id)`，必须读取保留所需明细的来源。
- 区分构建或刷新成功、满足改写条件、优化器实际选用，以及执行工作量减少。
- **实验衔接：** 各选择一个满足条件和一个刻意超出范围的查询，检查实际计划、比较完整分组结果、读取相关扫描和聚合计数。没有命中改写也是需要解释的观察结果。

#### 8.6 不替换主要排序方式，也能定位选择性明细

**需求场景：** 面向时间查询的事件表中，产品标识不是排序键的前导列，但调查需要按产品筛选。

- 简要说明 Partition、Bucket、Prefix Index 和 ZoneMap 过滤后剩余的工作，不重复实验 2 的布局重建。
- 以不分词的 Inverted Index 作为主要二级索引示例。
- 解释倒排索引是 Segment 内从列值到 Row ID bitmap 的额外结构：`product_id=某值` 先得到该 Segment 中可能匹配的行位，再由 Scanner 读取需要返回的列。它不改变 Partition、Bucket 或 Tablet 归属，也不是 MySQL 聚簇/非聚簇 B-tree 的同义词。
- 比较适用于等值或 `IN` 谓词的 BloomFilter Index，说明假阳性和数据块内的值分布，不能只看列基数。
- 分词搜索与 NGram BloomFilter 仅作为有限的选型对照：词项匹配和子串匹配回答的问题不同。
- 说明历史数据的索引构建覆盖范围，以及存储和写入开销。
- **实验衔接：** 本模块有索引和无索引的表保持相同行、结构、分布和排序，只改变 `INDEX ... (product_id) USING INVERTED`；核对业务结果、扫描表/索引身份、`RowsInvertedIndexFiltered` 与 `ScanRows`。Lab 只直接验证数值等值谓词和不分词倒排索引；BloomFilter、分词搜索及 NGram 仅在 Course 做选型边界，不写成 Lab 已验证结论，也不承诺固定加速倍数。

官方参考：[倒排索引](https://doris.apache.org/docs/4.x/key-features/inverted-index/)、[布隆过滤器索引](https://doris.apache.org/docs/4.x/table-design/index/bloomfilter/)、[索引选型](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/optimizing-table-index/)。

#### 8.7 在强制计划前检查优化器的输入

**需求场景：** 可用结构没有被选中，或输入规模估算明显不合理。

- 使用提示前，先检查相关统计信息和谓词形态。
- 说明统计信息用于估算，不是实际运行的行数。
- 统计信息应针对当前查询依赖的表和列采集，不把“对整个共享数据库执行维护操作”写成普通调优步骤；Join 顺序和 Runtime Filter 机制回顾模块 6。
- **实验衔接：** 记录统计信息与选中计划，不假定采集统计信息后计划一定改变。

官方参考：[统计信息采集与管理](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/statistics/)。

#### 8.8 判断查询收益是否值得维护成本

**需求场景：** 某个结构帮助了一个面板，但占用了存储和维护资源。

- 比较反复查询节省的工作与构建、写入、刷新、存储成本。
- 为观察查询实际执行的扫描与计算，应记录 Profile 级别并控制可能复用先前结果或过滤信息的会话缓存，采集结束或失败后恢复原设置；未清空操作系统和存储层缓存时，不能把结果描述为冷缓存性能基准。具体会话变量由 Lab 展示，不要求学员在 Course 中记忆配置清单。
- 保留算子身份、单位和计数汇总范围；不累加重叠计时，也不只按等待时间判断瓶颈。
- 用证据支持最终选择，并说明尚存的不确定性。
- **模块过渡：** 本地查询加速不能证明多节点容量、放置和可用性，模块 9 接着解决这些问题。

### 模块 8 实验：验证查询加速方案

实验文件：[Lab 8 Notebook](module08-query-acceleration/lab08_accelerate_queries.ipynb)。实验复用 Level 1–8 的单节点 `doris-rta` 容器和 `doris_course` Database；只读取 `events_modelled` 与 `dim_products`，所有可变对象均使用 `m08_*` 名称。以下编号严格对应 Notebook 的执行顺序。

0. **Initialize the Lab。**
   - **目的与数据环境：** 从课程根目录或模块目录定位 `doris_course/`，加载共享 `DorisLab` 并创建 `lab`；该单元格不启动 Docker、不连接 Doris、也不修改任何表。内核重启后只需先重跑这里。
   - **期望结果：** Python 初始化完成且没有 Doris 查询输出。
   - **说明：** Notebook 的路径解析与共享 helper 可从课程根目录启动 Jupyter，也可从 VS Code 直接打开模块 Notebook。

1. **Section 1A：检查上游事件和产品数据。**
   - **目的与数据环境：** 连接已有的单节点 `doris-rta`，要求 Lab 4 已创建 `events_modelled`、Lab 6 已创建且填充 `dim_products`；只检查 `[2020-03-01, 2020-03-02)` 左闭右开范围和产品表非空，不下载数据。
   - **期望结果：** `events_modelled` 在该范围内为 **75,259** 行，`dim_products` 行数大于零；不满足时立即提示先完成对应前置 Lab。
   - **说明：** 这一步只确认后续实验所需的最小数据环境，不把行数检查说成逐字段完整性验证。

2. **Section 1B：清理并重建 Module 8 自有表。**
   - **目的与数据环境：** 等待旧物化视图任务结束，删除旧的 `m08_async_category_metrics`、`m08_purchase_view`、同步索引所属基表及四张 `m08_*` 表；从前置表复制一天事件到 Duplicate Key 表 `m08_events`，复制被事件引用的产品到 Unique Key 表 `m08_products`，再同步采集统计信息。上游 `events_modelled` 和 `dim_products` 保持不变。
   - **期望结果：** 两张自有表创建并装载成功；Left Anti Join 返回 **501** 条没有产品匹配的 purchase 事件。
   - **说明：** 501 条事件都来自 Lab 6 刻意排除的产品 `1005115`，不是复制失败。地区报表直接读事件表会包含它们；后续类别报表使用 Inner Join 会排除它们，因此两类报表总量不必相等。

3. **Section 2A：用普通 View 复用 purchase 定义并比较答案。**
   - **目的与数据环境：** 在已准备的 `m08_events` 上创建 `m08_purchase_view`，分别执行直接带 `event_type='purchase'` 的地区报表和通过 View 的同义报表；Profile 捕获期间临时关闭 SQL Cache、Query Cache 和 Condition Cache，并在结束或失败后恢复会话设置。
   - **期望结果：** 两个结果都包含八个地区且逐行完全一致；固定数据中 `region_01` 为 2,319 条 purchase、收入 732,977.08。
   - **说明：** 普通 View 成功复用了筛选逻辑并保持语义，但结果相等本身不能说明扫描工作减少。

4. **Section 2B：检查普通 View 的计划扫描对象。**
   - **目的与数据环境：** 复用 2A 已捕获的两个 `EXPLAIN`，只显示选中的 `TABLE:` 行，不重新执行查询。
   - **期望结果：** 直接查询和 View 查询都选择 `m08_events(m08_events)`。
   - **说明：** 普通 View 保存的是查询定义，计划仍扫描底层事件表；`EXPLAIN` 只能证明计划选择，不能证明实际扫描了多少行。

5. **Section 2C：比较普通 View 的实际扫描工作。**
   - **目的与数据环境：** 读取 2A 已保存的 Query Profile，在对应 `OLAP_SCAN_OPERATOR` 下保留 `ScanRows` 与 `RowsProduced`，不重新执行 SQL。
   - **期望结果：** 经验证的运行中，两条路径都记录 `ScanRows=75,259`、`RowsProduced=18,298`，最终再聚合为八个地区。
   - **说明：** 该普通 View 没有减少本次运行观察到的扫描工作；运行计数、计划和业务答案是三类不同证据，不能用单次耗时替代。

6. **Section 3A：创建同步物化视图并等待初始构建。**
   - **目的与数据环境：** 在 Module 自有 Duplicate Key 表 `m08_events` 上创建按 `(region,event_type)` 汇总 count 与 revenue 的 `m08_sync_metrics`；记录旧 Job ID，只等待这次新建任务，并重新采集基表统计信息。
   - **期望结果：** 新任务明确对应 `m08_events` / `m08_sync_metrics` 且状态为 `FINISHED`；等待有超时，失败任务不能被旧成功记录掩盖。
   - **说明：** 构建完成只证明物化结构可用，不证明原报表一定会选择它；`ANALYZE ... WITH SYNC` 的 SYNC 表示同步等待统计信息采集，并非物化视图写入语义。

7. **Section 3B：运行不改写 SQL 的原地区报表并核对答案。**
   - **目的与数据环境：** 继续执行 Section 2 的 `regional_query`，SQL 仍引用 `m08_events`，并将完整八组结果与物化前 baseline 对账。
   - **期望结果：** 八个地区的 count 和 revenue 全部一致；`region_01` 仍为 2,319 和 732,977.08。
   - **说明：** 物化结构不应改变查询语义；结果一致仍不能回答实际用了哪个索引。

8. **Section 3C：确认计划选择同步物化索引。**
   - **目的与数据环境：** 比较物化前后的已捕获 `EXPLAIN` 扫描行，不重复执行报表。
   - **期望结果：** 扫描从 `m08_events(m08_events)` 变为 `m08_events(m08_sync_metrics)`。
   - **说明：** SQL 仍写基表名，优化器可以选择同步物化索引；这证明访问路径选择，不是扫描行数证据。

9. **Section 3D：比较基表路径与物化索引路径的 Profile。**
   - **目的与数据环境：** 从两个已保存的 Query Profile 中提取同一报表的扫描算子计数，并保留表/索引身份。
   - **期望结果：** baseline 扫描 75,259 条事件并输出 18,298 条 purchase；验证运行中的物化索引扫描约 64 条汇总记录并输出约 32 条 purchase 汇总记录，最终答案仍是八组。物理汇总行数允许随存储状态变化。
   - **说明：** 原始事件和预计算汇总具有不同粒度；更少的 `ScanRows` 支持“本次执行减少扫描行”的结论，但不能据此承诺固定延迟收益或忽略维护成本。

10. **Section 3E：验证一次提交写入后的同步维护。**
    - **目的与数据环境：** 以 `event_id=-8001` 的 `NOT EXISTS` 条件幂等追加一条 `region_01`、收入 19.95 的 purchase；不执行任何 refresh，再运行完整地区报表并单独执行 `EXPLAIN`。
    - **期望结果：** 只展示并验证 `region_01` 的 `event_count +1`、`total_revenue +19.95`；计划仍选择 `m08_sync_metrics`。
    - **说明：** 业务结果证明已提交写入进入报表，计划证明仍使用同步物化索引；两种证据共同支持“该受支持定义被同步维护”，但不外推到任意物化定义。

11. **Section 4A：创建异步多表物化视图、手动完整刷新并建立新鲜 baseline。**
    - **目的与数据环境：** 使用已含幂等 purchase 的 `m08_events` 和 `m08_products` 创建 `BUILD DEFERRED REFRESH COMPLETE ON MANUAL` 的 `m08_async_category_metrics`，提交一次新 COMPLETE refresh；关闭透明改写后比较源表 Join 与直接读取存储视图的完整结果。
    - **期望结果：** 新 Task ID 状态 `SUCCESS`、进度 100%；`mv_infos` 显示对象和刷新状态；源查询与存储视图均为 64 个 category/region 组且 `differing_rows=0`。
    - **说明：** 异步视图可以保存多表计算，但直接读取存储结果、刷新任务成功和透明改写是不同问题；禁用改写避免把视图与自身比较。

12. **Section 4B：修改维度并观察刷新前的陈旧结果。**
    - **目的与数据环境：** 选择 purchase 数最多且尚未改名的产品，把 Module 自有维度中的 category 更新为 `lab8_reclassified`；不刷新视图，分别查询当前源表与存储视图，并在正常开启 rewrite 时裁剪实际扫描计划。该步骤依赖 Section 1 重建出的原始 category，重复实验应从 Section 1 开始。
    - **期望结果：** 当前源表把 508 条 purchase、122,846.80 revenue 从 `category_8` 移到 `lab8_reclassified`，总事件数和收入不变；存储视图仍保留刷新前值，`lab8_reclassified` 为零组。
    - **说明：** 异步视图存在明确刷新滞后；源数据变化不会自动改写已存结果，计划展示也不会触发刷新。

13. **Section 4C：再次完整刷新并对账。**
    - **目的与数据环境：** 记录旧 Task ID 后提交第二次 COMPLETE refresh，等待新任务成功；在禁用 rewrite 的条件下比较当前源表与刷新后存储视图，并更新产品表和视图统计信息。
    - **期望结果：** 新任务 `SUCCESS`；两侧完整 72 组完全一致，`category_8` 为 1,814 / 551,991.97，`lab8_reclassified` 为 508 / 122,846.80。
    - **说明：** 完整刷新使存储结果追上改变后的源答案；实验验证正确性和任务边界，不测量生产刷新资源成本。

14. **Section 5A：验证满足粒度与指标条件的透明改写。**
    - **目的与数据环境：** 对相同事件—产品 Join、purchase 范围、category 分组及可加 count/sum 指标，分别关闭和开启 `enable_materialized_view_rewrite`；两次都保留 SQL 结果及 Query Profile，计划身份由断言静默检查。
    - **期望结果：** 两次返回相同九行 category 汇总；关闭时 Profile 扫描 `m08_events` 与 `m08_products`，开启时扫描 `m08_async_category_metrics`。
    - **说明：** 细粒度 `category,region` 视图可以上卷到 category，且保存的可加指标足以推导答案；Profile 证明本次实际扫描对象，不展示多余的完整 `EXPLAIN`。

15. **Section 5B：验证视图未保存的 distinct-buyer 指标不能被推导。**
    - **目的与数据环境：** 保持同一 Join、过滤和 category 分组，改为请求 `COUNT(DISTINCT user_id)`；分别关闭和开启 rewrite 并比较结果与 Profile。
    - **期望结果：** 两次九行 distinct-buyer 结果一致；开启 rewrite 后仍扫描 `m08_events` 与 `m08_products`，不扫描异步视图。
    - **说明：** 该视图没有保存 `user_id` 或可合并的 distinct 状态，因此不能仅凭相同维度复用；这是当前视图定义的能力边界，不代表所有 distinct 查询都无法加速。

16. **Section 6A：构造只有倒排索引不同的对照表和选择性谓词。**
    - **目的与数据环境：** 删除并重建结构、Key、Bucket、分布、副本和输入 SQL 相同的 `m08_events_unindexed` 与 `m08_events_indexed`；后者在装载前声明 `INDEX m08_product_idx(product_id) USING INVERTED`。两表都复制当前 `m08_events`，包括 Section 3 的一条自有 purchase，再选择“有正收入且事件数最少”的 product，避免硬编码数据相关 ID。
    - **期望结果：** 两表装载完成，单行结果给出本次 lookup 的 `product_id` 和 `matching_events`；可见 DDL 的主要实验差异是倒排索引。
    - **说明：** 这是数值等值倒排索引，不是全文分词、`MATCH` 或 Join Runtime Filter；相同逻辑输入用于隔离索引变量，但独立装载后的 Page、Compaction 和缓存状态不保证相同。

17. **Section 6B：执行相同 product lookup 并读取索引运行证据。**
    - **目的与数据环境：** 对两张表执行完整且相同的 `product_id = rare_product_id` 查询，核对每行结果，保留计划扫描身份和 DetailProfile 中每个扫描任务的索引计数。
    - **期望结果：** 两个查询返回完全相同的事件且行数等于 `matching_events`；验证运行中 indexed 路径出现正的 `RowsInvertedIndexFiltered` 并记录更少的 `ScanRows`，具体数值与时间允许变化。
    - **说明：** `EXPLAIN` 中的基表索引名不能单独证明二级索引过滤；`RowsInvertedIndexFiltered`、索引时间和 cache hit/miss 必须按算子与任务解释，不能把 `ScanBytes` 直接称为避免的物理磁盘 I/O，也不能承诺固定加速倍数。

18. **Stop、Restart 与 Lab complete。**
    - **目的与数据环境：** 可选停止单节点 `doris-rta` 释放资源，但保留容器、镜像和命名卷；重启单元格可在容器已停止、启动中或已运行时幂等执行，并重新连接检查 `m08_events`。
    - **期望结果：** 停止后状态为 `exited`；重启后容器回到 `healthy`，完整实验后的 `m08_events` 为 **75,260** 行，且 `event_id=-8001` 恰有一行。
    - **说明：** 停止/重启不会清空 Module 8 对象；结尾 `Lab complete` 用一段话回顾普通 View、同步/异步物化视图、改写边界与倒排索引证据，不再使用“证明事项”表格。

### 测验 8 的已实现覆盖范围

[Quiz 8 Notebook](module08-query-acceleration/quiz08_acceleration_choices.ipynb) 与 [Quiz 8 YAML](module08-query-acceleration/quiz08_acceleration_choices.yaml) 包含六个独立场景，覆盖逻辑复用与结果存储、新鲜度驱动的物化选择、改写条件、谓词驱动的索引选择、计划与运行证据、维护成本取舍。每个场景自行提供所需事实或小段证据。

## 模块 9：Apache Doris 的分片与副本

已实现课程：[Module 9 Course](module09-sharding-replication/course.md)。

### 模块目标

解释数据分片、Tablet 副本和 FE 元数据副本分别解决什么需求；在可从 3 FE + 2 BE 扩展至 3 FE + 3 BE 的多容器环境中，观察跨 BE 查询执行、Bucket Shuffle / Colocate Join、FE 查询入口切换、BE 副本再平衡及故障恢复。区分存储放置、计划选择和实际运行证据，并明确单机 Docker 实验的边界。

### 场景与逻辑主线

电商事件服务从单节点教学环境进入需要扩容和容错的多节点部署。主线不把 FE HA、BE 副本、MPP 执行和 Join 分发拆成无关主题，而是沿“入口故障→容量扩展→实际执行→副本故障→稳定布局上的 Join”推进：

| 主线阶段 | 运行状态变化 | 当前决策 | 证据与下一步 |
| --- | --- | --- | --- |
| 9.1 | 单 FE + 单 BE 不足以观察选举、副本放置和跨 BE 执行 | 建立三个可投票 FE 和两个初始 BE 的隔离拓扑 | 先核对真实角色、Master 和连接路径，避免把容器数当成集群可用性 |
| 9.2 | 应用直连当前 Master，该 FE 停止 | 分开处理 FE metadata quorum 和客户端新连接路由 | 原 TCP session 失败；存活 FE 选主；HAProxy 仅为新连接选健康 FE，且单代理仍是入口风险 |
| 9.3 | 两个 BE 已存储双副本表，容量需求促使团队加入第三个 BE | 让调度器重新分布 Replica placement，不改写原有 Sharding key | metadata 展示 Tablet 数不变、副本开始利用新 BE；`Alive` 不等于平衡完成 |
| 9.4 | 三个 BE 已持有不同 Tablet 子集，团队需要知道一条查询真正使用了哪些副本 | 沿 FE 计划追踪 Fragment Instance 和 BE PipelineTask | `SHOW REPLICA DISTRIBUTION` 回答存储放置，`EXPLAIN` 回答计划，Profile 中的 host/Tablet/ScanRows 回答本次执行 |
| 9.5 | 一个 BE 停机时事件写入仍在继续 | 按副本多数门槛决定能否提交，并把心跳恢复与版本追平分开 | 逻辑结果证明提交，逐 BE Version 证明落后副本是否追平；恢复后才进入稳定布局上的 Join |
| 9.6–9.7 | 事件与用户维度频繁按 `user_id` 连接 | 先在不兼容布局上用 Bucket Shuffle，再用稳定且兼容的 Colocation Group 避免 Join 输入 Shuffle | Join 附近的 `VEXCHANGE` 和 Join node 说明分发选择；业务答案一致不证明网络成本一样 |
| 9.8 | 实验在一台 Docker 宿主机上完成了扩容、停机和分布式执行 | 明确生产决策仍需独立故障域、负载和网络证据 | 不用单宿主机 elapsed time 给策略排名；数据已分布可用后进入 Module 10 的存储与生命周期 |

### Lab 开发环境基线（不进入 Course 正文）

本节的服务名、端口和容器生命周期仅供开发与复现实验使用。Course 正文讲解 FE/BE 职责、连接入口、副本与分发机制，不要求学员记忆这些本地标识符。

Module 9 使用 Apache Doris 官方 [`multi-node.yml`](https://github.com/apache/doris/tree/master/docker/runtime/all-in-one/4.1/compose)，固定镜像为 `apache/doris:all-in-one-4.1.3`。同一镜像通过 `DORIS_ROLE` 分别启动一个进程角色，形成以下拓扑：

```text
FE：fe-1、fe-2、fe-3（始终保持三个参与选举的 Follower）
BE：先启动 be-1、be-2 → 建立双副本基线 → 加入 be-3 → 执行查询与故障实验
客户端：先直连当前 Master FE → 验证连接失败 → 改用 HAProxy 统一入口
```

- `fe-1` 初始引导集群，`fe-2`、`fe-3` 默认作为 Follower 加入；基础实验不把 `fe-3` 改成 Observer，以保留三个参与选举的 FE。
- `be-1`、`be-2` 先运行，`be-3` 留给在线扩容实验。双副本事件基线在两个 BE 阶段使每个 BE 各存放每个 Tablet 的一份副本，加入第三个 BE 后再观察放置是否变化。三副本事件小表只在三个 BE 就绪后创建。默认副本数不能代替实验中明确的建表配置。
- Compose 文件不再包含官方 `multi-node.yml` 中的 `client` 服务（Lab 从未启动它）。FE、BE 是否完成注册，由 Lab 中的有界就绪检查确认，不用固定 `sleep` 代替。
- Module 9 使用独立 Compose project、私有子网和不与现有单节点沙箱冲突的主机端口。官方 Compose 支持 `FE_PORT`、`FE2_PORT`、`FE3_PORT`、`FE_HTTP_PORT`、`FE2_HTTP_PORT`、`FE3_HTTP_PORT`、`BE_HTTP_PORT` 和 `SUBNET`。课程的 compose 文件把端口变量改名为 `DORIS_RTA_M09_*`，默认值见 `doris_course/environment.py`（R-05）。课程候选值为 MySQL 端口 `9130`–`9132`、FE HTTP 端口 `8130`–`8132`、BE HTTP 端口 `8140` 和子网前缀 `172.31.91`，采用前必须检查占用。容器内部仍使用 Doris 默认端口。
- 在 Docker Desktop 上，主机不能直接路由到容器私网地址。当前 Notebook 的 `DorisLab.connect` 固定连接 `127.0.0.1:19130`，即 `fe-1`，停掉 Master 后才手动切换到另一个 FE；这不是 FE 负载均衡。新版实验先识别当前 Master 及其发布端口并明确直连，再停止该 FE，证明原 TCP 连接不会自动迁移；随后按官方方案加入带健康检查的轻量 HAProxy TCP 入口，让新连接避开故障 FE，并用代理统计或等价证据核对连接目标。恢复原 FE 后确认它重新加入，再为后续 Lab 保持完整 FE 拓扑。代理仍位于同一 Docker 宿主机，本身也不是冗余入口。[FE 负载均衡](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/load-balancing/)。
- 官方 Compose 默认不提供跨 `down` 的持久化。`stop/start`、`kill/start` 或再次 `up` 保留现有容器状态；`down` 删除容器、网络和其中的数据。故障实验不能用 `down` 代替停止单个节点。

官方依据：[All-in-One 镜像与多节点 Compose](https://doris.apache.org/community/developer-guide/all-in-one-image)。

### 学习目标

完成本模块后，学员应能够：

1. 区分为容量和并行工作服务的分片、为数据冗余服务的 Tablet 副本，以及为元数据服务可用性服务的 FE Follower。
2. 说明三个 FE、从两个扩展到三个的 BE 和负载均衡入口各自的职责及连接路径。
3. 说明 Partition、Bucket、Tablet 标识和物理副本之间的关系。
4. 根据数据量和查询条件选择分布列与 Bucket 数量，并解释低基数分布列可能带来的风险。
5. 区分期望副本配置、BE 上的实际放置、查询选择的副本，以及版本完整的健康副本。
6. 沿 FE 计划片段追踪参与执行的 BE，不把每个副本重复计入逻辑查询结果。
7. 在相同事件—用户连接场景中解释 Bucket Shuffle Join 与 Colocate Join 的数据移动和适用条件，并以实际计划核对选择。
8. 解释新增 BE 后的副本再平衡、旧 Bucket 数不变、停机写入门槛及返回节点的版本追赶。
9. 区分 FE Master 选举、客户端 FE 负载均衡与重连、BE 数据副本可用性和共享宿主机故障域。

### 课程内容大纲

#### 9.1 从单节点沙箱进入可扩展的多节点拓扑

**需求场景：** 单个 FE + 单个 BE 可以演示 SQL，但不能证明副本放置、跨 BE 执行或 FE 选举。

- 说明同一多节点教学镜像如何按角色启动 FE、BE 和客户端容器；镜像标签与环境变量属于 Lab 环境说明，不是课程需要记忆的 Doris 架构概念。
- 区分 FE 的查询规划与元数据职责，以及 BE 的数据存储与计划片段执行职责。
- 解释初始 FE 引导、其他 Follower 加入、初始 BE 注册、新 BE 后续加入和客户端健康检查的顺序。
- 使用 `SHOW FRONTENDS`、`SHOW BACKENDS` 和容器健康状态核对实际拓扑，不仅根据容器数量判断集群可用。
- 说明客户端直接连接某一台 FE 时，FE 选举不等于客户端负载均衡。统一入口需由客户端多地址机制或外部代理提供，并分别验证新连接分配与故障后重连。
- **实验衔接：** 先启动隔离 Compose project 中的三个 FE 和两个 BE，核对角色、版本、地址、当前 Master 与直连端口，证明连接没有误指向 Level 1–8 的单节点环境。

#### 9.2 分开验证 FE 选举和客户端负载均衡

**需求场景：** 多个 FE 均能提供 SQL 入口，但客户端只直连其中一台；该 FE 关闭后，已有连接会断开。

- 三个 Follower 中只有一个当前 Master；它失效后，存活 Follower 可选出新的 Master。选举维护的是 FE 元数据服务，不会自动迁移原有 MySQL TCP 会话，也不提供新连接的均匀分配。
- 先识别当前 Master FE 及其 localhost 发布端口并直连，记录本次连接的协调 FE；停止这个 FE 后，用该连接再次执行查询，预期得到连接错误，而不是透明切换到另一个 FE。
- 启动带健康检查的 HAProxy 统一入口，通过多次新建连接观察其分配目标。停止一个目标 FE 后，分别检查新 Master 选举、代理摘除故障目标和通过统一入口重新连接成功；不能仅用三个 FE 端口分别可查询来声称已经负载均衡。
- 解释代理统计字段的范围：`active connections` 是采样时仍由 HAProxy 转发到该 FE 的 TCP session，`total connections` 是 HAProxy 进程启动后累计分配到该 FE 的 session，连接两端是客户端与 HAProxy、HAProxy 与 FE MySQL 端口；`L4OK` 只说明 TCP 健康检查成功。累计值用来观察新连接分配，不表示查询数、并发查询数或 FE 生成计划的次数。
- 已经建立的 MySQL TCP 会话不会被 HAProxy 搬到另一台 FE；应用仍需要连接池或重试逻辑。恢复被停止的 FE 后确认它重新加入并重新进入代理可用目标，再继续后续数据实验。
- **实验衔接：** 保留“直连失效”“FE 选举”“代理健康检查与新连接分配”“客户端重连”四类证据，不承诺在途查询零中断，也不把单个 HAProxy 容器描述成冗余入口。

官方参考：[FE 负载均衡](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/load-balancing/)。

#### 9.3 区分分片、副本和新增 BE 后的自动再平衡

**需求场景：** 现有两个 BE 的存储或计算余量不足，团队加入第三个 BE，希望确认旧数据是否会被利用新节点承载。

- 副本数不能超过满足放置约束的可用 BE 数。若可用 BE 数量恰好等于 `replication_num`，每个 BE 都必须持有每个逻辑 Tablet 的一份副本，因此无法形成“不同 BE 持有不同 Tablet 子集”的放置；只有放置目标多于副本数时，调度器才有选择空间。
- 实验仍先在两个 BE 上建立两个副本的事件表，用它作为扩容前基线；此时两个 BE 确实都覆盖全表。加入第三个 BE 后变成 `BE 数量 > replication_num`，后台调度器才有条件把已有副本逐步复制到新 BE，再清理旧的多余副本，使三个 BE 分担不同 Tablet 子集。
- 说明 Bucket 对应逻辑 Tablet；副本是同一 Tablet 在不同 BE 上的物理拷贝，不会增加 SQL 可见的逻辑行数。分别统计唯一 Tablet ID、元数据副本记录和每 BE 副本数，不把三者混为一谈。
- 用事件表 DDL 串联这些概念：`event_time` 先决定时间 Partition，每个 Partition 内再由 `HASH(user_id)` 和 Bucket 数产生逻辑 Tablet；`逻辑 Tablet 数 = Partition 数 × 每 Partition Bucket 数`，物理副本记录数还要乘以 `replication_num`。多份副本代表同一个逻辑 Tablet，不会让 SQL 重复返回业务行；当前 Lab 的具体数量留在实验大纲中核对。
- 比较扩容前后 `SHOW BACKENDS`、`SHOW REPLICA DISTRIBUTION`、少量逐 Tablet 的 `SHOW TABLETS` 和 SQL 逻辑答案；用有界等待观察调度，不把“第三个 BE 已 Alive”误读为“迁移完成”。
- 旧表仍保持原来的 Partition 和 Bucket 数；新增 BE 改变可放置位置，不会自动增加既有 Bucket。共置表再平衡期间可能暂时不稳定，Join 计划需在稳定后另行核对。
- **实验衔接：** 只启动预留的新 BE 并确认它已注册。比较前后 Tablet–Backend 映射；若小数据样本在有界时间内未触发可见迁移，明确展示调度状态和证据不足，不通过手动移动副本伪装成“自动再平衡”。

官方参考：[弹性扩容](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/elastic-expansion/)、[副本均衡与修复](https://doris.apache.org/docs/4.x/admin-manual/maint-monitor/tablet-repair-and-balance/)。

#### 9.4 追踪一次查询选择的 Tablet 副本和 BE 扫描任务

**需求场景：** 扩容后的三个 BE 已持有不同 Tablet 子集，但团队需要知道一条查询实际使用了哪些副本和执行节点。

- 事件表按 `HASH(user_id)` 分成多个逻辑 Tablet，每个 Tablet 有配置数量的物理副本。多个 BE 是可用的放置目标；FE 对每个所需 Tablet 选择一个健康副本，不会把同一 Tablet 的所有副本都扫描一遍。
- 区分业务行数、逻辑 Tablet、BE 上保存的物理副本和本次查询选中的副本。`SHOW REPLICA DISTRIBUTION` 说明副本放置，不能证明某个 BE 参与了这次查询。
- 解释 FE 如何形成 Plan Fragment，为选中的 Tablet 副本下发 Fragment Instance；BE 执行扫描与局部聚合，Exchange 传递中间结果。`EXPLAIN` 表示计划，Query Profile 中的 BE host、Tablet ID 和 `ScanRows` 才是本次运行证据。
- 按一条 SQL 的真实分发顺序讲解：FE 先根据 `event_time` 谓词裁剪 Partition，再确定所需 Bucket/Tablet；从每个 Tablet 配置的多个副本中选择一个健康副本，把包含若干 Tablet 范围的扫描 Fragment Instance 下发到相应 BE；每个 BE 的 PipelineTask 扫描本地 Tablet、执行局部聚合，再通过 Exchange 把中间结果送往上层 Fragment，最终由协调 FE 返回答案。
- 明确四个容易混淆的数量：Plan Fragment 是一段可分布执行的计划模板；Fragment Instance 是该模板在某个执行节点上的实例；PipelineTask 是实例内部的并行任务；本地 Pipeline 并行度不改变 Tablet、副本数或业务结果。Lab 为缩短 Profile 而采用的具体并行设置只写在实验说明中，不能解释成关闭多 BE 执行。
- 用裁剪后的文本教会学员沿结构阅读：`tablets=已选择/总数` 是计划扫描范围，`numNodes` 是计划估计使用的节点范围；DetailProfile 中每个 `host` 下的 `TabletIds` 和 `ScanRows` 才说明该 BE 本次实际承担了哪些扫描。容器私网 IP、Tablet ID 和具体数量会随环境变化，Course 不固定这些值。
- 多个不同的 BE host 出现在扫描 Profile 中，可以证明这次执行跨 BE 并行；没有出现的 BE 即使保存副本，也没有执行本次表扫描。副本选择和调度可能变化，因此不固定断言三台 BE 都参与、具体 Tablet ID 或具体扫描行数。
- **实验衔接：** 对事件表执行地区聚合，先核对完整分组结果和总行数，再对照裁剪后的 `EXPLAIN` 与 DetailProfile。只解释实际出现的 BE 扫描任务，不增加第二张偏斜对照表，也不以同一宿主机耗时声称扩展收益。

#### 9.5 在一个 BE 停机时写入，并观察返回节点追赶版本

**需求场景：** 一个 BE 停止，但应用仍尝试读取和追加事件。

- 在默认“多数副本写入”策略下，可提交副本数取决于配置的副本数和可用副本。双副本表停掉一个持有副本的 BE 时，不能直接承诺写入成功；三副本表停掉一个 BE 后，另外两个副本仍可能形成多数。Course 先解释门槛，再由 Lab 使用独立三副本事件小表验证，不改动聚合基线。
- 停机前确认三个 BE 和故障写入事件表的每个 Tablet 都有三个健康、版本完整的副本，记录每个 BE 对应的 `Version`；再停止一个明确命名的 BE 容器。
- 区分 Docker 容器被停止、FE 心跳检测到节点不可用、正在执行的请求失败和后续重试结果。
- 在两个 BE 存活时做一次可重跑的写入，确认 SQL 已提交且逻辑结果更新；随后从 `SHOW TABLETS` 分别看到存活副本与停机副本的版本状态。停机副本元数据中的旧版本不能当作已从其容器读取的物理内容。
- 将版本值解释为相对证据而不是固定答案：停机期间发生新提交后，形成多数的存活副本应处于同一个较新版本并标记为 current version；停止的 BE 保留较小旧版本且不再是 current version。若停机前后没有新提交，版本可以相同；恢复完成后只要求全部副本相等，不硬编码具体版本数字。
- 使用 `kill/start` 或 `stop/start` 保留该容器的数据；不能使用会删除整个集群数据的 `down`。
- 启动原 BE 后立即读取一次节点与逐 BE 副本版本；若已经追平，如实说明恢复太快，不能保证每次都能捕捉到过渡态。随后有界等待全部副本版本一致且健康，并再次查询同一个业务值。节点 `Alive` 与副本版本追平是不同的完成条件。
- **实验衔接：** 展示写入前、停机写入后、节点刚返回和完全追平后的简短逐 BE `Version` 对照；不硬编码具体版本号，也不把原节点的追赶误称为向替代节点迁移。

官方参考：[写入高可用](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/load-high-availability/)、[系统架构与可用性](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)。

#### 9.6 最后比较 Bucket Shuffle 与 Colocate Join 的数据移动

**需求场景：** 扩容和副本恢复完成后，事件表与用户维度频繁按 `user_id` 连接，团队希望利用已经稳定的数据放置减少 Join 交换。

- 将 Join 放在故障恢复之后，先等待参与实验的表和 Colocation Group 稳定，避免把再平衡或修复期间的临时退化当成正常计划。
- 沿用模块 6 对逻辑 Join 与物理 Hash Join 的区分，此处只研究跨 BE 的数据移动：Bucket Shuffle 保留一侧 Bucket 布局并重分发另一侧，Colocate 在稳定且兼容的组内避免该 Join 的 Shuffle。
- 使用统一的事件—用户场景：事件表按 `HASH(user_id)` 分布，查询先选择一个时间 Partition，再把事件按 `user_id` 聚合为 `(user_id,event_count,total_revenue)`，使同一用户的中间状态继续位于可复用的事件 Bucket；用户维度包含 `(user_id,user_segment)`，第一种布局故意使用不兼容的 RANDOM 分布。
- 具体解释 Bucket Shuffle 的路由：如果某个用户的事件状态位于一个事件 Bucket，而 RANDOM 用户记录位于别处，Join 输入侧 `VEXCHANGE` 会按事件表的 `user_id` Bucket 映射把该用户记录发送到负责相应 Bucket 的 Fragment Instance；事件侧保持原布局，移动的是用户侧。Bucket 号与负责它的 BE 不是永久绑定关系，本次执行仍需从副本中选择实际扫描位置。
- `[shuffle]` 只用于阻止小维度表改走 Broadcast，不能单独证明 Bucket Shuffle；实际计划必须出现 `INNER JOIN(BUCKET_SHUFFLE)`，且 Join 输入分支出现 `VEXCHANGE`，才能解释为用户侧被重新分发。Join 上方为最终 `GROUP BY user_segment`、排序或结果合并出现的 Exchange 不属于 Join 输入移动。
- 随后用相同逻辑用户数据重建维度表，使其同样按 `user_id` 分桶、采用兼容的 Bucket 和副本定义，并与事件表加入同一个 Colocation Group。稳定后，对应 Bucket 的事件和用户 Tablet 具有兼容放置，计划应为 `INNER JOIN(COLOCATE)`，Hash Join 与两侧扫描之间不再需要输入 Exchange；具体行数与 DDL 参数留在 Lab 大纲中。
- 两次查询保持相同 Join Key、过滤范围、分组指标和业务答案。Bucket Shuffle 复用按 `user_id` 汇总后的事件侧 Hash 分布，只重分发用户侧；Colocate 还要求两张物理表的分桶列类型、Bucket 数、副本数与放置兼容，而且 `SHOW PROC "/colocation_group"` 必须报告 `IsStable=true`。
- **实验衔接：** 分别裁剪普通 `EXPLAIN` 中的 Join 节点、Join 下方关键 `VEXCHANGE`、表扫描和 Partition 范围。Bucket Shuffle 应在 Join 输入分支看到 Exchange；Colocate 的 Join 与两个输入扫描之间不应有 Exchange，但最终聚合或结果合并仍可有其他 Exchange。不比较本机容器耗时。

官方参考：[Doris 4.x Join 策略与限制](https://doris.apache.org/docs/4.x/query-data/join/)。

#### 9.7 解释存储放置、查询执行和服务可用性的证据边界

**需求场景：** 受控停止一个容器后查询和后续写入可恢复，但团队还需判断这些证据能支持什么可用性承诺。

- 区分 FE 元数据选举、FE 查询入口的健康检查与负载均衡、BE 副本修复，以及业务客户端对失败请求的重试。
- 区分 `SHOW REPLICA DISTRIBUTION` 展示的存储放置、`EXPLAIN` 展示的计划选择，以及 Query Profile 展示的实际执行。一个 BE 存有副本，不代表它一定参与本次扫描。
- 说明六个 Doris 节点仍共享宿主机、Docker Engine、物理磁盘和外部网络；容器级停机不能证明主机、机架或可用区容灾。
- 回顾存算分离架构的不同前提，但 Module 9 只使用官方存算一体 `multi-node.yml`，不启动 `cloud.yml`、FoundationDB 或 MinIO。

#### 9.8 从副本健康过渡到数据生命周期

**需求场景：** 节点和副本已经恢复健康，但业务仍需控制长期存储成本、历史保留和误删恢复。

- 副本解决同一集群内的冗余与可用性，不等于备份，也不会定义业务数据应保留多久。
- 扩容、再平衡和版本追赶都不会撤销错误写入或替代回收站与独立备份。
- **模块过渡：** 节点和副本健康不能撤销错误写入，也不能替业务定义数据保留和恢复策略。

### 模块 9 实验：从 3 FE + 2 BE 扩展并观察分布式行为

实验文件：[Lab 9 Notebook](module09-sharding-replication/lab09_observe_sharding_and_replication.ipynb)。实验使用模块目录的 `compose.multinode.yml`、固定镜像 `apache/doris:all-in-one-4.1.3`、独立 Compose project、私有子网和 localhost 端口；不与 Level 1–8 的单节点 `doris-rta` 同时运行。首次缺少本地 baseline 时只读课程 S3 的 `[2020-03-01 00:00:00, 2020-03-01 07:00:00)`，不修改 S3。以下编号严格对应 Notebook 的 1.1–3.2 与结尾控制步骤。

0. **Initialize the Lab。**
   - **目的与数据环境：** 定位课程根目录，加载共享 `DorisLab`，记录 Compose 文件、HAProxy 统计地址、代理端口、固定 FE 服务/IP/主机端口映射和期望事件行数；不启动或停止任何容器。初始 helper 指向直连 `fe-1`，后续步骤会按实验目的切换连接。
   - **期望结果：** Python 变量与 `lab` 对象创建完成，没有集群状态变化。
   - **说明：** 内核重启不会删除容器和数据，但必须重新运行初始化以恢复本地 Python 状态。

1. **Section 1.1：建立恰好两个存活 BE 的起点。**
   - **目的与数据环境：** 检查 Docker、Compose、隔离端口和固定镜像；若单节点 `doris-rta` 正在运行则停止并提示，不自动操作它。Module 9 保留已有容器 writable layer、FE 元数据和 Doris 数据，只重启 `be-1`、`be-2` 进程释放旧 RSS，显式停止 `be-3`、`client` 与 HAProxy；已有三 FE 容器同时启动以满足持久化 FE 元数据的多数派要求。这里不重建业务表。
   - **期望结果：** 三个 FE 均 `Alive=true`、角色均为 Follower 且恰有一个 Master；仅 `be-1`、`be-2` 存活，固定地址为 `.50`、`.51`，版本一致；已注册的 `be-3` 可以仍在 FE 元数据中但必须 `Alive=false`；HAProxy 保持停止。
   - **说明：** “已注册”不等于“正在提供放置”；重启 BE 进程会释放进程内存，但不会删除节点注册、容器层或已有 Doris 数据。

2. **Section 1.2A：只复用已提交事件内容，重建受控的两 BE 物理 baseline。**
   - **目的与数据环境：** 如果现有 `m09_events` 或 `m09_events_previous` 恰有 12,062 行，只把这批逻辑事件临时保留为本地复制源；`m09_events` 的物理表仍会重建为两 Partition、每 Partition 六 Bucket、双副本。除这批事件内容外，旧的 `m09_events_skewed`、`m09_availability_events`、旧 probe 和 `m09_users` 全部删除，后续按各自步骤重建；首次没有完整本地数据时才读取只读 S3。FE/BE 容器与元数据不会重建。
   - **期望结果：** 新 `m09_events` 为 **12,062** 行、12 个逻辑 Tablet、每 Tablet 两副本；在 `be-3` 停止时，副本放置固定为 `be-1=12`、`be-2=12`、`be-3=0`，总物理副本数 24；临时 `m09_events_previous` 随后删除。
   - **说明：** 该设计使每次实验都从相同两 BE 放置开始，同时避免重复读取 S3。被保留的是已提交的数据内容，不是旧表的 Partition、Tablet、Colocation 或其他物理状态。

3. **Section 1.2B：启动 `be-3` 并等待自动副本迁移。**
   - **目的与数据环境：** 在两副本事件表健康后只启动 `be-3`，不重载表、不执行手动 Tablet copy 或 `ADMIN REBALANCE`；有界轮询节点、存储路径和每 BE 副本数。
   - **期望结果：** 三个 BE 都存有至少一个事件表副本，精确分配可变；总副本仍为 24，逻辑行仍为 12,062。对照表第一行保持 `12/12/0`，第二行显示三台 BE 均为正数。
   - **说明：** Doris 在新增放置目标后自动迁移已有副本；扩容改变物理放置，不改变两个 Partition、六 Bucket/Partition、双副本配置或逻辑答案。

4. **Section 1.3A：观察 FE 状态，再切断当前直连 Master。**
   - **目的与数据环境：** 第一代码框只展示三个 FE 的 Host、Role、Master、Join、Alive 和 Version，不改变环境。第二代码框仅在三 FE 全部存活且 HAProxy 仍停止时，识别当前 Master、直连它的 `91xx` 端口、停止该 FE，并在原 TCP 连接上执行有业务含义的 `m09_events` 行数查询。
   - **期望结果：** 观察表本身不触发异常；停止直连 FE 后，原连接返回紧凑的 connection failed 结果，而不是自动切换。若前置拓扑不满足，第二代码框拒绝再停一台 FE。
   - **说明：** FE 选举可让另一个 Follower 成为 Master，但不能把已经断开的 MySQL TCP 会话迁移到它；FE 高可用与客户端入口高可用是两个问题。

5. **Section 1.3B：在故障 FE 仍停止时启动 HAProxy 并建立新连接。**
   - **目的与数据环境：** 用 `--no-deps` 启动 HAProxy，避免 Compose 顺带恢复故障 FE；读取代理健康状态，建立四个独立的新 MySQL session，并比较各 FE 目标的累计连接增量；再通过代理端口 `19230` 查询事件表。
   - **期望结果：** 至少四个新连接只分配到两个 `UP` 的 FE，停止目标增量为零；Doris 侧仍是两个存活 FE、恰有一个 Master；代理查询返回 12,062 行。
   - **说明：** HAProxy 的 L4 健康检查和 round-robin 负责新连接入口，Doris FE 选举负责元数据服务；代理不能恢复旧会话，应用仍需重新连接或重试。

6. **Section 1.4：恢复停止的 FE 并为 Profile 选择明确协调 FE。**
   - **目的与数据环境：** 只恢复实际停止的 FE，等待 Doris 报告三 FE 存活并等待 HAProxy 将该目标重新标为 `UP`；随后识别当前 Master，改为直连其 MySQL 与 HTTP 端口，供后续 Query Profile 获取。
   - **期望结果：** 三 FE 均 `Alive=true`、恰有一个 Master；代理状态为 `UP`，`last check` 被解释为 `L4OK — TCP connection to FE port 9030 succeeded`。返回 FE 不必重新成为 Master。
   - **说明：** `L4OK` 只证明 TCP 端口可连接，不执行 SQL、也不识别 Master；累计连接总数不用于证明恢复，原先失败的会话也不会复活。

7. **Section 2.1：查看 `m09_events` 的逻辑与物理布局摘要。**
   - **目的与数据环境：** 在三 BE 扩容完成后等待事件表的 Tablet 行数元数据，再显示 Partition、Bucket、Tablet、副本与每 Tablet 行数范围；不执行用于观察运行位置的查询。
   - **期望结果：** 两 Partition、六 Bucket/Partition、12 个逻辑 Tablet、两副本/Tablet、12,062 逻辑行；`rows/tablet` 是本次布局的范围，具体数值可变。
   - **说明：** 该表说明存储布局和可选副本，不说明下一条查询选择哪一个副本或哪个 BE 实际扫描。

8. **Section 2.2：用一条地区聚合观察计划范围与实际 BE 扫描任务。**
   - **目的与数据环境：** 查询 `m09_events` 的八个地区 count/revenue；临时把每个 BE 上该 Fragment 的 `parallel_pipeline_task_num` 设为 1 以减少同一 BE 的重复 PipelineTask 输出，同时开启 Profile level 2、关闭三类结果/条件缓存并在结束后恢复。显示裁剪后的普通 `EXPLAIN` 与原始 DetailProfile 的 host、TabletIds、ScanRows。
   - **期望结果：** 八个地区的 `event_count` 合计 12,062；`EXPLAIN` 展示扫描 Fragment、聚合与 Exchange，通常为 `tablets=12/12`；Profile 至少显示实际参与扫描的 BE host 及其任务，但不固定要求三台 BE、特定 Tablet ID 或特定扫描行数。
   - **说明：** `EXPLAIN` 是计划范围，Profile 是本次运行证据。每个逻辑 Tablet 只选择一个可用副本；某 BE 存有副本却未出现在 Profile，表示它没有执行本次表扫描。单宿主机耗时不能用于证明扩展收益。

9. **Section 2.3A：创建三副本故障写入表并建立版本 baseline。**
   - **目的与数据环境：** 不修改双副本 `m09_events`，另行删除重建一 Bucket、三副本的 Unique Key 表 `m09_availability_events`；插入一条 baseline 事件，等待三个副本都存活且版本完整，并按 BE 汇总当前版本。
   - **期望结果：** 三台 BE 各有一个存储副本、一个 current-version replica，版本一致；baseline 事件可查询。
   - **说明：** 双副本在默认多数写入条件下不能承诺停一个副本仍写成功；独立三副本表让两个存活副本可以形成多数，同时不污染固定 12,062 行聚合样本。

10. **Section 2.3B：停止 `be-2`，提交一条业务事件并比较副本版本。**
    - **目的与数据环境：** 明确停止 `be-2`，等待 FE 只报告两个存活 BE；向三副本表插入 `event_id=9000002`、`region_01`、收入 19.95 的 purchase，再查询完整业务行和逐 BE 版本摘要。
    - **期望结果：** purchase 在两个存活 BE 形成多数后提交并可查询；`be-1` 与 `be-3` 为同一较新版本 `V_new` 且 current-version=1，停止的 `be-2` 仍列出物理副本但版本为较小的 `V_old`、current-version=0。具体版本数字不硬编码。
    - **说明：** 停止进程不会删除副本；逻辑查询成功和元数据中停机副本落后是两项互补证据。停机副本行来自 FE 元数据，不表示此刻从已停止容器读取了物理文件。

11. **Section 2.4：重启 `be-2` 并等待版本追平。**
    - **目的与数据环境：** 启动原 BE，先等待心跳 `Alive=true` 并立即抓取一次版本摘要，再有界等待全部三副本正常且版本完整，最后重查同一 purchase。
    - **期望结果：** 立即采样可能仍看到 `be-2` 版本较小，也可能因恢复过快已经相等；等待结束后，三台 BE 版本相同、current-version 均为 1，事件 `9000002` 仍为 19.95。
    - **说明：** 节点存活与副本追平是不同恢复里程碑；过渡态未被采样到时必须如实说明，单 Docker 宿主机也不能证明跨主机灾难恢复。

12. **Section 3.1：让同一业务查询实际选择 Bucket Shuffle。**
    - **目的与数据环境：** 删除旧 `m09_users`，把 `m09_events` 从可能残留的 Colocation Group 移出；创建 RANDOM 分布、双副本的用户表，从事件表生成 **6,706** 个 distinct user 及 `new/returning/loyal` 分群。查询只选 `p_first_half`，先按 `user_id` 汇总事件，再用 `[shuffle]` 连接用户表，避免小维度被 Broadcast。
    - **期望结果：** 分群结果固定为 `loyal 1098 / 100089.35`、`new 1177 / 113473.45`、`returning 994 / 102868.16`；计划必须出现 `INNER JOIN(BUCKET_SHUFFLE)`、Join 输入侧 `VEXCHANGE`、`partitions=1/2 (p_first_half)`。
    - **说明：** 事件侧按 `user_id` 汇总后保留可复用的 Hash 分布，用户侧被路由到对应 Bucket；`[shuffle]` 是控制 Broadcast 的教学提示，最终结论仍以实际计划为准，Join 上方为最终聚合出现的 Exchange 不属于 Join 输入重分发。

13. **Section 3.2：把相同用户数据预先共置并观察 Colocate。**
    - **目的与数据环境：** 再次删除并重建同名 `m09_users`，这次使用 `HASH(user_id)`、六 Bucket、双副本、Unique Key，并让它与 `m09_events` 加入 `m09_user_join_group`；等待 `IsStable=true` 后执行与 3.1 相同过滤、Join Key、指标和分组的查询，但不使用 `[shuffle]`。
    - **期望结果：** 组状态显示六 Bucket、双副本、stable=true；三行业务答案与 3.1 完全相同；计划出现 `INNER JOIN(COLOCATE)`，Hash Join 与两侧扫描之间没有 `VEXCHANGE`。
    - **说明：** 相同 Join Key 和 Bucket 数不足以单独证明共置；同组、兼容副本定义和稳定放置共同允许本地 Join。其他最终聚合 Exchange 仍可存在，实验不以同机耗时宣称 Colocate 必然更快。

14. **Stop、Restart 与 Lab complete。**
    - **目的与数据环境：** 可选 `docker compose stop` 释放三 FE、三 BE 和 HAProxy 进程，同时保留容器 writable layer 与 Doris 数据；重启时先同时启动已有三个 FE 形成多数派，再启动或复用三 BE 和 HAProxy，通过代理重新连接并检查三张关键表。
    - **期望结果：** 停止后服务为 `Exited`；重启后所有 FE/BE healthy，持久化检查为 `m09_events=12,062`、`m09_users=6,706`、停机期间 purchase 行数 `=1`。
    - **说明：** `stop/start` 保留该隔离集群，`down` 会删除未外挂的容器数据，不能用于本实验；结尾 `Lab complete` 用一段话回顾入口切换、副本再平衡、实际扫描、版本追赶和 Join 数据移动，不使用证明清单表格。

### 证据边界与清理约定

- 初始阶段对三 FE、两 BE 的就绪检查与扩容后对第三个 BE 的就绪检查，只证明各阶段预期节点在该时刻完成注册，不代表后续每个 Tablet 都健康。
- `SHOW FRONTENDS`、`SHOW BACKENDS`、`SHOW REPLICA DISTRIBUTION` 和 Tablet 元数据说明控制面观察到的节点与副本状态；代理侧连接记录用于检查 FE 入口分配，SQL 结果用于检查逻辑数据，`EXPLAIN` 用于检查计划，Query Profile 用于检查实际执行位置。
- 新增 BE 后看到副本数变化可支持“副本在移动”，不能据此断言新增 Bucket、逻辑行发生迁移或自动扩容已经达到生产均衡。新增节点不等于原节点副本已恢复；停机恢复实验必须分别检查版本。
- 单次正在执行的请求可能在节点停止时失败；后续重连成功不能改写为“零中断”。
- 同一宿主机上的多个容器不提供独立物理故障域，不能用于生产网络性能、磁盘容灾或跨可用区结论。
- `stop/start` 用于节点实验和结尾的可选资源释放；Notebook 不再运行 `down`，避免删除未外挂的 Module 9 数据。Notebook 只能操作 Module 9 Compose project，不能停止或删除其他模块的容器、网络和数据。

### 测验 9 的已实现覆盖范围

[Quiz 9 Notebook](module09-sharding-replication/quiz09_distribution_and_availability.ipynb) 与 [Quiz 9 YAML](module09-sharding-replication/quiz09_distribution_and_availability.yaml) 包含六个独立场景，覆盖存储副本与查询选中的副本、跨 BE 扫描任务、Bucket Shuffle / Colocate 的条件、两 BE 到三 BE 的副本再平衡、双副本与三副本的停机写入门槛、FE 选举与客户端入口切换，以及容器级和生产级故障域的区别。每题自行提供拓扑、配置和元数据，不要求正在运行 Docker 或 Doris。

## 模块 10：控制 Apache Doris 的存储成本与数据生命周期

已实现课程：[Module 10 Course](module10-managing-data/course.md)。

### ClickHouse 参考课程与 Doris 映射

ClickHouse Academy 当前把 Module 10 分为 `Compression`、`TTL`、`Lab 10.1: Configuring Compression` 和 `Lab 10.2: Configuring TTL`。本地 `ClickHouse101.pdf` 只列出 Module 10 标题，没有记录这些内容；以下映射来自实际 Academy 课程目录和 Lab 页面。

- Compression Lab 先从 `system.parts` 读取整表压缩前后字节和 Part 数，再从 `system.parts_columns` 查看逐列压缩率；它用 Compact/Wide Part 解释为什么小表可能没有可用的逐列文件统计，然后让学员用相同数据比较默认压缩与 `T64 + LZ4`、`DoubleDelta + ZSTD`、`LZ4HC` 等列级 Codec。
- TTL Lab 创建 60 秒行级 TTL，先等待再查询，说明到期不等于已经被后台 Merge 删除，并用 `MATERIALIZE TTL` 强制执行；随后增加 15 秒列级 TTL，观察列值先变为类型默认值、整行再在 60 秒后删除，最后把五年保留规则应用到已有表。
- Doris 4.x 的可迁移问题是“怎样在压缩率与解压成本之间选择”和“怎样让旧时间范围自动退出在线数据集”；ClickHouse 的 `CODEC(...)`、Compact/Wide Part、行级/列级 TTL 与 `MATERIALIZE TTL` 不能改名后当作 Doris 功能。
- Doris 的 `compression` 是建表时选择的表级存储属性。Doris 内部仍按列编码、按 Page 压缩，但课程不宣称可以像 ClickHouse 一样为每列组合 Delta、DoubleDelta、Gorilla 或 T64 Codec。
- Doris 的滚动保留主线采用 Dynamic Partitioning：调度器按当前时间创建和删除完整 Range Partition。它不是为每一行单独计算过期时间，也没有与 ClickHouse `MATERIALIZE TTL` 等价的实验命令。

ClickHouse 参考：[Real-time Analytics with ClickHouse](https://learn.clickhouse.com/real-time-analytics-with-clickhouse)。Doris 参考：[数据压缩](https://doris.apache.org/docs/4.x/table-design/column-compression/)、[动态分区](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning/)。

### 模块目标

面对持续增长的事件数据，选择可解释的压缩策略和按时间分区的保留策略；用逻辑结果、表定义、调度状态和存储元数据分别验证结果。学员最终应能说明数据何时不再可查询、何时仍可能位于回收站、何时才需要独立备份，并避免把副本、TTL 和物理空间回收混为一谈。

### 场景与逻辑主线

实时事件表每天继续增长，团队需要同时控制每份数据的存储成本、在线时长和删除后的恢复风险。主线沿“降低存储成本→定义可管理时间范围→让旧范围自动离线→处理迟到与误删→建立独立恢复边界”推进：

| 主线阶段 | 数据生命周期变化 | 当前决策 | 证据与下一步 |
| --- | --- | --- | --- |
| 10.1 | 事件无限增长，团队同时面对存储、保留和恢复需求 | 先定义热度、保留时长、迟到数据、RPO 和 RTO | 把“数据太多”拆成压缩、Partition 管理、在线过期和恢复四个决策 |
| 10.2–10.3 | 相同逻辑事件需要更少空间，但查询仍需读取相同值 | 从 CPU、I/O 和存储的紧张程度选压缩侧重，用受控输入决定是否偏离默认 | DDL 说明有效算法，逻辑核对说明输入可比，存储报告只支持当前样本的大小结论 |
| 10.4 | 数据已经更紧凑，但旧时间范围仍会无限积累 | 在 Manual、Auto 与 Dynamic Partitioning 之间按创建触发条件和删除责任选择 | 将保留单位明确为完整 Partition，不翻译成逐行 TTL |
| 10.5 | 团队需要滚动窗口，还会收到迟到事件 | 用 `time_unit`、`start`、`end`、时区和历史例外定义窗口，另行定义窗口外数据政策 | 先推导半开 Partition 边界和写入归属，再让时钟和 scheduler 推进窗口 |
| 10.6 | 策略已接受，但最旧 Partition 可能仍可见 | 分开验证配置、scheduler 观察、catalog/SQL 可见性和物理回收 | 跨过边界只代表已符合过期条件；调度完成和字节回收还是独立状态 |
| 10.7 | 近期数据需要高速介质，旧数据需要更低成本的在线存储 | 只在真实多介质或远端存储部署上选择冷热分层 | Course 说明架构选择；单磁盘 Docker Lab 不伪装成迁移证据 |
| 10.8 | Partition 可能被误删，错误也可能传播到所有在线副本 | 用回收站处理有限窗口内的合格对象删除，用独立 backup/重放处理更广故障 | `RECOVER` 成功后还需核对数据；Replica 和 recycle bin 都不是 backup |

### 学习目标

完成本模块后，学员应能够：

1. 解释列式编码、Page 压缩、压缩率、解压 CPU 和查询 I/O 之间的关系。
2. 根据实时查询、均衡成本或归档优先级选择 Doris 支持的表级压缩算法，并说明为什么必须用真实数据验证。
3. 在相同表结构、相同逻辑行和相同导入批次下比较压缩后的存储报告值，不用单次运行时间声称某算法更快。
4. 区分 Manual Partitioning、Auto Partitioning 与 Dynamic Partitioning 的创建依据和生命周期职责。
5. 用 `time_unit`、`start`、`end`、时区和保留例外定义完整 Partition 的滚动窗口。
6. 区分属性被接受、调度器运行正常、Partition 实际出现或消失，以及物理字节最终回收。
7. 解释迟到数据、无匹配 Partition 和历史保留例外对写入的影响。
8. 区分在线副本、回收站恢复、远端备份和权威数据源重放所解决的问题。
9. 说明本地/远端冷热分层需要真实的存储介质或对象存储，不能由单个 Docker 文件系统证明。

### 课程内容大纲

#### 10.1 从无限增长的问题定义生命周期边界

**需求场景：** 事件持续写入，团队必须同时回答“每行占多少空间”“保留多久”和“删除错误能否撤销”。

- 先明确查询热度、保留时长、迟到数据、监管例外、可接受的恢复点目标（Recovery Point Objective，RPO）和恢复时间目标（Recovery Time Objective，RTO）。
- 将生命周期拆成四个决策：减少每份数据的存储成本、创建可管理的时间范围、让旧范围退出在线表、为误删或集群损失准备恢复路径。
- 回顾模块 4 的 Partition 与 Bucket：Partition 是本模块执行保留和恢复的业务范围，Bucket/Tablet 仍是分布与副本单位。
- 回顾模块 7 的行级更新、删除、`TRUNCATE` 与 `INSERT OVERWRITE`，本模块不再重复数据修改语法目录。
- **实验衔接：** 选择前置模块已清洗事件表的有界一天作为压缩输入，只复制到 Module 10 自有表，不修改来源。

#### 10.2 先理解 Doris 在哪里压缩数据

**需求场景：** 同一批事件需要更少磁盘空间，但报表仍要读取相同的列和值；团队要先判断更紧张的是存储与读取 I/O，还是查询时的解压 CPU，再决定是否偏离默认设置。

- Doris 先按列组织数据并应用字典编码、Run-Length Encoding（RLE）等编码，再按 Page 使用压缩算法；查询只解压实际读取的 Page。
- 避免把编码简化成“整列只保存一次值，再让所有行指向它”。字典编码可以把重复完整值映射为较短编号，RLE 可以记录连续相同值及重复次数；具体编码由存储层按数据特征选择。Page 压缩则在编码后的字节上寻找重复片段，因此两层收益可能同时存在。
- 区分两层机会：`event_type` 只有 `cart`、`purchase` 两个完整取值，列编码可能高效表示重复值；`event_context` 的完整字符串因 `event_id` 不同而逐行唯一，JSON 字段名及消息文本仍反复出现，Page 压缩可以利用重复的字节片段。高重复值不等于任何压缩算法都会取得固定的表级压缩率；完整值唯一也不等于 Page 压缩没有收益。
- 说明 Page 尺寸、列编码方式、Segment/Tablet 的索引及元数据等开销都会影响小表的报告大小；表级报告无法隔离某一列节约的字节，也不能推断 CPU 或查询速度。
- 说明 4.1.3 所属版本从 4.0.3 起默认使用 Zstandard（ZSTD）；仍以本地 `SHOW CREATE TABLE` 和实际构建验证为准。
- 比较 `LZ4`/`LZ4F`、`LZ4HC`、ZSTD、Snappy、Zlib 与不压缩的主要权衡：压缩和写入成本、解压 CPU、读取字节与存储占用。官方算法列表将其记为 `none`，但本地 `doris-4.1.3-rc02-7126cf65d96` 建表实测接受并回显的属性值是 `NO_COMPRESSION`；Lab 使用实测值。
- 明确 Doris 通过表级 `PROPERTIES ("compression" = "...")` 选择算法；不能把 ClickHouse 每列 `CODEC(...)` 示例翻译成 Doris DDL。
- 给出场景决策：没有代表性证据时保留默认 ZSTD；频繁读取且解压 CPU 已经成为瓶颈时，尝试 LZ4F 并测量查询 CPU、时延及额外存储/I/O；存储或读取 I/O 昂贵时优先验证 ZSTD 的实际节省。`NO_COMPRESSION` 是对照而非普遍建议。不要只凭算法名称或实验中的压缩率承诺性能。

官方参考：[数据压缩](https://doris.apache.org/docs/4.x/table-design/column-compression/)、[FE `default_compression_type`](https://doris.apache.org/docs/4.x/admin-manual/config/fe-config/)。

#### 10.3 用相同逻辑数据比较压缩选择

**需求场景：** 团队需要决定是否偏离默认 ZSTD，而不是只根据算法介绍做选择。

- 控制变量：列、Table Model、Key 顺序、Partition、Bucket、输入行、导入批次和副本数保持相同，只改变 `compression`。
- 用同一批确定性 `INSERT ... SELECT` 输入和相同的行数核对比较对象；本实验不为三张副本重复展示相同的业务汇总查询。
- 压缩对照必须从空表装入同一批确定性输入，不能在已有数据上重复追加后继续比较。具体的清理、重建和导入顺序属于 Lab 的可重跑设计，Course 只说明为什么输入批次和装载次数必须一致。
- 从同一天的 `events_modelled` 确定性生成一个结构化事件日志 `event_context`：`event_id` 让完整字符串逐行不同，而 JSON 字段名、消息文本等字节模式反复出现。用 `COUNT(DISTINCT ...)` 验证“完整值不重复”，再用表级存储报告比较这种输入下不同 Page 压缩设置的整体结果；不能只靠该报告把收益归因于 `event_context`，也不能只靠不同取值数量预测压缩比。Doris 不照搬 ClickHouse 的 `system.parts_columns`、Compact/Wide Part 或逐列 Codec 实验。
- 用 `SHOW CREATE TABLE` 确认声明的算法；用 `SHOW DATA`、`SHOW PARTITIONS` 或 `SHOW TABLETS` 读取 Doris 报告的压缩后存储大小和副本范围。
- 解释 `SHOW DATA` 的 Size 包含副本，比较单副本小表时仍可能受文件头、索引、Segment 数和元数据上报延迟影响。
- 不把一次小数据结果写成普遍压缩率，也不使用共享容器上的单次查询时间给算法排名。
- **实验衔接：** 只用 `NO_COMPRESSION`、`LZ4F` 与 `ZSTD` 三张对照表，均装入相同事件和相同的生成日志文本；先展示两个 `event_type` 的值及频数、完整日志值逐行不同但前缀共享，再核对行数和报告大小，最后判断差异足以支持哪一种存储判断、尚不足以支持哪一种 CPU/时延判断。`NO_COMPRESSION` 仍保留列编码及表结构开销，不等于原始行字节数；实验文本是教学构造，不代表实际生产事件的压缩率。

官方参考：[SHOW DATA](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/data-and-status-management/SHOW-DATA/)。

#### 10.4 把“TTL”翻译成 Doris 的完整分区保留

**需求场景：** 只保留最近若干天的在线事件，同时预先准备未来写入范围。

- Manual Partitioning 适合边界由业务显式控制的场景；Auto Partitioning 根据到达的数据值创建缺失 Partition；Dynamic Partitioning 根据当前时钟滚动创建未来 Partition 并删除窗口外的历史 Partition。
- Auto Partitioning 是当前文档推荐的自动建分区方式，但它本身不按时钟删除旧范围；滚动保留仍需 Dynamic Partitioning 或外部管理流程。
- Doris Dynamic Partitioning 支持单个 `DATE`/`DATETIME` Range Partition Key；课程按完整 Partition 解释保留，不描述逐行 TTL。
- ClickHouse 行 TTL、列 TTL、默认值替换和 `MATERIALIZE TTL` 只作为差异对照，不进入 Doris SQL 示例。
- **实验衔接：** 使用相对当前时钟生成的小型事件表，避免把固定历史日期直接放入今天的动态窗口。

官方参考：[手动分区](https://doris.apache.org/docs/4.x/table-design/data-partitioning/manual-partitioning/)、[自动分区](https://doris.apache.org/docs/4.x/table-design/data-partitioning/auto-partitioning/)、[动态分区](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning/)。

#### 10.5 定义滚动窗口并处理迟到数据

**需求场景：** 保留昨天到今天的数据、预建明天的范围，同时保留一个业务指定的历史例外。

- `dynamic_partition.time_unit` 决定按小时、日、周、月或年滚动；`start` 决定最早保留偏移，`end` 决定预创建到未来多远。
- `dynamic_partition.time_zone` 决定“今天”的计算基准；周/月边界还受起始日配置影响。
- `create_history_partition` 控制首次创建时是否补齐窗口内历史 Partition；它不同于迟到数据到达后任意创建窗口外 Partition。
- `reserved_history_periods` 用于保留明确的历史时间范围，但不能替代完整归档策略。
- 分析三种迟到数据：仍落在现存 Partition、落在保留例外、落在已删除且不会自动重建的范围。第三种写入不能假定成功。
- **实验衔接：** Course 用按日保留解释业务选择；Lab 为了观察时间自然推进，使用小时分区和一个位于保留边界的标记事件，先展示小时边界与行归属，再于下一个整点之后观察最旧 Partition 被调度器移除；单独验证一个窗口外迟到写入的实际错误。具体 `start` 值和事件 ID 留在 Lab 大纲中。
- 强调动态策略删除的是整个时间 Partition，不是只删除用于观察边界的标记行；其他落在同一小时范围内的行会一起退出在线表。

#### 10.6 分开验证配置、调度和过期结果

**需求场景：** `ALTER TABLE` 已成功，但旧 Partition 仍然可见。

- `ALTER TABLE ... SET` 成功只证明属性被接受；Dynamic Partition 调度线程按 `dynamic_partition_check_interval_seconds` 周期执行，不保证立即变化。
- `time_unit` 最细是 `HOUR`，不能配置“只保留几分钟”的 Partition 窗口。Lab 采用真实的整点滚动，不修改 FE 检查间隔；调度周期仅影响越过整点后任务何时执行，不能改变小时 Partition 的保留边界。具体运行值必须从目标环境读取，不写成课程中的固定常量。
- 用 `SHOW DYNAMIC PARTITION TABLES` 检查 Enable、State、LastSchedulerTime、LastCreatePartitionMsg 和 LastDropPartitionMsg。
- 用 `SHOW PARTITIONS` 检查实际 Partition 集合，用 SQL 检查仍可见的业务日期与指标；三类证据分别回答不同问题。
- 实验把一个事件放在当前滚动窗口的最早小时，显示其所属完整小时与下一整点的最早到期时刻；暂停 Notebook 后，学员可在该时刻之后回来并重新连接。helper 先判断是否已跨过整点：未到时提示返回时间，不长时间阻塞；跨过后才进行有界的调度等待。再次执行相同 `SELECT` 并检查实际 Partition 集合，策略不变，也不执行手动 `DROP PARTITION` 或修改全局 FE 配置。
- 区分两个时刻：跨过下一整点只表示最旧 Partition 已经处于窗口之外；真正从在线表消失还要等 Dynamic Partition 调度器运行。计时器只在已经满足到期条件后等待调度，超时给出最后状态，不无限轮询，也不把等待时长解释为 TTL 精度。
- Partition 从查询结果消失不证明磁盘空间立即回收。回收站保留和后台清理可能继续占用空间，实验不声称观察到具体 Rowset、Segment 或回收字节。
- Doris 没有本实验可调用的 `MATERIALIZE TTL` 等价命令；不能为了模仿 ClickHouse 强制 Compaction。

#### 10.7 将冷热分层作为部署选择，而不是本地假演示

**需求场景：** 近期数据需要本地高速介质，较老数据需要更低成本的存储。

- 本地 SSD/HDD 分层通过 Partition 的 `storage_medium` 与 `storage_cooldown_time` 表达，前提是 BE 实际配置了不同介质的数据路径。
- 本地到远端的分层通过 Resource、Storage Policy 与 `cooldown_ttl` 把冷数据迁移到 S3 兼容存储或 HDFS；远端数据可靠性依赖外部存储自身保障。
- Storage Policy、Table Model、备份恢复和存算分离模式之间存在限制，设计时必须重新核对当前版本。
- Module 10 Lab 不访问 AWS S3、不创建远端 Resource，也不把同一 Docker 文件系统上的多个目录称为冷热介质；课程用选择场景和官方架构图解释这一能力。

官方参考：[本地/远端冷热分层](https://doris.apache.org/docs/4.x/table-design/tiered-storage/remote-storage/)、[Partition 属性](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/table-and-view/table/ALTER-TABLE-PARTITION/)。

#### 10.8 在自动保留之外建立恢复边界

**需求场景：** 旧 Partition 被错误删除，或错误已经传播到所有在线副本。

- 在线副本解决节点故障，不撤销已提交并复制的错误操作。
- 对不带 `FORCE` 的 Database、Table 或正式 Partition 删除，Doris 将对象放入回收站；先用 `SHOW CATALOG RECYCLE BIN` 确认对象身份和保留资格，再选择 `RECOVER`。FE 参数 `catalog_trash_expire_second` 的官方默认值是 **86400 秒（24 小时）**，本地 4.1.3 沙箱当前值也是 `86400`；实际部署可以修改，条目也可能被主动清理，不能把“默认一天”当作恢复保证。`DROP ... FORCE` 绕过这条可恢复路径，不能靠 `RECOVER` 撤销该次强制删除。
- 区分两种删除用途：Lab 初始化可以对自己拥有的旧沙箱对象执行不可恢复的 FORCE 清理，以确保实验可重跑；正式恢复演示必须对目标 Partition 使用不带 `FORCE` 的删除，再查回收站并恢复。不能从初始化清理方式推导生产删除建议，具体对象名留在 Lab 大纲中。
- 同名对象、对象 ID、保留时间、权限和 `FORCE` 会影响恢复结果；恢复命令成功后仍需核对结构、已知标识、行数和指标。
- Lab 故意不预先保存 Partition ID，并在受控环境中按名称恢复最近删除的目标 Partition，用来证明“不知道 ID 仍可能恢复”；Course 必须同时说明同名历史条目会产生歧义，真实事故应在回收站中结合 TableId、PartitionId 与 DropTime 选择目标。
- 不承诺 Dynamic Partition 自动淘汰的每个对象都能作为操作流程依赖回收站恢复；实验恢复使用单独的手动 Partition，和调度器样本分开。
- 回收站不是备份。跨集群恢复或整个集群丢失需要 Repository Snapshot 或从权威来源重放，并根据 RPO/RTO 定期验证。
- 基础实验不创建备份仓库；课程只说明当前 Doris 备份恢复的部署限制、异步物化视图、Storage Policy、Colocation Group 和动态分区恢复后的额外工作。

官方参考：[RECOVER](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/recycle/RECOVER/)、[FE 配置](https://doris.apache.org/docs/4.x/admin-manual/config/fe-config/)、[备份恢复概览](https://doris.apache.org/docs/4.x/admin-manual/data-admin/backup-restore/overview/)。

### 模块 10 实验：比较压缩并验证分区生命周期

实验文件：[Lab 10 Notebook](module10-managing-data/lab10_manage_data.ipynb)。实验使用 Level 1–8 的单节点 `doris-rta` 和 `doris_course`，不要求 Module 9 多节点集群运行；只读 `events_modelled` 的一天范围，其他数据均在本地生成。所有可变对象使用 `m10_*` 名称，不访问 AWS S3。以下编号严格对应 Notebook 的执行顺序。

0. **Initialize the Lab。**
   - **目的与数据环境：** 定位课程根目录并加载 `DorisLab` 与 UI helper；不启动 Docker、不连接 Doris、不修改表。内核重启后只需重新运行这里。
   - **期望结果：** `lab` 对象创建完成，没有数据库输出。
   - **说明：** Python 会话状态与 Doris 容器/命名卷状态彼此独立。

1. **Section 1A：启动单节点环境并检查压缩输入。**
   - **目的与数据环境：** 启动或复用 `doris-rta`，连接 `doris_course`，只读 Lab 4 的 `events_modelled` 在 `[2020-03-01, 2020-03-02)` 的行数；不修改源表。
   - **期望结果：** 完整一天为 **75,259** 行，否则提示先完成 Lab 4。
   - **说明：** 这建立三种压缩表共同的数据范围，只验证已知行数，不把它当作逐字段一致性证明。

2. **Section 1B：重建并装载 `NO_COMPRESSION` 对照表。**
   - **目的与数据环境：** `DROP ... FORCE` 仅清理旧的 Module 自有 `m10_events_none`，随后创建固定一 Partition、四 Bucket、单副本的 Duplicate Key 表，并用确定性 `INSERT ... SELECT` 为每行生成 `event_context`；完整字符串因 `event_id` 唯一，但 JSON key 与说明文本重复。
   - **期望结果：** `m10_events_none` 提交 **75,259** 行，表属性为 `NO_COMPRESSION`。
   - **说明：** `NO_COMPRESSION` 仍保留 Doris 列编码，只跳过 Page 压缩，因此它是 Page 压缩对照，不是源文本原始字节大小。

3. **Section 1C：以相同结构和输入重建 `LZ4F` 表。**
   - **目的与数据环境：** 单独删除、创建和装载 `m10_events_lz4f`；列、Key、Partition、Bucket、副本与生成 SQL 均与 baseline 相同，只把表级 compression 改为 `LZ4F`。该代码框可单独重跑，但三个建表代码框不是一个跨表原子事务。
   - **期望结果：** `m10_events_lz4f` 提交 **75,259** 行。
   - **说明：** 控制表结构和输入后，后续报告大小差异才可用于比较当前 Page 压缩选择。

4. **Section 1D：以相同结构和输入重建 `ZSTD` 表。**
   - **目的与数据环境：** 单独删除、创建和装载 `m10_events_zstd`，唯一实验变量为表级 `ZSTD`；它也是当前构建的 FE 默认压缩类型。
   - **期望结果：** `m10_events_zstd` 提交 **75,259** 行。
   - **说明：** 当属性等于默认值时，`SHOW CREATE TABLE` 可能省略显式 property，helper 需结合 FE `default_compression_type` 解析有效算法。

5. **Section 1E：观察低基数列值与唯一字符串中的共同字节。**
   - **目的与数据环境：** 在 `m10_events_none` 上按 `event_type` 分组，显示行数、完整 `event_context` distinct 数以及短前缀；不删除重复行、不读取单列物理文件。
   - **期望结果：** `cart=56,961`、`purchase=18,298`；两个类型中 `distinct_contexts=event_count`，完整字符串全部不同，但示例前缀中的 `source/schema/pipeline/message` 结构相同。
   - **说明：** `event_type` 的少量取值可先受列编码影响；完整字符串不重复仍可因相同字节模式受 Page 压缩。该查询不能证明 Doris 选择了哪种内部编码，也不能给出逐列压缩比。

6. **Section 1F：等待元数据并比较三张表的存储报告。**
   - **目的与数据环境：** 先用 SQL 确认三表可查询，再有界等待 `SHOW DATA` 报告 75,259 行和非零大小；汇总有效算法、解析来源、逻辑行、报告大小、Partition、Tablet、副本和相对 `NO_COMPRESSION` 的节省比例。
   - **期望结果：** 三行均为 75,259 行、一 Partition、四 Tablet、单副本，effective compression 分别为 `NO_COMPRESSION`、`LZ4F`、`ZSTD`；本地验证中 LZ4F 与 ZSTD 都明显少于 baseline，但具体大小和百分比允许变化。
   - **说明：** 这是整表、当前布局和当前元数据快照的存储报告，不能把差异全部归因到 `event_context`，也不能据此推断 CPU、延迟或通用压缩率；是否修改默认值仍需代表性生产数据和工作负载测试。

7. **Section 2A：创建五个小时 Partition 的 Dynamic Partition 窗口。**
   - **目的与数据环境：** 设置 Doris 会话和动态分区时区为 `Asia/Shanghai`，强制删除重建 Module 自有 `m10_retained_events`；配置 `time_unit=HOUR`、`start=-3`、`end=1`、`create_history_partition=true`，并等待五个初始 Partition。该步骤开始一次新的时钟观察，返回后不能重跑。
   - **期望结果：** 当前表拥有“前三个完整小时 + 当前小时 + 下一小时”共五个 Range Partition。
   - **说明：** 规则管理完整小时边界，不是从每行写入时刻开始的精确三小时 TTL；设置相同的会话和调度时区避免边界解释不一致。

8. **Section 2B：插入三个时间标记并记录最早过期边界。**
   - **目的与数据环境：** 向刚创建的窗口插入 `NOW()-3 HOUR`、`NOW()-2 HOUR` 和 `NOW()` 三条已知事件；查询事件 `1001` 的实际时间与 `eligible_at`，并显示调度状态及每个 Partition 的半开边界和行数。
   - **期望结果：** 三行写入成功；`1001` 位于最旧保留小时，`eligible_at` 是下一整点；五个 Partition 中三个各有一行，另两个为空，具体名称与时间随运行时刻变化。
   - **说明：** 已满三小时的事件仍可在线到其整个小时 Partition 越过窗口且调度器完成检查，证明 Dynamic Partition 是整段生命周期管理。

9. **Section 3A：跨整点后有界等待自动删除。**
   - **目的与数据环境：** 学员可关闭 Notebook 或重启内核，但必须保留容器/卷且不能重跑 Section 2；回来后启动或复用 `doris-rta`、重新连接并恢复时区。若尚未到 `eligible_at`，helper 显示准确返回时间并停止；越过边界后最多等待 900 秒，显示实时计时器，不修改 FE 检查间隔、不改 `start`、不手动 DROP。
   - **期望结果：** 已删除时立即成功；尚未删除时计时器在调度器移除最旧 Partition 后结束；超时会给出最后状态而不是无限阻塞。
   - **说明：** 计时测的是整点后等待调度器运行的时间，不是三小时行级 TTL，也不是物理空间回收耗时。

10. **Section 3B：用相同 SQL 与 Partition 状态确认逻辑过期。**
    - **目的与数据环境：** 再次按 `event_id=1001` 查询，读取 Dynamic Partition 调度状态和当前 Partition 窗口；不执行任何删除命令。
    - **期望结果：** `1001` 返回零行，原最旧小时已不在 Partition 列表中；若只跨一个小时，`1002/1003` 通常仍在线，离开更久时允许更多完整小时过期。
    - **说明：** SQL 答案与实际边界证明该时间范围已不在线，调度状态只证明调度器观察；这仍不能证明所有 BE 物理字节已立即回收。

11. **Section 3C：尝试写入窗口之外的迟到事件。**
    - **目的与数据环境：** 插入当前整点前四小时的事件 `1099`，要求捕获 `no partition for this tuple`；随后显示仍在线的行。
    - **期望结果：** 写入被拒绝，在线表中既没有已过期的 `1001`，也没有失败的 `1099`；更新事件是否仍在取决于实际离开时长。
    - **说明：** Dynamic Partition 不会替业务决定如何处理窗口外迟到数据；业务需选择拒绝、转存或显式管理历史 Partition。

12. **Section 4A：创建与调度器隔离的手动恢复样本。**
    - **目的与数据环境：** `DROP TABLE IF EXISTS m10_recovery_events FORCE` 仅用于不可恢复地清理上次 Lab 自有旧表；随后创建手动 Range Partition 表，`p_recover` 存两行、`p_keep` 存一行，并先查询两天汇总。该表不启用 Dynamic Partition。
    - **期望结果：** 2020-03-01 为两行、49.90；2020-03-02 为一行、9.95。
    - **说明：** 独立手动表避免自动调度改变恢复样本；初始化的 FORCE 清理和下一步正式的不带 FORCE 误删必须区分。

13. **Section 4B：不带 `FORCE` 删除 Partition，并在事后查询回收站。**
    - **目的与数据环境：** 执行 `ALTER TABLE ... DROP PARTITION p_recover`，不预先记录 Partition ID；删除后先查询在线汇总，再按名称执行 `SHOW CATALOG RECYCLE BIN`，展示 Type、TableId、PartitionId 与 DropTime。
    - **期望结果：** 在线只剩 2020-03-02 的一行 9.95；回收站至少包含一个名为 `p_recover` 的 Partition 条目，可能还包含旧运行的同名历史条目。
    - **说明：** 不带 FORCE 的手动 Partition 删除进入有限期回收路径；默认 `catalog_trash_expire_second=86400` 只是当前恢复窗口默认值，不是保证。生产事故必须结合 ID 与时间确认目标。

14. **Section 4C：在未预先保存 ID 的情况下按名称恢复。**
    - **目的与数据环境：** 在刚刚完成的隔离实验中执行不带 ID 的 `RECOVER PARTITION p_recover FROM m10_recovery_events`，再查询两天完整汇总。该设计有意选择同名对象中最近删除的条目。
    - **期望结果：** 恢复后重新得到 2020-03-01 两行 49.90 和 2020-03-02 一行 9.95。
    - **说明：** “不知道 ID 也可能恢复”依赖目标恰是最近删除且条目仍有效；若同名历史复杂，应使用回收站 ID 精确选择。`DROP ... FORCE`、行级 DELETE、自动淘汰和整集群丢失不能套用此恢复结论，回收站也不是独立备份。

15. **Stop、Restart 与 Lab complete。**
    - **目的与数据环境：** 可选停止单节点 `doris-rta` 释放资源，同时保留容器、镜像、FE/BE 命名卷和全部 `m10_*` 对象；幂等重启后重新连接并检查三张压缩表与恢复表。
    - **期望结果：** 停止后为 `exited`；重启后为 `healthy`，三张压缩表各 **75,259** 行，`m10_recovery_events` 为 **3** 行。
    - **说明：** 停止/重启验证本地命名卷持久化，不证明备份、跨集群恢复或冷热介质迁移；结尾 `Lab complete` 用一段话回顾压缩选择、小时保留、迟到数据和回收站恢复，不使用证据汇总表格。

### 实验 10 的证据边界

- 相同的确定性插入 SQL 和行数核对支持受控比较；不把行数相同当作逐行相等的独立证明。`SHOW CREATE TABLE` 与 FE 默认值确定有效算法；存储元数据只说明当前样本和当前布局报告的压缩后大小，不拆分逐列贡献。
- Dynamic Partition 属性证明策略定义，调度状态证明调度器观察，`SHOW PARTITIONS` 与 SQL 结果证明某个完整范围当前是否在线；三者不能互相替代。
- Partition 不可查询不等于物理字节已删除；回收站 Size、Tablet Size 或磁盘可用量也可能异步变化。
- 单节点容器不能验证介质迁移、远端对象可靠性、备份恢复、并发负载或生产压缩收益。
- Lab 只操作明确列出的 `m10_*` 对象和临时 FE 配置；共享 helper 必须在异常路径恢复原配置。

### 测验 10 的已实现覆盖范围

[Quiz 10 Notebook](module10-managing-data/quiz10_data_lifecycle_and_recovery.ipynb) 与 [Quiz 10 YAML](module10-managing-data/quiz10_data_lifecycle_and_recovery.yaml) 包含六道独立场景题，覆盖：

1. 根据查询频率、CPU 与存储目标选择压缩侧重点。
2. 结合 Partition、Bucket、Tablet、Replica 与 `SHOW DATA` 的统计范围，判断两张物理布局不同的表能否用于给压缩算法排名。
3. 区分 Doris 表级压缩与 ClickHouse 列级 Codec。
4. 在 Manual、Auto 与 Dynamic Partitioning 之间选择。
5. 根据 `start`、`end`、时区和迟到日期预测 Partition 与写入结果。
6. 区分属性成功、调度完成、逻辑到期、回收站恢复、物理回收和备份恢复。

测验不依赖 Docker、Doris、S3 或已经运行的 Lab；每题自行提供必要的表定义、时间基准和元数据片段。


## 准备情况与开发前置验证

本节记录开发状态，与各模块内容大纲分开。检查日期：**2026-09-28**。

### 本地文件现状与缺失产物

初始化前，Level 3 README 仅列出三个主题和隔离要求，没有模块目标、学习目标、章节顺序、数据约定、测验计划或证据矩阵。每个 `course.md` 只有标题和一句范围说明。因此不存在可以直接认可或判定过时的详细旧大纲。

| 模块 | 现有内容 | 缺失产物 | 已实现文件 |
| --- | --- | --- | --- |
| 8 | 已实现英文 Course、已验证的 Lab 8、共享 helper，以及六题 Quiz Notebook 与 YAML | 无 | `course.md`、`lab08_accelerate_queries.ipynb`、`quiz08_acceleration_choices.ipynb` 及 `.yaml` |
| 9 | 已实现英文 Course、Lab 9 三个部分、多节点 Compose、HAProxy、共享 helper，以及六题 Quiz Notebook 与 YAML；已在 Doris 4.1.3 验证 Bucket Shuffle 与 Colocate 计划 | 无 | `course.md`、`lab09_observe_sharding_and_replication.ipynb`、`quiz09_distribution_and_availability.ipynb` 及 `.yaml` |
| 10 | 已实现英文 Course、已验证的 Lab 10、压缩/动态分区/回收站共享 helper，以及六题 Quiz Notebook 与 YAML | 无 | `course.md`、`lab10_manage_data.ipynb`、`quiz10_data_lifecycle_and_recovery.ipynb` 及 `.yaml` |

表中 Course、Lab 与 Quiz 均已创建。Quiz 沿用 Level 2 的共享 `CourseQuiz`、本地 YAML、交互式反馈和导航方式；题目独立提供所需事实，不依赖 Docker、Doris、S3、Kafka、已运行的 Lab 或系统时钟。在两个课程目录及已检查的工作区上层目录中，未发现适用的 `AGENTS.md` 或 `SKILL.md`。

### 已核验的本地资产

初始化时的只读检查确认一个存活 FE 和一个存活 BE，二者报告的版本均为 `doris-4.1.3-rc02-7126cf65d96`。`SELECT VERSION()` 返回 MySQL 兼容版本字符串 `5.7.99`，因此应使用 FE/BE 版本元数据确认 Doris 构建。实验 8 随后在同一构建中完成验证。

| 资产 | 已观察到的定义或结果 | 使用方式 |
| --- | --- | --- |
| `events` | Duplicate Key `(event_time, event_id, user_id)`；Random Buckets Auto；10,158,080 个逻辑行 | 保留模块 1 基线 |
| `events_modelled` | 相同 Duplicate Key；2019 年 12 月和 2020 年 3 月的月度 Auto Range Partition；`HASH(user_id)`，每分区 10 个 Bucket；10,158,080 行，收入 39,984,455.64 | 只读，用于模块 8 有界副本 |
| `daily_event_metrics` | Aggregate Key `(event_date, region, event_type)`；280 个组，代表 10,158,080 个事件，收入 39,984,455.64 | 参考其数据约定，不描述为自动维护 |
| `dim_products` | Unique Key `product_id`；`HASH(product_id)`，4 个 Bucket；204,231 行 | 只读维度来源 |
| 模块 7 表 | `order_state`、`order_merge_target`、`order_merge_changes`、`order_deletions`、`order_lifecycle` 均存在；`order_state` 使用 Sequence column `updated_at` | 全部保留 |

其他本地表，包括 `price_event_cases` 和 `product_price_history`，不默认属于 Level 3。表存在不代表可以清理。上表中的数量来自 SQL 查询结果，不代表物理行数。

| 归属模块 | 建议对象命名 | 数据来源与隔离方式 |
| --- | --- | --- |
| 模块 8 | `m08_events`、`m08_products`、`m08_events_unindexed`、`m08_events_indexed`、`m08_purchase_view`、`m08_sync_metrics`、`m08_async_category_metrics` | 有界本地副本及自有追加数据，不在其他模块基表上附加结构 |
| 模块 9 | `m09_events`、`m09_users`、`m09_availability_events` | 隔离多节点环境中从只读课程 S3 源导入的有界样本；`m09_events` 与 `m09_users` 复用兼容的 `user_id` 分布 |
| 模块 10 | `m10_events_none`、`m10_events_lz4f`、`m10_events_zstd`、`m10_retained_events`、`m10_recovery_events` | 单节点环境中的有界本地副本和相对当前小时的微型数据；不访问 S3 |

使用明确的对象归属清单，不做通配符清理。重复运行必须处理依赖视图、未完成任务、恢复后的名称和部分完成的步骤。Module 9 只读导入课程 S3 数据的有界子集；Module 10 的基础计划不访问 AWS S3。

### 共享支持的复用与缺口

| 领域 | 已检查的现有支持 | 执行前需要补齐的能力 |
| --- | --- | --- |
| 根目录定位与界面 | 向上查找 `COURSE_ROOT`、`DorisLab`、统一青绿色样式、原始日志展示 | 继续支持从根目录启动 Jupyter 和直接在 VS Code 打开 Notebook |
| SQL 连接 | 显式 `connect` 接受主机与端口；自动 `_require_connection` 默认 localhost:19030；假定 root 和空密码 | Module 9 需区分直连 FE、代理入口与实际协调查询的 FE；重连绑定选定环境并核实身份，不能静默回退到基线环境 |
| Docker | 网络、存储卷、健康检查基础函数、单容器 All-in-One 生命周期和 Module 9 多节点 Compose 支持 | Module 9 需支持服务级 2 BE → 3 BE 启动、代理健康与可观测连接分配；Module 10 复用单节点 `doris-rta` 的 Stop/Restart 模式；不新建模块级 Python 文件 |
| Profile 获取 | `profiles.py` 转调 `DorisLab`；支持原始计划和 Join Runtime Filter 片段 | FE HTTP 地址不能固定为单节点 localhost:18030；经代理连接时需定位实际协调查询的 FE，并保留查询、算子、BE host 和实例身份 |
| 扫描摘要 | `compare_profiles` 提取少量计数及固定结果别名 | 保留原始索引、物化视图、聚合、Exchange 证据，避免只取首个匹配或跨无关算子汇总全文 |
| 元数据 | 已有 Partition/Tablet 摘要 | 保留副本放置行；不能沿用将元数据 `RowCount` 标成 `Logical rows` 的做法；精确行数使用 SQL |
| 后台任务 | 已有 Routine Load 专用等待逻辑 | 为物化视图、索引、结构变更、保留策略和副本健康提供有界等待，显示错误及最后状态 |
| 会话设置 | Profile 辅助函数保存并恢复多个变量 | 恢复逻辑还需覆盖初始化和采集失败，区分结果缓存与存储缓存 |
| 测验 | `CourseQuiz.from_yaml`、独立导入、校验、导航、反馈、重试和测试 | Module 8–10 已创建模块内 Notebook 与 YAML；未修改 `quiz.py`，并已在真实 JupyterLab 检查单选按钮首行对齐 |

实验 8 已在共享 `profiles.py` 中增加 `capture_query`、临时会话设置恢复和保留算子范围的原始扫描计数展示；继续使用现有本地 FE Profile 接口。物化视图任务等待、结果核对与选中扫描检查已整合到共享 `DorisLab`，通过参数传入表名、视图名和任务 ID，不在共享实现中硬编码模块 8 对象。Notebook 通过 `lab` 调用；任务等待按新 Job/Task ID 识别本次提交，处理失败和超时，并在重置前等待旧实验任务结束。模块目录不再包含 Python 支持文件。多节点地址隔离等后续缺口仍需处理。缺失计数不填零，不累加 MergedProfile 与 DetailProfile。

部分 Level 2 测验 YAML 的对齐字段仍引用旧章节号，并带有 `course_review_required` 标记。后续应以当前课程标题和 Notebook 单元格为对齐依据，不盲目复制旧映射。本轮不修改既有内容。

### 范围修正与 ClickHouse 边界

8 → 9 → 10 的顺序合理，原先缺失的选择依据和证据结构已在上文补齐。开发时避免以下范围扩张和假设：

| 主题 | 范围决定 |
| --- | --- |
| Prefix Index、裁剪、手动汇总重建 | 仅作前置回顾，模块 8 新增持续维护的物化结果与二级索引选择 |
| 所有逻辑 Join 和分布提示 | 模块 6 已覆盖，模块 9 只对照本场景的 Bucket Shuffle 与 Colocate 实际计划 |
| upsert、部分列更新、MERGE、清空、覆盖 | 模块 7 已覆盖，模块 10 新增压缩、分区级保留与恢复边界 |
| ClickHouse Projections、MergeTree parts/granules、插入数据块触发的物化视图 | 不改名当作 Doris 机制，不假设历史回填语义相同 |
| Keeper、ReplicatedMergeTree、Distributed 表、`ON CLUSTER` | 不将其部署和 SQL 模型照搬到 Doris FE/BE 与 Tablet 副本 |
| ClickHouse 列级 Codec、行级/列级 TTL、`MATERIALIZE TTL`、`OPTIMIZE FINAL` | 不用来描述 Doris 表级压缩、Dynamic Partition 保留或 Doris Compaction |
| “三个副本就代表高可用” | 还需核对放置、完整版本、写入策略、FE 可用性和故障域 |
| “视图存在，所以查询已加速” | 必须同时有计划选用、实际工作量和正确结果的证据 |
| 跨主机或生产级故障切换、物理空间回收、生产网络性能排名 | 多容器环境只验证受控 FE/BE 停机、代理新连接分配、BE 副本再平衡与追赶，不扩展为这些结论 |
| SSD/HDD 与远端冷热分层、外部目录、跨集群复制、备份仓库 | 课程说明能力与限制，基础 Lab 不部署 |

本地 `ClickHouse101.pdf` 共十页，第 8–10 页描述模块 8 的加速和模块 9 的分布，模块 10 只在目录中出现。2026-09-21 已进一步读取 [ClickHouse Academy 当前学习路径](https://learn.clickhouse.com/real-time-analytics-with-clickhouse)及两份公开 Lab：Module 10 包含 Compression、TTL、配置压缩 Lab 和配置 TTL Lab。上文只借鉴问题顺序与实验方法；ClickHouse 的 Part、列级 Codec、行级/列级 TTL 和 `MATERIALIZE TTL` 不作为 Doris 能力。Doris 机制以 4.x 官方文档和本地 4.1.3 验证为准。

### 版本敏感事项验证清单

实验 8 已完成下述限定范围验证；其他功能仍需逐项验证。优先查阅 4.x 文档，再核对 `apache/doris` 的 4.1.3 源码，必要时核对本地实际构建对应提交。持续更新的 4.x 文档不能替代当前构建的测试结果。

#### 实验 8 已验证范围（2026-09-16）

- 使用本地 `events_modelled` 的 2020-03-01 子集：75,259 行、收入 5,670,241.29，并复制所引用的产品维度。实验追加一条自有购买事件，收入为 19.95。
- 普通视图与直接查询的完整分组结果一致；两者计划均扫描基表。
- 同步视图以 `(region, event_type)` 为粒度保存 `COUNT(*)` 与 `SUM(revenue)`。当前构建要求投影列使用不与基表冲突的别名；初始任务 `FINISHED` 后，区域购买报表选中 `m08_sync_metrics`，追加事件后无需手动刷新即可核对已提交变化。
- 异步视图使用 `BUILD DEFERRED REFRESH COMPLETE ON MANUAL`、`grace_period=0`，通过 `tasks("type"="mv")` 检查新的刷新任务。维度重分类后直接读取的旧存储结果保持不变；再次刷新成功后，全部品类/区域组与当前源查询一致。
- 同一品类收入 SQL 在关闭/开启异步改写时结果一致；开启时选中物化结果。`COUNT(DISTINCT user_id)` 缺少所需明细，实际计划仍扫描事实和维度。
- 两张索引对照表保持相同列、排序、分布和完整行多重集；只在一张表加载前声明 `product_id BIGINT` 倒排索引，使用数值等值谓词，无文本分词。索引运行显示正的 `RowsInvertedIndexFiltered` 和更少的 `ScanRows`，不据此承诺固定耗时比例。
- 索引过滤计数在本构建的 DetailProfile 中展示；保留 Fragment、host、PipelineTask、表/索引身份与原始单位。[本地构建对应扫描源码](https://github.com/apache/doris/blob/7126cf65d96/be/src/exec/operator/olap_scan_operator.cpp)用于核对 `ScanRows` 和索引计数注册。
- Notebook 分别从课程根目录和模块目录完整执行通过；第二次执行复用了已有实验环境并重建自有对象。两次均核对其他 17 张表的定义与行数未变化。离线测试覆盖部分设置失败后的恢复、旧成功任务排除、失败/超时、分组与重复数核对、计划候选与选中扫描的区别，以及 Profile 证据范围。

以上不覆盖后加索引的 `BUILD INDEX`、BloomFilter、定时或分区增量刷新、多节点性能及正式 4.1.3 与该候选构建之间的全部差异。

#### 实验 9 当前实现及已验证范围（截至 2026-09-28）

- 基于 Apache Doris 官方 4.1 All-in-One 多节点环境使用三个 FE，并把数据节点从两个存活 BE 扩展到三个存活 BE；Module 9 使用独立 Compose project、固定私有子网和 localhost 发布端口。初始化显式停止单节点 `doris-rta` 与 HAProxy，避免端口、内存和入口状态混淆。
- `m09_events` 固定为 12,062 行、两个 Partition、每 Partition 六 Bucket、双副本。重建时只复用这批已提交的逻辑事件作为本地来源；旧物理表及其他 Module 9 业务对象按各自步骤重建。首次没有完整本地来源时才读取只读 S3。
- 在 `be-3` 停止时，12 个 Tablet 的 24 个副本位于 `be-1` 和 `be-2`；启动 `be-3` 后，不重载数据也不发出手动迁移命令即可观察到已有副本进入新 BE，总副本数和逻辑答案保持不变。
- 停止当前直连 Master FE 后，原 MySQL TCP 会话失败；两个存活 FE 完成选举。HAProxy 只向健康 FE 建立新连接，通过代理可以重新查询 12,062 行。恢复旧 FE 后，它重新加入但不要求重新成为 Master；`L4OK` 仅表示 FE MySQL 端口的 TCP 检查成功。
- 地区聚合的普通 `EXPLAIN` 展示 12 个 Tablet 的计划范围，DetailProfile 展示本次实际选择的 BE host、TabletIds 和 ScanRows；实验不固定参与 BE 数、Tablet ID 或行数，也不把存有副本等同于参与本次扫描。
- 三副本 `m09_availability_events` 在 `be-2` 停止时由另外两个副本形成多数并提交一条已知 purchase。停机 BE 的副本版本落后且不是 current version；恢复后先观察 `Alive=true`，再等待三个副本版本追平。
- RANDOM 分布的 `m09_users` 与按 `user_id` 分布的事件输入实际选择 `INNER JOIN(BUCKET_SHUFFLE)`；用相同 6,706 个用户重建为稳定 Colocation Group 后，相同业务答案的计划选择 `INNER JOIN(COLOCATE)`，且 Join 两侧扫描之间不再出现输入 Exchange。
- 结尾使用 `docker compose stop/start` 释放和恢复进程，保留隔离集群数据，并检查事件表、用户表和停机写入事件。以上不证明共享 Docker 宿主机上的生产级无中断、跨主机故障域或性能扩展比例。

#### 实验 10 已验证范围（截至 2026-09-22）

- 在单节点 `doris-rta` 环境中只读 `events_modelled` 的 `[2020-03-01, 2020-03-02)`：75,259 行、收入 5,670,241.29；三张 `m10_*` 压缩表的完整行数与收入一致。
- 当前构建拒绝 `compression = NONE`，接受并回显 `NO_COMPRESSION`；`LZ4F` 显式回显，显式创建的 `ZSTD` 因等于 FE `default_compression_type` 而在规范化后的 `SHOW CREATE TABLE` 中省略，helper 使用 FE 默认值解析有效算法。
- 原先只复制事件列时，相同一个 Partition、四个 Tablet 和单副本样本的一次报告值分别为 `NO_COMPRESSION` 849.246 KB、`LZ4F` 848.231 KB 和 `ZSTD` 797.770 KB；这一组小差异是修改教学数据设计的原因，已不再作为当前 Notebook 的预期结果。
- 用当前 Notebook 相同的 DDL 和 `INSERT ... SELECT`（只替换为临时测试表名）在本地 4.1.3 验证：每张表仍为 75,259 行，`event_context` 有 75,259 个不同的完整字符串；`SHOW DATA` 的一次报告值分别为 `NO_COMPRESSION` 18.022 MB、`LZ4F` 2.415 MB、`ZSTD` 1.856 MB。测试表已清理。Notebook 不固定这些大小，不把教学构造文本的压缩效果推广到生产，也不比较单次查询时间。
- 先前按日版本曾在 `Asia/Shanghai` 使用 `start=-2`、`end=1` 创建四个分区；收紧到 `start=-1` 后由调度器移除最旧分区。该历史验证**不等于**新设计已跨整点完整运行通过。
- 先前按日版本临时将 `dynamic_partition_check_interval_seconds` 设为 5，并在成功或异常时恢复；当前按小时自然过期版本已不修改该全局配置。已在本地验证 `SET time_zone = 'Asia/Shanghai'` 与小时截断 SQL，但尚未等待真实整点完成整本 Notebook 回归。
- 先前按日版本验证过窗口外迟到写入返回 `no partition for this tuple`；当前按小时迟到写入仍待新流程完整验证。
- 在独立手动分区表上不带 `FORCE` 删除 `p_recover`，删除后按名称检查回收站，再以省略 ID 的 `RECOVER PARTITION` 恢复最近删除的同名对象；恢复后已知两日行数和收入全部一致。Notebook 提醒在真实事故中核对所属表、Partition ID 和删除时间以避免同名歧义。
- 原版 Notebook 的核心单元、可选 Stop/Restart 与持久化核对曾完整执行通过；新的生成文本压缩对照已单独在本地验证，但修改后的 Notebook 尚未整本重跑。模块目录没有新增 Python 支持文件。

以上不证明 Partition 离开在线表后物理字节立即回收，也不验证 SSD/HDD 迁移、远端对象存储、备份仓库或跨集群灾难恢复。

| 领域 | 编写预期结果前必须完成的本地验证 |
| --- | --- |
| 运行版本 | FE 和全部 BE 构建；当前候选发布构建与正式版本标签的区别；镜像兼容性和架构 |
| 同步物化视图 | 支持的模型、表达式、聚合；初始任务状态；历史与新增数据覆盖；扫描索引标签；依赖清理 |
| 异步物化视图 | 构建与刷新语法；任务检查方式；完成条件；源表和维度变化；直接查询新鲜度；改写与过期控制 |
| 查询改写 | 满足与不满足条件的计划、粒度、聚合推导和谓词；提示不能保证实际选用 |
| 倒排索引 | 类型与谓词、不分词语义、创建与历史数据 `BUILD INDEX` 的区别、完成元数据和实际计数 |
| BloomFilter | 谓词、类型、历史覆盖；当前文档指出 4.1.2 起 `CHAR` 行为变化，示例采用前需核实当前构建 |
| 统计信息与缓存 | 采集和检查语法、会话变量及默认值、失败时恢复 |
| Query Profile | 查询 ID、HTTP 格式、采集级别、算子名称、单位、合并与逐实例范围；避免合并与明细重复计数 |
| 多节点 | 官方 `multi-node.yml` 与 `all-in-one-4.1.3` 的兼容性；初始 3 FE + 2 BE 到 3 FE + 3 BE 的服务级启动和自动注册；`client` 三 BE 健康检查的时序；FE 代理镜像、健康检查、连接分配、失败会话重连和端口资源；Compose v2 与 `stop/start` 数据生命周期 |
| 副本 | 双副本事件表与三副本事件小表的解析配置、默认多数写入门槛及 `min_load_replica_num`；新 BE 加入后的自动均衡是否对小表发生、具体迁移和等待上限；停机写入与返回节点版本追赶 |
| 分布与共置 | 副本放置与本次查询选中的 Tablet 副本；Profile 中实际参与扫描的 BE；Bucket Shuffle 在单分区查询中的 4.1.3 计划、Broadcast 回退、Colocation Group 稳定性；新增 BE 不等于旧数据重新分桶 |
| 压缩 | 4.1.3 接受的 `compression` 值、默认算法、`SHOW CREATE TABLE` 输出、相同数据的报告大小、元数据更新延迟与副本计数范围 |
| 动态分区 | 属性、调度状态与间隔及时区、起止边界、历史与例外、迟到数据、错误、实际到期处理 |
| 回收站 | 不带 `FORCE` 的恢复资格、保留时间、身份与同名冲突、权限、分区兼容性、自动删除差异、恢复后内容 |
| 维护 | 报告值与延迟字段、Version/VersionCount/RowCount 范围；不能推断精确 Rowset/Segment 或回收字节 |
| 备份 | 后续扩展前重查支持架构、对象和恢复依赖；基础计划不访问仓库 |

已只读观察到的本地配置：

- `dynamic_partition_enable = true`。
- `dynamic_partition_check_interval_seconds = 600`。
- `catalog_trash_expire_second = 86400`。

当前[动态分区文档](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning/)列出的调度器默认值为关闭，但本地运行值为开启。因此记录实际值，不依赖默认假设。短时间运行 Notebook 也不能假定下一调度周期已经执行。[4.1.3 配置源码](https://github.com/apache/doris/blob/4.1.3/fe/fe-common/src/main/java/org/apache/doris/common/Config.java)定义了回收站保留时间，但存在保留时间不意味着所有删除方式都可恢复。

### 证据与测验约定

| 证据 | 可以支持的结论 | 不能据此推断的结论 |
| --- | --- | --- |
| 实验直接结果 | SQL 可见内容、返回结构、观察到的状态 | 未展示的内部机制或普遍生产行为 |
| `EXPLAIN` | 计划访问路径、改写、片段、分布、过滤位置 | 实际过滤行数、节省字节或耗时收益 |
| Query Profile | 一次执行中明确算子和实例范围的命名计数 | 单独证明正确性、物理回收、并行计时可直接相加 |
| 文档与源码 | 指定版本的机制和限制 | 证明 Notebook 直接观察到了该机制 |

每模块使用四至六道独立英文单选题，优先采用场景选择、结果预测和原因解释。复用 `doris_course/quiz.py` 与 Level 1–2 Notebook 风格。Notebook 目标与 YAML 保持一致，并在两种 Notebook 使用方式中检查长选项单选按钮与第一行文字的对齐。测验不依赖 Docker、Doris、S3、Kafka 或已完成的实验。

### 后续复核顺序

1. **先复核 Module 8：** 保持普通 View、同步/异步物化视图、透明改写和倒排索引之间的术语与证据边界一致。
2. **再复核 Module 9：** 按实际 Lab 的入口切换、BE 扩容与执行位置、副本版本恢复、Bucket Shuffle / Colocate 顺序核对 Course、Lab 与 Quiz。
3. **最后复核 Module 10：** 核对数据形状与压缩选择、小时级 Dynamic Partition、迟到数据和回收站恢复；跨整点自然过期仍需真实时钟与调度周期才能完成实验观察。

学员学习顺序保持 **8 → 9 → 10**。Course、Lab 与 Quiz 已经实现；后续变更继续以实际 Course 和 Notebook 为约束，在三类内容之间统一术语、场景和证据边界。
