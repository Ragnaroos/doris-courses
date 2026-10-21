# Data Warehousing 课程维护

学员入口：[课程首页](../../doris-course/02-data-warehousing/README.md)。
本目录只供课程作者和评审者使用，不是学员的学习步骤。

## 讲义结构约定

14 份讲义都按课程模板（Level 1 在 B5、Level 2–3 在 B6 改写）：课程信息表、Module goal、
Learning objectives、Module structure、按 N.M 编号的各节、Lab、Summary、Quiz、References，
全部用英文。课程单元按学习顺序连续编号（Module 1–14），数据集围绕数仓业务组织。
学员只有一份课程 README（课程目录下的 `README.md`）；原来的 `GETTING_STARTED.md`、各 Level 指南、
环境与数据说明中学员需要的内容并入了课程 README 和各 Lab，原文移到 `former-readmes/`（B6，DW-05）。

测验链接指向可交互的 ipynb，YAML 只作为题库源文件。
官方参考资料按本单元主题选择；版本限制和未完成实验需保留明确说明。
正文按业务问题、概念、示例与结果解释组织，不以“观察与练习”或录制待办代替讲解。
分节标题保留简洁的功能名称，例如 Streaming Job 与 CDC_STREAM；业务场景、术语含义和工作过程放在正文讲清楚。
学员材料保留实验前置条件、操作风险与功能成熟度；制作状态和测试记录集中在本目录。
Level 1 的 Iceberg Lab 已实测；三份基础扩展覆盖文件查询、Group Commit 等操作，新增 Lab 5A / 5B 覆盖 Kafka 与 MySQL/Flink CDC 的选做链路。Streaming Job / CDC_STREAM 和持续文件仍仅介绍。具体实测边界见 VALIDATION.md。
每份讲义有六条学习目标，与六道测验逐项对应，单元总结回扣相同目标；
题目定义中的 objective 保存对应的学习目标原文，`tests/test_lessons.py` 检查；Module 5 的选读材料
`optional05_continuous_ingestion.md` 另有六题。每道题的出处见 [quiz-alignment.md](quiz-alignment.md)。
教学时间是包含讲义、实验和测验的估计，不含环境准备，仍需试讲校准。
讲义完善不代表外部集成实验或目标发布版本已经验证；实际范围见验证记录。

| 文件或目录 | 用途 |
| --- | --- |
| [VALIDATION.md](VALIDATION.md) | 实际验证结果与未验证范围 |
| [WWI-VALIDATION.md](WWI-VALIDATION.md) | 候选 WWI 数据集的实际导入结果与业务缺口 |
| [integration-backlog.md](integration-backlog.md) | 已覆盖范围及未验证边界 |
| [PR_DRAFT.md](PR_DRAFT.md) | PR 说明草稿 |
| [former-readmes/](former-readmes/GETTING_STARTED.md) | B6 之前公开的学员说明（`GETTING_STARTED.md`、`datasets/`、`environments/*/`、各 Level 和扩展的 README），按原路径存放。学员需要的内容已并入课程 README 和各 Lab；这里只供查阅，不再更新，其中的数字和依赖以课程 README 为准 |
| scripts/prepare_wwi.py | 校验并暂存本地 WWI Parquet 包，不上传。在仓库根目录执行 `doris-course/02-data-warehousing/.venv/bin/python maintenance/02-data-warehousing/scripts/prepare_wwi.py --source <已解压的目录>`，默认复制到课程的 `.runtime/wwi/`，目标已有同名文件时停止；学员不需要它（Lab 5 自动解压仓库中的包） |
| tests/test_maintenance_docs.py | 检查本目录的维护文档（链接、集成清单）和 Jupyter 浏览配置 |

课程的离线测试和执行 Lab 的脚本属于课程代码，在课程目录中：
`doris-course/02-data-warehousing/tests/`（离线检查材料、数据与辅助工具），
`doris-course/02-data-warehousing/scripts/run_labs.py`（执行主线与三份基础扩展的代码单元），
`scripts/run_streaming_labs.py`（显式选择 Kafka / CDC 选做 Lab，固定独立库 dw_course_l1_streaming）。

安装课程依赖后，在课程目录 `doris-course/02-data-warehousing` 下执行：

```bash
.venv/bin/python -m unittest discover -s tests -v
# 使用课程单容器沙箱；先选择独立测试库并确认实验表重置范围。
export DW_DATABASE=dw_course_l1_validation
export DW_ALLOW_WRITES=yes
.venv/bin/python scripts/run_labs.py
# 加入本地湖表实验（折叠的参考答案是代码单元，和 Run All 一样总会执行）：
.venv/bin/python scripts/run_labs.py --iceberg
# 再加三份基础扩展（需要 .[extensions] 的 PyArrow）；主线结果已在库中时改用 --extensions-only：
DW_DATABASE=dw_course_l1_extensions_check .venv/bin/python scripts/run_labs.py --iceberg --extensions
# 单独选做持续接入；先读 Lab 5A / 5B 开头的资源要求，使用固定独立实验库：
.venv/bin/python scripts/run_streaming_labs.py all
```

本目录维护文档的检查从仓库根目录执行：

```bash
doris-course/02-data-warehousing/.venv/bin/python -m unittest discover -s maintenance/02-data-warehousing/tests -v
```
测试检查待提交 Notebook 不带执行输出；不要为通过检查清空学员的本地记录，
可导出 Git 暂存区到临时目录后验证。

## 编号迁移记录（2026-09-18）

这次迁移时学员材料按 D01–D13 连续编号；之后模块统一称为 Module 1–14（R-11），Level 3 增加了
Module 14，D 编号只留在旧的验证记录中。下表是当时的对应关系，查阅旧记录时用。

| 原编号 | 当前编号 | 内容 |
| --- | --- | --- |
| D09-A | D06 | 数据质量与 Schema 校验；视频 D06-01～03 |
| D06 | D07 | 更新、删除与事件重放 |
| D07 | D08 | 视图与物化视图 |
| D08 | D09 | 数仓建模与 Join |
| D12 | D11 | BI 与 AI 应用 |
| D09-B | D12 | 发布、权限与审计；原视频 D09-04～08 改为 D12-01～05 |
| D11 | D13 | 存储与生命周期管理 |

D01–D05、D10 编号保持不变。Level 1 的两个目录已改为
`module06-data-quality` 和 `module07-state-changes`，对应讲义、Lab、Quiz 文件同步更名。
Jupyter 中打开旧路径的标签页需关闭，再从课程目录进入新路径。

## Jupyter 浏览入口

从仓库根目录启动，01 和 02 使用同一个界面：

```bash
.venv/bin/jupyter lab --config=maintenance/jupyter_lab_config.py --ServerApp.port=18890 --ServerApp.port_retries=0
```

配置以仓库为文件根目录，默认打开 doris-course，确保维护资料的相对链接也可访问。
安装元数据、Python 缓存和 Jupyter 检查点只从文件列表隐藏，不删除；
仍保留默认认证机制。学员无需预设连接地址；各 Lab 固定连接课程单容器沙箱。
主线多人使用时，可在启动前用 DW_DATABASE 分配独立实验库；Lab 5A / 5B 使用固定的课程服务和独立库，不能在同一沙箱并发执行。
