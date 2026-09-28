# Level 3：分析数据的查询加速、分布与生命周期管理

本大纲供课程开发者参考，使用中文编写；后续面向学员的课程正文（Course）、实验（Lab）和测验（Quiz）仍使用英文。Doris 官方术语、SQL 标识符、配置项和文件名保留原文，以便与前两级课程及官方文档对照。

Level 3 延续 Level 1–2 已建立的电商分析流程：

```text
在保持分析结果正确的前提下减少查询工作量
    → 分布数据并维持可用副本
    → 随时间演进、保留和恢复数据
```

**当前状态：实验 8–9 已实现并通过关键路径验证；实验 10 暂不包含在本次更新中。** [Lab 8](module08-query-acceleration/lab8_accelerate_queries.ipynb) 与 [Lab 9](module09-sharding-replication/lab9_observe_sharding_and_replication.ipynb) 使用英文；模块 8–10 的 Course 仍是占位内容，Quiz 尚未实现。本文件保留中文开发大纲，并以实际 Lab 顺序记录 Module 8–9 的目的、预期结果和证据边界。

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

## 模块 8：在 Apache Doris 中加速查询

当前占位文件：[模块 8 课程](module08-query-acceleration/course.md)。

### 模块目标

从重复计算、选择性访问和数据新鲜度要求出发，选择查询加速方案。同时解释减少的查询工作量，以及额外的存储、写入、刷新和运维成本。

### 场景与逻辑主线

电商团队需要在同一份事件历史上提供反复查询的收入面板，以及按产品筛选的明细调查。先通过共享查询定义统一报表逻辑，再由重复聚合引出物化视图，由选择性明细查询引出索引。两条路径最终都回到同一验证流程：保持结果正确、检查计划、观察实际工作量、评估成本。

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
- 使用模块 2、6 已介绍的概念，定位可能需要减少的扫描、Join、聚合和 Exchange 工作。
- 区分结果错误、计划不合理、实际工作量过大，以及受噪声影响的总耗时；不以配置项清单开场。
- **实验衔接：** 建立结果可核对的基线，在修改本模块对象之前保留计划和 Query Profile。

#### 8.2 复用查询逻辑，不把逻辑复用当成结果存储

**需求场景：** 多个面板需要共享同一个购买收入定义。

- 普通视图用于复用查询逻辑，CTE 用于单条语句内部的逻辑组织；定义本身不代表持久化计算结果。
- 与模块 4 的 `daily_event_metrics` 对照：该表存储汇总数据，但现有填充过程没有建立自动刷新关系。
- 在明确重复计算需求后，再引入需要持续维护的预计算结果。
- **实验衔接：** 比较本模块普通视图与其定义查询的结果；结果相同不能证明发生了缓存或物化。

#### 8.3 让受支持的单表汇总与写入保持一致

**需求场景：** 反复执行的聚合必须反映基表已经提交的变化。

- 从新鲜度要求引入同步物化视图。
- 明确视图定义受到表达式、聚合函数和 Table Model 支持范围的限制，不承诺任意 SQL 或 Join 都适用。
- 区分初始构建、后续写入维护和优化器选择 rollup/index；同时说明存储与导入开销。
- **实验衔接：** 在本模块的 Duplicate Key 表上创建受支持的视图，等待构建完成，检查计划选中的扫描索引，并在追加本模块数据后核对基表查询结果。

官方参考：[同步物化视图](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/sync-materialized-view/)。

#### 8.4 用明确的新鲜度取舍复用多表计算

**需求场景：** 品类收入需要反复连接事件和产品属性，报表允许一定刷新延迟。

- 引入异步物化视图，并明确刷新约定。
- 区分直接查询视图中的存储数据，与对基表查询进行透明改写。
- 比较手动与定时刷新、全量与满足条件的分区增量刷新；维度变化同样会影响新鲜度。
- **实验衔接：** 使用本模块的事实表和维度表副本，演示手动刷新、源数据变化及刷新后的对账。核实一致性配置之前，不预先规定过期视图的改写行为。

