# Module 2 课程大纲：使用 Apache Doris AI Functions 调用大模型

> 文档状态：课程设计稿
>
> 文件用途：本文是开发大纲；面向学习者的正式课程将位于同目录下的 `course.md`
>
> 课程形态：Markdown Course + Jupyter Lab + Quiz
>
> Course 接入范围：云 API Key 路径 + 本地 Ollama 路径
>
> Lab 固定路径：Ollama + `qwen2.5:1.5b-instruct`，发布时记录实际模型 digest
>
> Doris 基线：复用本机已有的 `apache/doris:all-in-one-4.1.3` 单 FE、单 BE Docker
> 实验边界：现有 `doris` 容器 + 宿主机 Ollama + 小批量合成客服工单

## 1. 课程结论

本 Module 恢复此前课程的 `course.md + Jupyter Lab + Quiz` 结构。

`course.md` 同时解释两类接入方式：使用 API Key 的云模型服务，以及不需要 API Key 的本地 Ollama。两条路径最终都抽象为 Doris AI Resource，后续 AI Function SQL 基本一致。

Lab 只选择本地 Ollama 作为唯一执行路径。这样学习者不需要购买额度或粘贴密钥，也能在 Notebook 中重复运行 SQL、检查返回值并物化结果。Quiz 同时考查 Course 中的云端与本地概念，但不要求联网或真实调用云 API。

```text
04-ai-integrations/
  doris_course/
    ai_functions.py
  level1/
    module02-doris-ai-functions/
      readme.md
      course.md
      lab02_doris_ai_functions.ipynb
      quiz02_doris_ai_functions.ipynb
      quiz02_doris_ai_functions.yaml
      data/
        ai_support_tickets.csv
```

| 文件 | 面向对象 | 负责内容 | 不负责内容 |
|---|---|---|---|
| `readme.md` | 课程开发者 | 模型选型、教学结构、PoC 与验收标准、版本冻结 | 不作为学习者操作手册 |
| `course.md` | 学习者 | AI Function 原理、云 API Key 与本地 Ollama 两种接入、Resource、函数选择、结果验证与生产边界 | 不要求学习者拥有付费云账号，不堆积大段运行结果 |
| `doris_course/ai_functions.py` | Lab 运行时 | 封装 Doris/Ollama 预检、数据加载、Resource 校验和结果物化 | 不与 Notebook 同目录，不保存密钥或模型权重 |
| `lab02_doris_ai_functions.ipynb` | 学习者 | 使用本地 Ollama 完成环境预检、创建 Resource、执行代表性 SQL、验证与物化结果、清理 | 不调用云 API，不读取 API Key，不自动安装 Ollama 或下载模型 |
| `quiz02_doris_ai_functions.ipynb` / `.yaml` | 学习者 | 检查云端/本地 Resource 差异、BE 网络、函数选择、结果验证、成本与安全边界 | 不执行 SQL，不依赖 Lab 状态或外部服务 |
| `data/ai_support_tickets.csv` | Lab | 受控、合成、可评估的中英文文本 | 不包含真实客户数据或个人信息 |

Course 保留 API Key 调用方式的完整说明，以 DeepSeek Chat Completions 为示例；但云端示例是讲解路径和可选扩展，不是完成课程的前提。Lab 和 Quiz 不需要 API Key、云账户或互联网推理费用。Lab 的互联网需求只发生在课前安装 Ollama 和执行标准模型下载命令时，模型下载完成后推理链路完全在本机运行。

## 2. 模型与运行时选型

### 2.1 Course 与 Lab 的选型

| 项目 | Course 云端讲解路径 | Lab 固定执行路径 |
|---|---|---|
| 服务/运行时 | DeepSeek API | Ollama |
| 模型 | `deepseek-chat`，以发布时官方名称为准 | `qwen2.5:1.5b-instruct` |
| Doris provider | `deepseek` | `local` |
| 身份凭证 | `ai.api_key`，只使用占位符讲解 | 不需要 API Key |
| API 协议 | Chat Completions | OpenAI-compatible Chat Completions |
| endpoint | `https://api.deepseek.com/chat/completions` | `http://host.docker.internal:<OLLAMA_PORT>/v1/chat/completions`，默认端口 `11434` |
| 成本与网络 | 需要外网、账号、额度，可能限流 | 首次下载需联网，推理使用本机资源 |
| 实际执行 | 可选，不进入 Lab 验收 | Course smoke test + Lab 全部练习 |
| 建议生成参数 | `temperature=0`、`ai.max_token=256`、`max_retries=1` | 同左 |

### 2.2 为什么选择 `qwen2.5:1.5b-instruct`

本课需要的不是开放式知识问答，而是标签选择、情感判断、字段抽取、短摘要、翻译和小规模跨行归纳。模型需要满足：

1. 中英文指令和文本都能处理；
2. 能遵循短输出、有限标签和字段名约束；
3. 在普通教学电脑上能与现有单节点 Doris Docker 同时运行；
4. 不默认输出长推理过程，避免污染函数需要解析的短结果；
5. 模型足够小，首次下载和课堂启动时间可控。

