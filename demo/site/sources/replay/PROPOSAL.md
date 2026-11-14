# 随机精确回放能否替代逐步保真？硬显存预算下的激活压缩校正

*示例03｜Rethinking default assumptions。研究提案，无模型实验结果。*

## 摘要

训练系统通常在保存中间激活与精确重计算之间取舍；激活压缩进一步允许有损反向传播。我们重新审视的默认要求是：为了可靠优化，是否必须让每一次反向所需的中间状态都保持高保真？随机自动微分和激活压缩已经否定这一要求的普遍性。本提案进一步研究，在所有步骤均满足硬显存上限的条件下，能否用便宜的压缩反传作为默认计算，并以低概率执行参考精度重计算，校正完整梯度残差。逆概率校正的无偏性是已知估计原理；潜在贡献在于概率、压缩程度与重计算计划的联合成本控制，以及对优化器非线性和偶发峰值的完整处理。只有在同显存、同墙钟与相同任务质量下优于已有激活压缩和checkpointing，才能支持这一设计。

## 1. 被重审的假设与证据

默认假设是“每次反传的状态必须精确恢复，否则只能接受系统性梯度偏差”。这不是所有现有方法都持有的假设：RAD已直接研究用随机导数估计换内存[1]；ActNN使用随机压缩和混合精度[2]；GACT明确指出一般非线性反向计算中，压缩器无偏并不意味着最终梯度无偏，并通过线性化处理误差[3]。Checkmate则在硬内存预算下规划张量重计算[4]。

本研究不重新提出“不需要每步精确梯度”。剩余问题是：**在允许有偏但廉价的压缩反传时，少量同批次参考重放能否更有效地管理偏差与方差，而且所有分支的峰值显存都可行？** 这区别于只提高位宽，也区别于定期执行一次高精度训练步骤后把它误当成无偏校正。

## 2. 目标与两种计算

固定当前参数 $\theta_t$、批次 $\xi_t$、dropout随机状态和其他前向可变状态。参考梯度 $g_t$是指定数值实现下的完整梯度，不指无限精度数学导数。压缩反传产生 $g_t^c$，可以有偏。为隔离激活存储，第一阶段保持前向函数和权重精度不变，只压缩保存给反向的上下文。

选择已知概率 $p_t\in[p_{min},1]$，在参考残差尚未被完整求得前抽取 $B_t\sim\operatorname{Bernoulli}(p_t)$；使用

$$
\widehat g_t=g_t^c+\frac{B_t}{p_t}(g_t-g_t^c).
\tag{1}
$$

当 $B_t=0$ 时执行压缩路径；当 $B_t=1$ 时，通过受内存约束的重计算获得同一批次、同一参数的参考梯度。条件于两条计算的潜在结果，且抽样概率正确时，

$$
\mathbb E_{B_t}[\widehat g_t]=g_t,\qquad
\operatorname{Cov}_{B_t}(\widehat g_t)
=\frac{1-p_t}{p_t}r_tr_t^\top,
\quad r_t=g_t-g_t^c.
\tag{2}
$$

式(1)是逆概率/多保真控制变量的直接应用，不作为新数学结果。$p_t$可以依赖此前残差统计或本步廉价观测，但不能在看到抽样事件后偷换概率。按固定周期偶尔用 $g_t$替代 $g_t^c$、忽略校正系数，通常仍有偏。

## 3. 硬内存约束如何进入设计

偶发参考计算必须同样满足内存上限，不能用“平均只有少数步骤超限”逃避显存要求。候选实现保留可重放的输入、随机状态及稀疏checkpoint；先完成压缩反传，释放压缩激活上下文，再进行参考重计算。梯度缓冲可就地缩放为 $(1-1/p_t)g_t^c$，随后累加 $g_t/p_t$，但需实际确认框架不会隐式保留两份梯度或两张计算图。

若参考路径的峰值记为 $M_f$，压缩路径为 $M_c$，额外重放元数据为 $M_r$，应检查实际计划的峰值而非简单相加或取平均。双重执行还必须防止BatchNorm统计、随机数和数据增强被推进两次。动态控制流、不可重放算子以及分布式归约需列为明确限制。

候选控制器以历史参考样本估计 $v_t\approx\mathbb E\|r_t\|^2$，联合选择压缩配置和 $p_t$：

$$
\min\; C_c+p_t C_f
\quad\text{s.t.}\quad
M_{peak}\le M_{max},\qquad
\frac{1-p_t}{p_t}v_t\le V_{budget}.
\tag{3}
$$

此处 $C_f$包含额外参考重计算；若分支能够共享部分计算，应以实测差分成本替换。估计 $v_t$本身有成本且存在抽样偏差，需要保留最低探测概率并报告不确定性。先用全模型Bernoulli开关验证正确性；不能未经推导把式(1)拆成逐层局部梯度修正，因为误差会沿反向链耦合。

## 4. 无偏梯度不等于原优化器轨迹

