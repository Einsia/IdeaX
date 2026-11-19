# Reconstruction：历史贡献重建

评价较早文献生成的提案能否重建后来出现的研究贡献。生成必须使用日期截断的离线文献，并核验生成模型训练截止早于任务日期。目标论文仅供裁判使用，不能放进生成工作区；开放式Generation当前文献输出不能直接当作历史重建输入。

GPT（Astra）和Claude（Opus）独立评价每个候选×目标：

| 等级 | 含义 |
|---|---|
| 0 | 不相关，或仅宽泛主题相同 |
| 1 | 方向相同，关键机制不同 |
| 2 | 关键机制相同或高度相近 |
| 3 | 问题与关键机制基本相同 |

每任务十张已排序候选，对每个目标取最高等级。**Grade**为该等级，**方向命中率**为Grade≥1，**机制命中率**为Grade≥2。两位裁判分别报告。主报告先对领域内目标平均，再对实际目标领域等权；历史按目标等权均值另存。

仓库冻结数据实际包含 **37个目标领域、58个领域–截止日任务、69个主要目标**。另有3个补充目标，不计入主均值。不能套用开放式生成的38领域分母；扩展到38领域须冻结新目标版本。报告从目标数据计算覆盖，任一目标未评时完整 `domain_mean` 为null。

## 输入与命令

`submissions.json` 每条含 `system`、来自任务清单的 `task_id`、十张 `cards` 和：

```json
{
  "generation_protocol": {
    "web_access": false,
    "literature_before": "2025-09-01",
    "generator_training_before": "2025-08-01"
  }
}
```

日期仅示例，实际须匹配任务、生成模型与文献证据。元数据声明不替代泄漏审计。

```bash
python benchmarks/evaluate.py reconstruction prepare --input submissions.json --out runs/reconstruction
python benchmarks/evaluate.py reconstruction run --out runs/reconstruction --workers 16
python benchmarks/evaluate.py reconstruction report --out runs/reconstruction
```

`results.json` 与逐对评审保持原格式；`paper_scores.json` 另给GPT/Claude领域等权结果、历史目标等权结果及覆盖数。漏判不默认0。预算内最大匹配不改变Generation的外评前selector Top1规则。

源码：[原rubric](../founder/rubric.py)、[任务和目标](../founder/data/)、[准备与评分](../run.py)、[领域等权报告](../shared/paper_report.py)。