`qwen2.5:1.5b-instruct` 的 Ollama Q4_K_M 版本约 986 MB，具备中英文能力，并针对 instruction following、结构化数据理解和结构化输出做过优化。它不是本地小模型中质量最高的选择，但更符合“先完整展示 Doris AI Function，而不是展示模型规模”的课程目标。

Lab 不选以下方案作为默认值：

| 方案 | 不作为默认值的原因 |
|---|---|
| 0.5B 模型 | 更小，但分类边界、结构化抽取和 `AI_AGG` 的稳定性不足 |
| `qwen3:1.7b` | 体积约 1.4 GB，且默认支持 thinking；对严格短返回并不比非 thinking 模型更省事 |
| `qwen3:4b-instruct` | 质量更稳，但约 2.5 GB；作为 1.5B 模型 PoC 失败时的备用方案 |
| 7B/8B 及以上模型 | 质量更高，但下载、内存和推理时间会明显提高课程门槛 |
| DeepSeek 云 API | Course 用它说明 API Key 接入；Lab 为保证零付费、可重复和无密钥泄漏风险而不实际调用 |
| embedding 专用模型 | 不能完成生成式 `AI_*` 任务；留给后续 Vector/Hybrid Search Module |

如果发布 PoC 证明 1.5B 模型无法让某个函数返回可解析类型，先把该样本改为更短、更明确、更适合教学验证的输入；仍失败时才把备用模型升级为 `qwen3:4b-instruct`。模型发生语义误判可以作为课程案例，但返回类型或协议不兼容不能降低验收标准。

### 2.3 硬件基线

- Apple Silicon 或支持 Ollama 的 x86-64 电脑；
- 8 GB 内存是尝试运行的下限，12 GB 及以上更适合同时运行 Doris Docker、Notebook 和约 1 GB 的量化模型；
- 至少预留 3 GB 磁盘空间给模型、运行时和临时文件；
- GPU 不是功能前提，但纯 CPU 推理会更慢；
- 如果 Doris 容器已经占用大量内存，应先停止其他无关容器，而不是继续缩小模型并牺牲函数输出质量。

硬件数字是课程经验基线，不写成 Ollama 或模型的官方最低要求。发布前应在课程目标硬件上记录首 token 延迟、完整函数耗时和峰值内存。

## 3. Doris AI Function 的统一调用模型

### 3.1 调用链

无论模型位于云端还是本机，都不会加载到 Doris FE 或 BE 进程里。Doris 通过 AI Resource 保存 provider、endpoint、model 和可选凭证，由 BE 发出 HTTP 请求：

```text
SQL Client / Jupyter Notebook
  -> 通过 MySQL Protocol 向 Doris FE 提交 SQL
    -> FE 解析 AI Function 和 AI Resource
      -> Doris BE 读取文本并组成请求
        -> HTTPS 调用云模型 API，或 HTTP 调用宿主机 Ollama
          -> deepseek-chat 云端推理，或 qwen2.5:1.5b-instruct 本地推理
        <- OpenAI-compatible JSON 响应
      <- BE 提取并转换函数结果
  <- 客户端得到 STRING / BOOLEAN / 数值结果
```

两条路径的差异主要发生在 Resource 配置、网络、凭证、成本和数据边界；AI Function 的 SQL 用法不随 provider 改变。Lab 所说的“本地”表示请求不离开学习者电脑，不表示模型在 Doris 进程内执行。

### 3.2 为什么需要 OpenAI-compatible endpoint

Doris 不直接读取模型文件，也不理解 GGUF 或量化权重。它只需要一个能够构造请求并解析响应的 HTTP endpoint。DeepSeek 提供云端 Chat Completions API，Ollama 提供兼容的本地 `POST /v1/chat/completions` 接口。

| 组件 | 责任 |
|---|---|
| Doris AI Function | 为分类、摘要、抽取等任务构造任务提示并定义 SQL 返回类型 |
| Doris AI Resource | 保存 provider、endpoint、model、生成参数和云端路径所需的 API Key |
| DeepSeek API | 接收带身份凭证的公网请求并执行云端推理 |
| Ollama | 接收兼容请求、加载模型、执行推理、返回兼容 JSON |
| `qwen2.5:1.5b-instruct` | 根据 prompt 生成实际文本 |

### 3.3 Docker 网络是接入重点

课程环境中 Doris BE 在 Docker 容器内，而 Ollama 运行在宿主机。容器里的 `127.0.0.1` 指向 BE 容器自身，不是宿主机：

```text
错误：BE -> http://127.0.0.1:11434
              这里是 BE 容器，不是宿主机 Ollama

正确：BE -> http://host.docker.internal:11434
                         Docker Desktop 宿主机入口
```

课程必须从 BE 所在容器验证可达性。Lab 在初始化单元集中设置 `OLLAMA_PORT = 11434`；如果本机 Ollama 使用其他宿主机端口，学习者只修改这个参数。宿主机执行 `curl localhost:<OLLAMA_PORT>` 成功，只证明宿主机能访问 Ollama，不能证明 BE 能访问。

Linux 原生 Docker 没有统一保证 `host.docker.internal`。Course 需给出 Linux 分支：在 compose 中配置 `extra_hosts: ["host.docker.internal:host-gateway"]`，或把 Ollama 放入同一 Docker network 并使用服务名；Lab 主路径仍以课程当前的 Docker Desktop 环境为准。

