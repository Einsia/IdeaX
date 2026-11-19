# IS：IdeaScientist 外部指标

采用IdeaScientist公开评价提示词，对已有创意卡片或Blueprint评分。每份输出由GPT（Astra/xhigh）和Claude（Opus 5.5/xhigh）分别评价一次。卡片/Blueprint、不同生成模型分别建目录。

| 指标 | 尺度与含义 |
|---|---|
| Actionability | 1–10，可执行性 |
| Specificity | 1–10，具体性 |
| Clarity | 1–10，清晰度 |
| Impact | 1–10，影响力 |
| Soundness | 1–10，论证可靠性 |
| Relevance | 1–10，与给定研究任务的相关性 |
| Quality mean（Q） | 上述六维不加权均值 |
| Literature novelty（N） | 1–10，与冻结当前文献比较的新颖性 |
| Structural transfer | 0/1，须有来源/目标场景、机制、共享结构、适配及原文证据 |

Q不包含novelty或transfer。IS的N不是Generation概念新颖性，不除以20。新颖性参考资料投影保留问题、挑战和机制，排除摘要与实测结果。质量依据提案本身；相关性依据实际给定任务，不从答案反推任务。

这是**已有输出的当前文献适配**，不冒充IdeaScientist原版历史截止任务复现。本适配没有定义原论文Overall：报告保留 `Overall: null` 和原因，不临时发明加权公式。

## 命令

先完成Generation C/S/I独立取证，IS复用同一冻结证据。

```bash
python benchmarks/evaluate.py is prepare --input runs/cis --out runs/is
python benchmarks/evaluate.py is run --out runs/is --workers 16
python benchmarks/evaluate.py is report --out runs/is
```

结构迁移需要原生输出中明确的机制文本。Markdown或Blueprint输入在prepare时加 `--mechanisms mechanisms.json`，内容为 `idea_id -> 原输出机制文本`，不能按分数改写机制。

`results.json`保留原始结果；`paper_scores.json`按GPT/Claude报告六维、Q、N、transfer及每指标固定190目标下的有效数/缺失数。未评项不填零。

源码：[请求与校验](../ideascientist/rescore.py)、[原版prompts](../ideascientist/vendor/prompts.py)、[执行入口](../run.py)、[双裁判报告](../shared/paper_report.py)。
