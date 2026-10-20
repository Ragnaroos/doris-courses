# Module 1 课程大纲：用 MCP 连接 AI Agent 与 Apache Doris

> 文档状态：课程设计稿
> 文件用途：本文是开发大纲；面向学习者的正式课程位于同目录下的 `course.md`
> 课程形态：单篇 Markdown Course，不使用 Jupyter Notebook，不再拆分 Course 与 Lab
> 主验证客户端：Codex CLI / Codex desktop
> 其他连接客户端：Claude Desktop、Cursor、VS Code + GitHub Copilot
> 环境边界：Agent、Doris MCP Server 和 Doris Docker 均在同一台电脑上

## 1. 课程定位

本节课不是“MCP 全部工具速查”，而是一条可复现的本地连接与验证链路：

```text
配置一个本机 Doris MCP Server
  → 将同一个 launcher 和 Doris 目标配置到 4 个 Agent
    → 在 Codex 中检查真实 Schema
      → 执行有界的只读分析
        → 切换到 doris_cluster 查看单 BE 的内存资源证据
          → 区分 Doris 事实、Agent 解释与不可用证据
```

### 1.1 学习目标

完成课程后，学习者能够：

1. 说清 MCP Host、MCP Client、Doris MCP Server 和 Doris 各自的责任。
2. 使用一个不含明文密码的 launcher，连接本地 Doris Docker。
3. 在 Claude Desktop、Cursor、VS Code 和 Codex 中完成 stdio 配置与连接检查。
4. 在 Codex 中完成 `get_table_context → execute_query → get_memory_stats` 的主展示链路。
5. 识别最小权限、密钥管理、只读边界和指标不可用时的正确表达。

### 1.2 预计时长与先决条件

- 预计时长：45–60 分钟。
- 四个 Agent 已安装并可正常对话；本课不讲解 Agent 的下载、安装或账号登录。
- 前置课程的单 FE、单 BE `doris` 容器已启动，并已创建 `doris_course.events`。
- 该容器将 `9030`、`8030` 和 `8040` 绑定到宿主机 `127.0.0.1`。Module 9 的多节点环境不是本课先决条件。
- 本机有 Python 3.12+，课程固定 `doris-mcp-server==1.0.0`，或在发布课程时重新固定已验证的最新 patch。

## 2. 内容形式与截图规则

配置文件、命令、prompt 和预期调用链都用文字/代码块，便于学习者复制；截图只用来证明产品 UI 状态或 Agent 真的发起了某次工具调用。

| 编号 | 内容 | 形式 | 是否必须截图 | 截图要点 |
|---|---|---|---:|---|
| S0 | MCP 四角色与本机边界 | 文字 + 静态架构图 | 否 | 静态图比产品截图更易维护 |
| S1 | Claude Desktop 连接成功 | JSON + 操作步骤 | 是 | 同一张图显示 `doris` 已连接和工具可见 |
| S2 | Cursor 连接成功 | JSON + 操作步骤 | 是 | 显示 MCP 状态和 tool approval 开关，不显示密码 |
| S3 | VS Code 连接成功 | JSON + 操作步骤 | 是 | 显示 server running 与 Agent mode 工具选择器 |
| S4 | Codex 连接成功 | TOML + CLI 命令 | 是 | `codex mcp list` 或 `/mcp` 显示 `doris` connected |
| S5 | Schema grounding | prompt + tool trace | 是 | 只展示 `doris_catalog/get_table_context` 和脱敏参数 |
| S6 | 只读聚合 | SQL + tool trace + 结果 | 是 | 展示 `doris_query/execute_query`、`LIMIT 10` 与结果表 |
| S7 | 内存指标 | prompt + tool trace + 结果 | 是 | 展示 `doris_cluster/get_memory_stats` 的 source、tracker 和 warning |
| S8 | 排障矩阵 | 文字表格 + 命令 | 否 | 失败 UI 变动快，不取决于截图 |

