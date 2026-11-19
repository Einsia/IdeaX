# Generation 的 C/S/I · 原三维 Reviewer

Astra 与 Opus 各评一次，使用同一冻结证据包。原始 JSON 字段 `N/I/S` 与 prompt 保留，
论文显示映射为 **C/I/S**：原 `N` 表示 Contribution，不能当作独立 Novelty 分数。
Generation 的 Novelty 另走五份提案通读评分，并除以20显示为0–5。

使用 `python benchmarks/evaluate.py generation cis prepare/check/run/report …`，
或原 `pipeline.py` 入口。完整四维定义与双裁判合并报告见[Generation说明](../generation/README.md)。
一次评审没有复评标准差；历史三次复评、工具型 integrated prompt 均保留独立协议，不混排。