### 3.4 本地 Ollama AI Resource 模板

```sql
CREATE RESOURCE "ollama_qwen25_1_5b"
PROPERTIES (
  "type" = "ai",
  "ai.provider_type" = "local",
  "ai.endpoint" = "http://host.docker.internal:11434/v1/chat/completions",
  "ai.model_name" = "qwen2.5:1.5b-instruct",
  "ai.temperature" = "0",
  "ai.max_token" = "256",
  "ai.max_retries" = "1",
  "ai.retry_delay_second" = "1"
);
```

- `provider_type=local` 表示自托管 endpoint；不需要 `ai.api_key`；
- endpoint 必须指向完整的 Chat Completions 路径；
- model name 必须与 `ollama list` 中的名称一致；
- `temperature=0` 降低随机性，但不保证完全确定；
- `ai.max_token` 控制单次输出上限，不限制输入长度或整条 SQL 的总推理量；
- `max_retries=1` 防止课堂错误配置造成重复等待；
- Doris 对 `local` provider 跳过创建时有效性探测，因此 `CREATE RESOURCE` 成功不等于模型可用，必须再执行一次 `AI_GENERATE` smoke test。

### 3.5 云端 DeepSeek AI Resource 模板

Course 使用下面的模板说明 API Key 接入，但不要求学习者执行。文档和截图中只能出现占位符，不能出现真实密钥：

```sql
CREATE RESOURCE "deepseek_chat"
PROPERTIES (
  "type" = "ai",
  "ai.provider_type" = "deepseek",
  "ai.endpoint" = "https://api.deepseek.com/chat/completions",
  "ai.model_name" = "deepseek-chat",
  "ai.api_key" = "<YOUR_DEEPSEEK_API_KEY>",
  "ai.temperature" = "0",
  "ai.max_token" = "256",
  "ai.max_retries" = "1",
  "ai.retry_delay_second" = "1"
);
```

Course 必须解释完整接入过程：在模型服务商控制台创建最小权限或教学专用 Key；只在受控管理员会话中创建 Resource；立即清除剪贴板和临时命令；用 `SHOW RESOURCES` 检查非敏感属性；执行一条受限 smoke test；完成后轮换或撤销教学 Key。不要把 Key 写进 Git、Notebook、截图、Shell history、课程数据或错误日志。

云端 Resource 是数据库对象，能够使用它的用户会间接消耗云端额度并可能发送数据，因此生产环境必须限制 `USAGE_PRIV`、审计调用、设置预算和速率限制。Course 不承诺 DeepSeek 是唯一云 provider；它只是本课用于解释 API Key 路径的具体示例。

## 4. Module 定位、学习目标和前置条件

拟定标题：**Module 2: Connect Apache Doris AI Functions to LLMs**。

建议时长：105–125 分钟，其中 Course 50–60 分钟，Lab 环境准备 15–25 分钟，Lab 30 分钟，Quiz 10 分钟。

完成课程后，学习者能够：

1. 解释 AI Function、AI Resource、云模型 API 与本地模型之间的调用关系；
2. 比较 API Key 云端 Resource 与无密钥本地 Resource 的配置、网络、成本和数据边界；
3. 说明如何安全创建、使用、撤销云端 API Key，以及为什么密钥不能出现在课程文件和 Notebook 中；
4. 在宿主机启动 Ollama 并固定 `qwen2.5:1.5b-instruct`；
5. 验证 Doris BE 容器到 Ollama 的网络路径，并用 `provider_type=local` 创建 Resource；
6. 根据结果形状选择合适的 AI Function；
7. 对分类、抽取、摘要和聚合结果做结构与质量验证；
8. 说明云端模型有外发、额度与限流，本地模型有资源竞争与运维成本，两者都有延迟和非确定性；
9. 将可复用 AI 结果写入派生表，而不是在每次查询中重新推理。

前置条件：

- 完成 Level 1 / Module 1，已有可运行的单 FE、单 BE Doris Docker；
- 能在 Notebook 中执行 SQL，理解 `SELECT`、`WHERE`、`LIMIT`、`INSERT ... SELECT`、`GROUP BY`；
- Lab 学习者可在宿主机安装 Ollama 并通过标准 `ollama pull qwen2.5:1.5b-instruct` 下载约 986 MB 模型；
- 已按前置课程启动本机 `doris` 容器，拓扑为单 FE、单 BE；
- 使用课程现有的 `apache/doris:all-in-one-4.1.3`，不为本 Module 另建 Doris 集群；
- 学习者理解本课输出不是事实保证，不能直接驱动安全、权限、支付等高风险动作；
- 不要求 DeepSeek 账号或 API Key；希望自行尝试 Course 云端路径的学习者自行承担服务费用并使用临时教学 Key。

本课不依赖 MCP Module。两者只在开头用一张对照表区分：

| 能力 | 调用方向 |
|---|---|
| Doris MCP Server | Agent 调用 Doris 工具 |
| Doris AI Function | Doris SQL 调用大模型 |

### 4.1 固定复用的本机 Doris 环境