所有截图必须裁掉用户主目录、Doris 密码、API key、会话 ID 和无关窗口。课程正文同时写出截图中的关键状态，避免信息只存在图片中。

## 3. 第一部分：理解 MCP 与 Doris 能力地图（文字 + 静态图）

### 3.1 本课的四个角色

```text
用户
  → Agent / MCP Host（管理会话、选择工具、组织答案）
    → MCP Client（启动本机 stdio 子进程、交换 MCP 消息）
      → Doris MCP Server（发布 Schema、只读校验、限时限量执行）
        → 本地 Doris Docker（最终的权限、元数据、SQL 和指标来源）
```

### 3.2 八个内置 domain 概览

Doris MCP Server 1.0 在分层模式下将内置只读能力组织为 8 个顶层 domain。Agent 先发现与任务最相关的 domain，获取当前可用的 child schema 和 `manifest_version`，再用精确参数调用 child capability。

| Domain | 能力概括 | 典型问题 |
|---|---|---|
| `doris_catalog` | 浏览 catalog/database/table，读取表结构、索引与表大小 | 某张表有哪些列、索引和分区？ |
| `doris_query` | 执行有界只读 SQL，获取 Explain/Profile 并诊断查询 | 这条聚合的结果和执行计划是什么？ |
| `doris_cluster` | 查看节点、任务、内存、缓存、Compaction 和资源组状态 | 当前有哪些内存 tracker 和部分可用的资源证据？ |
| `doris_pipeline` | 观察导入任务、Materialized View、数据新鲜度和有界依赖 | Routine Load 是否正常，表数据是否足够新？ |
| `doris_search` | 文本、向量和 Hybrid Search，分词预览、索引检查与检索诊断 | 指定索引能否完成一次有界 hybrid retrieval？ |
| `doris_governance` | 列分析、存储形状、血缘、访问模式、审计与权限映射 | 这个字段的质量和可追溯证据是什么？ |
| `doris_lakehouse` | 检查外部 Catalog、Lakehouse 表与 Variant 列 | 某个 Iceberg/Hudi/Paimon 表有哪些可用元数据与下推证据？ |
| `doris_semantic` | 消费已配置的语义模型或 MetricFlow 模型 | 哪些指标、维度和已保存查询可用？ |

`doris_admin` 是保留面，不作为内置 domain 注册。完整 child 列表放在官方参考链接中，课堂不逐项演示。

### 3.3 本课实际演示的三个 child

| Domain | Child capability | 在主链中的作用 |
|---|---|---|
| `doris_catalog` | `get_table_context` | 获取 `doris_course.events` 的真实 Schema 和索引上下文 |
| `doris_query` | `execute_query` | 执行有时间边界和 `LIMIT` 的只读聚合 |
| `doris_cluster` | `get_memory_stats` | 查看单 BE 教学环境的内存 tracker 和可用性证据 |

## 4. 第二部分：准备共用的本机 MCP 入口（文字 + 代码块）

### 4.1 本课固定使用的 Doris 环境

四个 Agent 的演示全部连接 Level 1–8 共用的**单 FE、单 BE 教学容器**，不连接 Module 9 的多节点环境。

| 项目 | 课程要求 |
|---|---|
| Docker 容器 | `doris`，镜像为课程固定的 `apache/doris:all-in-one-4.1.3` |
| 拓扑 | 1 FE + 1 BE |
| FE MySQL Protocol | `127.0.0.1:9030` |
| FE HTTP | `127.0.0.1:8030` |
| BE Web Server | `127.0.0.1:8040` |
| Database | `doris_course` |
| Table | `events` |
| 基线数据 | 10,158,080 行，时间范围 `2019-12-01 00:00:12` 至 `2020-03-11 04:53:08` |

选择这套环境的理由：

- `events` 是前置课程已建立的共享基线，Catalog 和 Query 演示可直接复用。
- 9030/8030/8040 都已映射到固定本机端口，`get_memory_stats` 的数据源比多节点环境更易稳定复现。
- 本课要教的是 MCP 连接和 Agent 调用，不重复 Module 9 的 FE 选主、副本与多 BE 故障教学。

