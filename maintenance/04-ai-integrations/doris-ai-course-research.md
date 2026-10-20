# Apache Doris AI 课程前期调研

> 初始调研：2026-09-30；MCP 展示链路更新：2026-10-09
> 证据基线：Apache Doris 4.1.3（Latest）/ 4.0.8（Stable）；Doris MCP Server 1.0.0。Doris 4.0 是 AI Functions、原生 ANN 向量索引和官方所称 Hybrid Search 的首次正式发布线。版本状态以 [Doris 下载页](https://doris.apache.org/download/) 和 [4.0.0 Release Note](https://doris.apache.org/releases/v4.0/release-4.0.0/) 为准。
> 安全说明：本文所有地址、用户名、Token 和模型密钥均为占位符；不要把真实凭据写进课程仓库、Markdown 或截图。

## 1. 结论摘要

三个方向都已有真实实现，但不应被包装成同样成熟的课程产品。

| 方向 | 结论 | 当前最合适的课程形态 |
|---|---|---|
| Doris MCP 与 Agent | **最适合优先开发。** Apache 官方组织已有 `apache/doris-mcp-server` 1.0.0，内置能力只读且有结果、超时、SQL 形状和权限边界；但“GA”只指 MCP 2026-07-28 协议兼容，Python 包仍标为 Beta，并且各 Host 对该新协议和分层工具发现的兼容性仍需逐一实测。 | 一篇合并概念、连接、实操、排障和验收的 Markdown Course；不再创建 Jupyter Lab。 |
| Doris AI Functions | **功能已落地，生产治理仍较年轻。** 4.0 起有 10 个 scalar function、`AI_AGG` 和 `EMBED()`；源码、单元测试、回归测试和 Release Note 相互印证。它本质上是同步外部模型调用，天然有成本、限流、延迟、失败和非确定性。 | 先做探索性 Workshop；通过带本地模型或小配额 provider 的 PoC 后，再判断是否升格为 Module。 |
| Hybrid Search + Lakehouse | **检索主线已具备 Module 价值，但必须拆清两个架构。** 4.0 原生 ANN + 已有倒排索引/全文检索可以在 Doris 内表上组合；Catalog 联邦查询也成熟，但“能联邦读湖仓”不等于“外部表自动获得 Doris ANN/全文索引”。 | “全部进入 Doris”的 Hybrid Search 可做本地 Lab；跨湖仓检索先做架构课或 Workshop，完成 PoC 后再承诺一条 SQL 的具体边界。 |

推荐开发顺序：**MCP 最小链路 → 4.0 本地 Hybrid Search → AI Functions Workshop → Lakehouse 联邦 PoC**。

最大依赖与风险：Doris 4.x 镜像和硬件资源、MCP Host 协议差异、外部 LLM/embedding provider 的凭据与费用、模型非确定性、对象存储与 Catalog 环境复杂度，以及官方 4.x 文档仍在快速演进。课程必须固定版本并保留验证日期。

---

## 2. Doris MCP 与主流 Agent

### 2.1 MCP 架构与职责

```text
用户
  → Agent / MCP Host（保存会话，调用 LLM，决定是否选工具）
    → MCP Client（通过 stdio 管理本机 MCP 子进程）
      → 本机 Doris MCP Server（工具 Schema、只读校验、限时限量执行）
        → 127.0.0.1:9030（FE MySQL Protocol，Catalog/Query）
        → 127.0.0.1:8030/8040（FE/BE HTTP，Cluster 可观测性）
          → 本地 Doris Docker：FE（鉴权、解析、规划、元数据）/ BE（扫描、计算、指标与结果）
```

本课程只研究这一种部署：**Agent、MCP Server 和 Doris Docker 都在同一台学习者电脑上**。Doris MCP Server 作为 Agent 启动的本机 stdio 子进程运行；Doris FE/BE 在 Docker 中运行，并将 9030/8030/8040 只映射到宿主机 `127.0.0.1`。不讨论远程 Doris、远程 MCP endpoint、SSE、Streamable HTTP、TLS、OAuth 或跨主机网络。

四个容易混淆的角色：

- **LLM** 理解用户问题、选择工具、组织答案；它不是数据库，也不应持有高权限 Doris 账号。
- **MCP Client** 通常嵌在 Claude、Cursor、VS Code、Codex 等 Host 中，负责 stdio 报文和本机子进程生命周期。配置“启动哪个本机命令”属于客户端。
- **Doris MCP Server** 把 Doris 能力包装成有输入/输出 Schema 的工具，校验只读 SQL、超时、行数和字节数；它不是 SQL 引擎。
- **Doris** 最终执行元数据和 SQL 请求；对象、列、行的最终可见性仍由 Doris RBAC 决定。

官方 MCP 文档对这条边界有明确表述：[Host integrations](https://github.com/apache/doris-mcp-server/blob/master/docs/integrations/hosts.md) 和 [Architecture overview](https://github.com/apache/doris-mcp-server/blob/master/docs/architecture/overview.md)。

### 2.2 Doris MCP Server 现状

Apache 官方组织已有 [Apache Doris MCP Server](https://github.com/apache/doris-mcp-server)。1.0.0 要求 Python 3.12+、Doris 2.0+。Server 支持多种 transport，但本课程只使用 **stdio**：Agent 启动本机 `doris-mcp-server --transport stdio`，该进程通过宿主机映射端口连接本地 Doris Docker。[Deployment](https://github.com/apache/doris-mcp-server/blob/master/docs/operations/deployment.md)

成熟度应谨慎描述：仓库声明 MCP `2026-07-28` 的协议兼容已 GA，但同时说明 Python package classifier 仍为 Beta。因此课程可以使用现有官方实现，**没有必要自行开发最小 Doris MCP Server**；真正需要开发的是连接本地 Doris Docker 的课程启动包装、示例只读用户和四个客户端的 stdio 配置模板。

默认的分层模式提供 8 个 domain、55 个 child capability。课程会先概括介绍八个 domain 的能力边界，但**不逐项演示完整工具面**。[Tool domains](https://github.com/apache/doris-mcp-server/blob/master/docs/capabilities/tool-domains.md) 作为课后参考。主展示使用三个 domain、三个 child capability：

| 展示顺序 | Domain | Child capability | 在链路中的作用 |
|---:|---|---|---|
| 1 | `doris_catalog` | `get_table_context` | 读取 `doris_course.events` 的字段、类型和索引上下文，避免模型凭空假设 Schema |
| 2 | `doris_query` | `execute_query` | 执行一条有时间范围、聚合、排序和 `LIMIT` 的只读 SQL |
| 3 | `doris_cluster` | `get_memory_stats` | 展示单 BE 教学环境的内存 tracker，并保留 source、partial 和 warning |

这三个调用已经足以说明 domain 的价值：Host 先发现最匹配的 domain，再取得其中经过授权的 child Schema，最后提交精确 child 调用。课程介绍但不实操 Pipeline、Search、Governance、Lakehouse、Semantic 等 domain，也不扩展到 Query Profile、慢查询或全量 monitoring metrics。

默认 catalog 是只读的，`doris_admin` 被保留但未注册；`execute_query` 拒绝 DDL、DML、管理 SQL、堆叠语句和无界结果。Server 还对 identifier、参数、timeout、rows、bytes、schema 做边界检查，并对错误与日志去敏。[Security and permission model](https://github.com/apache/doris-mcp-server/blob/master/docs/security/security-model.md)

结论：课程应使用 `doris-mcp-server==1.0.0`（或教学开始时重新固定最新已验证 patch），而不是社区 fork；开发前只需完成四个 Host 的本机 stdio 连接 smoke test，并在 Codex 上完成主链 PoC。

### 2.3 Agent 候选与选择标准

选择标准是：当前有一手 MCP 文档；支持本机 stdio Server；覆盖不同产品形态；配置差异有教学价值；能展示工具列表、调用和结果。

最终选择：

1. **Claude Desktop**：最直观的桌面 MCP 教学入口，本地 stdio 与桌面扩展生态成熟。
2. **Cursor**：代表开发者 IDE，项目级与用户级 `mcp.json` 清晰，并能启动本机 stdio Server。[Cursor MCP](https://docs.cursor.com/context/model-context-protocol)
3. **VS Code + GitHub Copilot Agent mode**：用户覆盖面大；`.vscode/mcp.json`、portable `.mcp.json`、input secret 与 sandbox 能讲清团队配置和安全。[VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
4. **Codex CLI/IDE**：代表命令行/编码 Agent；CLI 与 IDE 共用 `~/.codex/config.toml`，适合展示本机 stdio 配置和 `codex mcp list`。[OpenAI Docs MCP 的 Codex 配置示例](https://developers.openai.com/learn/docs-mcp)

排除项：

- **Claude Code**：能力很好，但与 Claude Desktop 同属 Anthropic，本机 stdio 配置教学重复。若课程受众偏 CLI，可用 Claude Code 替换 Claude Desktop，而不是两者都讲。
- **ChatGPT Web 自定义 Connector、Claude Web Connector、Dify**：这些产品形态不能直接复用本文的“本机 stdio MCP → 本地 Doris Docker”路径，超出课程范围。
- **其他小众 IDE/Agent**：缺少新增的教学维度，且版本变化会增加维护成本。

### 2.4 最终推荐的 4 个 Agent

| Agent | 产品形态 | MCP transport | MCP Server 位置 | Doris 位置 | 配置位置 | 安全边界 | 独特教学价值 |
|---|---|---|---|---|---|---|---|
| Claude Desktop | Desktop | stdio | 本机子进程 | 本地 Docker，`127.0.0.1:9030` | `claude_desktop_config.json`；也可封装为 `.mcpb` | 本机进程边界 + Doris 只读用户 | 最少组件、工具调用 UI 和日志直观 |
| Cursor | IDE | stdio | 本机子进程 | 本地 Docker，`127.0.0.1:9030` | 项目 `.cursor/mcp.json`；用户 `~/.cursor/mcp.json` | 本机进程边界 + tool approval | 项目/用户作用域、IDE approval |
| VS Code + Copilot | IDE | stdio | 本机子进程 | 本地 Docker，`127.0.0.1:9030` | `.vscode/mcp.json`、portable `.mcp.json` 或用户配置 | 本机进程边界 + secret input/sandbox | 团队共享、secret input、sandbox |
| Codex | CLI + IDE | stdio | 本机子进程 | 本地 Docker，`127.0.0.1:9030` | `~/.codex/config.toml` | 本机进程边界 + tool approval | 命令行可重复验证，CLI/IDE 共用配置 |

### 2.5 每个 Agent 的连接方式

以下四个客户端都启动同一个本机 stdio Server。为了避免把 Doris 密码复制进四份客户端文件，课程应提供一个本地 launcher/wrapper：它从 Git 忽略的环境文件或操作系统 secret store 读取连接参数，再执行 `doris-mcp-server --transport stdio`。客户端配置只保存 launcher 的绝对路径。

**A. Claude Desktop：本地 stdio**

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

macOS 常见位置是 `~/Library/Application Support/Claude/claude_desktop_config.json`，Windows 是 `%APPDATA%\\Claude\\claude_desktop_config.json`。新产品形态更推荐把本地 Server 打成 `.mcpb` desktop extension，并将敏感字段标为 sensitive，让系统 keychain 保存；调试时在 Developer/Extensions 查看连接状态与日志。[Claude Desktop local MCP](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)

**B. Cursor：项目级 stdio**

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

项目配置为 `.cursor/mcp.json`，个人配置为 `~/.cursor/mcp.json`。Agent 默认在工具调用前要求批准。[Cursor MCP](https://docs.cursor.com/context/model-context-protocol)

**C. VS Code + Copilot：workspace stdio**

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

保存为 `.vscode/mcp.json`。不要在 workspace 文件中硬编码 Doris 密码；本机 stdio 可以启用 `sandboxEnabled`，并只允许访问 `127.0.0.1:9030`。[Add and manage MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers)

**D. Codex：本机 stdio**

在 `~/.codex/config.toml` 写入：

```toml
[mcp_servers.doris]
command = "/absolute/path/to/run-doris-mcp-local"
args = []
```

用 `codex mcp list` 验证配置。TOML 中只保存 launcher 路径，不保存 Doris 密码。

**统一的本地 Docker 与 MCP 启动边界**

```bash
python3.12 -m venv .venv
.venv/bin/pip install 'doris-mcp-server==1.0.0'

# run-doris-mcp-local 读取受保护的本地配置后设置：
# DORIS_HOST=127.0.0.1
# DORIS_PORT=9030
# DORIS_USER=mcp_reader
# DORIS_PASSWORD=<从本地 secret/environment 读取>
# DORIS_DATABASE=doris_course
# DORIS_FE_HTTP_HOST=127.0.0.1
# DORIS_FE_HTTP_PORT=8030
# DORIS_BE_HOSTS=127.0.0.1
# DORIS_BE_WEBSERVER_PORT=8040
# MCP_TOOL_EXPOSURE_MODE=hierarchical
.venv/bin/doris-mcp-server --transport stdio
```

Doris Docker 必须只向宿主机回环地址发布课程所需端口：

```yaml
ports:
  - "127.0.0.1:9030:9030"  # FE MySQL Protocol
  - "127.0.0.1:8030:8030"  # FE HTTP，doris_cluster 能力使用
  - "127.0.0.1:8040:8040"  # BE Web Server，内存/指标证据使用
```

先从宿主机用 MySQL client 验证 `127.0.0.1:9030`，再验证 MCP；这样能把“Docker/Doris 未就绪”和“Agent/MCP 配置错误”分开。Catalog/Query 主链依赖 9030；为了展示 `get_memory_stats`，本课还使用单 BE 教学环境已映射的 8030/8040。如果某个 HTTP/BE 证据源不可用，必须展示 Server 返回的 partial/warning/callable 状态，不得伪造指标。

```bash
mysql -h 127.0.0.1 -P 9030 -u mcp_reader -p \
  -e 'SELECT 1; SHOW DATABASES;'
```

### 2.6 本地 Docker、权限与安全

安全边界应落实为四层，而不是只说“只读”：

1. **Doris 用户**：创建专用 `mcp_reader`，只对课程 database/table 授予 `SELECT` 和必要 metadata 可见性；不使用 `root`，需要租户隔离时叠加 row policy。
2. **MCP Server**：只启用所需 domain/child scope；设置查询 timeout、最大行数/字节数。Server 的只读 guard 是第二道防线，不能替代 Doris RBAC。
3. **MCP Client/Host**：保留 tool approval；不要开启全局 auto-run；workspace 配置可共享命令但不可共享 secret。
4. **网络与结果**：Doris 端口只绑定 `127.0.0.1`；MCP 只走 stdio，不监听网络端口；对大字段、PII 和错误日志做裁剪与脱敏。

Doris Docker 镜像应固定为课程验证过的 4.x patch。`mcp_reader` 的密码放在 Git 忽略的本地环境文件或 secret store 中；不要为了省事改用 `root`。MCP Server 本身不放进 Docker，以免引入 `host.docker.internal`、Compose service name 和双层容器网络差异。

### 2.7 主展示链路：Codex + Catalog/Query + Cluster 可观测性

主演示采用 **Codex CLI**；需要更直观的录屏界面时，可在 **Codex desktop** 重放同一个任务。OpenAI 官方文档说明桌面端、Codex CLI 和 IDE extension 共享同一份 MCP 配置，因此不需要维护第二套 Doris MCP 接入。[Model Context Protocol](https://learn.chatgpt.com/docs/extend/mcp)

课程在一个连续的 Codex 会话中使用三个 domain 和三次有效 child 调用。四个 Agent 都通过同一 launcher 指向 Level 1–8 共用的单 FE、单 BE 教学容器；同时打开多个 Agent 时，每个 Host 会启动自己的 stdio Server 子进程。使用 Level 1 已创建的 `doris_course.events`，固定时间范围以避免课程数据是历史样例时“最近 7 天”返回空结果。

**学习者输入的分析问题：**

> 请先检查 `doris_course.events` 的表结构，再统计 2020-03-01（含）至 2020-03-09（不含）每种 `event_type` 的事件数和去重用户数，按事件数降序，最多返回 10 行。只允许只读查询；最后列出你使用的 MCP domain，并把数据库事实与解释分开。

**预期调用链：**

```text
Codex 启动并连接本机 Doris MCP Server
  → doris_catalog：发现授权的 Catalog child capabilities
    → get_table_context：读取 doris_course.events 的 Schema/索引上下文
      → Codex 根据真实字段生成只读 SQL
        → doris_query：发现授权的 Query child capabilities
          → execute_query：在本地 Doris Docker 中执行有界聚合
            → doris_cluster：切换到资源观测意图
              → get_memory_stats：返回单 BE 的内存 tracker 及 source/partial/warning
```

分层模式下，Host 实际上先以 `{}` 调用 domain 取得 child Schema 和 `manifest_version`，再用返回的精确 `child_tool`、`arguments` 和 `manifest_version` 调用同一个 domain。演示时展开 tool trace 说明这一点，但不要求学习者手写 MCP JSON。[Host integrations](https://github.com/apache/doris-mcp-server/blob/master/docs/integrations/hosts.md)

预期 SQL 形状如下；最终 SQL 应以 `get_table_context` 返回的真实 Schema 为准：

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

**主链保留四类演示画面：**

1. `codex mcp list`，或桌面端 composer 中的 `/mcp`，显示 `doris` 已连接；不得出现密码。
2. 展开的 `get_table_context` tool trace，只保留 domain、child 名称、脱敏参数和成功状态。
3. `execute_query` tool trace 与最终结果，明确分为查询事实和 Agent 解释。
4. `get_memory_stats` 返回的单 BE 内存指标，保留 source、partial 和 warning。

**验收标准：** Codex 必须先读取表上下文再生成 SQL；SQL 必须有固定时间边界和 `LIMIT 10`；答案中的数字必须能与 MySQL client 执行同一 SQL 的结果对应。资源观测部分只调用 `get_memory_stats`，遇到不可用或部分证据时必须原样保留状态，不猜测。课程不展示完整工具列表、Profile 或跨 Host 的重复执行。

若 Codex 对 hierarchical discovery 的实测兼容不通过，再把 Server 改为 `MCP_TOOL_EXPOSURE_MODE=flat`；此时主链仍然只调用 `doris_catalog_get_table_context` 和 `doris_query_execute_query`，不扩展教学范围。

### 2.8 课程结构决策

- MCP Module 用 `readme.md` 保存开发大纲，用 `course.md` 保存面向学习者的完整内容；概念、四客户端连接、Codex 实操、排障和验收都在 `course.md` 中，不创建 Jupyter Notebook 或独立 Lab。
- 主验证固定使用 Codex CLI；需要更直观的图形界面时，使用共享同一配置的 Codex desktop。两者都通过 stdio 连接同一台电脑上的 Doris Docker。
- Claude Desktop、Cursor、VS Code、Codex 的四个 Agent 连接步骤和连接成功截图全部保留，但不在四个 Host 上重复执行完整分析。
- 完整调用验收集中在 Codex 的 `get_table_context → execute_query → get_memory_stats` 主链。
- 记录每个 Host 实际协商的 MCP protocol revision；本课程不通过切换 HTTP endpoint 或部署远程 Server 来绕过 stdio 兼容问题。

---

## 3. Doris AI Function

### 3.1 概念解释

AI Function 可以理解为“SQL 中的一次模型调用”。普通 `LOWER(text)` 在 BE 内用确定性代码处理字符串；`AI_SENTIMENT(text)` 则把文本通过一个已注册的 AI Resource 发给外部模型，再把模型回答作为 SQL 列返回。

| 概念 | 在哪里执行 | 是否通常确定 | 主要用途 |
|---|---|---:|---|
| 普通 SQL scalar function | Doris 进程内 | 是 | 数学、字符串、日期、JSON 等确定转换 |
| UDF | Doris 加载的自定义代码/外部执行环境 | 取决于实现 | 扩展数据库没有的逻辑 |
| AI Function | SQL 在 Doris；推理在外部或本地模型 endpoint | 否 | 分类、抽取、摘要、生成等语义任务 |
| 应用直接调用模型 API | 应用服务 | 否 | 复杂工作流、异步队列、定制重试/评估/缓存 |
| Agent Tool | Agent 决定何时调用的有 Schema 操作 | 取决于工具 | 多步计划、查询系统或执行动作 |

AI Function 不是 Agent：它不会自己规划多步任务；也不是普通 UDF：核心语义依赖网络外部模型。它的优势是数据不必先由 Python 应用逐行拉出，结果可直接参与 `SELECT`、`INSERT ... SELECT`、`UPDATE`、过滤或聚合；不足是 SQL 查询生命周期被模型延迟和费用绑住。

### 3.2 Doris 当前能力

官方 [AI Functions overview](https://doris.apache.org/docs/4.x/ai/ai-function-overview/) 与 [SQL reference](https://doris.apache.org/docs/dev/sql-manual/sql-functions/ai-functions/overview/) 给出以下能力：

| 函数 | 主要输入 | 返回 | 典型场景 |
|---|---|---|---|
| `AI_CLASSIFY` | 文本、候选标签 | 单个标签 `STRING` | 工单/商品/反馈分类 |
| `AI_EXTRACT` | 文本、待抽取标签 | 抽取结果 `STRING` | 实体与字段抽取 |
| `AI_FILTER` | 文本、自然语言条件 | `BOOLEAN` | 语义筛选、审核候选 |
| `AI_FIXGRAMMAR` | 文本 | 修正文 `STRING` | 清洗文本 |
| `AI_GENERATE` | prompt | 生成文本 `STRING` | 解释、改写、结构化生成 |
| `AI_MASK` | 文本、敏感字段标签 | `[MASKED]` 后文本 | PII 脱敏辅助 |
| `AI_SENTIMENT` | 文本 | positive/negative/neutral/mixed | 评论与反馈分析 |
| `AI_SIMILARITY` | 两段文本 | `DOUBLE`，0–10 | 小规模语义比较 |
| `AI_SUMMARIZE` | 文本 | 摘要 `STRING` | 工单、日志、文档摘要 |
| `AI_TRANSLATE` | 文本、目标语言 | 译文 `STRING` | 多语言标准化 |
| `AI_AGG` | 多行文本、prompt | 每组一个 `STRING` | 周报、主题汇总 |
| `EMBED`（相关能力） | 文本 | `ARRAY<FLOAT>` | 生成 ANN 索引所需向量 |

Provider 通过 `CREATE RESOURCE ... type='ai'` 配置 endpoint、model、API key、temperature、max tokens、retries、retry delay 和 embedding dimension。SQL reference 明确列出 OpenAI、Anthropic、Gemini、DeepSeek、Local、MoonShot、MiniMax、Zhipu、QWen、Baichuan；其他与 OpenAI/Anthropic/Gemini API 兼容的 provider 也可按对应协议接入。另一张官方 feature card 还列出 VoyageAI/Jina，推测主要针对 embedding；**provider × function 的精确兼容矩阵尚未在同一官方页面闭合，正式课程前必须逐项实测，不应写成“所有 provider 支持所有函数”。**

执行语义：这些函数由 BE 发起 HTTP 请求，SQL 查询同步等待结果；BE 会按 batch/context window 合并输入，重试受 Resource 参数控制，请求还受剩余 `query_timeout` 约束。[LLM SQL Functions](https://doris.apache.org/docs/dev/key-features/llm-sql-functions/) 明确说明它适合 batch enrichment/backfill，不适合要求亚秒响应或严格复现的在线查询。

“支持批量”应准确表述为：一条 SQL 可处理多行，BE 会内部 batching；它不是独立的异步推理作业系统。大批量生产任务仍需按主键分片、落结果表、记录失败行、支持幂等重跑和预算上限。

### 3.3 关键源码或测试证据

这不是只存在于宣传材料的功能。Doris 主仓库中可核对：

- scalar 实现注册与适配器：[`be/src/exprs/function/ai/`](https://github.com/apache/doris/tree/master/be/src/exprs/function/ai)
- aggregate 实现：[`aggregate_function_ai_agg.cpp`](https://github.com/apache/doris/blob/master/be/src/exprs/aggregate/aggregate_function_ai_agg.cpp)
- BE 单元测试：[`be/test/ai/ai_function_test.cpp`](https://github.com/apache/doris/blob/master/be/test/ai/ai_function_test.cpp) 和 [`aggregate_function_ai_agg_test.cpp`](https://github.com/apache/doris/blob/master/be/test/ai/aggregate_function_ai_agg_test.cpp)
- SQL 回归测试：[`regression-test/suites/ai_p0/test_ai_functions.groovy`](https://github.com/apache/doris/blob/master/regression-test/suites/ai_p0/test_ai_functions.groovy)
- Resource 与授权测试：[`test_create_ai_resource.groovy`](https://github.com/apache/doris/blob/master/regression-test/suites/ai_p0/test_create_ai_resource.groovy) 和 [`test_ddl_ai_resource_auth.groovy`](https://github.com/apache/doris/blob/master/regression-test/suites/auth_call/test_ddl_ai_resource_auth.groovy)
- 发布证据：[Apache Doris 4.0.0 Release Note](https://github.com/apache/doris/issues/56823#issuecomment-3485687514)

首次支持版本是 4.0。课程不要在现有 2.x/3.x Lab 环境上暗示可用；应固定 4.0.8 或经过验证的 4.1 patch。

### 3.4 同类产品场景对比

| 产品 | 调用形态 | 模型/治理方式 | 批量与错误处理 | 判断 |
|---|---|---|---|---|
| Doris 4.x | `AI_*`、`AI_AGG`、`EMBED` | AI Resource 连接外部/本地 provider | 同步 SQL、BE batching、retry/query timeout | 开源数据库内原生，功能完整度高；生产治理需自行补齐 |
| Snowflake Cortex AI | `AI_COMPLETE`、`AI_CLASSIFY`、`AI_FILTER`、`AI_EXTRACT`、`AI_AGG` 等 | 托管模型、细粒度 `USE AI FUNCTION` 权限、计量 | 有 row-level error 选项、AI Function evaluation | 托管与治理最完整，但依赖 Snowflake 服务。[官方函数与权限](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-privileges-and-access) |
| Databricks | task-specific functions + `ai_query` | Databricks/Model Serving endpoint、Unity Gateway | 自动并行、重试、扩缩；`failOnError=false` 保留成功行 | 批处理和工作流集成成熟，当前相关 batch 能力仍标 Public Preview。[`ai_query`](https://docs.databricks.com/aws/en/large-language-models/ai-query) |
| BigQuery ML | `AI.GENERATE_TEXT` / `ML.GENERATE_TEXT` + remote model | Cloud connection service account、Vertex/partner model | row status、quota error、迭代重试脚本 | IAM 与对象表/多模态整合强，但 Cloud 依赖重。[官方文档](https://docs.cloud.google.com/bigquery/docs/generate-text) |
| ClickHouse | `aiGenerate`、`aiClassify`、`aiExtract`、`aiEmbed` 等 | Cloud 可托管，自管需 provider 配置 | 2026 年功能仍标 Beta/Cloud private preview | 值得持续追踪，不宜当成熟生产基准。[官方发布说明](https://clickhouse.com/blog/ai-functions-in-clickhouse) |

### 3.5 真实应用场景

| 场景 | 输入 / SQL 与模型位置 | 是否写回 Doris | 为什么不用普通 SQL / 应用直调 | 风险与建议 |
|---|---|---:|---|---|
| 工单分类、商品标签 | Doris 文本列；SQL 在 Doris，模型在 provider | 推荐写回 | 标签依赖语义；批量数据已在 Doris，SQL 回填比另建一次性脚本简单 | 标签漂移；固定 prompt/model/version，抽样评估 |
| 情感分析 | 评论、客服对话 | 推荐写回 | 普通 SQL 关键词规则脆弱 | 讽刺/领域语言误判；保留原文和人工校准集 |
| 实体/结构化字段抽取 | 发票、工单、日志文本 | 推荐写回结构化列 | 普通 regex 难覆盖变化；批量回填适合 SQL | 输出格式不稳定；强校验、失败表、禁止直接驱动财务动作 |
| 摘要/周报 | 单行长文本或分组多行 | 写入派生表 | `AI_AGG` 减少应用 glue | token 爆炸、遗漏、不可复现；限制行数/长度并保留证据链接 |
| 数据清洗/语法修正/翻译 | 脏文本、多语言文本 | 写回新列，不覆盖原列 | 语义变换超出普通 SQL | 可能改意；永远保留 raw column |
| PII masking | 自由文本 | 只能作为辅助结果 | 规则可能漏掉语义型 PII | **炫但不宜单独作为合规控制**；必须叠加确定性 DLP/regex 和审计 |
| 日志解释 | 日志行或聚合后的错误簇 | 通常不写回，或写调查表 | 模型能解释上下文 | 在线逐行调用昂贵且慢；先 SQL 聚类/采样再调用 |
| 在线查询时生成 | 用户查询命中行 | 通常不写回 | 开发快 | 延迟、费用、429 会直接拖垮查询；仅 Demo，不作为核心 serving 路径 |

端到端示例流程（不是完整 Lab）：

```text
support_tickets.raw_text
  → SQL 先过滤新增且未处理的 100 行
  → AI_CLASSIFY / AI_EXTRACT（外部或本地模型）
  → 校验标签集合与 JSON/字段格式
  → INSERT 到 ticket_enrichment（保留 model、prompt_version、processed_at、error）
  → SQL 聚合标签/优先级
  → 人工抽样评估与失败重跑
```

### 3.6 成本、可靠性和治理

- 一行一个逻辑推理不等于一个 HTTP 请求：Doris 可 batch，但 provider 仍按 token/请求计费。先 `COUNT` 和 `LIMIT`，再执行 AI SQL。
- `temperature`、模型升级和 provider 后端变化会造成同一 SQL 不同结果。把模型名、prompt 版本、参数和处理时间写入结果表。
- retry 会增加延迟和重复计费风险；查询 timeout 不是预算控制。生产需要每日 token/金额上限、并发限制和熔断。
- API key 虽会在 `SHOW RESOURCES` 中遮蔽，仍是 FE 持久化的敏感配置；只给管理员创建/查看 Resource 的权限，使用专用低额度 key 并定期轮换。
- 任何会影响权限、财务、医疗、安全封禁的结果都必须有人审或确定性规则兜底。
- 不在 dashboard 查询中按刷新频率重复调用；优先离线 enrich 并物化结果。

### 3.7 课程化可行性判断

当前建议为 **Workshop，而非独立完整 Module**。理由不是功能不存在，而是学习结果会被 provider 凭据、费用、网络和模型差异干扰。若以下 PoC 全部通过，可把“SQL 内批量文本 enrichment”升格为 Module 中的一节：

- 固定 Doris 4.0.8/4.1.x 与本地 Ollama 或低成本 provider；
- 验证 100、1,000、10,000 行的 batching、timeout、429、部分失败和重跑；
- 为分类/抽取建立小型 ground truth，测 accuracy 而不是只展示漂亮输出；
- 验证 Resource 权限、key 遮蔽和查询审计；
- 明确结果持久化 schema 与幂等规则。

---

## 4. Hybrid Search 与 Lakehouse

### 4.1 概念边界

| 概念 | 准确定义 | 不等于 |
|---|---|---|
| keyword/full-text search | tokenizer/analyzer 把文本变成 term，倒排索引用 `MATCH_*`/BM25 找词、短语和相关性 | 向量语义相似 |
| structured filtering | tenant、时间、价格、状态等 `=`, range, `IN` 条件 | 全文检索 |
| semi-structured search | 查询 JSON/VARIANT/ARRAY/MAP/STRUCT 内的字段与元素 | 多模态或向量检索 |
| vector similarity search | embedding 的 ANN/精确距离 Top-K | 关键词匹配 |
| lexical + vector hybrid search | 同一问题同时使用 lexical 与 vector retrieval，再过滤、排序或融合 | “SQL 里条件很多”或“数据源很多” |
| reranking | 对第一阶段较小 candidate set 用更贵模型重新排序 | ANN 本身 |
| metadata filtering | ANN 前后按 tenant/ACL/time/type 缩小结果 | ranking fusion |
| lakehouse federation | Doris 经 Catalog 直接读取 Hive/Iceberg/Hudi/Paimon 等外部数据 | 数据已复制进 Doris |
| 多数据源 Join | 一个 SQL plan 扫多个 catalog/source 并 join | 所有源都拥有 Doris 内表索引 |

“多模态”是文本、图片、音频等不同模态；“半结构化”是 schema 灵活的 JSON 类数据；“多数据源”是物理存储位置不同；“混合检索”是检索算法组合。四者可以同时出现，但不是同义词。

### 4.2 Doris 检索能力

| 能力 | 版本/边界 | 证据 |
|---|---|---|
| Inverted index | 2.0 起；结构化 equality/range/IN/null/array 与全文 `MATCH_*` | [Inverted Index](https://doris.apache.org/docs/4.x/key-features/inverted-index/) |
| tokenizer/analyzer | 内置 none/standard/english/chinese/unicode 等；3.1 起 custom analyzer，4.x 持续扩展 | [TOKENIZE](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/scalar-functions/string-functions/tokenize/) |
| BM25 / `score()` / `SEARCH()` | 4.0 重点增强 | [4.0 Release](https://doris.apache.org/releases/v4.0/release-4.0.0/) |
| JSON/VARIANT | 动态 JSON；VARIANT 自动拆 sub-column，适合 log/trace/IoT | [Data types](https://doris.apache.org/docs/4.x/sql-manual/basic-element/sql-data-types/data-type-overview/) |
| ARRAY/MAP/STRUCT | 固定 schema nested type；ARRAY 同时承载 vector | 同上 |
| ANN vector index | 4.0 起，`ARRAY<FLOAT> NOT NULL`，Faiss HNSW/IVF；有 TopN、range、filter | [Vector Search](https://doris.apache.org/docs/4.x/table-design/index/vector-index/overview/) |
| Hybrid Search | 官方定义为同一内表上 inverted index + ANN index 的查询模式 | [Hybrid Search](https://doris.apache.org/docs/4.x/key-features/hybrid-search/) |
| Catalog federation | Hive/Iceberg/Hudi/Paimon/JDBC 等；一个 SQL 可跨 catalog join | [Lakehouse Overview](https://doris.apache.org/docs/4.x/lakehouse/lakehouse-overview/) |
| Runtime Filter | join 执行优化，把 build-side 条件下推到 probe-side，减少扫描 | 不是检索类型，不应用来定义 Hybrid Search |

源码/测试证据：ANN 有 [`be/test/storage/index/ann/`](https://github.com/apache/doris/tree/master/be/test/storage/index/ann) 的 writer/reader/iterator/range/edge case/Faiss 测试和 [`regression-test/suites/ann_index_p0/`](https://github.com/apache/doris/tree/master/regression-test/suites/ann_index_p0)；VARIANT 有 [`be/test/storage/variant/`](https://github.com/apache/doris/tree/master/be/test/storage/variant) 与 `variant_p0` 回归套件。4.0 Release Note 同时给出 ANN 限制：最初只支持 Duplicate Key、vector 必须非 NULL 且维度匹配。较新的 4.x feature card 表示也支持 Merge-on-Write Unique Key；课程必须以所固定 patch 的实际 DDL 为准。

### 4.3 一条 SQL 能组合哪些能力

对 **Doris internal table**，4.0 可以在一条 SQL 中组合：

```sql
SELECT id, body,
       l2_distance_approximate(embedding, /* query vector */) AS distance
FROM knowledge_chunks
WHERE tenant_id = 42
  AND created_at >= '2026-01-01'
  AND attrs['region'] = 'cn-east'
  AND body MATCH_ANY 'payment timeout'
ORDER BY distance
LIMIT 10;
```

其中 structured predicate、VARIANT 路径、全文条件先缩小候选，ANN 再排序。embedding 的生成发生在写入前或查询前，可由 `EMBED()`、应用服务或外部 pipeline 完成；Doris 的 ANN index 只消费向量，不理解原始图片/音频。

必须区分两种“Hybrid”：

- 官方 Hybrid Search 快速路径是 **全文条件作为 pre-filter + vector distance 排序**，一条 SQL、一个表。
- 真正把 BM25 列表与 ANN 列表都保留再融合，需要 RRF/加权融合。Doris 没有内置 `rrf()`。官方 [RRF 页面](https://doris.apache.org/docs/4.x/key-features/reciprocal-rank-fusion/) 给出用两个 CTE、`ROW_NUMBER()`、`FULL OUTER JOIN` 实现单 SQL RRF；但 Hybrid Search 页面又写过“需要 RRF 时由应用发两次查询融合”。共同可确认的是“无内置 RRF”；单 SQL RRF 的计划、索引命中、候选规模和延迟需在固定版本 PoC 后才可进入 Lab。

**外部 Catalog 边界：** 一条 SQL 确实能 join Doris internal table 与 Iceberg/Hive 等外部表，但外部数据没有因为被 Catalog 读取就自动拥有 Doris internal table 的 ANN/倒排索引。最可靠架构是把需要低延迟检索的 chunk、embedding、ACL/tenant metadata 导入 Doris，把湖仓保留为历史事实或冷数据，再在 SQL 中 join/union。不要写成“对任意 S3/Iceberg 表直接建立 Doris ANN 后零复制检索”，除非专门 PoC 证明该 connector/version 支持。

### 4.4 外部 Catalog 与数据存储位置

**A. 数据全部进入 Doris**

```text
对象/文本/metadata
  → chunk / embedding model
    → Doris internal table（文本、embedding、tenant/ACL、VARIANT metadata）
      → structured filter + full-text/vector retrieval
        → 可选 reranker
          → LLM
```

特点：

- 性能：最容易命中本地倒排和 ANN 索引，适合低延迟、高并发 serving。
- 数据复制：需要从对象存储/源系统复制 chunk 和 embedding，并维护增量同步。
- 实时性：Doris ingestion 可较快更新；embedding 生成通常是瓶颈。
- 运维：一个 serving store，但多一条 ingest/embedding pipeline；索引占空间和内存。

**B. 实时数据与湖仓数据并存**

```text
Doris realtime tables ─┐
                       ├→ Doris SQL / Catalog federation → retrieval result → 可选 reranker → LLM
S3/Iceberg/Hive data ──┘
```

特点：

- 性能：外部 object scan、metadata、网络和文件布局决定尾延迟；cache 能改善热点，但通常不适合每次聊天都扫大湖表。
- 数据复制：历史事实可留在湖仓，减少复制；但热检索索引往往仍需一份 Doris 内表 projection。
- 实时性：实时事实在 Doris 新鲜；湖仓受 snapshot/commit/catalog refresh 延迟影响。
- 运维：少一部分复制，多了 Catalog、IAM、对象存储、metadata cache 和跨源故障面；没有跨 catalog 事务。

Doris Multi Catalog 使用 `catalog.db.table`，可在一个 MPP plan 中跨 internal/Hive/Iceberg/JDBC 等数据源 join；官方也提醒外部源不适合写密集 OLTP，网络稳定性与 cache freshness 必须治理。[Multi Catalog](https://doris.apache.org/docs/4.x/key-features/multi-catalog/)

### 4.5 同类产品对比

| 产品 | lexical + vector | 过滤/融合/重排 | 数据与计算形态 | 相对 Doris 的启示 |
|---|---|---|---|---|
| Elasticsearch | 同一 search request | RRF/linear retriever、metadata filter、semantic reranker | 搜索引擎，检索生态成熟 | 相关性调优和 reranking 更成熟；复杂 SQL analytics/join 不是强项。[Hybrid search](https://www.elastic.co/docs/solutions/search/hybrid-search) |
| OpenSearch | 2.11 起 hybrid query + search pipeline | normalization 或 RRF score ranker，pre/post filter | 开源搜索引擎 | 课程可借鉴“召回→归一/融合→重排”分层。[官方文档](https://docs.opensearch.org/latest/vector-search/ai-search/hybrid-search/index/) |
| Snowflake Cortex Search | 托管 vector + keyword | 托管 reranking、权重/boost/time decay | Snowflake 内托管 Search Service | 开箱质量和治理强，但不是普通 SQL index；服务有独立刷新/计费。[Cortex Search](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-search/cortex-search-overview) |
| Databricks AI Search | Delta Sync index 支持 ANN/hybrid/full text | filter API；服务端 index endpoint | 从 Delta 表同步到 Search index | 数据治理/同步与湖仓结合强，但仍有独立 endpoint/index。[Create AI Search](https://docs.databricks.com/aws/en/vector-search/create-vector-search) |
| PostgreSQL + pgvector | PostgreSQL FTS + vector | SQL/application RRF 或 cross-encoder；metadata filter | 单库扩展，HNSW/IVFFlat | 小中规模和事务结合简单；分布式分析/大规模吞吐取决于外围架构。[pgvector](https://github.com/pgvector/pgvector#hybrid-search) |
| ClickHouse | 原生 vector + 2026 GA full-text | SQL 组合，相关能力快速演进 | 列式分析库 | 与 Doris 最相近；其 FTS 26.2、vector 25.8 GA，课程材料需按新版本重做，不能沿用旧 Bloom filter 结论。[FTS GA](https://clickhouse.com/blog/full-text-search-ga-release) |

### 4.6 AI/RAG 场景

| 场景 | 数据位置与类型 | 一条 SQL？ | embedding / reranker | Doris 的主要价值与短板 |
|---|---|---|---|---|
| RAG 文档检索 | chunk、正文、ACL、tenant、embedding 放 Doris；原 PDF 可留对象存储 | 检索可一条 SQL | ingest/query 都需同模型 embedding；高质量场景可 rerank Top 20–100 | 过滤、全文、向量、join 一体；缺少开箱托管 reranker/evaluation |
| 商品搜索 | 商品标题/描述、品牌、价格、库存、embedding 在 Doris | 是 | query embedding；可按点击数据 rerank | 实时库存/行为 analytics 与检索同库；纯搜索相关性工具不如 Elastic 成熟 |
| 日志/可观测性 | 日志文本、VARIANT attributes、时间、service、embedding | 是（内表） | 先全文/结构化，只有语义调查才需要 embedding | 时间/聚合/全文统一；给所有日志做 embedding 费用巨大 |
| 客服知识库 | FAQ、历史工单、产品/地区/版本 metadata | 是（热知识入 Doris） | embedding 必需；答案生成在 LLM | 能把用户/订单上下文 join 到检索结果；需严格 ACL |
| 安全事件调查 | event/log、IOC keyword、tenant、时间、embedding | 通常可 | embedding 用于相似事件；reranker 可选 | 结构化过滤和聚合强；模型结论不可替代取证事实 |
| 行为 + 内容联合检索 | user events 与内容/商品 embedding 同 Doris | 是 | 内容/user embedding；可二阶段模型排序 | SQL join/aggregation 是相对纯向量库的优势；ANN 极限成本可能更高 |
| 湖仓历史 + 实时 | 历史 Iceberg/Hive，实时事实与热检索 projection 在 Doris | join 可一条 SQL；全湖 ANN 不应默认承诺 | 历史 embedding 可预计算；热候选 rerank | 统一查询和计算；跨源延迟、索引边界和 snapshot freshness 是短板 |

与纯向量数据库相比，Doris 的优势是 SQL、结构化过滤、全文、join、aggregation 和实时分析同一引擎；不足是纯 ANN 极限场景可能更耗资源，相关性融合、托管 embedding/reranking、向量生命周期与评估工具不如专用产品完整。

### 4.7 可运行 Lab 与外部依赖

适合稳定本地 Lab：

- 小型 product/knowledge chunks 表；预先提交确定性 embedding fixture，避免 API key。
- 创建 inverted index + ANN index；依次跑 structured filter、全文、vector、pre-filter + ANN。
- 对照 exact distance 与 approximate Top-K；用 `EXPLAIN`/profile 验证是否命中 index。
- 用 VARIANT metadata 做 tenant/region/time 过滤。

适合 Notebook：

- chunking、离线 embedding、recall@k 对比、RRF SQL 与简单 relevance 标注。
- Notebook 只读取环境变量中的 provider key；默认路径用预计算向量。

必须依赖外部环境或截图式 Workshop：

- S3 + Hive Metastore/Glue/Unity Catalog、Iceberg/Hudi/Paimon federation。
- 托管 embedding API、OAuth、Cloud IAM、大规模 ANN benchmark。
- 多用户 Web Agent + RAG 端到端 UI。

### 4.8 课程化可行性判断

可发展为 Module 的内容：概念边界、倒排/full-text、structured/VARIANT filter、ANN、同一内表的 Hybrid Search、RAG retrieval 架构。首个 Lab 用预计算向量和 Doris 4.0.8，完全本地运行。

暂留 Workshop 的内容：SQL RRF 性能、外部 embedding、reranker、跨 Catalog 历史 + 实时检索。先完成以下 PoC：

- internal table 上 `MATCH_* + ANN + structured + VARIANT` 的 index plan；
- CTE RRF 是否分别命中 BM25/ANN，候选 50/100/200 的延迟；
- Iceberg 历史表 join Doris 热检索结果的 predicate pushdown、扫描量和 p95；
- 数据更新后 inverted/ANN 可见性与索引构建成本；
- MoW Unique Key 在固定 4.x patch 的实际支持范围。

---

## 5. 三个方向的课程优先级

| 方向 | 当前成熟度 | 学习价值 | 实验复杂度 | 外部依赖 | 推荐课程形态 | 优先级 |
|---|---|---|---|---|---|---:|
| Doris MCP + Codex 主链 | 中高；官方 Server 1.0，包仍 Beta | 高：职责、安全、Agent-facing analytics 与集群可观测性 | 低到中 | Codex；Doris 本地 | 单篇 Markdown Course，内嵌实操 | P0 |
| MCP 多 Host 连接 | 中；Host 协议兼容需验证 | 中高：transport/配置差异 | 中 | 4 个客户端，部分账户/模型 | 同一 Markdown 中的配置卡 + 连接截图 | P1 |
| Doris 内表 Hybrid Search | 中高；4.0+ 原生 | 很高：RAG 基础和 Doris 差异化 | 中 | Doris 4.x；预计算向量即可 | 独立 Module + Notebook/Lab | P0 |
| AI Functions | 中；源码/测试齐全，外部模型治理年轻 | 高 | 中到高 | 模型 endpoint、费用/网络 | 探索性 Workshop | P1 |
| Lakehouse + 实时联合检索 | 联邦成熟，检索组合边界待 PoC | 高但进阶 | 高 | S3/MinIO、Catalog、table format | 架构课 + Workshop | P2 |
| 多模态/RRF/reranker | 能力分散，端到端证据不足 | 中高 | 高 | embedding/reranker/model | 先 PoC，不承诺 Module | P2 |

---

## 6. 后续课程开发建议

### 可发展成 Module

- **Agent-facing analytics 基础**：MCP 四角色、只读安全，以及 Codex 完成 `get_table_context → execute_query → get_memory_stats` 展示链路。
- **Doris 4.x Hybrid Search**：从 keyword/structured/semi-structured/vector 到同表组合；用 RAG 或商品搜索贯穿。

### 适合 Workshop/Tutorial

- AI Functions：100 行工单 enrichment + 质量/成本/失败讨论。
- Claude Desktop、Cursor、VS Code、Codex 的客户端接入：保留四套详细连接配置和连接成功截图；完整操作只在 Codex CLI/Desktop 演示一次。
- Lakehouse federation：用小型 Iceberg/MinIO 环境展示历史数据 join，而不是宣称任意外部表原地 ANN。

### 需要先完成的 PoC

1. **首选 PoC：Doris MCP 1.0 + 课程单 FE/单 BE Doris 4.1.3 + Codex stdio。** 创建最小权限账号，完成 `get_table_context → execute_query → get_memory_stats`；分析数字与 MySQL client 的同一 SQL 结果核对，内存指标保留 source/partial/warning。
2. 四个 Host 只验证本机 stdio 启动和连接；Codex 额外验证 hierarchical discovery，不支持时才使用 flat。
3. 4.0.8/4.1.3 Hybrid Search 的 DDL、EXPLAIN、recall 和更新可见性。
4. AI Function 的 provider compatibility、batching、429、部分失败、重试费用和 Resource 权限。
5. Iceberg + Doris internal 热索引表的单 SQL join 与 p95，明确哪些 predicate/index 能下推。

### Markdown、截图与 Cloud 的分工

- MCP Markdown：概念、命令、配置、prompt、预期调用链、排障和验收均放在同一篇 `course.md`；不设 MCP Notebook/Lab。
- MCP 截图：四个 Host 各一张连接成功图；Codex 的 Catalog、Query 和 Memory stats 调用/结果图。配置文本本身不用截图。
- 其他 AI 主题的 Notebook：Hybrid Search、RRF/recall 评估、AI Function 小批量 enrich 和质量抽样；这一结构不适用于 MCP Module。
- Cloud/外部环境：托管模型、S3/Glue/Unity Catalog、大规模 ANN；这些仅用于 AI Function 和 Lakehouse 专题，不改变 MCP 连接本地 Doris Docker 的主线。
- 本地必跑：Doris 4.x、预计算 embedding、inverted + ANN、MCP stdio 只读链路。

### 正式发布课程前仍缺的证据

- 四个推荐 Host 与 MCP `2026-07-28`、hierarchical tool discovery 的实测兼容矩阵。
- Doris MCP Server 1.0 的稳定 release/tag 与 PyPI provenance、升级策略。
- AI Resource 中每个 provider 对 chat/embedding/batch 的精确支持矩阵；凭据加密/持久化和审计边界。
- AI Functions 在 4.0.8 与 4.1.3 的吞吐、并发、429、错误行语义和成本数据。
- Hybrid Search 官方文档关于 RRF 的矛盾在固定 patch 上的实测结论。
- ANN 对 Duplicate Key / MoW Unique Key、schema change、update/delete、replication/compaction 的课程级限制表。
- 外部 Catalog 查询中全文/向量算子的 pushdown 与 index 使用边界。
- 至少一个带人工 relevance label 的小数据集，用 recall@k/NDCG 评价检索，而不是只凭“看起来相关”。

上述未定证据不阻塞 MCP 大纲设计，但在截图和课程发布前必须完成四个 Host 的实机 smoke test 与 Codex 主链 PoC。对其他 AI 主题，不要把“一个 SQL 能 join 多源”写成“所有数据源都原地支持 Doris Hybrid Search”。