本 Module 不创建第二套 Doris，也不使用 Module 9 的多节点集群。Course 和 Lab 固定连接前置课程留下的本机单节点环境：

| 项目 | 固定值 |
|---|---|
| Docker 容器 | `doris` |
| 镜像基线 | `apache/doris:all-in-one-4.1.3` |
| 拓扑 | 1 FE + 1 BE |
| FE MySQL Protocol | `127.0.0.1:9030` |
| FE HTTP | `127.0.0.1:8030` |
| BE Web Server | `127.0.0.1:8040` |
| Database | `doris_course` |

Lab 初始化时必须用 `SHOW FRONTENDS`、`SHOW BACKENDS` 和版本元数据确认只有一个存活 FE、一个存活 BE，且构建符合课程 4.1.3 基线。`SELECT VERSION()` 返回的是 MySQL 兼容版本字符串，不能单独用来判断 Doris 构建。

如果当前运行的是 Module 9 多节点环境，学习者先按 Lab 9 的停止步骤关闭它，再按 Level 1 / Module 1 的 restart 步骤启动现有 `doris` 容器。课程不复制数据、不创建新 Docker volume，也不升级镜像。

## 5. 贯穿场景与数据设计

继续使用前置课程的 `doris_course` Database，但不使用 `events` 作为文本输入。Lab 创建两张小表：

```text
doris_course.ai_support_tickets
  ticket_id, created_at, language, raw_text
  expected_topic, expected_sentiment

doris_course.ai_ticket_enrichment
  ticket_id, topic, sentiment, summary
  model_name, model_digest, prompt_version
  processed_at, run_id
```

数据集使用 12–16 条合成客服工单，覆盖：

- 退款、物流、质量、账号和产品咨询五类主题；
- 中英文文本；
- 正面、负面、中性和 mixed 情感；
- 两条反讽或复合情绪样本；
- 一条缺少待抽取字段的样本；
- 可供 `AI_AGG` 分组的重复主题；
- 虚构姓名、邮箱和订单号，用于讲解 `AI_MASK` 的局限，不包含真实 PII。

不用 `events` 表的原因：它是结构化电商行为数据，没有自然语言文本。直接对上千万行调用任何模型都会产生不可控的延迟与成本，也不能体现 AI Function 的正确使用场景。

```text
安装并启动本地模型
  -> 从 BE 验证 endpoint
    -> 创建 local AI Resource
      -> 一行 AI_GENERATE smoke test
        -> 小批量分类和情感判断
          -> 验证标签与误差
            -> 摘要和字段抽取
              -> 物化结果
                -> 小 group 的 AI_AGG
                  -> 清理 Resource 与实验表
```

## 6. 函数覆盖范围

| 结果形状 | 函数 | Course 重点 | Lab |
|---|---|---|---|
| 有限标签 | `AI_CLASSIFY`、`AI_SENTIMENT` | 标签集合、领域误差、返回值校验 | 主练习 |
| 结构化事实 | `AI_EXTRACT` | 输出格式、缺失值、字段验证 | 小练习 |
| 布尔判断/分数 | `AI_FILTER`、`AI_SIMILARITY` | 不能直接替代安全策略或精确阈值 | 只讲或可选 |
| 单行文本变换 | `AI_SUMMARIZE`、`AI_TRANSLATE`、`AI_FIXGRAMMAR`、`AI_MASK` | 保留 raw，mask 不是合规 DLP | summary 主练习，其余只讲 |
| 自由生成 | `AI_GENERATE` | prompt 边界和不可验证性 | 仅 smoke test |
| 跨行归纳 | `AI_AGG` | group 输入规模、token 膨胀、遗漏 | 最后一个小练习 |

`EMBED()` 不进入本 Module。它需要 embedding 模型，并属于下一门 Vector/Hybrid Search 课程。

## 7. `course.md` 详细大纲

### 7.1 开场：SQL 为什么会需要模型

- 展示三条仅靠关键词难以稳定分类的客服工单；
- 先让学习者判断普通 SQL 是否足够，再引出 AI Function；
- 明确 AI Function 是同步 HTTP 推理，不是 Doris 内部的确定性字符串函数；
- 给出本课结果：理解云端与本地两种接入、用本地模型完成代表性函数实验、验证并物化结果。

### 7.2 AI Function、MCP、UDF 和应用服务的边界

- AI Function：数据留在 SQL 流程中，模型以函数形式被调用；
- MCP：Agent 决定何时调用 Doris；
- UDF：扩展计算逻辑，不等同于调用 LLM；
- 应用服务：更适合异步队列、流式输出、复杂重试和高并发模型编排；
- 小批量离线 enrichment 适合 AI Function，交互式高并发生成不适合。

### 7.3 认识 provider-neutral 调用链

- 使用第 3 节架构图；
- 解释 FE 解析、BE 调用外部 endpoint 和 SQL typed result；
- 强调云模型和本地模型都不在 Doris 进程里；
- 先讲相同部分：AI Function SQL、Resource 选择、同步 HTTP、非确定性返回；
- 再讲差异：API Key、网络边界、数据外发、按量费用、本地算力和服务运维。

### 7.4 使用 API Key 连接云模型

以 DeepSeek 为例完整说明但不放入 Lab：