因此主链不展示 `get_cluster_overview`。它在单节点环境中只会返回 1 FE/1 BE，教学价值有限；课程保留 `get_memory_stats` 作为一个 `doris_cluster` 资源监控例子。

### 4.2 环境不满足时回到哪个 Lab

| 当前情况 | 学习者应该做什么 |
|---|---|
| 没有 `doris` 容器，或没有 `doris_course.events` | 回到 **Level 1 / Module 1 / Lab 1: Start Doris and Build a Baseline Dataset**，完整执行 Initialize、第 2 节准备环境、第 3 节创建 database、第 5 节创建 `events`、第 6 节加载并验证基线数据。首次执行还需按 Lab 1 完成 S3 读取凭据配置。 |
| `doris` 容器存在但已停止 | 执行 Lab 1 末尾的 **Restart the Doris sandbox**，不需要重新加载数据。 |
| Module 9 多节点环境正在运行 | 先执行 Lab 9 末尾的 **Stop the Module 9 cluster**，再回到 Lab 1 执行 **Restart the Doris sandbox**。两套教学环境不在本课中同时使用。 |
| `events` 行数或时间范围不符合基线 | 重新执行 Lab 1 第 6 节 **Reload and validate the baseline dataset**，不在 MCP 课中临时修补数据。 |

Lab 3 创建的 `events_stream`、`events_s3` 和 `events_routine` 不是本课依赖，因此学习者无需为 MCP 课额外执行 Lab 3。

### 4.3 先验证 Doris，后验证 MCP

先检查三个宿主机端口：

- `127.0.0.1:9030`：FE MySQL Protocol，用于 Catalog 与 Query 主链。
- `127.0.0.1:8030`：FE HTTP，用于部分运维证据。
- `127.0.0.1:8040`：BE Web Server，用于内存 tracker 证据。

再用 MySQL client 验证拓扑和基线数据：

```bash
mysql -h 127.0.0.1 -P 9030 -u root -e '
SHOW FRONTENDS;
SHOW BACKENDS;
SELECT
  COUNT(*) AS row_count,
  MIN(event_time) AS min_event_time,
  MAX(event_time) AS max_event_time
FROM doris_course.events;
'
```

预期只有 1 个 Alive FE 和 1 个 Alive BE，且查询返回 10,158,080 行以及上表中的时间范围。此处的 `root` 只用于本机课程环境预检与创建后续的低权限账号；Agent 不使用 `root`。

这一步只用文字和预期输出片段，不需要截图。

### 4.4 创建最小权限账号

正式课程提供可复制的 SQL：创建 `mcp_reader`，只授予课程 database/table 所需的 `SELECT` 与元数据可见性。数据库密码由学习者在本机生成，示例不使用 `root`，不在 Markdown 中展示真实密码。

### 4.5 安装固定版本的 Doris MCP Server

```bash
python3.12 -m venv .venv
.venv/bin/pip install 'doris-mcp-server==1.0.0'
```

这是 MCP Server 的课程依赖，不是四个 Agent 的部署教程。

### 4.6 配置本地环境文件

课程建议文件名为 `.env.mcp.local`，并将它加入 `.gitignore`：

```dotenv
DORIS_HOST=127.0.0.1
DORIS_PORT=9030
DORIS_USER=mcp_reader
DORIS_PASSWORD=<LOCAL_SECRET>
DORIS_DATABASE=doris_course

DORIS_FE_HTTP_HOST=127.0.0.1
DORIS_FE_HTTP_PORT=8030
DORIS_BE_HOSTS=127.0.0.1
DORIS_BE_WEBSERVER_PORT=8040

MCP_TOOL_EXPOSURE_MODE=hierarchical
```

`DORIS_BE_HOSTS` 只写 hostname/IP，端口单独写在 `DORIS_BE_WEBSERVER_PORT`。如果 HTTP/BE 证据源不可用，课程要求 Agent 报告 `callable=false`、partial 或 warning，不允许用猜测补齐指标。

