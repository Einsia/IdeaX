# Benchmark 评测：Generation、Reconstruction、IS

三类评测都分别报告 **GPT（Astra / xhigh）和 Claude（Opus 5.5 / xhigh）**。
每份输出由每位裁判独立评一次；生成模型与裁判模型分开登记。每个生成模型使用独立输入、manifest 和输出目录，两位裁判不共享评分历史，分数不混成一个均值。

| Benchmark | 指标 | 说明与源码 |
|---|---|---|
| **Generation** | **C、N、S、I** | [四维定义与命令](generation/README.md)；[Reviewer](reviewer/pipeline.py) 和 [Novelty](interesting/read_all.py) |
| **Reconstruction** | Grade、方向命中率、机制命中率 | [历史重建协议与命令](reconstruction/README.md)；[匹配 rubric](founder/rubric.py) |
| **IS** | 六维质量、质量均值、文献新颖性、结构迁移 | [适配范围与命令](is/README.md)；[请求构造与校验](ideascientist/rescore.py) |

统一入口是 [`evaluate.py`](evaluate.py)，报告映射与完整性检查在 [`shared/paper_report.py`](shared/paper_report.py)。原来的 `run.py reviewer / interesting / founder / ideascientist` 入口仍保留；原 prompt、原始评分字段和成功缓存不重写。

```bash
python benchmarks/evaluate.py --help
```

## 共同输入与运行规则

- 研究资料来自本地离线语料或冻结证据包，模型 API 可以使用。新入口的 C/S/I 取证只接受本机离线 LitGraph 服务；已有完整证据时直接复用。评分会话禁用研究工具。部署仍须对研究进程实施网络隔离，地址检查不替代断网。
- 复用同一原提案、原五份 panel、原 rubric 和各裁判自己的成功缓存。`prepare`、`check`、`report` 不调用模型；`run` 调用模型。
- 新入口单次运行评分 worker 合计不超过 **20**。在当前实验环境中，生成、评分、子代理及其他批次还须使用同一个物理请求限流桥，总上限 **250**。CLI 的 worker 数不是跨进程物理 API 请求计数器。
- 凭据由受保护 profile 或环境加载，配置见根目录 `.env.example`。不提交凭据、真实运行日志或私有配置。
- API/适配/评审故障按原输入和 checkpoint 有界重试、退避，保留成功步骤和实际消耗。明确策略拒评不通过换 key、模型或 provider 绕过。

## 覆盖与报告

Generation 默认每系统/生成模型 **38 × 5 = 190** 个目标槽，两裁判各有该分母。报告保存真实有效数、成功均值、确认原生失败零数、已覆盖均值与缺失数；只有该指标目标全部覆盖，才给 `full_mean`。待启动、缺 panel、API 失败、adapter_invalid、外部评审失败不能自动填零；临时零分情景不写回原评审。

原生失败零是 benchmark outcome，不是裁判评分。公开入口的旧 `zero_score_outcomes.json` 只接纳既有、可验证的原生查新终止类型，不是任意失败标签的通用认证器。当前 AR 批次的逐槽认证及离线评分快照见 [system/baselines](../system/baselines/README.md)。

Top1 必须是外部评审前选择器记录的第一名。卡片/Blueprint、不同取证协议、生成模型和历史三次复评结果分别保存。IS 的已有输出适配不定义原论文 Overall，不用六维均值冒充 Overall。

## 源码范围

公开可移植入口提供单次双裁判流程及论文报告层。原 Reviewer 的 `N` 在论文中显示为 Contribution（C）；论文 Novelty（N）来自独立 Interesting 分数除以20，二者不可混淆。当前 AR 离线取证、材料版本和恢复有[独立源码快照](../system/baselines/README.md)。离线检查通过不表示已经用新入口重跑并复现论文分数。