1. 在服务商控制台创建教学专用 Key，并设置预算、限流或告警；
2. 确认 provider、endpoint 和 model name 来自同一版本的官方文档；
3. 使用第 3.5 节模板创建 Resource，示例中始终使用 `<YOUR_DEEPSEEK_API_KEY>`；
4. 说明真实执行时必须在受控管理员会话中替换占位符，不能把替换后的 SQL 保存到仓库或 Notebook；
5. 用 `SHOW RESOURCES` 核对 provider、endpoint 和 model，不在课程输出中回显密钥；
6. 使用一条短 prompt 和很小的输出上限完成 smoke test；
7. 完成教学验证后删除 Resource，并轮换或撤销临时 Key；
8. 说明模型输入会离开 Doris 所在环境，必须先完成数据分类、合规和供应商审查。

Course 同时给出概念性生产方案：由管理员或部署系统注入 secret、限制 Resource 权限并审计额度；不把“在 SQL 文本里粘贴长期 Key”描述为生产最佳实践。

### 7.5 安装 Ollama 和下载 Lab 模型

Course 给出 macOS 主路径，并为 Windows/Linux 提供官方链接，不在 Notebook 中自动安装：

1. 从 Ollama 官方渠道安装；
2. 确认服务运行：`ollama --version`；
3. 下载固定模型：`ollama pull qwen2.5:1.5b-instruct`；
4. 用 `ollama list` 确认模型名；
5. 用 `ollama show qwen2.5:1.5b-instruct` 记录模型元数据；
6. 使用一条很短的 `ollama run` 或 `/v1/chat/completions` 请求完成宿主机 smoke test；
7. 解释 Ollama 服务与一次交互式推理命令的区别。

默认下载路径只写 Ollama 官方命令。下载失败时提示学习者检查本机网络环境并查阅 Ollama 官方故障排查，不把个别环境的修复过程写进 Course 或 Lab 主链。

若修改 `OLLAMA_HOST`，必须说明监听 `0.0.0.0` 可能向局域网暴露无鉴权接口。课程优先依赖 Docker Desktop 的宿主机转发并从 BE 实测；确需扩大监听范围时，应限制防火墙并在课后恢复。

### 7.6 从 Doris BE 验证 Ollama

1. 宿主机 `/api/tags` 可访问；
2. 宿主机 `/v1/chat/completions` 能调用指定模型；
3. BE 容器可解析 `host.docker.internal`；
4. BE 容器能访问 `/api/tags`；
5. BE 容器能对 `/v1/chat/completions` 发起一次短请求；
6. 记录实际 endpoint，之后再创建 Resource。

若 BE 镜像没有 `curl`，Course 提供不修改容器镜像的替代检查方法，例如使用容器内已有 Python/BusyBox，或从同一 Docker network 的临时诊断容器发请求。Lab 只报告连通性，不自动改 Docker 网络。

### 7.7 创建并理解 AI Resource

- 并排展示第 3.4、3.5 节模板，逐项解释共同属性和 provider-specific 属性；
- 对比 `local` 和 `deepseek` 的 key、endpoint、网络、计费与数据边界；
- 说明 `SHOW RESOURCES` 展示的是连接配置，不是模型或业务数据；
- 解释 `SET default_ai_resource='ollama_qwen25_1_5b'` 的 session 范围；
- 说明 `local` Resource 创建成功后仍必须执行真实函数验证；
- 生产环境中 Resource 创建与 `USAGE_PRIV` 应由管理员控制，Lab 为本地教学简化权限。

### 7.8 用 `AI_GENERATE` 做最小 smoke test

发送一个可验证的短指令，例如“只返回 `LOCAL_OK`”。检查 SQL 成功、返回非空、不包含 thinking 标签或额外解释。解释第一次调用可能因为模型冷启动明显更慢。这一步只证明链路可用，不证明模型适合所有任务。

### 7.9 按结果形状介绍全部函数

对第 6 节每一类说明输入参数、SQL 返回类型、模型任务、可自动验证项、人工评估项、适用和不适用场景。重点提醒：

- `AI_CLASSIFY` 返回值必须再次检查是否属于候选标签；
- `AI_SENTIMENT` 的固定标签不一定符合每个业务领域；
- `AI_EXTRACT` 返回模型生成的字符串，不能假定天然满足数据库结构约束；
- `AI_FILTER` 和 `AI_SIMILARITY` 是模型判断，不是安全策略或数学真值；
- `AI_MASK` 可能漏识别，不是合规 DLP；
- `AI_AGG` 是跨行归纳，不等于无损的 `GROUP_CONCAT`。

### 7.10 先限制输入，再调用模型

- 先执行纯 SQL candidate query 和 `COUNT(*)`；
- 再 `ORDER BY ticket_id LIMIT n`；
- 限制文本长度与每个 group 的行数；
- 同一个 `SELECT` 中的多个 AI Function 代表多个模型任务；
- 云端调用消耗额度并受限流影响；本地调用消耗 CPU/GPU、内存和时间；
- 不允许在 dashboard 刷新路径或上千万行事实表上直接执行。

### 7.11 验证模型结果

