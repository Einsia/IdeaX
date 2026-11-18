# 当前离线 AR baselines

这里保存 2026-11-18 当前离线批次的八套 baseline 适配源码，以及共享断网执行、模型桥、本地文献访问、故障恢复和评分实现。[catalog.json](catalog.json) 记录比较范围和上游 commit。

| 系统 | 范围 | 原生流程与适配 |
|---|---|---|
| [AutoResearchClaw](autoresearchclaw/README.md) | 主比较 | 原生 stages 1–9；止于提案 |
| [Dr. Claw](dr_claw/README.md) | 主比较 | 原生构思、审阅、选择；取消额外的 30 轮硬上限 |
| [ResearchAgent](researchagent/README.md) | 主比较 | 原生问题、方法、实验设计及验证；逐域 seed / 引用 / 实体输入 |
| [CycleResearcher](cycleresearcher/README.md) | 主比较 | 每槽 10 候选，Standard Mode / 4 reviewers，官方教程 Top1 |
| [SciAgents](sciagents/README.md) | 主比较 | 匹配领域图与原生对话；原图迁移单列 |
| [DeepScientist](deepscientist/README.md) | 主比较 | 原生 idea stage、候选比较和选择；proposal-only 边界 |
| [InsightAgents](insightagents/README.md) | 主比较 | 原生专家推荐、讨论和最终提案；本地文献接口 |
| [AI-Scientist v3 native ideation](ai_scientist_v3_native_ideation/README.md) | Additional | 原生 ideation 阶段单列 |

现有 CoI、IdeaScientist 入口仍在仓库根目录的 [`baselines/`](../../baselines/)。已退休 AI-Researcher、旧在线运行和 source probes 不在本次方法清单中。

## 源码布局

`snapshot/` 保留部署源码的相对目录结构；[source_manifest.json](source_manifest.json) 逐文件记录原始与发布 SHA-256。这是部署适配器的源码快照，**不是已配好材料和准入凭据的即装即跑包**。源码保留原批次的目录名、机器路径、版本绑定和恢复约束，旧路径不能直接作为新机器的有效配置。

- `snapshot/phases/offline-20261117/adapters/`：原生方法适配和隔离内模型客户端。
- `snapshot/phases/offline-20261117/runtime/`：网络 namespace、只读挂载、Unix socket 模型桥。
- `snapshot/phases/offline-20261117/services/local_literature/`：共享离线语料的构建、检索、阅读与核验。
- `snapshot/phases/offline-20261117/scoring/`：当前 C/I/S 和同系统、同模型、同领域五份原提案的 Novelty 评审。
- `snapshot/phases/offline-20261117/staging/`：InsightAgents、SciAgents、AI-Scientist v3 的集成版本。
- `snapshot/phases/offline-20261117/state/`：版本化恢复程序源码；没有生产队列、运行状态、准入签发文件或历史 checkpoint。
- `snapshot/adapters/common.py`：宿主模型传输与共享物理请求限流。凭据文件不在仓库；迁移时须配置自己的受保护凭据位置。

CycleResearcher 当前选择入口是 `adapter_v5.py`：调用上游 parser、教程 `extract_average_rating` / `max`，保留候选原顺序。v4 文件保留为既有请求载体依赖，旧兼容解析和缺分即失败策略不参与 v5 选择。教程内部 fallback 数值也不等于 benchmark 原生失败零分。

## 协议

每个当前方法目标为 38 领域 × 5 个输出槽，Astra / xhigh。生成、评分和子代理的实际模型请求共用 **250** 上限；进程数和内部候选数不能替代实际请求数。

研究工具只访问共同离线语料，公网不可达；模型 API 经宿主桥访问。运行前必须验收共同语料、断网边界、共享限流、原生 adapter、逐域材料和离线评分。扩大 scope 或并发配置不自动授予槽位准入。

API、磁盘、适配器及外部评审错误按原输入、原 checkpoint 和成功缓存恢复；保留每次实际消耗，缺失用量保持未知。使用有界尝试与退避，一轮预算耗尽不等于永久完成。不能借重试选择更好的提案或评审。

原生失败零分需要独立证据并保留原 failure 类型。未尝试槽、API 失败、adapter-invalid 和 evaluation-failure 不填零。固定目标分母、真实成功均值和原生失败零分覆盖分别报告；指标不齐时完整均值未知。Novelty 缺合格五份 panel 时保持未知。

## 离线检查与复现依赖

在仓库根目录执行：

```bash
python system/baselines/check.py
python scripts/check_release.py
```

检查只验证清单、Python 语法、源文件哈希、方法范围及运行产物排除规则，不导入执行 adapter，不发起网络或模型调用。通过检查表示源码包完整，不代表复现了 benchmark 分数或取得了任务准入。

实际运行还需要：

1. 各方法 `source.json` 指定 commit 的上游源码和各自依赖环境；上游仓库未整体重复打包，许可说明随方法保存。
2. 独立准备并冻结的共同语料、逐域 seed / 图 / 实体材料与输入哈希；旧聊天和旧在线结果不能作为新输入。
3. 配置本机路径、只读挂载、模型凭据及共享 250 请求锁池，验证隔离后运行。
4. 对新路径和实际源码重新验收，建立版本化 route / manifest / admission；不能复制旧批次授权或成功记录跳过验证。

本次发布没有调用模型或改写正在运行的实验。原始结果、请求日志、用量、数据库、图数据、密钥和论文不在源码包内。当前 Astra 与另行规划的 unified-matrix 继续分开追踪，源码发布不表示两者已跑完。