### 4.7 只暴露一个 launcher

课程提供 `run-doris-mcp-local` 示例：从受保护的本地文件读取环境变量，然后执行：

```bash
/absolute/path/to/.venv/bin/doris-mcp-server --transport stdio
```

正文需特别标注：

- 四个 Agent 配置中只保存 launcher 的绝对路径。
- 不在 JSON/TOML、屏幕截图或 Git 中保存 Doris 密码。
- stdio Server 的 stdout 只能输出 MCP 协议消息，调试日志写到 stderr。
- GUI 客户端常常继承不同的 `PATH`，所以不使用相对路径。

#### “同一个 MCP Server”的准确含义

四个 Agent 复用的是同一个 MCP Server 实现、同一个 launcher 和同一组 Doris 连接参数。由于 stdio Server 由 Host 启动，同时打开四个 Agent 时，通常会有四个独立的 `doris-mcp-server` 子进程；它们都指向同一个单节点 Doris 环境。

一个已启动的 MCP Server 进程不会在两套 Doris 端口之间自动切换。如果未来需要同时连接单节点和 Module 9 多节点环境，应定义两个 launcher/两个 MCP server entry，例如 `doris_single` 和 `doris_multinode`，每个进程使用自己的 `DORIS_PORT`、FE HTTP 和 BE HTTP 配置。该双目标设计不进入本课。

## 5. 第三部分：将四个 Agent 连接到同一个 Doris 目标

> 这一部分不讲解客户端安装。每个客户端只完成“写配置 → Host 启动自己的 stdio Server 子进程 → 检查连接状态”。四个客户端都指向 `127.0.0.1:9030/8030/8040` 这套单节点 Doris 环境，不重复执行后面的业务演示。

### 5.1 Claude Desktop（代码块 + 操作文字 + S1）

1. 打开 Claude Desktop 的 Developer/MCP 配置入口，编辑 `claude_desktop_config.json`。
2. 新增：

```json
{
  "mcpServers": {
    "doris": {
      "command": "/absolute/path/to/run-doris-mcp-local",
      "args": []
    }
  }
}
```

3. 完全退出并重启 Claude Desktop。
4. 在 MCP/Extensions 状态页确认 `doris` 已连接且工具可见。
5. 拍摄 S1；截图中不打开环境文件。

### 5.2 Cursor（代码块 + 操作文字 + S2）

1. 选择项目级 `.cursor/mcp.json` 或用户级 `~/.cursor/mcp.json`；课程为了可复制性使用项目级文件，但不将 secret 写入项目。
2. 写入：

```json
{
  "mcpServers": {
    "doris": {
      "command": "/absolute/path/to/run-doris-mcp-local",
      "args": []
    }
  }
}
```

3. 重启 Cursor，打开 MCP 设置页，确认 `doris` 状态正常。
4. 保留 tool approval，不开启全局 auto-run。
5. 拍摄 S2；如果连接失败，文字指导学习者查看 Output 面板的 MCP Logs。

### 5.3 VS Code + GitHub Copilot（代码块 + 操作文字 + S3）

1. 在 workspace 中创建 `.vscode/mcp.json`。
2. 写入：

```json
{
  "servers": {
    "doris": {
      "type": "stdio",
      "command": "/absolute/path/to/run-doris-mcp-local",
      "args": []
    }
  }
}
```

3. 点击配置文件中的 Start，或从 Command Palette 执行 `MCP: List Servers` 后启动 `doris`。
4. 打开 Copilot Chat 的 Agent mode，在 Tools 选择器中确认 Doris MCP 工具可见。
5. 拍摄 S3，同一张图展示 running 状态和 Tools 选择器。

### 5.4 Codex CLI / Desktop（代码块 + 操作文字 + S4）

Codex CLI、Codex desktop 和 IDE extension 在同一台主机上共享 MCP 配置。课程使用 `~/.codex/config.toml`：

```toml
[mcp_servers.doris]
command = "/absolute/path/to/run-doris-mcp-local"
args = []
required = true
startup_timeout_sec = 20
tool_timeout_sec = 60
```

