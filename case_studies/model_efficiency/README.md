# IdeaX / LitGraph：Efficiency领域六类研究示例

整理与打包日期：2026年11月13日（Asia/Shanghai）。

本文件包收录六类探索模式，每类两份正式文件，共12份正文。所有案例由单agent独立完成。各模式非互斥，编号表示案例的主要探索视角。

- `PROCESS.md`：检索全过程、实际API路径、来源与阅读深度、候选调整、查新风险和请求记录。
- `PROPOSAL.md`：可用于论文案例或研究计划的独立idea提案，含研究问题、机制、前作关系、验证方案和失败条件。

建议先读各例的PROPOSAL.md了解核心想法，再按需查阅PROCESS.md核对证据。

|编号|模式|主题|全过程|论文提案|
|---|---|---|---|---|
|01|A+B mechanisms｜机制组合|谱范数最陡下降 × 权重谱球面约束|[阅读](01_AB_mechanisms/PROCESS.md)|[阅读](01_AB_mechanisms/PROPOSAL.md)|
|02|Cross-domain transfer｜跨领域迁移|以量化与剪枝操作进行任务适配|[阅读](02_Cross_domain_transfer/PROCESS.md)|[阅读](02_Cross_domain_transfer/PROPOSAL.md)|
|03|Rethinking default assumptions｜重审默认假设|激活压缩与随机精确回放|[阅读](03_Rethinking_assumptions/PROCESS.md)|[阅读](03_Rethinking_assumptions/PROPOSAL.md)|
|04|Diagnosis and reattribution｜诊断与重新归因|区分FP4振荡中的权重移动与共享尺度变化|[阅读](04_Diagnosis_reattribution/PROCESS.md)|[阅读](04_Diagnosis_reattribution/PROPOSAL.md)|
|05|Extending capability boundaries｜扩展能力边界|压缩验证状态下保持参考分布的投机解码|[阅读](05_Extending_boundaries/PROCESS.md)|[阅读](05_Extending_boundaries/PROPOSAL.md)|
|06|Free exploration｜自由探索|回滚感知的MoE专家缓存管理|[阅读](06_Free_exploration/PROCESS.md)|[阅读](06_Free_exploration/PROPOSAL.md)|

## 使用说明

这些材料是研究案例和提案，未报告新完成的模型训练或硬件性能实验。文中区分已有文献事实、研究推论与待验证假设。第1例以已有SSO方法作机制组合重构，并将W4A4扩展作为待验证问题；其余案例也明确披露与前作的重合及尚未排除的新颖性风险。

文献与API链接保留在正文中。LitGraph使用临时公网地址，未来可能失效；已核实的论文标题、编号、原文链接和阅读记录仍保留在各案例中。该包仅收录当前12份正式正文与本总目录，原始响应、代码和早期草稿不在包内。
