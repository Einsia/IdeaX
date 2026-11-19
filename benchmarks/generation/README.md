# Generation：C、N、S、I

每系统、每个生成模型使用 38 领域 × 5 份原提案。GPT 和 Claude 各独立评一次，分别报告四维，不合并成一个总分。

## C — Contribution，贡献（1–5）

相对于最接近前作，提案仍保留的实质性新知识或新能力。独立获取证据后冻结同一证据包，区分摘要、结构化来源卡和正文。**原 Reviewer JSON 的 `N` 映射为论文 `C`**；原字段与 prompt 不重写。

## N — Novelty，新颖性（0–5）

评价非显然的概念突破，例如机制联系、问题重述和新研究方向。不开展外部检索。每位裁判先通读同系统、同生成模型、同领域五份原提案，再按固定顺序评分。

原 Interesting 分数为0–100，**`N = score / 20`**，不提前舍入。缺五份不能用补写提案或其他系统提案拼 panel；成功兄弟槽不补零。底层历史入口支持其他 panel 大小，新 Generation 入口限定五份。

## S — Soundness，论证可靠性（1–5）

前提、机制和预期结果是否构成连贯论证。尚未执行实验或执行成本高本身不构成扣分理由。来自原 Reviewer `S`，使用与 C、I 相同的冻结证据。

## I — Importance，重要性（1–5）

问题本身的价值及研究目标实现后能带来的进展。来自原 Reviewer `I`。历史 Reviewer 加权总分保留，但不替代这里四个独立指标。

## 输入与命令

输入为JSON数组，每项含 `system`、`task_id`、`idea_id`、`idea_text`，并有 `domain_ids`、`task_context` 等上下文；可附 `selector_top1`。每个输出目录只放一种生成模型；若提供 `generation_model` 字段，会检查它一致。完整格式见[运行指南](../../docs/RUNNING.md#benchmark-commands)。

```bash
# 准备输入，不调用模型。
python benchmarks/evaluate.py generation cis prepare --input cards.json --out runs/cis
python benchmarks/evaluate.py generation novelty prepare --input cards.json --out runs/novelty

# 若尚需取证，先部署仅访问本地冻结语料的服务；如已有证据，见下方替代命令。
export LITGRAPH_API_BASE_URL=http://127.0.0.1:8900
python benchmarks/evaluate.py generation cis run --out runs/cis --astra-concurrency 8 --opus-concurrency 8
python benchmarks/evaluate.py generation novelty run --out runs/novelty --workers 16

# 校验两套原输入与收据后合并；不调用模型。
python benchmarks/evaluate.py generation report --reviewer runs/cis --novelty runs/novelty --generation-model gpt-6-astra --expected-slots 190 --out reports/generation
```

已有相同 rubric 的冻结证据时，用下面命令替代首次 CIS prepare；须使用尚不存在的新输出目录，不导入旧裁判分数：

```bash
python benchmarks/evaluate.py generation cis prepare --from-evaluation frozen-cis --out runs/cis
```

上述 run 顺序执行；并行多个命令须另外协调共享评分20/物理请求250上限。`scores.json` 每个系统保留GPT、Claude两行及每指标分母/覆盖/成功均值；`REPORT.md` 每格顺序 **GPT / Claude**，不完整均值显示pending。

源码：[C/S/I pipeline](../reviewer/pipeline.py)、[rubric](../reviewer/reviewer_prompt.md)、[Novelty预读](../interesting/read_all.py)、[评分循环](../run.py)、[报告映射](../shared/paper_report.py)。