官方参考：[物化视图选型](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/overview/)、[异步物化视图概述](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/overview/)、[管理与查询](https://doris.apache.org/docs/4.x/query-acceleration/materialized-view/async-materialized-view/functions-and-demands/)。

#### 8.5 验证预计算结果能否回答当前查询

**需求场景：** 物化视图已经存在，但仪表板仍然执行原有工作。

- 检查请求的粒度、维度、谓词以及指标是否能够从视图推导。
- 复用此前的语义区分：可加指标、需要兼容分子和分母状态的平均值，以及不可直接相加的去重计数。
- 区分构建或刷新成功、满足改写条件、优化器实际选用，以及执行工作量减少。
- **实验衔接：** 各选择一个满足条件和一个刻意超出范围的查询，检查实际计划、比较完整分组结果、读取相关扫描和聚合计数。没有命中改写也是需要解释的观察结果。

#### 8.6 不替换主要排序方式，也能定位选择性明细

**需求场景：** 面向时间查询的事件表中，产品标识不是排序键的前导列，但调查需要按产品筛选。

- 简要说明 Partition、Bucket、Prefix Index 和 ZoneMap 过滤后剩余的工作，不重复实验 2 的布局重建。
- 以不分词的 Inverted Index 作为主要二级索引示例。
- 比较适用于等值或 `IN` 谓词的 BloomFilter Index，说明假阳性和数据块内的值分布，不能只看列基数。
- 分词搜索与 NGram BloomFilter 仅作为有限的选型对照：词项匹配和子串匹配回答的问题不同。
- 说明历史数据的索引构建覆盖范围，以及存储和写入开销。
- **实验衔接：** 本模块有索引和无索引的表保持相同行、结构、分布和排序，只改变索引条件；核对结果和原始索引计数，不承诺固定加速倍数。

官方参考：[倒排索引](https://doris.apache.org/docs/4.x/key-features/inverted-index/)、[布隆过滤器索引](https://doris.apache.org/docs/4.x/table-design/index/bloomfilter/)、[索引选型](https://doris.apache.org/docs/4.x/query-acceleration/tuning/tuning-plan/optimizing-table-index/)。

#### 8.7 在强制计划前检查优化器的输入

**需求场景：** 可用结构没有被选中，或输入规模估算明显不合理。

- 使用提示前，先检查相关统计信息和谓词形态。
- 说明统计信息用于估算，不是实际运行的行数。
- 统计信息采集只针对模块 8 的对象，不对共享数据库整体执行；Join 顺序和 Runtime Filter 机制回顾模块 6。
- **实验衔接：** 记录统计信息与选中计划，不假定采集统计信息后计划一定改变。

官方参考：[统计信息采集与管理](https://doris.apache.org/docs/4.x/query-acceleration/optimization-technology-principle/statistics/)。

#### 8.8 判断查询收益是否值得维护成本

**需求场景：** 某个结构帮助了一个面板，但占用了存储和维护资源。

- 比较反复查询节省的工作与构建、写入、刷新、存储成本。
- 控制结果缓存，同时单独记录存储缓存条件。
- 保留算子身份、单位和计数汇总范围；不累加重叠计时，也不只按等待时间判断瓶颈。
- 用证据支持最终选择，并说明尚存的不确定性。
- **模块过渡：** 本地查询加速不能证明多节点容量、放置和可用性，模块 9 接着解决这些问题。

### 模块 8 实验：验证查询加速方案

实验文件：[Lab 8 Notebook](module08-query-acceleration/lab8_accelerate_queries.ipynb)。实验复用 Level 1–8 的单节点 `doris` 容器和 `doris_course` Database；只读取 `events_modelled` 与 `dim_products`，所有可变对象均使用 `m08_*` 名称。以下编号严格对应 Notebook 的执行顺序。

0. **Initialize the Lab。**
   - **目的与数据环境：** 从课程根目录或模块目录定位 `doris_course/`，加载共享 `DorisLab` 并创建 `lab`；该单元格不启动 Docker、不连接 Doris、也不修改任何表。内核重启后只需先重跑这里。
   - **期望结果：** Python 初始化完成且没有 Doris 查询输出。
   - **说明：** Notebook 的路径解析与共享 helper 可从课程根目录启动 Jupyter，也可从 VS Code 直接打开模块 Notebook。

1. **Section 1A：检查上游事件和产品数据。**
   - **目的与数据环境：** 连接已有的单节点 `doris`，要求 Lab 4 已创建 `events_modelled`、Lab 6 已创建且填充 `dim_products`；只检查 `[2020-03-01, 2020-03-02)` 左闭右开范围和产品表非空，不下载数据。
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
    - **目的与数据环境：** 可选停止单节点 `doris` 释放资源，但保留容器、镜像和命名卷；重启单元格可在容器已停止、启动中或已运行时幂等执行，并重新连接检查 `m08_events`。
    - **期望结果：** 停止后状态为 `exited`；重启后容器回到 `healthy`，完整实验后的 `m08_events` 为 **75,260** 行，且 `event_id=-8001` 恰有一行。
    - **说明：** 停止/重启不会清空 Module 8 对象；结尾 `Lab complete` 用一段话回顾普通 View、同步/异步物化视图、改写边界与倒排索引证据，不再使用“证明事项”表格。

### 测验 8 的拟议覆盖范围

约六个独立场景，覆盖逻辑复用与结果存储、新鲜度驱动的物化选择、改写条件、谓词驱动的索引选择、计划与运行证据、维护成本取舍。每个场景自行提供所需事实或小段证据。

## 模块 9：Apache Doris 的分片与副本

当前占位文件：[模块 9 课程](module09-sharding-replication/course.md)。

### 模块目标

解释数据分片、Tablet 副本和 FE 元数据副本分别解决什么需求；在可从 3 FE + 2 BE 扩展至 3 FE + 3 BE 的多容器环境中，观察跨 BE 查询执行、Bucket Shuffle / Colocate Join、FE 查询入口切换、BE 副本再平衡及故障恢复。区分存储放置、计划选择和实际运行证据，并明确单机 Docker 实验的边界。

### 场景与逻辑主线

事件服务首先需要一个不会绑定单个 FE 的查询入口。团队先识别当前 Master 并直连它，停止该 FE 后观察原连接失败，再加入带健康检查的统一入口，验证新连接能够避开故障 FE；恢复该 FE 后再继续数据实验。存储侧先在两个 BE 上建立双副本事件表，此时两个 BE 都持有每个 Tablet 的一份副本；加入第三个 BE 后，后台再平衡才使三个 BE 持有不同 Tablet 子集。完成扩容后，用一条地区聚合观察 FE 选择哪些 Tablet 副本并把扫描任务下发到哪些 BE；三台 BE 都保存副本，不代表每次查询都必须使用三台。随后用三副本事件小表观察一个 BE 停机期间的写入与返回节点版本追赶。最后复用事件与用户表，对照 Bucket Shuffle Join 和 Colocate Join，把数据放置与 Join 数据移动连接起来。

### 官方实验环境基线

Module 9 使用 Apache Doris 官方 [`multi-node.yml`](https://github.com/apache/doris/tree/master/docker/runtime/all-in-one/4.1/compose)，固定镜像为 `apache/doris:all-in-one-4.1.3`。同一镜像通过 `DORIS_ROLE` 分别启动一个进程角色，形成以下拓扑：

```text
FE：fe-1、fe-2、fe-3（始终保持三个参与选举的 Follower）
BE：先启动 be-1、be-2 → 建立双副本基线 → 加入 be-3 → 执行查询与故障实验
客户端：先直连当前 Master FE → 验证连接失败 → 改用 HAProxy 统一入口
```

- `fe-1` 初始引导集群，`fe-2`、`fe-3` 默认作为 Follower 加入；基础实验不把 `fe-3` 改成 Observer，以保留三个参与选举的 FE。
- `be-1`、`be-2` 先运行，`be-3` 留给在线扩容实验。`m09_events` 显式使用两个副本；在两个 BE 阶段每个 BE 各存放每个 Tablet 的一个副本，加入第三个 BE 后再观察放置是否变化。三副本事件小表只在三个 BE 就绪后创建。默认副本数不能代替实验中明确的建表配置。
- 当前 `client` 容器的健康检查期望三个 BE；若沿用此条件，初始阶段只启动三 FE + 两 BE，扩容后再启动 `client`。实际 Lab 需核对官方镜像对新增 BE 的注册方式，使用有界就绪检查，不用固定 `sleep` 代替。
- Module 9 使用独立 Compose project、私有子网和不与现有单节点沙箱冲突的主机端口。官方 Compose 支持 `FE_PORT`、`FE2_PORT`、`FE3_PORT`、`FE_HTTP_PORT`、`FE2_HTTP_PORT`、`FE3_HTTP_PORT`、`BE_HTTP_PORT` 和 `SUBNET`。课程候选值为 MySQL 端口 `9130`–`9132`、FE HTTP 端口 `8130`–`8132`、BE HTTP 端口 `8140` 和子网前缀 `172.31.91`，采用前必须检查占用。容器内部仍使用 Doris 默认端口。
- 在 Docker Desktop 上，主机不能直接路由到容器私网地址。需要跟随 FE 重定向到 BE 的操作应从 `client` 容器执行。当前 Notebook 的 `DorisLab.connect` 固定连接 `127.0.0.1:9130`，即 `fe-1`，停掉 Master 后才手动切换到另一个 FE；这不是 FE 负载均衡。新版实验先识别当前 Master 及其发布端口并明确直连，再停止该 FE，证明原 TCP 连接不会自动迁移；随后按官方方案加入带健康检查的轻量 HAProxy TCP 入口，让新连接避开故障 FE，并用代理统计或等价证据核对连接目标。恢复原 FE 后确认它重新加入，再为后续 Lab 保持完整 FE 拓扑。代理仍位于同一 Docker 宿主机，本身也不是冗余入口。[FE 负载均衡](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/load-balancing/)。
- 官方 Compose 默认不提供跨 `down` 的持久化。`stop/start`、`kill/start` 或再次 `up` 保留现有容器状态；`down` 删除容器、网络和其中的数据。故障实验不能用 `down` 代替停止单个节点。

官方依据：[All-in-One 镜像与多节点 Compose](https://doris.apache.org/community/developer-guide/all-in-one-image)。

### 学习目标

完成本模块后，学员应能够：

1. 区分为容量和并行工作服务的分片、为数据冗余服务的 Tablet 副本，以及为元数据服务可用性服务的 FE Follower。
2. 说明三个 FE、从两个扩展到三个的 BE、`client` 和负载均衡入口各自的职责及连接路径。
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

- 说明同一 `all-in-one-4.1.3` 镜像如何由 `DORIS_ROLE` 启动 FE、BE 和 `client` 角色。
- 区分 FE 的查询规划与元数据职责，以及 BE 的数据存储与计划片段执行职责。
- 解释 `fe-1` 初始引导、Follower 加入、两个初始 BE 注册、第三个 BE 后续加入和 `client` 健康检查的顺序。
- 使用 `SHOW FRONTENDS`、`SHOW BACKENDS` 和容器健康状态核对实际拓扑，不仅根据容器数量判断集群可用。
- 说明现有 Notebook 固定直连 `fe-1`；FE 选举不等于客户端负载均衡。统一入口需由客户端多地址机制或外部代理提供，并分别验证新连接分配与故障后重连。
- **实验衔接：** 先启动隔离 Compose project 中的三个 FE 和两个 BE，核对角色、版本、地址、当前 Master 与直连端口，证明连接没有误指向 Level 1–8 的单节点环境。

#### 9.2 分开验证 FE 选举和客户端负载均衡

**需求场景：** 三个 FE 均能提供 SQL 入口，但当前 Notebook 只连 `fe-1`；它关闭后，已有连接会断开。

- 三个 Follower 中只有一个当前 Master；它失效后，存活 Follower 可选出新的 Master。选举维护的是 FE 元数据服务，不会自动迁移原有 MySQL TCP 会话，也不提供新连接的均匀分配。
- 先识别当前 Master FE 及其 localhost 发布端口并直连，记录本次连接的协调 FE；停止这个 FE 后，用该连接再次执行查询，预期得到连接错误，而不是透明切换到另一个 FE。
- 启动带健康检查的 HAProxy 统一入口，通过多次新建连接观察其分配目标。停止一个目标 FE 后，分别检查新 Master 选举、代理摘除故障目标和通过统一入口重新连接成功；不能仅用三个 FE 端口分别可查询来声称已经负载均衡。
- 已经建立的 MySQL TCP 会话不会被 HAProxy 搬到另一台 FE；应用仍需要连接池或重试逻辑。恢复被停止的 FE 后确认它重新加入并重新进入代理可用目标，再继续后续数据实验。
- **实验衔接：** 保留“直连失效”“FE 选举”“代理健康检查与新连接分配”“客户端重连”四类证据，不承诺在途查询零中断，也不把单个 HAProxy 容器描述成冗余入口。

官方参考：[FE 负载均衡](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/load-balancing/)。

#### 9.3 区分分片、副本和新增 BE 后的自动再平衡

**需求场景：** 现有两个 BE 的存储或计算余量不足，团队加入第三个 BE，希望确认旧数据是否会被利用新节点承载。

- 副本数不能超过满足放置约束的可用 BE 数。若 `BE 数量 = replication_num`，每个 BE 都会持有每个逻辑 Tablet 的一份副本；因此 2 BE + 2 副本和原来的 3 BE + 3 副本一样，都不能展示不同 BE 持有不同 Tablet 子集。
- 实验仍先在两个 BE 上建立两个副本的事件表，用它作为扩容前基线；此时两个 BE 确实都覆盖全表。加入第三个 BE 后变成 `BE 数量 > replication_num`，后台调度器才有条件把已有副本逐步复制到新 BE，再清理旧的多余副本，使三个 BE 分担不同 Tablet 子集。
- 说明 Bucket 对应逻辑 Tablet；副本是同一 Tablet 在不同 BE 上的物理拷贝，不会增加 SQL 可见的逻辑行数。分别统计唯一 Tablet ID、元数据副本记录和每 BE 副本数，不把三者混为一谈。
- 比较扩容前后 `SHOW BACKENDS`、`SHOW REPLICA DISTRIBUTION`、少量逐 Tablet 的 `SHOW TABLETS` 和 SQL 逻辑答案；用有界等待观察调度，不把“第三个 BE 已 Alive”误读为“迁移完成”。
- 旧表仍是原来的 Partition 和 Bucket 数；新增 BE 改变可放置位置，不会自动把已有 6 个 Bucket 改成更多 Bucket。共置表再平衡期间可能暂时不稳定，Join 计划需在稳定后另行核对。
- **实验衔接：** 只启动预留的 `be-3` 并确认它已注册。比较前后 Tablet–Backend 映射；若小数据样本在有界时间内未触发可见迁移，明确展示调度状态和证据不足，不通过手动移动副本伪装成“自动再平衡”。

官方参考：[弹性扩容](https://doris.apache.org/docs/4.x/admin-manual/cluster-management/elastic-expansion/)、[副本均衡与修复](https://doris.apache.org/docs/4.x/admin-manual/maint-monitor/tablet-repair-and-balance/)。

#### 9.4 追踪一次查询选择的 Tablet 副本和 BE 扫描任务

**需求场景：** 扩容后的三个 BE 已持有不同 Tablet 子集，但团队需要知道一条查询实际使用了哪些副本和执行节点。

- `m09_events` 仍按 `HASH(user_id)` 分成 12 个逻辑 Tablet，每个 Tablet 有两个物理副本。三台 BE 是可用的放置目标；FE 对每个所需 Tablet 选择一个可用副本，不会把两个副本都扫描一遍。
- 区分业务行数、逻辑 Tablet、BE 上保存的物理副本和本次查询选中的副本。`SHOW REPLICA DISTRIBUTION` 说明副本放置，不能证明某个 BE 参与了这次查询。
- 解释 FE 如何形成 Plan Fragment，为选中的 Tablet 副本下发 Fragment Instance；BE 执行扫描与局部聚合，Exchange 传递中间结果。`EXPLAIN` 表示计划，Query Profile 中的 BE host、Tablet ID 和 `ScanRows` 才是本次运行证据。
- 多个不同的 BE host 出现在扫描 Profile 中，可以证明这次执行跨 BE 并行；没有出现的 BE 即使保存副本，也没有执行本次表扫描。副本选择和调度可能变化，因此不固定断言三台 BE 都参与、具体 Tablet ID 或具体扫描行数。
- **实验衔接：** 对 `m09_events` 执行一条地区聚合，先核对八个地区和总行数，再对照裁剪后的 `EXPLAIN` 与 DetailProfile。只解释实际出现的 BE 扫描任务，不增加第二张偏斜对照表，也不以同一宿主机耗时声称扩展收益。

#### 9.5 在一个 BE 停机时写入，并观察返回节点追赶版本

**需求场景：** 一个 BE 停止，但应用仍尝试读取和追加事件。

- 双副本表在默认“多数副本写入”策略下需要两份都成功，停一个持有副本的 BE 不能直接承诺写入成功；三副本表在一个 BE 停止后仍可由另外两个副本形成写入多数。因此在第三个 BE 已加入且稳定后，用独立的 `m09_availability_events` 三副本事件小表承载故障写入，不改动事件聚合的固定样本。
- 停机前确认三个 BE 和故障写入事件表的每个 Tablet 都有三个健康、版本完整的副本，记录每个 BE 对应的 `Version`；再停止一个明确命名的 BE 容器。
- 区分 Docker 容器被停止、FE 心跳检测到节点不可用、正在执行的请求失败和后续重试结果。
- 在两个 BE 存活时做一次可重跑的写入，确认 SQL 已提交且逻辑结果更新；随后从 `SHOW TABLETS` 分别看到存活副本与停机副本的版本状态。停机副本元数据中的旧版本不能当作已从其容器读取的物理内容。
- 使用 `kill/start` 或 `stop/start` 保留该容器的数据；不能使用会删除整个集群数据的 `down`。
- 启动原 BE 后立即读取一次节点与逐 BE 副本版本；若已经追平，如实说明恢复太快，不能保证每次都能捕捉到过渡态。随后有界等待全部副本版本一致且健康，并再次查询同一个业务值。节点 `Alive` 与副本版本追平是不同的完成条件。
- **实验衔接：** 展示写入前、停机写入后、节点刚返回和完全追平后的简短逐 BE `Version` 对照；不硬编码具体版本号，也不把原节点的追赶误称为向替代节点迁移。

官方参考：[写入高可用](https://doris.apache.org/docs/4.x/data-operate/import/load-best-practices/load-high-availability/)、[系统架构与可用性](https://doris.apache.org/docs/4.x/features-architecture/system-architecture/)。

#### 9.6 最后比较 Bucket Shuffle 与 Colocate Join 的数据移动

**需求场景：** 扩容和副本恢复完成后，事件表与用户维度频繁按 `user_id` 连接，团队希望利用已经稳定的数据放置减少 Join 交换。

- 将 Join 放在故障恢复之后，先等待参与实验的表和 Colocation Group 稳定，避免把再平衡或修复期间的临时退化当成正常计划。
- 沿用模块 6 对逻辑 Join 与物理 Hash Join 的区分，此处只研究跨 BE 的数据移动：Bucket Shuffle 保留一侧 Bucket 布局并重分发另一侧，Colocate 在稳定且兼容的组内避免该 Join 的 Shuffle。
- 只使用 `m09_events` 和同名的 `m09_users` 业务对象。先把单个事件 Partition 按 `user_id` 汇总为中间结果，并让 `m09_users` 使用不兼容的 RANDOM 布局；`[shuffle]` 只用于阻止小维度表改走 Broadcast，Doris 4.1.3 的实际计划必须出现 `BUCKET_SHUFFLE` 才继续解释。随后用相同用户数据重建同名表，使其按 `user_id` 使用六 Bucket、双副本，并与 `m09_events` 加入同一个 Colocation Group。
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

实验文件：[Lab 9 Notebook](module09-sharding-replication/lab9_observe_sharding_and_replication.ipynb)。实验使用模块目录的 `compose.multinode.yml`、固定镜像 `apache/doris:all-in-one-4.1.3`、独立 Compose project、私有子网和 localhost 端口；不与 Level 1–8 的单节点 `doris` 同时运行。首次缺少本地 baseline 时只读课程 S3 的 `[2020-03-01 00:00:00, 2020-03-01 07:00:00)`，不修改 S3。以下编号严格对应 Notebook 的 1.1–3.2 与结尾控制步骤。

0. **Initialize the Lab。**
   - **目的与数据环境：** 定位课程根目录，加载共享 `DorisLab`，记录 Compose 文件、HAProxy 统计地址、代理端口、固定 FE 服务/IP/主机端口映射和期望事件行数；不启动或停止任何容器。初始 helper 指向直连 `fe-1`，后续步骤会按实验目的切换连接。
   - **期望结果：** Python 变量与 `lab` 对象创建完成，没有集群状态变化。
   - **说明：** 内核重启不会删除容器和数据，但必须重新运行初始化以恢复本地 Python 状态。

1. **Section 1.1：建立恰好两个存活 BE 的起点。**
   - **目的与数据环境：** 检查 Docker、Compose、隔离端口和固定镜像；若 Level 1–8 的 `doris` 正在运行则停止并提示，不自动操作它。Module 9 保留已有容器 writable layer、FE 元数据和 Doris 数据，只重启 `be-1`、`be-2` 进程释放旧 RSS，显式停止 `be-3`、`client` 与 HAProxy；已有三 FE 容器同时启动以满足持久化 FE 元数据的多数派要求。这里不重建业务表。
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
   - **目的与数据环境：** 用 `--no-deps` 启动 HAProxy，避免 Compose 顺带恢复故障 FE；读取代理健康状态，建立四个独立的新 MySQL session，并比较各 FE 目标的累计连接增量；再通过代理端口 `9230` 查询事件表。
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

- 初始阶段对三 FE、两 BE 的服务级就绪检查与扩容后 `client` healthy，只证明各阶段预期节点在该时刻完成注册，不代表后续每个 Tablet 都健康。
- `SHOW FRONTENDS`、`SHOW BACKENDS`、`SHOW REPLICA DISTRIBUTION` 和 Tablet 元数据说明控制面观察到的节点与副本状态；代理侧连接记录用于检查 FE 入口分配，SQL 结果用于检查逻辑数据，`EXPLAIN` 用于检查计划，Query Profile 用于检查实际执行位置。
- 新增 BE 后看到副本数变化可支持“副本在移动”，不能据此断言新增 Bucket、逻辑行发生迁移或自动扩容已经达到生产均衡。新增节点不等于原节点副本已恢复；停机恢复实验必须分别检查版本。
- 单次正在执行的请求可能在节点停止时失败；后续重连成功不能改写为“零中断”。
- 同一宿主机上的多个容器不提供独立物理故障域，不能用于生产网络性能、磁盘容灾或跨可用区结论。
- `stop/start` 用于节点实验和结尾的可选资源释放；Notebook 不再运行 `down`，避免删除未外挂的 Module 9 数据。Notebook 只能操作 Module 9 Compose project，不能停止或删除其他模块的容器、网络和数据。

### 测验 9 的拟议覆盖范围

约六个独立场景，覆盖存储副本与查询选中的副本、跨 BE 扫描任务、Bucket Shuffle / Colocate 的条件、两 BE 到三 BE 的副本再平衡、双副本与三副本的停机写入门槛、FE 选举与客户端入口切换，以及容器级和生产级故障域的区别。每题自行提供拓扑、配置和元数据，不要求正在运行 Docker 或 Doris。

## 模块 10：在 Apache Doris 中管理数据生命周期

当前占位文件：[模块 10 课程](module10-managing-data/course.md)。

### 模块目标

在结构演进、时间范围到期和误操作恢复的场景中选择并验证生命周期操作。把对象管理、后台存储维护和灾难恢复，与模块 7 的行级变化区分开。

### 场景与逻辑主线

服务需要增加报表属性、保留滚动时间窗口，并处理迟到的历史数据。一次误删分区进一步引出恢复问题：哪些数据可以恢复、多久内可以恢复、依赖什么机制？最后区分副本、回收站恢复和独立备份。

### 学习目标

完成本模块后，学员应能够：

1. 在选择操作前明确结构兼容性、保留范围、时区、迟到数据策略和恢复要求。
2. 区分满足条件的轻量结构变更与后台变更，并使用相应证据确认完成。
3. 根据创建和保留需求选择手动分区、Auto Partitioning 或 Dynamic Partitioning。
4. 解释整分区保留策略与逐行过期的区别。
5. 按作用范围和恢复预期区分对象删除、清空、条件删除和覆盖。
6. 判断回收站恢复的适用条件及其无法撤销的操作。
7. 读取维护元数据，但不声称观察到了未展示的物理清理。
8. 区分数据冗余、已删除对象恢复和备份恢复。

### 课程内容大纲

#### 10.1 将生命周期需求转化为明确边界

**需求场景：** 增加属性、删除旧数据和恢复操作都必须保持报表语义。

- 明确事件时间与处理时间、保留边界、迟到数据和对象归属。
- 从允许丢失多少变化、允许中断多久，引入恢复点目标（Recovery Point Objective，RPO）和恢复时间目标（Recovery Time Objective，RTO）。
- 沿用模块 7 的行、分区、整表范围划分，不重复其数据修改语句目录。
- **实验衔接：** 创建本模块小表，在操作前记录结构和内容检查结果。

#### 10.2 在保持数据约定的前提下演进表结构

**需求场景：** 新报表属性需要同时适用于旧行和新写入。

- 根据可空性和默认值语义，选择兼容的 Value column 新增操作。
- 如果变更以后台任务运行，区分语句被接受与任务完成。
- 讨论 Key、分布、索引、物化视图依赖，不承诺任意类型变更或 Table Model 转换。
- **实验衔接：** 执行一个受支持的新增操作，检查变更后的结构及新旧行行为；只有实际产生任务时才轮询任务。

官方参考：[表结构变更](https://doris.apache.org/docs/4.x/table-design/schema-change/)。

#### 10.3 选择分区应在何时创建

**需求场景：** 近期数据日期可预测，但回填可能包含很早的日期。

- 比较手动边界、由导入值驱动的 Auto Partitioning，以及由时钟驱动的 Dynamic Partitioning。
- 在模块 4 自动分区示例之上，新增“创建与保留分别如何管理”的选择问题。
- 检查调度器实际时区和执行间隔。
- **实验衔接：** 用本地生成、相对当前时间的日期观察动态分区创建，不直接使用基线中的 2019–2020 年时间戳。

官方参考：[自动分区](https://doris.apache.org/docs/4.x/table-design/data-partitioning/auto-partitioning/)、[动态分区](https://doris.apache.org/docs/4.x/table-design/data-partitioning/dynamic-partitioning/)。

#### 10.4 保留滚动窗口，同时保护必要历史数据

**需求场景：** 系统应淘汰完整旧范围，但保留约定的历史例外。

- 按分区边界定义策略，不把它解释为每一行独立计算年龄。
- 说明调度延迟、历史保留例外和迟到数据行为。
- 检查实际分区：修改属性成功不能证明清理已经执行。
- **实验衔接：** 使用少量相对日期样本和有界轮询。调度间隔调整只允许发生在隔离环境。
- 不能将其等同于 ClickHouse 行级 TTL，也不能在共享历史表上启用该实验策略。

#### 10.5 区分数据移除与可恢复的对象删除

**需求场景：** 操作者可能需要清空范围、替换范围或删除其定义，并想知道是否可以撤销。

- 简要对照模块 7 的清空、覆盖，与删除 Partition 或表的区别。
- 回收站恢复面向符合条件的已删除对象，不是对行删除、upsert 或清空操作的通用撤销。
- 说明 `FORCE`、过期、同名冲突和操作特有限制；不能暗示所有自动保留策略造成的删除都能恢复。
- **实验衔接：** 使用单独手动管理的恢复样本表，而不是动态分区样本表，执行不带 `FORCE` 的删除与恢复流程。

#### 10.6 按预期内容验证恢复

**需求场景：** 删除的对象重新出现，但仍需核实其中的业务数据。

- 恢复前检查可恢复对象身份和资格。
- 恢复后检查结构、已知标识、数量和指标。
- 区分命令成功与业务恢复验证成功。
- **实验衔接：** 只操作本模块的 Partition 或表，绝不删除共享数据库或清空全局回收站。

官方参考：[回收站恢复](https://doris.apache.org/docs/4.x/admin-manual/data-admin/recyclebin/)。

#### 10.7 解释维护状态，不虚构内部证据

**需求场景：** 查询结果正确，但版本、存储使用或任务状态显示潜在压力。

- 将小批次写入压力与已讲过的 Group Commit、Compaction 联系起来。
- 区分精确查询计数与报告元数据，分别解释任务状态、保留版本和磁盘使用。
- 使用观察结果指导排查，不据此声称精确 Rowset/Segment 数量或物理空间回收。
- **实验衔接：** 检查本模块操作前后的元数据；不强制 Compaction、不执行无界写入基准，也不承诺观察到空间回收。

#### 10.8 选择超出在线副本能力的数据保护方式

**需求场景：** 错误已传播到所有副本，或整个集群丢失。

- 比较在线副本、回收站恢复、独立保留的快照，以及从权威来源重放。
- 将备份频率和恢复验证与 RPO、RTO 联系起来。
- 说明范围与依赖：当前文档不将异步物化视图纳入备份，恢复后还需关注共置和动态分区配置。
- 基础计划只讲备份恢复概念，不访问 AWS S3 或部署备份仓库。本地仓库扩展需要另行确定范围并验证。

官方参考：[备份恢复能力与限制](https://doris.apache.org/docs/4.x/admin-manual/data-admin/backup-restore/overview/)。

### 模块 10 实验：管理结构、保留范围与对象恢复

使用独立命名、可重置的一个 FE 和一个 BE 的管理环境，本地生成数据，数据库仍为 `doris_course`。它不依赖完整事件基线、模块 9 持续运行或外部存储。

拟按以下四个主体步骤组织，具体操作和预期结果仍待验证：

1. **演进表结构并核对新旧行**：在自有样本表上执行一个受支持的 Value column 新增操作，检查变更后的定义、旧行取值和新写入行为。如果操作产生后台任务，则检查其完成状态；不把语句被接受等同于任务完成，也不推断所有结构变更都立即完成或没有成本。
2. **建立滚动保留策略并观察实际分区**：使用相对当前日期生成的小型样本，检查 Dynamic Partition 调度器配置、状态和实际分区集合。通过有界等待比较调度前后的分区，解释历史保留例外和迟到数据边界；修改属性成功不等于清理已经发生，也不将整分区保留解释为行级 TTL。
3. **删除并恢复手动管理的对象**：使用独立恢复样本表，对本模块的表或 Partition 执行不带 `FORCE` 的删除，检查回收站中的对象身份与恢复资格，再恢复并核对结构、已知标识、数量和指标。该步骤不删除共享数据库、不清空全局回收站，也不把对象恢复描述为对数据修改、清空或强制删除的通用撤销。
4. **对照逻辑结果与维护元数据**：检查上述自有操作前后的查询结果和原始元数据，明确标注 Version、VersionCount、RowCount 等字段的来源和范围。区分 SQL 可见内容与存储报告值，不声称直接观察了 delete bitmap、Rowset/Segment 内部状态或物理空间回收。

### 测验 10 的拟议覆盖范围

约六个场景，覆盖兼容结构变更、自动与动态分区、保留策略与迟到数据、恢复资格、逻辑与物理证据，以及副本和恢复目标。无需运行服务或完成实验。

## 准备情况与开发前置验证

本节记录开发状态，与各模块内容大纲分开。检查日期：**2026-09-21**。

### 本地文件现状与缺失产物

初始化前，Level 3 README 仅列出三个主题和隔离要求，没有模块目标、学习目标、章节顺序、数据约定、测验计划或证据矩阵。每个 `course.md` 只有标题和一句范围说明。因此不存在可以直接认可或判定过时的详细旧大纲。

| 模块 | 现有内容 | 缺失产物 | 建议后续文件名 |
| --- | --- | --- | --- |
| 8 | 课程占位内容、已验证的 Lab 8、共享 helper 支持 | 完整课程、测验 Notebook 与 YAML | `course8_accelerating_queries_in_apache_doris.md`；`quiz8_acceleration_choices.ipynb` 及 `.yaml` |
| 9 | 课程占位内容；已实现 Lab 9、多节点 Compose 和共享 helper | 完整课程、测验 Notebook 与 YAML | `course9_sharding_and_replication_in_apache_doris.md`；`quiz9_distribution_and_availability.ipynb` 及 `.yaml` |
| 10 | 两行课程占位内容 | 完整课程、实验、测验配套文件、管理环境配置 | `course10_managing_data_in_apache_doris.md`；`lab10_manage_data.ipynb`；`quiz10_data_lifecycle_and_recovery.ipynb` 及 `.yaml`；`compose.management.yml` |

以上只是建议名称，不代表文件已经存在。后续课程沿用 Level 2 的组织方式：课程信息表、模块目标、学习目标、场景主线、概念章节、实验衔接、总结和官方参考。在两个课程目录及已检查的工作区上层目录中，未发现适用的 `AGENTS.md` 或 `SKILL.md`。

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
| 模块 9 | `m09_events`、`m09_events_skewed`、`m09_users`、`m09_availability_probe` | 隔离多节点环境中从只读课程 S3 源导入的有界样本；`m09_events` 与 `m09_users` 复用兼容的 `user_id` 分布 |
| 模块 10 | `m10_schema_events`、`m10_retained_events`、`m10_recovery_events` | 隔离管理环境中的微型本地样本 |

使用明确的对象归属清单，不做通配符清理。重复运行必须处理依赖视图、未完成任务、恢复后的名称和部分完成的步骤。Module 9 只读导入课程 S3 数据的有界子集；其他模块继续遵循各自的数据边界。

### 共享支持的复用与缺口

| 领域 | 已检查的现有支持 | 执行前需要补齐的能力 |
| --- | --- | --- |
| 根目录定位与界面 | 向上查找 `COURSE_ROOT`、`DorisLab`、统一青绿色样式、原始日志展示 | 继续支持从根目录启动 Jupyter 和直接在 VS Code 打开 Notebook |
| SQL 连接 | 显式 `connect` 接受主机与端口；自动 `_require_connection` 默认 localhost:9030；假定 root 和空密码 | 重连绑定选定环境并核实身份，不能静默回退到基线环境 |
| Docker | 网络、存储卷、健康检查基础函数、单容器 All-in-One 生命周期和 Module 9 多节点 Compose 支持 | 后续模块继续使用独立名称、端口、存储和限定范围的生命周期操作 |
| Profile 获取 | `profiles.py` 转调 `DorisLab`；支持原始计划、Join Runtime Filter 和跨 BE 扫描任务证据 | FE HTTP 地址绑定实际协调查询的 FE，并保留查询、算子、BE host 和实例身份 |
| 扫描摘要 | `compare_profiles` 提取少量计数及固定结果别名 | 保留原始索引、物化视图、聚合、Exchange 证据，避免只取首个匹配或跨无关算子汇总全文 |
| 元数据 | 已有 Partition/Tablet 摘要 | 保留副本放置行；不能沿用将元数据 `RowCount` 标成 `Logical rows` 的做法；精确行数使用 SQL |
| 后台任务 | 已有 Routine Load 专用等待逻辑 | 为物化视图、索引、结构变更、保留策略和副本健康提供有界等待，显示错误及最后状态 |
| 会话设置 | Profile 辅助函数保存并恢复多个变量 | 恢复逻辑还需覆盖初始化和采集失败，区分结果缓存与存储缓存 |
| 测验 | `CourseQuiz.from_yaml`、独立导入、校验、导航、反馈、重试和测试 | 后续创建模块内配套文件，保留 `quiz.py` 已实现的单选按钮首行对齐 |

实验 8 已在共享 `profiles.py` 中增加 `capture_query`、临时会话设置恢复和保留算子范围的原始扫描计数展示；继续使用现有本地 FE Profile 接口。物化视图任务等待、结果核对与选中扫描检查已整合到共享 `DorisLab`，通过参数传入表名、视图名和任务 ID，不在共享实现中硬编码模块 8 对象。Notebook 通过 `lab` 调用；任务等待按新 Job/Task ID 识别本次提交，处理失败和超时，并在重置前等待旧实验任务结束。模块目录不再包含 Python 支持文件。多节点地址隔离等后续缺口仍需处理。缺失计数不填零，不累加 MergedProfile 与 DetailProfile。

部分 Level 2 测验 YAML 的对齐字段仍引用旧章节号，并带有 `course_review_required` 标记。后续应以当前课程标题和 Notebook 单元格为对齐依据，不盲目复制旧映射。本轮不修改既有内容。

### 范围修正与 ClickHouse 边界

8 → 9 → 10 的顺序合理，原先缺失的选择依据和证据结构已在上文补齐。开发时避免以下范围扩张和假设：

| 主题 | 范围决定 |
| --- | --- |
| Prefix Index、裁剪、手动汇总重建 | 仅作前置回顾，模块 8 新增持续维护的物化结果与二级索引选择 |
| 所有逻辑 Join 和分布提示 | 模块 6 已覆盖，模块 9 重点是放置和可用性 |
| upsert、部分列更新、MERGE、清空、覆盖 | 模块 7 已覆盖，模块 10 新增生命周期与恢复 |
| ClickHouse Projections、MergeTree parts/granules、插入数据块触发的物化视图 | 不改名当作 Doris 机制，不假设历史回填语义相同 |
| Keeper、ReplicatedMergeTree、Distributed 表、`ON CLUSTER` | 不将其部署和 SQL 模型照搬到 Doris FE/BE 与 Tablet 副本 |
| ClickHouse 行级 TTL、`OPTIMIZE FINAL` | 不用来描述 Dynamic Partition 保留或 Doris Compaction |
| “三个副本就代表高可用” | 还需核对放置、完整版本、写入策略、FE 可用性和故障域 |
| “视图存在，所以查询已加速” | 必须同时有计划选用、实际工作量和正确结果的证据 |
| 完整故障切换、物理空间回收、生产网络性能排名 | 不属于基础实验可宣称的结果 |
| 云端冷热分层、外部目录、跨集群复制、备份仓库 | 作为未来可选范围，本轮不部署 |

本地 `ClickHouse101.pdf` 共十页，第 8–10 页描述模块 8 的加速和模块 9 的分布。模块 10 只在目录中出现，没有详细笔记。因此它可以支持总体顺序参考，不能直接提供模块 10 大纲。本次检查未能通过网页读取工具获取 [ClickHouse 学习网站](https://learn.clickhouse.com/)，不声称已检查其当前课程。Doris 机制以本文链接的官方资料为依据。

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

- 基于 Apache Doris 官方 4.1 All-in-One 多节点环境使用三个 FE，并把数据节点从两个存活 BE 扩展到三个存活 BE；Module 9 使用独立 Compose project、固定私有子网和 localhost 发布端口。初始化显式停止单节点 `doris` 与 HAProxy，避免端口、内存和入口状态混淆。
- `m09_events` 固定为 12,062 行、两个 Partition、每 Partition 六 Bucket、双副本。重建时只复用这批已提交的逻辑事件作为本地来源；旧物理表及其他 Module 9 业务对象按各自步骤重建。首次没有完整本地来源时才读取只读 S3。
- 在 `be-3` 停止时，12 个 Tablet 的 24 个副本位于 `be-1` 和 `be-2`；启动 `be-3` 后，不重载数据也不发出手动迁移命令即可观察到已有副本进入新 BE，总副本数和逻辑答案保持不变。
- 停止当前直连 Master FE 后，原 MySQL TCP 会话失败；两个存活 FE 完成选举。HAProxy 只向健康 FE 建立新连接，通过代理可以重新查询 12,062 行。恢复旧 FE 后，它重新加入但不要求重新成为 Master；`L4OK` 仅表示 FE MySQL 端口的 TCP 检查成功。
- 地区聚合的普通 `EXPLAIN` 展示 12 个 Tablet 的计划范围，DetailProfile 展示本次实际选择的 BE host、TabletIds 和 ScanRows；实验不固定参与 BE 数、Tablet ID 或行数，也不把存有副本等同于参与本次扫描。
- 三副本 `m09_availability_events` 在 `be-2` 停止时由另外两个副本形成多数并提交一条已知 purchase。停机 BE 的副本版本落后且不是 current version；恢复后先观察 `Alive=true`，再等待三个副本版本追平。
- RANDOM 分布的 `m09_users` 与按 `user_id` 分布的事件输入实际选择 `INNER JOIN(BUCKET_SHUFFLE)`；用相同 6,706 个用户重建为稳定 Colocation Group 后，相同业务答案的计划选择 `INNER JOIN(COLOCATE)`，且 Join 两侧扫描之间不再出现输入 Exchange。
- 结尾使用 `docker compose stop/start` 释放和恢复进程，保留隔离集群数据，并检查事件表、用户表和停机写入事件。以上不证明共享 Docker 宿主机上的生产级无中断、跨主机故障域或性能扩展比例。

### 证据与测验约定

| 证据 | 可以支持的结论 | 不能据此推断的结论 |
| --- | --- | --- |
| 实验直接结果 | SQL 可见内容、返回结构、观察到的状态 | 未展示的内部机制或普遍生产行为 |
| `EXPLAIN` | 计划访问路径、改写、片段、分布、过滤位置 | 实际过滤行数、节省字节或耗时收益 |
| Query Profile | 一次执行中明确算子和实例范围的命名计数 | 单独证明正确性、物理回收、并行计时可直接相加 |
| 文档与源码 | 指定版本的机制和限制 | 证明 Notebook 直接观察到了该机制 |

每模块使用四至六道独立英文单选题，优先采用场景选择、结果预测和原因解释。复用 `doris_course/quiz.py` 与 Level 1–2 Notebook 风格。Notebook 目标与 YAML 保持一致，并在两种 Notebook 使用方式中检查长选项单选按钮与第一行文字的对齐。测验不依赖 Docker、Doris、S3、Kafka 或已完成的实验。

### 建议开发顺序

1. **先验证模块 8 的可行性：** 在本模块小表上验证一个同步物化视图、一个异步物化视图和一组索引对照。确认 Query Profile 证据后再编写课程，然后将实验与测验对齐到受支持的范围。
2. **模块 9 已完成环境和证据验证：** 已验证连接隔离、资源检查、副本放置、跨 BE 执行、Colocate Join、受控 BE 停机恢复和 FE 选举。
3. **隔离方式明确后开发模块 10：** 准备独立小环境，先验证结构变更和手动恢复，再处理依赖时钟的保留策略。最后讲恢复方式的选择，不引入外部集成。

学员学习顺序保持 **8 → 9 → 10**。每个模块内部依次完成：确定场景、验证敏感行为、根据证据编写课程和实验、创建独立测验。当前实验 8 和实验 9 已进入实现；后续内容继续按各自大纲开发。