1. 结构验证：非空、类型正确、标签属于允许集合；
2. 小样本任务验证：与 `expected_topic`、`expected_sentiment` 比较并列出 mismatch；
3. 业务验证：人工抽样，高风险动作继续使用确定性规则或审批。

不要把十几条样本的一致率称为模型准确率，也不要自动把模型与教学标签不一致视为模型错误。

### 7.12 物化结果而不是重复推理

- 将 enrichment 写入派生表，不覆盖 `raw_text`；
- 保存 `model_name`、模型 digest、`prompt_version`、`run_id` 和时间；
- 用 anti-join 或唯一键避免无意重跑；
- dashboard 只查询物化列并执行普通 `GROUP BY`；
- 模型升级时生成新版本，不静默覆盖历史结果。

### 7.13 排障和生产边界

```text
Ollama 未启动
  -> 宿主机端口不可达
模型未下载或名称错误
  -> Ollama 返回 model not found
云端返回 401 / 403
  -> API Key 无效、已撤销或权限不足
云端返回 429
  -> 额度、速率限制或并发限制
宿主机成功、BE 失败
  -> Docker DNS / host gateway / Ollama 监听地址
Resource 成功、函数失败
  -> local provider 跳过有效性检查，检查 endpoint 与响应格式
调用超时
  -> 冷启动 / 模型过大 / query_timeout 太短 / 机器资源竞争
SQL 成功但输出不合规
  -> 模型能力 / 输入歧义 / 返回格式 / 任务本身不可验证
```

云模型降低本地运维门槛，但引入数据外发、密钥、额度、供应商和网络依赖；本地模型降低数据外发和按量费用，但引入本机资源竞争与模型服务运维。两条路径都需要权限控制、日志治理、升级策略和可观测性。Ollama 默认本地开发服务不能直接等同于生产推理平台。

## 8. Jupyter Lab 逐节设计

Notebook 标题：**Lab: Run Doris AI Functions with a Local Qwen Model**。

Lab 只使用 `ollama_qwen25_1_5b`，不提供云 provider 切换参数，也不读取环境变量中的 API Key。Course 的 DeepSeek 模板用于理解和课后自选扩展，不能成为 Notebook 隐含依赖。

### Initialize the Lab

- 连接现有 Doris sandbox；
- 显示 `SELECT VERSION()` 作为协议信息，并从 `SHOW FRONTENDS`、`SHOW BACKENDS` 读取真实 Doris 构建；
- 检查现有 `doris` 容器中恰好有一个 healthy FE、一个 healthy BE，以及 `doris_course`；
- 构建不符合课程固定的 4.1.3 环境时停止，不在 Notebook 内升级或另建集群；
- 设置有限 `query_timeout`；
- 显示固定模型、由 `OLLAMA_PORT` 派生的 endpoint 与实验最大行数；
- 不自动安装 Ollama，不自动执行模型下载；课前准备只要求学习者在终端运行标准命令 `ollama pull qwen2.5:1.5b-instruct`。

### 1. Verify Ollama from the host and Doris BE

- 宿主机读取 `/api/tags`，确认 `qwen2.5:1.5b-instruct`；
- 从 BE 路径检查 `host.docker.internal:<OLLAMA_PORT>`；
- 发一条直接 Chat Completions 请求并只显示返回文本和耗时；
- preflight 失败时停止，不继续创建 Resource。

如果模型不存在，Notebook 只提示运行标准 `ollama pull` 命令并停止，不实现环境特定的下载修复；模型分发和网络排障不是 AI Function 学习目标。

### 2. Create a bounded support-ticket dataset

- 创建两张 module-owned 表；
- 导入 12–16 条合成文本；
- 展示 topic、language、文本长度分布；
- 后续主练习只处理固定的 6–8 行。

### 3. Register a local AI Resource

- 检查是否存在同名 Resource；
- 只允许删除本 Lab 创建且属性匹配的旧 Resource；
- 创建 `ollama_qwen25_1_5b`；
- 检查 provider、endpoint 和 model；
- 设置 `default_ai_resource`。

### 4. Run one `AI_GENERATE` smoke test

- 显式指定 Resource 调用一次；
- 解释 session default 的等价写法，避免第二次无意义生成；
- 记录首次调用耗时并解释冷启动；
- 只检查非空和目标标记，不断言完整字符串完全一致。

### 5. Classify tickets and validate labels

- 先显示 candidate IDs；
- 使用 `AI_CLASSIFY(raw_text, ['refund','shipping','quality','account','product_question'])`；
- 验证结果属于候选集合；
- 与 `expected_topic` 比较；
- 单独展示 NULL、unexpected label 和 mismatch。

这是 Lab 的第一主练习。

### 6. Analyze sentiment

- 对同一受控批次执行 `AI_SENTIMENT`；
- 检查结果集合；
- 重点展示 mixed 和反讽样本；
- 讨论为什么结果不能直接触发退款、封禁或升级告警。

这是 Lab 的第二主练习。

### 7. Extract fields and summarize text

- 对含订单号、产品名、诉求的文本运行 `AI_EXTRACT`；
- 对故意缺少某字段的文本观察缺失值表达；
- 保留原始返回字符串，验证字段名和必要值，不假定结果天然是 JSON；
- 对一条较长工单运行 `AI_SUMMARIZE`；
- 检查摘要非空、长度上限以及是否遗漏关键诉求。

