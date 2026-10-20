# AI Integrations 课程维护

学员入口：[课程首页](../../doris-course/04-ai-integrations/README.md)。
本目录只供课程作者和评审者使用，不是学员的学习步骤。

| 文件 | 用途 |
| --- | --- |
| [module01-design-outline.md](module01-design-outline.md) | Module 1 的中文设计大纲（原 `level1/module01-doris-mcp/readme.md`）。写于课程改为自带环境之前：其中的容器名、端口、数据表、截图计划和文件清单都已过时，以课程目录中的讲义和 Lab 为准 |
| [doris-ai-course-research.md](doris-ai-course-research.md) | Doris AI 课程的前期调研：MCP、Hybrid Search、AI Functions 等方向的能力边界、版本和课程形态建议 |
| [clickhouse-ai-course-research.md](clickhouse-ai-course-research.md) | ClickHouse Academy 中 AI 相关教程的调研，用于对照课程定位 |

## 维护要点

- 课程自带环境：容器 `doris-ai`，端口 39030 / 38030 / 38040（`DORIS_AI_*`），数据 `datasets/events.csv`（由 `datasets/generate_events.py` 按固定种子生成；改动后同步 `datasets/events.yaml` 和讲义中的数字，测试会核对）。
- 讲义 1.6 节的参考记录（reference trace）来自经 launcher 调用 MCP Server 的真实结果，测试用的原始结果在 `tests/fixtures/reference_results.json`。升级 `doris-mcp-server` 或 Doris 后，用 Lab 第 6 节或 `doris_course.mcp_client.run_host_session` 重新取结果，更新讲义和 fixture，并更新讲义末尾的 Tested with 表。
- `doris-mcp-server` 1.0.0 已知问题：`execute_query` 的 `max_rows` 在 2000 左右以上时，对 `ai_course.events` 的 `SELECT *` 返回 `CHILD_RESULT_INVALID`（输出 schema 校验失败，原因被日志脱敏），1000 行正常。讲义只写默认的 100 行上限。

## 后续模块的统一要求（AI-10）

课程以 Preview 发布（D-12），模块陆续补齐，路线图写在课程 README 的 Roadmap 一节：Hybrid Search、AI Functions、Lakehouse 联邦检索，按调研文档推荐的顺序。每个新模块在发布前满足：

1. 讲义开头写明它用到 Module 1 的哪项能力（只读账号、launcher、证据核对、`doris_*` 某个 domain 等），并有 Before you begin 一节：平台、Docker 资源、Python 版本、需要的 Host 或外部服务、账号与费用。
2. 环境声明：沿用本课的 `doris-ai` 沙箱（容器、端口、`DORIS_AI_*` 变量不变），需要额外的容器或服务时用 `doris-ai-` 前缀、本课端口段，并能用环境变量覆盖；需要外部模型或 embedding 服务的（AI Functions），默认用本地开源模型，付费服务只作为可选项，key 只从环境变量读（conventions.md 第 8 节）。
3. 固定版本并写明验证日期：Doris 镜像、`doris-mcp-server` 和其他 pip 包锁定版本；讲义末尾有 Tested with 表，写明验证了什么、在哪个版本和日期。
4. 可判分的测验：`quizNN_<slug>.yaml` 和 `.ipynb`，6 道单选题，每题对应讲义的一条学习目标，结构符合 `doris_labkit.quizbank`，CI 中 `check_quiz_balance.py --strict` 通过。
5. Lab 按 conventions.md 第 4 节：首个代码单元初始化，每个步骤后有 Expected result，有空白练习单元加折叠的可执行参考答案，有清理单元；离线测试放在课程的 `tests/`，CI 运行。
6. 讲义中的工具调用结果来自真实运行（像 Module 1 的 reference trace），测试核对其中稳定的部分。
