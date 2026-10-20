# ClickHouse AI 相关课程调研

> 调研时间：2026-09-29
> 调研范围：[ClickHouse Academy](https://learn.clickhouse.com/) 当前位于 **Workshops and Tutorials** 下的 AI、MCP、LibreChat、Langfuse 和 ClickStack 相关教程。

## 一、整体定位

ClickHouse Academy 当前把系统性课程集中为 Real-time Analytics、Data Warehousing 和 Observability 三条主线，而把 AI Agent、MCP、LibreChat 和 Langfuse 放在 Workshops and Tutorials 中。这四门教程的重点不是训练大语言模型，而是把已经存在的模型、聊天客户端、MCP 工具和 ClickHouse 数据服务连接起来。

四门教程共同使用的基本关系如下：

```text
用户
└── Claude Desktop 或 LibreChat
    └── 大语言模型
        └── MCP Server
            └── ClickHouse Cloud 或 ClickStack
```

其中，LibreChat 是可自行部署的 Web 聊天和 Agent 平台；大语言模型负责理解问题与组织答案；MCP Server 把数据库或可观测性能力包装成模型可以调用的工具；Langfuse 记录大语言模型和 Agent 的运行过程。

---

## [Deploying an AI Agent and Langfuse with ClickHouse Cloud Tutorial](https://learn.clickhouse.com/deploying-an-ai-agent-and-langfuse-with-clickhouse-cloud-tutorial)

**一句话概述：** 在 LibreChat 中创建一个能够通过 ClickHouse Cloud MCP 查询数据的 AI Agent，再使用 Langfuse Cloud 记录和分析 Agent 的执行过程。

### 课程定位

这是四门教程中覆盖链路最完整的一门。它同时包含：

- ClickHouse Cloud 中的数据；
- ClickHouse Cloud 托管的 MCP endpoint；
- Docker 中运行的 LibreChat Web 应用；
- LibreChat 中配置的 AI Agent；
- Anthropic 模型；
- Langfuse Cloud 中的 LLM Trace、成本和延迟监控。

最终形成的链路是：

```text
浏览器
  ↓
LibreChat Web UI
  ↓
LibreChat Agent + Anthropic 模型
  ↓
https://mcp.clickhouse.cloud/mcp
  ↓
ClickHouse Cloud

同时：LibreChat ── Trace ──> Langfuse Cloud
```

### 内容形式

- **课程首页说明：** 解释课程将完成 LibreChat、ClickHouse Cloud MCP 和 Langfuse Cloud 的完整连接，并列出 ClickHouse Cloud、Anthropic API key、GitHub 和 Docker 等前置条件。
- **图文 Hands-on Lab：** 课程主体由 6 个带截图和配置示例的操作步骤组成。
- **Additional Resources：** 提供其他资源和课程调查。
- **视频：** 当前目录中没有单独列出的 Demo 视频，核心内容是交互式图文实验。

### Hands-on Lab 详细内容

1. **Configure the MCP Server**
   - 在 ClickHouse Cloud 的连接页面选择 MCP。
   - 启用 Model Context Protocol。
   - 使用 ClickHouse Cloud 提供的远程 MCP endpoint，而不是在本地单独启动 MCP 容器。

2. **Install and configure LibreChat**
   - 从 GitHub 克隆 LibreChat。
   - 从示例文件创建 `.env`，配置 Anthropic API key。
   - 从示例文件创建 `librechat.yaml`。
   - 在 `librechat.yaml` 中添加远程 ClickHouse MCP endpoint。
   - 通过 Docker Compose 启动 LibreChat，并从浏览器访问 `localhost:3080`。
   - 在 Agent Builder 中创建专用 ClickHouse Agent，选择模型、填写 ClickHouse Cloud organization/service 信息，并为 Agent 添加 MCP tools。

3. **Use the agent**
   - 在 LibreChat 中选择刚创建的 Agent。
   - 先验证 Agent 能列出数据库。
   - 再使用英国房价数据提出业务问题，例如寻找价格较低的居住地区。
   - Agent 根据问题决定调用 MCP 工具、查询 ClickHouse，并把结果整理成自然语言答案。

4. **Create a Langfuse Cloud account**
   - 创建 Langfuse Cloud 项目。
   - 获取 LibreChat 向 Langfuse 上报 Trace 所需的项目配置。

5. **Configure LibreChat to use Langfuse**
   - 将自己的 Langfuse 项目配置写入 LibreChat 的 `.env`。
   - 重启 LibreChat，使监控配置生效。
   - 课程展示的是配置位置和重启过程，实际密钥应由学员自行创建并妥善保存。

6. **Monitor your LLM usage in Langfuse**
   - 再次在 LibreChat 中向 Agent 提问。
   - 在 Langfuse 的 Tracing 页面找到对应的 `AgentRun`。
   - 查看一次请求中的详细 Trace。
   - 在首页和预置 dashboard 中观察请求数量、成本、延迟和使用量。

### 完成后的能力

学员完成的不只是“用自然语言查询 ClickHouse”，而是一套可以观察的 AI 数据应用：Agent 可以调用数据库工具，Langfuse 可以说明它调用了什么、运行多久、成本多少以及哪里出错。

---

## [How to integrate the ClickHouse MCP Server with Claude Desktop](https://learn.clickhouse.com/how-to-integrate-the-clickhouse-mcp-server-with-claude-desktop)

**一句话概述：** 在 macOS 上安装并配置 Claude Desktop，使它通过本地运行的 Python ClickHouse MCP Server 查询 ClickHouse Cloud。

### 课程定位

这是组件最少、最适合理解 MCP 基本作用的一门教程。它不用 LibreChat，也不加入 Langfuse：

```text
Claude Desktop
      ↓ stdio
本地 mcp-clickhouse Python 进程
      ↓ HTTPS
ClickHouse Cloud
```

### 内容形式

- **课程首页说明：** 介绍 ClickHouse MCP Server 是连接 AI client 与 ClickHouse service 的 Python 程序，并说明教程主要按 macOS 环境编写。
- **Demo 视频：** [The ClickHouse MCP Server](https://www.youtube.com/watch?v=y9biAm_Fkqw)，演示 ClickHouse MCP Server 与 Claude Desktop 的连接效果。
- **Hands-on Lab：** 包含创建 Cloud service、安装 Python/`uv`、安装 Claude、配置 Claude 和自然语言提问五个步骤。
- **Additional Resources：** 提供其他资源和课程调查。

### Hands-on Lab 详细内容

1. **Create a ClickHouse Cloud service**
   - 创建课程使用的 ClickHouse Cloud 服务和示例数据环境。

2. **Install Python and uv**
   - 安装 Python。
   - 安装 `uv`，用于临时获取并运行 `mcp-clickhouse` Python package。

3. **Install Claude**
   - 安装 Claude Desktop。
   - 本教程使用原生桌面客户端，而不是浏览器中的 LibreChat。

4. **Configure Claude**
   - 在 Claude Desktop 的 Developer 设置中打开配置文件。
   - 在 `claude_desktop_config.json` 中定义 `mcp-clickhouse`。
   - Claude Desktop 通过 `uv run --with mcp-clickhouse ...` 启动本地 MCP Server。
   - ClickHouse host、用户、密码、TLS 和 timeout 等连接参数通过 MCP 进程的环境变量传入。
   - 重启 Claude Desktop，并通过 Developer 页面和日志确认 MCP Server 已成功启动。

5. **Ask some questions!**
   - 询问当前有哪些数据，触发列出数据库的 MCP tool。
   - 围绕英国房价数据询问低价城镇、最高和最低房价、城市价格差异等问题。
   - 询问 cluster health，展示 MCP 不只可以查询业务表，也可以暴露受控的集群信息。

### 完成后的能力

学员能够看清一次最小 MCP 集成：Claude 负责理解问题，本地 MCP Server 提供数据库工具，ClickHouse Cloud 执行实际查询。该教程不包含多用户 Web UI、Agent Builder 或 LLM 运行监控。

---

## [How to integrate the ClickHouse MCP Server with LibreChat](https://learn.clickhouse.com/how-to-integrate-the-clickhouse-mcp-server-with-librechat)

**一句话概述：** 使用 Docker 同时运行 LibreChat 和 ClickHouse MCP Server，使用户可以从自托管 Web 聊天界面查询 ClickHouse Cloud。

### 课程定位

它与 Claude Desktop 教程解决相同的数据库问答问题，但把原生桌面客户端换成可自行部署的 LibreChat，并把 MCP Server 也放进 Docker：

```text
浏览器
  ↓
LibreChat Web UI / API
  ↓ SSE
Docker 中的 mcp/clickhouse
  ↓
ClickHouse Cloud
```

### 内容形式

- **课程首页说明：** 说明 LibreChat 是开源聊天应用，并将通过 Docker 完成从克隆仓库到第一次 ClickHouse 查询的完整配置。
- **Demo 视频：** [LibreChat and the ClickHouse MCP server](https://www.youtube.com/watch?v=fuyu-AnfRDA)，展示 LibreChat 与 ClickHouse MCP Server 的整体工作方式。
- **Hands-on Lab：** 包含创建 Cloud service、启动 LibreChat、访问 Web UI 和自然语言提问四个步骤。
- **Additional Resources：** 提供其他资源和课程调查。

### Hands-on Lab 详细内容

1. **Create a ClickHouse Cloud service**
   - 创建 ClickHouse Cloud 服务和课程所需数据。

2. **Run LibreChat**
   - 克隆 LibreChat 仓库。
   - 从示例文件创建 `.env` 并配置 Anthropic API key。
   - 使用 `docker-compose.override.yml` 增加 `mcp/clickhouse` 服务。
   - 通过环境变量为 MCP 容器配置 ClickHouse Cloud 连接。
   - 从示例文件创建 `librechat.yaml`，使用 SSE endpoint 把 LibreChat 指向本地 MCP 容器。
   - 启用 LibreChat 界面中的 MCP Server 功能并配置允许访问的域名。
   - 使用 Docker Compose 启动全部服务。

3. **Access LibreChat**
   - 从浏览器进入 LibreChat。
   - 注册或登录本地 LibreChat 账户。
   - 选择模型并确认 ClickHouse MCP tools 可用。

4. **Ask some questions!**
   - 先询问当前有哪些数据。
   - 再围绕英国房价表询问低价城镇、最贵或最便宜的房产、城市价格差异和集群健康。
   - 课程问题与 Claude Desktop 版本基本相同，用于突出“聊天客户端可以替换，而 MCP 提供的数据工具保持相似”。

### 完成后的能力

学员能够部署一个类似 ChatGPT 的自托管 Web 应用，让多个用户通过统一界面选择模型、使用 MCP 工具并查询 ClickHouse。与完整 AI Agent 教程相比，本教程不配置 Langfuse，也不强调专用 Agent 的运行监控。

---

## [How to Integrate the ClickStack MCP Server with LibreChat](https://learn.clickhouse.com/how-to-integrate-the-clickstack-mcp-server-with-librechat)

**一句话概述：** 把 LibreChat Agent 连接到 ClickStack MCP Server，使用户可以用自然语言分析日志、Trace 和指标，并创建可观测性 dashboard。

### 课程定位

这门教程的重点不再是通用表查询，而是 AI 辅助故障排查：

```text
日志、Trace、指标和 Session Replay
              ↓
ClickStack / ClickHouse Cloud
              ↑
ClickStack MCP Server
              ↑
LibreChat 中的 ClickStack Agent
```

### 内容形式

- **Tutorial Overview：** 说明课程将连接并使用 ClickStack MCP Server 与 LibreChat。
- **图文 Tutorial：** 课程主体是 6 个带截图、命令和操作说明的页面。
- **实验数据：** 使用 ClickStack OTel Collector 和课程样例生成日志、Trace、指标和前端 session 数据。
- **视频：** 当前教程目录中没有单独列出的 Demo 视频，重点是逐步完成故障排查和 Agent 配置。

### Tutorial 详细内容

1. **Create a ClickHouse Cloud service**
   - 创建 ClickHouse Cloud service。
   - 启动 ClickStack 和 ClickStack OTel Collector。
   - 下载并通过 OpenTelemetry HTTP endpoint 写入课程样例数据。

2. **Explore ClickStack**
   - 在 ClickStack Search 中确认日志已经写入。
   - 使用 Client Sessions 和 session replay 重现用户无法完成付款的问题。
   - 从浏览器请求中的 HTTP 500 错误进入 Trace。
   - 沿 Trace 找到 checkout service 和 payment service。
   - 结合日志确认 Visa 支付相关 cache 出现问题。
   - 在 Chart Explorer 中使用指标验证 cache size 上升与错误出现之间的关系。
   - 这一步先让学员手工走完一次调查流程，为后续对比 AI Agent 的简化效果建立基线。

3. **Run LibreChat**
   - 在 ClickHouse Cloud 中启用 MCP。
   - 克隆 LibreChat 并配置 Anthropic API key。
   - 在 `librechat.yaml` 中配置 ClickStack Cloud MCP endpoint，并通过 service ID 限定目标服务。
   - 挂载配置文件并通过 Docker Compose 启动 LibreChat。

4. **Connect LibreChat to the ClickStack MCP Server**
   - 登录 LibreChat。
   - 连接 ClickStack MCP Server。
   - 完成 Cloud MCP endpoint 所需的认证流程。

5. **Create a ClickStack agent**
   - 在 Agent Builder 中创建专用 ClickStack Agent。
   - 选择模型。
   - 为 Agent 添加 ClickStack MCP tools。

6. **Use the ClickStack Agent**
   - 直接询问“为什么客户无法完成订单”。
   - 让 Agent 使用 ClickStack 数据完成与前面手工调查相同的问题定位。
   - 进一步要求 Agent 创建可视化 dashboard，并在 ClickStack 中查看结果。

### 完成后的能力

学员能够比较手工可观测性调查与 AI Agent 调查：前者逐步查看 session、Trace、日志和指标，后者通过自然语言调用 ClickStack MCP tools 完成调查和 dashboard 创建。它展示的是可观测性 Agent，而不是普通 SQL 问答 Agent。

---

## 二、四门教程的主要差异

| 教程 | 用户界面 | MCP Server 位置 | 目标系统 | LLM | Langfuse | 最终结果 |
|---|---|---|---|---|---|---|
| Deploying an AI Agent and Langfuse with ClickHouse Cloud Tutorial | LibreChat Web UI | ClickHouse Cloud 托管 endpoint | ClickHouse Cloud 数据 | 学员接入 Anthropic 等模型 | 有 | 可查询 ClickHouse 且可观测的 AI Agent |
| How to integrate the ClickHouse MCP Server with Claude Desktop | Claude Desktop | 本地 Python 进程，由 `uv` 启动 | ClickHouse Cloud 数据和集群信息 | Claude Desktop 使用的模型 | 无 | 最小 Desktop MCP 数据助手 |
| How to integrate the ClickHouse MCP Server with LibreChat | LibreChat Web UI | 本地 Docker MCP 容器 | ClickHouse Cloud 数据和集群信息 | 学员接入 Anthropic 等模型 | 无 | 自托管 Web 数据助手 |
| How to Integrate the ClickStack MCP Server with LibreChat | LibreChat Web UI | ClickHouse Cloud 托管 ClickStack endpoint | 日志、Trace、指标和 dashboard | 学员接入 Anthropic 等模型 | 无 | ClickStack 故障排查 Agent |

## 三、不同课程之间重复的内容

### 1. ClickHouse Cloud 和样例环境

- Claude Desktop 与 ClickHouse MCP 教程、LibreChat 与 ClickHouse MCP 教程都会创建 ClickHouse Cloud service。
- 完整 AI Agent 教程假设已经存在带英国房价样例数据的 ClickHouse Cloud service。
- ClickStack 教程也创建 Cloud service，但写入的是可观测性样例数据，而不是英国房价数据。

### 2. MCP 的基本解释

四门课都在重复同一个核心概念：大语言模型不直接连接数据库或可观测性系统，而是通过 MCP Server 暴露的工具完成操作。区别在于客户端、传输方式和 MCP 提供的工具集合。

### 3. LibreChat 的安装和模型配置

以下三门课都需要克隆 LibreChat、创建 `.env`、配置模型 API key、创建或挂载 `librechat.yaml`，然后使用 Docker Compose 启动 Web 应用：

- Deploying an AI Agent and Langfuse with ClickHouse Cloud Tutorial；
- How to integrate the ClickHouse MCP Server with LibreChat；
- How to Integrate the ClickStack MCP Server with LibreChat。

重复的原因是三门课都把 LibreChat 当作 Agent 和 MCP 的用户界面。不同点是它们连接的 MCP endpoint 不同。

### 4. 英国房价自然语言分析

前三门 ClickHouse 数据 Agent 教程大量复用英国房价数据以及相似问题：

- 查看当前有哪些数据；
- 查找房价较低的城镇；
- 查找最高或最低房价；
- 比较城市价格；
- 查看 cluster health。

这些问题的主要作用不是教授新的 SQL，而是证明不同 AI client 都可以通过 MCP 使用同一类 ClickHouse 工具。

### 5. Agent Builder

- 完整 AI Agent + Langfuse 教程使用 Agent Builder 创建专用 ClickHouse Agent。
- ClickStack MCP 教程使用 Agent Builder 创建专用 ClickStack Agent。
- Claude Desktop 教程直接在桌面客户端配置 MCP，不使用 LibreChat Agent Builder。
- 基础 LibreChat + ClickHouse MCP 教程更偏向验证 Web chat 与 MCP 连接，不把 Langfuse 或运行监控作为重点。

### 6. 课程完成后的验证

- 数据 Agent 教程通过自然语言问题和实际 ClickHouse 查询结果验证 MCP 可用。
- ClickStack 教程通过故障原因和 dashboard 验证 MCP 可用。
- Langfuse 教程额外要求在 Tracing 页面看到 `AgentRun`，并观察成本、延迟和使用量。

## 四、内容重叠关系

```text
How to integrate the ClickHouse MCP Server with Claude Desktop
└── 最小客户端 + 本地 MCP Server

How to integrate the ClickHouse MCP Server with LibreChat
└── 把客户端换成自托管 Web UI，并用 Docker 运行 MCP Server

Deploying an AI Agent and Langfuse with ClickHouse Cloud Tutorial
└── 在 LibreChat 路径上增加专用 Agent、Cloud MCP endpoint 和 Langfuse 监控

How to Integrate the ClickStack MCP Server with LibreChat
└── 复用 LibreChat/Agent/MCP 结构，但把业务数据分析换成可观测性故障排查
```

从课程设计角度看，前三门课在 ClickHouse Cloud、MCP、英国房价样例和自然语言提问方面重复较多，主要通过更换客户端、MCP 部署位置和是否加入 Langfuse 来区分。第四门课虽然复用了 LibreChat 的安装流程，但数据、任务和最终产物不同，独立性更强。

## 五、对 Doris AI 方向的初步启示

ClickHouse 当前没有把 AI Agent 作为第四条大型主课程，而是把它作为跨产品集成教程。Doris 可以采用相似结构：

- 核心数据库知识仍由实时分析、数据仓库和可观测性课程负责；
- AI 目录重点展示 Doris MCP、不同 AI client、Agent 权限与执行证据；
- 将通用的 LibreChat/模型配置抽成一次共享环境准备，避免每门教程重复安装；
- 分别保留“业务数据分析 Agent”“Query Profile 分析 Agent”“可观测性故障排查 Agent”和“LLM 运行观测”这类结果不同的实验；
- 数据库账号默认采用只读和最小权限，明确区分模型推理、MCP 工具调用与 Doris 实际执行三层职责。