`AI_EXTRACT` 是小练习，`AI_SUMMARIZE` 是第三个主练习。

### 8. Optional function gallery

使用折叠/可选 cell 展示：

- `AI_FILTER`：判断一条文本是否需要人工复核；
- `AI_SIMILARITY`：比较两条工单语义相似度；
- `AI_TRANSLATE`：中英文转换；
- `AI_FIXGRAMMAR`：修正一条英文工单；
- `AI_MASK`：遮蔽虚构邮箱和订单号，同时说明漏识别风险。

默认不要求全部运行，避免把函数列表变成耗时演示；Course 必须完整讲解。

### 9. Materialize reusable enrichment

- 对固定 ID 执行一次 `INSERT ... SELECT`；
- 写入模型名、digest、prompt version、run id 和时间；
- 再次运行 candidate query，结果应为 0；
- 用普通 SQL 按 topic/sentiment 聚合，证明报表不再触发推理。

### 10. Aggregate across rows with `AI_AGG`

- 1.5B 默认模型下每个 topic 最多选择 2 行；
- 先显示参与聚合的原文；
- 调用 `AI_AGG(raw_text, '将每条工单的共同问题与差异总结为不超过60字的一段话，不要补充原文没有的事实。')`；
- 检查每组只返回一行；
- 人工标记遗漏和新增事实；
- 解释输入行数、单行长度和 group 数会扩大 context 与推理时间。

### 11. Clean up

- 删除本 Lab 创建的 AI Resource；
- 表的保留/删除行为与前置 Lab 保持一致并明确告知；
- 检查 Resource 已不存在；
- 可选执行 `ollama ps` 观察已加载模型；
- 不自动删除模型，因为下载成本高且后续 Module 可能复用。

### Lab complete

最终验收：

1. BE 成功访问本地 Ollama；
2. Doris 成功创建 local AI Resource；
3. `AI_GENERATE` smoke test 返回非空短文本；
4. `AI_CLASSIFY` 和 `AI_SENTIMENT` 通过集合校验；
5. `AI_EXTRACT` 和 `AI_SUMMARIZE` 完成小规模调用并检查输出；
6. enrichment 已物化，第二次 candidate count 为 0；
7. `AI_AGG` 在受控 group 上返回每组一条结果；
8. Resource 已清理，模型文件保留。

自动检查只验证对象状态、数据类型、标签集合、行数与幂等性，不比较完整模型文本。

## 9. Quiz 设计

Quiz 标题：**Quiz: Choose and Operate Doris AI Functions Safely**。

Quiz 使用现有课程的 YAML + Jupyter 单选题结构，建议 7 题。每题必须能仅凭 `course.md` 回答，不要求先运行 Lab；解释文字指出为什么其他选项不成立。

| 题号 | 学习目标 | 题目场景 | 正确判断 |
|---|---|---|---|
| Q1 | 区分调用方向 | 比较 Doris MCP 与 AI Function | AI Function 是 Doris SQL 调用模型 |
| Q2 | 选择 Resource | 给出云端与本地两种部署约束 | 云端需要 provider/API Key；Ollama 使用 `local` 且不需要 Key |
| Q3 | 保护云端密钥 | 选择 API Key 的保存和执行方式 | 不写入 Git、Notebook、截图或长期 Shell history；由受控管理员流程注入并限制权限 |
| Q4 | 判断网络地址 | Doris BE 在 Docker、Ollama 在宿主机 | Resource 使用 BE 可达的 `host.docker.internal`，不是容器内 `127.0.0.1` |
| Q5 | 理解 smoke test | `CREATE RESOURCE` 成功但函数失败 | Resource 存在不证明 endpoint、模型或响应可用，必须执行真实短调用 |
| Q6 | 验证非确定性结果 | 分类返回新标签，mask 漏掉订单号 | 做集合/结构验证并保留人工或确定性控制，不能直接信任生成结果 |
| Q7 | 控制重复成本 | dashboard 每次刷新都调用多个 AI Function | 先限制候选行并物化 enrichment，报表读取物化列 |

Quiz 不考 Ollama CLI 冷门参数、特定网络故障、模型文件目录或下载内部实现，也不要求记忆云服务价格。重点是可迁移的 Doris 概念、凭证安全、网络边界、结果验证和成本控制。

## 10. 截图和图表计划

| 编号 | 内容 | 形式 | 截图要求 |
|---|---|---|---|
| S1 | Doris → 云 API / Ollama 双路径调用链 | 静态架构图 | 标清共同的 FE/BE/Resource，以及 API Key 只属于云端路径 |
| S2 | Ollama 安装完成与模型存在 | 终端截图 | 显示 `ollama list` 中模型名；裁掉用户主目录 |
| S3 | BE 可以访问 Ollama | Notebook 输出 | 显示 endpoint、HTTP 成功状态和模型名 |
| S4 | Resource 创建与检查 | Notebook 输出 | 显示 provider=`local`、endpoint、model |
| S5 | 分类结果与 mismatch | Notebook 结果表 | 同时显示 raw、expected、actual、valid |
| S6 | 物化后的普通 SQL 聚合 | Notebook 结果表 | 证明不再调用模型 |