连接步骤：

1. 保存 TOML 后执行 `codex mcp list`，确认已注册 `doris`。
2. 启动 Codex CLI，输入 `/mcp`，确认 `doris` 已连接。
3. 在 Codex desktop 演示时，也可通过 Settings 的 MCP servers 添加同一个 STDIO command，保存后重启；不再为 desktop 维护另一份连接参数。
4. 拍摄 S4；优先使用 `/mcp` 画面，因为它同时证明当前会话可用。

## 6. 第四部分：在 Codex 中完成主验证链路

完整演示只在 Codex 中执行一次。使用一个连续会话，让学习者看到 Agent 能从业务数据分析切换到资源观测，而不需要将全部工具一次性暴露在 prompt 中。

### 6.1 步骤 A：读取真实表上下文（文字 + S5）

学习者输入：

> 请检查 `doris_course.events` 的表结构、关键列和索引上下文。不要查询业务数据，也不要猜测缺失字段。

预期链路：

```text
doris_catalog {}
  → 返回 child schema + manifest_version
    → doris_catalog/get_table_context(database=doris_course, table=events)
```

验收点：Codex 答案中的列名来自工具结果，而不是模型常识。拍摄 S5。

### 6.2 步骤 B：执行有界的只读聚合（文字 + S6）

继续输入：

> 基于刚才读取的真实 Schema，统计 2020-03-01（含）至 2020-03-09（不含）每种 `event_type` 的事件数和去重用户数，按事件数降序，最多返回 10 行。只允许只读查询；把查询事实与解释分开。

预期链路：

```text
doris_query {}
  → doris_query/execute_query
    → 有固定时间边界、GROUP BY、ORDER BY 和 LIMIT 10 的 SELECT
```

预期 SQL 形状：

```sql
SELECT
    event_type,
    COUNT(*) AS event_count,
    COUNT(DISTINCT user_id) AS distinct_users
FROM doris_course.events
WHERE event_time >= '2020-03-01 00:00:00'
  AND event_time <  '2020-03-09 00:00:00'
GROUP BY event_type
ORDER BY event_count DESC
LIMIT 10;
```

正式课程还要给出用 MySQL client 执行同一 SQL 的复核命令。验收点：Agent 结果必须与直连 Doris 的结果一致。拍摄 S6。

### 6.3 步骤 C：查看一类具体资源指标（文字 + S7）

继续输入：

> 请查看当前 Doris 内存使用证据。优先总结最重要的 memory tracker，并保留结果中的 source、partial 和 warning 信息。不要对缺失指标做推断。

预期链路：

```text
doris_cluster {}
  → doris_cluster/get_memory_stats
    → 可用的 memory trackers / usage / source
    → 或明确的 partial、warning、callable=false
```

只选一类具体资源指标，不再扩展到 CPU、磁盘、压缩、查询 Profile 和全量 monitoring metric 枚举。拍摄 S7。

## 7. 第五部分：读懂工具调用（文字 + S5 标注图）

在 S5 原图上做一次标注，讲清：

1. 第一次 domain 调用为什么可能只有 `{}`。
2. `child_tool`、`arguments` 和 `manifest_version` 各自解决什么问题。
3. Host 决定是否调用工具；Server 发布可用能力并执行边界校验。
4. MCP 调用成功不等于 Agent 解释一定正确，所以数字要用直连 SQL 复核。

不新增截图，避免将同一个 trace 重复展示。

## 8. 第六部分：安全与排障（文字表格）

### 8.1 安全边界

- Doris 使用专用最小权限账号；MCP Server 的只读 guard 不替代 RBAC。
- Agent 保留 tool approval，不启用全局自动执行。
- `9030/8030/8040` 只绑定 `127.0.0.1`；MCP 只使用 stdio，不启动网络 listener。
- 课程截图不使用真实业务数据和凭据。

### 8.2 排障矩阵