式(2)不保证Adam状态、学习曲线或最终模型与参考一致。取 $g=1$、$g^c=2$、$p=1/4$，估计器以概率3/4取2、概率1/4取−2：均值确为1，但平方均值为4，参考梯度平方为1。这会改变二阶矩。梯度裁剪也会破坏简单的条件无偏结论。

因此，首先使用SGD/线性动量隔离估计器，再把AdamW作为单独实验；不预设“无偏就能无损替换”。若要校正二阶矩，必须处理校正量可能为负等新问题，本提案不在未验证前加入该组件。

## 5. Previous work与剩余贡献

|工作|已覆盖的部分|需要证明的剩余部分|
|---|---|---|
|RAD[1]|随机AD、逆概率缩放、无偏性与内存—方差取舍|完整压缩梯度残差回放及其可执行硬预算计划|
|ActNN[2]|低比特保存激活与敏感性位宽分配|有偏廉价路径加参考校正是否超越其同成本前沿|
|GACT[3]|通用计算图压缩、在线敏感性、非线性偏差分析|不依赖线性化近似的残差校正，以及其方差代价|
|Checkmate[4]|重计算执行计划与硬内存约束|把随机参考频率纳入训练成本，而非只做确定性重计算|
|AC-GC[5]|按允许损失增长自适应压缩率|必须超越已有误差容忍方案，不能只新增一个采样超参|

最危险的等价风险是，它可能只是现有多保真估计器在激活压缩上的直接应用。如果系统成本模型、方差分配或理论边界都没有独立发现，迁移本身不足以构成新论文。

## 6. 可证伪预测与最小验证

在同一checkpoint与批次上重复抽样，先核对梯度均值、残差方向和式(2)；同时验证所有分支的真实峰值内存。再比较：完整checkpointing、GACT/ActNN、同平均位宽的混合精度、定期精确但不校正、等参考调用次数的式(1)、等墙钟增加batch/token的基线。

预测是：有系统性残差且可低成本重计算的层/模型应更受益；参考概率过小时方差应按式(2)上升；使用非线性优化器时可能出现即使均值正确仍退化的范围。若误差本来已无偏、精确回放不可在硬预算运行、均值检验失败、或等墙钟下更高位宽方案更好，则候选不成立。

记录达到同验证loss的时间、训练峰值而非仅激活字节、校正分支长尾延迟、残差方差、最终质量与稳定性。小网络可精确枚举；后续模型规模由实际资源决定，不假定具备特定GPU。

## 7. 论文潜力

本例体现从“每个状态都要保真”转到“估计器与资源预算共同设计”。已有文献完成了这个默认假设的第一次挑战，当前提案只在明确的残差回放问题上争取新的效率前沿或失效边界。关键风险是罕见大校正、二阶状态污染和参考路径峰值；无偏恒等式本身不代表训练优势。

## 参考文献与阅读范围

[1] **Randomized Automatic Differentiation**。[来源](https://arxiv.org/abs/2007.10412)；[LitGraph paper_id=242175](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/242175)。阅读：`source_card`，API abstract/insight/technique；arXiv HTML 404，未计全文。

[2] **ActNN: Reducing Training Memory Footprint via 2-Bit Activation Compressed Training**。[来源](https://arxiv.org/html/2104.14129)；[LitGraph paper_id=80813](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/80813)。阅读：`source_card`，API abstract/insight/technique/boundaries；原文已下载，本轮不计通读。

[3] **GACT: Activation Compressed Training for Generic Network Architectures**。[来源](https://arxiv.org/html/2206.11357)；[LitGraph paper_id=87292](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/87292)。阅读：`fulltext_selected`，原文§3.1–3.2、§4.2；API abstract/insight/technique/boundaries。

[4] **Checkmate: Breaking the memory wall with optimal tensor rematerialization**。[来源](https://arxiv.org/html/1910.02653)；[LitGraph paper_id=48423](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/48423)。阅读：`source_card`，API abstract/insight/technique/boundaries。

[5] **AC-GC: Lossy Activation Compression with Guaranteed Convergence**。[来源](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/173423)；[LitGraph paper_id=173423](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/173423)。阅读：`source_card`，API abstract/insight/technique/boundaries；来源摘要。

整理日期：2026年11月13日（Asia/Shanghai）。检索、候选调整与覆盖缺口见同目录PROCESS.md。

## LitGraph证据索引

- [efficient-model-compression-P0039](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0039)：长生命周期激活、重计算与近似误差共同制约受限训练预算。
- [efficient-model-compression-P0172](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0172)：低内存方法需统一预算和收敛代价，避免只看存储字节。
- [efficient-model-compression-I0069](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0069)：激活压缩、重计算与可逆恢复提供不同误差/计算取舍。
- [automatic-and-physics-differentiation-I0026](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/automatic-and-physics-differentiation-I0026)：聚合条目提供随机AD等来源；具体RAD机制仍由242175卡片核验。

以上条目用于来源追溯；并非本提案已被证明或问题尚未解决的凭据。