DeepSeek API Key 路径使用脱敏代码块和架构图，不截控制台密钥页面，不展示真实 Key，也不截图带 Key 的 `CREATE RESOURCE` 执行结果。不截图安装器的每一步。Course 用可复制的标准命令和操作说明承担安装指导，避免 UI 版本变化导致整课过期。

## 11. PoC 与发布验收清单

| 项目 | 发布值 | 验证证据 |
|---|---|---|
| Doris image/patch | `apache/doris:all-in-one-4.1.3` | `SHOW FRONTENDS`、`SHOW BACKENDS` 的版本字段 |
| Ollama version | PoC 为 `0.40.8`；发布前重新固定 | `ollama --version` |
| Model tag | `qwen2.5:1.5b-instruct` | `ollama list` |
| Model digest | PoC manifest digest `65ec06548149...`; 发布前记录完整值 | `ollama show` / `/api/tags` |
| Resource endpoint | 默认 `http://host.docker.internal:11434/v1/chat/completions`；端口可由 `OLLAMA_PORT` 调整 | BE 实际请求成功 |
| Cloud example | DeepSeek `deepseek-chat`，仅 Course 讲解 | 发布时核对 DeepSeek 与 Doris 官方文档；仓库扫描不得包含真实 Key |
| Dataset revision | 待固定 commit/hash | 行数与 expected label 校验 |
| 验证硬件 | 8 GB 下限与 12/16 GB 常见教学机 | 内存与耗时记录 |
| 最近本地 PoC | `2026-10-22` | 当前单 FE/单 BE Docker + Ollama 实测记录 |

PoC 必须验证：

1. 干净环境可按官方安装方式安装 Ollama，并用标准 `ollama pull qwen2.5:1.5b-instruct` 下载模型；
2. 宿主机和 BE 两条网络检查都成功；
3. `provider_type=local` 不需要虚构 API key；
4. Course 的 DeepSeek 模板与发布时官方属性一致，且所有课程文件只包含 Key 占位符；
5. 课程固定 Doris patch 能运行全部列出的函数；
6. 1.5B instruct 模型不会输出 thinking 内容，且返回值可被各函数适配器解析；
7. `AI_CLASSIFY` 只返回候选标签；
8. `AI_SENTIMENT` 的实际标签集合与当前 Doris 文档一致；
9. `AI_EXTRACT` 的实际格式可被课程验证逻辑处理；
10. `AI_FILTER` 返回 BOOLEAN；当前 4.1.3 PoC 的 `AI_SIMILARITY` Planner 类型为 FLOAT，因此课程只断言其为 0–10 的数值，不硬编码 DOUBLE；
11. `AI_MASK` 的漏识别与额外格式会作为风险案例保留，Lab 不把它当作合规 DLP；
12. `AI_AGG` 返回完整单一文本，不发生 response parser 异常；
13. 模型冷启动和热调用都不会超过课程 `query_timeout`；
14. 重新运行 Notebook 不会重复插入或无界调用模型；
15. 清理只删除 module-owned Resource/table，不删除学习者其他模型或数据；
16. Quiz 的每个答案都能定位到 Course 章节，并且不依赖外部服务或 Lab 状态。

本 Module 明确复用现有 `apache/doris:all-in-one-4.1.3` 单节点环境，不在课程中升级镜像。发布前必须在这一实际容器完成所有函数 PoC；如果某个函数因 4.1.3 的适配器行为而不能稳定执行，应记录具体错误并重新决定该函数是只讲解还是需要课程级版本调整，不能在 Notebook 中悄悄启动另一套 Doris。

## 12. 官方资料基线

- Apache Doris：[AI Functions Overview](https://doris.apache.org/docs/4.x/ai/ai-function-overview/)
- Apache Doris：[LLM SQL Functions](https://doris.apache.org/docs/4.x/key-features/llm-sql-functions/)
- Apache Doris：[AI Functions SQL Reference](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/ai-functions/overview/)
- Apache Doris：[AI_AGG](https://doris.apache.org/docs/4.x/sql-manual/sql-functions/aggregate-functions/ai-agg/)
- Apache Doris：[CREATE RESOURCE](https://doris.apache.org/docs/4.x/sql-manual/sql-statements/cluster-management/compute-management/CREATE-RESOURCE/)
- DeepSeek：[API Documentation](https://api-docs.deepseek.com/)
- Ollama：[OpenAI Compatibility](https://docs.ollama.com/api/openai-compatibility)
- Ollama：[Qwen2.5 1.5B Instruct](https://ollama.com/library/qwen2.5:1.5b-instruct)

最终结论：Course 解释 Doris AI Function 的统一调用模型，并完整保留 DeepSeek API Key 云端路径与 Ollama 本地路径；Lab 只复用本机单 FE、单 BE `doris` Docker，通过 `local` AI Resource 调用约 986 MB 的 `qwen2.5:1.5b-instruct`，不需要任何云端密钥；Quiz 检查 provider 选择、密钥安全、BE 网络、结果验证和物化策略。标准模型下载使用 `ollama pull`，不把个别机器的网络故障处理固化为课程步骤。