| 现象 | 先检查 | 解决方向 |
|---|---|---|
| Agent 显示 server failed | launcher 是否是绝对路径、是否可执行 | 在同一用户下手动执行 launcher，检查 stderr |
| `9030` connection refused | Docker 容器和 FE readiness | 先恢复 MySQL client 直连，不先改 Agent 配置 |
| 工具可见但查询拒绝 | `mcp_reader` 权限、SQL 形状和 limit | 保持只读，缩小范围，不切换 root |
| Cluster child 不可用 | `8030/8040` 映射、FE/BE host 配置 | 检查 `DORIS_FE_HTTP_*` 和 `DORIS_BE_*`；保留 unavailable 证据 |
| manifest 过期 | trace 中的 `manifest_version` | 让 Host 重新发现 domain，不复用旧 child schema |
| CLI 可用、GUI 不可用 | GUI 的 `PATH` 和环境继承 | 使用 launcher/解释器绝对路径，重启 GUI |
| hierarchical 不兼容 | Host 的实际 tool discovery 行为 | 完成记录后才用 `flat` 作兼容备选，不扩展课程工具面 |

## 9. 第七部分：验收与思考题（文字）

### 9.1 完成清单

- [ ] 四个 Agent 都能通过同一 launcher 启动各自的本机 stdio Server 子进程，并连接同一个单节点 Doris 目标。
- [ ] 四份客户端配置都没有 Doris 明文密码。
- [ ] Codex 先读取 `events` 真实上下文，再生成 SQL。
- [ ] 聚合 SQL 只读、有固定时间边界、排序和 `LIMIT 10`。
- [ ] Agent 数字与 MySQL client 复核结果一致。
- [ ] `get_memory_stats` 保留 source/partial/warning，不猜测缺失值。

### 9.2 文字思考题

1. 为什么 MCP Server 已经拒绝写 SQL，Doris 仍然需要一个最小权限账号？
2. 分层工具发现如何减少 Agent 一次性需要理解的工具 Schema？
3. 为什么监控结果中的 partial/warning 是有用证据，而不是应该隐藏的错误？
4. 为什么四个 Agent 只做连接 smoke test，而不各自重复完整分析？

## 10. 正式写课时的文件与素材清单

该 Module 保留开发大纲和一篇面向学习者的主课程：

```text
level1/module01-doris-mcp/
├── readme.md                     # 内部开发大纲、截图规则与验收设计
├── course.md                     # 展示给学习者的完整课程内容
├── assets/
│   ├── mcp-local-architecture.svg
│   ├── claude-mcp-connected.png
│   ├── cursor-mcp-connected.png
│   ├── vscode-mcp-connected.png
│   ├── codex-mcp-connected.png
│   ├── codex-catalog-trace.png
│   ├── codex-query-result.png
│   └── codex-memory-stats.png
└── resources/
    ├── run-doris-mcp-local
    ├── env.mcp.local.example
    ├── claude-desktop.example.json
    ├── cursor.example.json
    ├── vscode.example.json
    └── codex.example.toml
```

不创建 `lab.ipynb`、`quiz.ipynb` 或独立 Lab 文档。实操命令直接嵌入 `course.md`，文字思考题放在末尾。

## 11. 一手参考资料

- [Apache Doris MCP Server Quickstart](https://github.com/apache/doris-mcp-server/blob/master/docs/getting-started/quickstart.md)
- [Apache Doris MCP Host integrations](https://github.com/apache/doris-mcp-server/blob/master/docs/integrations/hosts.md)
- [Apache Doris MCP Tool domains](https://github.com/apache/doris-mcp-server/blob/master/docs/capabilities/tool-domains.md)
- [Apache Doris MCP Configuration](https://github.com/apache/doris-mcp-server/blob/master/docs/reference/configuration.md)
- [OpenAI: Model Context Protocol](https://learn.chatgpt.com/docs/extend/mcp)
- [Claude Desktop: local MCP servers](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
- [Cursor: Model Context Protocol](https://prod.cursor.com/help/customization/mcp)
- [VS Code: MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
