# FP4训练振荡来自哪里？区分权重移动、共享尺度变化与功能扰动

*示例04｜Diagnosis and reattribution。机制诊断提案，无模型实验结果。*

## 摘要

低比特训练中，连续主权重的小幅变化可能伴随量化权重的大幅跳变。已有工作将这一现象与阈值附近的振荡联系起来，也指出可学习尺度可能加剧问题。本提案进一步区分归一化变量 $w/s$ 的两种变化来源：参数本身移动与共享量化尺度变化。我们以同一检查点的四种受控重放分解实际量化输出和损失变化，并将码字切换与函数扰动分开评价。目标不是预先否定权重振荡解释，而是检验共享尺度是否在某些FP4格式、分组和训练阶段中制造同步误差，导致不稳定被错误地归因于优化器步长或单权重阈值行为。研究价值取决于因果干预、跨设置可复现性，以及据此选择的修正是否优于现有振荡抑制方法。

## 1. 现有解释与待诊断问题

Overcoming Oscillations已分析QAT中阈值反复跨越，并提出阻尼与冻结[1]。OFQ明确指出可学习缩放因子会加剧振荡[2]。TetraJet把主权重、量化权重和固定输入下的激活变化联系起来，并提出Q-EMA与Q-Ramping[3]；TetraJet-v2进一步以轨迹变化比识别风险并重置主权重[4]。

因此，“量化权重会振荡”和“尺度会影响振荡”都不是新发现。剩余问题是：**在组共享尺度的FP4训练中，观测到的变化有多少由主权重移动造成，有多少由尺度重估造成；哪些变化真正扰动下游计算？** 如果原因不同，仅降低参数学习率或重置个别主权重可能不是合适的干预。

## 2. 三个不能混用的量

令反量化后的实际权重为 $\widehat W=Q(W;s)$。区分：

1. 主权重变化 $W_t-W_{t-1}$。
2. 整数量化标签变化；标签的数值含义依赖当前尺度与零点。
3. 实际反量化矩阵及固定输入下的输出变化。

例如同一个整数标签2在尺度0.1和0.11下分别表示0.2和0.22，标签未变但函数发生变化；反之，尺度调整时标签不同也未必意味着同等大小的实际扰动。判断振荡应记录反量化数值、尺度与固定输入输出，而不能只数bit/code翻转。

对归一化变量作局部一阶展开，

$$
\Delta(W/s)\approx\Delta W/s-W\Delta s/s^2.
\tag{1}
$$

式(1)解释了为何同一个阈值跨越可能由分子或分母触发，但它不直接量化不连续舍入后的误差，也不能当作因果证明。

## 3. 四点受控重放

保存相邻状态 $(W_0,s_0)$与$(W_1,s_1)$，在同一输入、同一随机状态、相同其他层参数下，构造

$$
Z_{00}=Q(W_0;s_0),\quad Z_{10}=Q(W_1;s_0),
\quad Z_{01}=Q(W_0;s_1),\quad Z_{11}=Q(W_1;s_1).
\tag{2}
$$

对张量、固定输入层输出，或固定其余计算的任务损失，采用对称分解

$$
D_W=\tfrac12[(Z_{10}-Z_{00})+(Z_{11}-Z_{01})],
\quad
D_s=\tfrac12[(Z_{01}-Z_{00})+(Z_{11}-Z_{10})].
\tag{3}
$$

它满足 $D_W+D_s=Z_{11}-Z_{00}$；同时报告交互项 $I=Z_{11}-Z_{10}-Z_{01}+Z_{00}$。这是标准两因素差分/对称归因，不是新的统计公式。对张量必须先分解再分别测量范数，不能声称范数贡献简单相加。负贡献表示局部抵消，不代表不可能。

若采用随机舍入，四种重放应使用共同随机数并重复估计期望与不确定性；一次随机实现的差分不能被当成稳定的成因份额。

尺度往往是权重或激活的确定函数。式(2)的交叉组合是人为干预，应使用量化器允许的固定尺度模式，并记录溢出、裁剪和范围失配；不将不合法状态的损失归咎于原算法。对激活，先固定上游输入分析局部直接作用，再进行整网同步重放，防止将上游变化重复归因。干预的局部效应也不自动等于长期训练的总因果效应。

## 4. 竞争假设与干预

**H_W：参数阈值振荡主导。** 固定尺度后，量化输出的大部分异常变化仍保留；减小对应主权重扰动或执行OsciReset能恢复稳定。

**H_S：尺度事件主导。** 保持主权重不变、仅重放尺度变化，能复现组内同步输出跳变；保持尺度更新幅度/分布而打乱事件位置后，模式随之改变。此处不预设该假设成立。

**H_E：共同外因主导。** 离群激活、数据切换、裁剪或梯度异常同时影响尺度与损失，尺度只是伴随变量。此时直接尺度干预无法在合理裁剪预算下恢复质量。

实验先使用短窗口、训练状态完全可重放的诊断，不立即添加一个“尺度平滑优化器”。随后比较冻结尺度、延迟/平滑尺度、同MSE尺度方案、主权重重置和组边界重排。若冻结尺度只是减少了裁剪覆盖，或Half-S类改进通过更好的单步表示解释全部收益，就不能声称发现了新的时序机制。Half-S[5]与Quartet II[6]均为需要区分的尺度/舍入近邻。

## 5. 实验设计

分别设置W4A16、W16A4、W4A4，以区分权重和激活因素；INT4、MXFP4、NVFP4单列，不把所有尺度更新规则合并。保留共同的梯度、累加器、主权重精度和优化器设置。扫分组大小、训练阶段、共享尺度更新周期及数据分布变化，记录这些设置是否改变主要归因来源。

关键对照包括现有Q-EMA、Q-Ramping、OsciReset、固定尺度量化、不同尺度选择规则，以及相同主权重轨迹上的离线量化回放。后者只能解释瞬时数值机制，不能声称已经证明完整训练收益。最终再做同token、同墙钟和同搜索预算的训练比较。

指标包括实际反量化权重变化、固定输入输出漂移、梯度方向偏差、组内跨坐标同步性、裁剪比例、验证loss和loss-spike频率。提前定义尖峰阈值和事件窗口，使用多个种子并报告不确定性，避免从事后挑选的异常步构造故事。

## 6. 可证伪预测

若H_S成立，量化尺度阶跃的时间与组内同步扰动应具有可重放的对应关系，且在控制主权重变化后仍可复现；这种作用应随尺度共享粒度、量化格式和尺度决策边界而改变。若只在原始码字标签中出现、在反量化输出中消失，则属于表示层面的假象。

如果固定尺度后问题完全不减、因果交换不能复现尖峰、或改变尺度时序的效果可以被单步MSE与裁剪完全解释，则放弃尺度事件主导的结论。若相反发现H_W主导，应保留为对既有阈值机制的支持，不能为追求“重新归因”强行颠倒原因。

## 7. 剩余贡献与论文潜力

独立价值可能来自一套可复现的因果诊断协议、不同FP4训练设置的机制分区，以及按原因选择干预的证据。没有证据前，不提出新的“普适稳定优化器”。最薄弱处是OFQ和TetraJet已覆盖部分尺度与阈值解释；只有组共享微尺度、实际函数扰动与长期结果之间建立新的、可检验联系，才超出已有分析。

## 参考文献与阅读范围

[1] **Overcoming Oscillations in Quantization-Aware Training**。[来源](https://arxiv.org/html/2203.11086)；[LitGraph paper_id=87671](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/87671)。阅读：`source_card`，API abstract/insight/technique/boundaries。

[2] **Oscillation-free Quantization for Low-bit Vision Transformers**。[来源](https://arxiv.org/html/2302.02210)；[LitGraph paper_id=96191](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/96191)。阅读：`source_card`，API abstract/insight/technique/boundaries。

[3] **Oscillation-reduced mxfp4 training for vision transformers**。[来源](https://arxiv.org/html/2502.20853)；[LitGraph paper_id=91569](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91569)。阅读：`fulltext_selected`，原文§4–6，式(10)及Q-Ramping说明；API卡片。

[4] **TetraJet-v2: Accurate NVFP4 Training for Large Language Models with Oscillation Suppression and Outlier Control**。[来源](https://arxiv.org/html/2510.27527)；[LitGraph paper_id=103182](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103182)。阅读：`fulltext_selected`，原文§3.1–3.3、Algorithm 1；API卡片。

[5] **Half-{S}: Halving the Scale for Near-Lossless 4-Bit {LLM} Training**。[来源](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/239846)；[LitGraph paper_id=239846](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/239846)。阅读：`source_card`，API abstract/insight/technique/boundaries；来源摘要。

[6] **Quartet II: Accurate LLM Pre-Training in NVFP4 by Improved Unbiased Gradient Estimation**。[来源](https://arxiv.org/html/2601.22813)；[LitGraph paper_id=102046](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102046)。阅读：`source_card`，API abstract/insight/technique/boundaries。

整理日期：2026年11月13日（Asia/Shanghai）。检索、候选调整与覆盖缺口见同目录PROCESS.md。

## LitGraph证据索引

- [efficient-model-compression-P0033](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0033)：动态范围、细小更新丢失和系统量化误差影响收敛。
- [efficient-model-compression-I0036](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0036)：包含TetraJet、Half-S、Quartet等数值来源，需逐篇核验。

以上条目用于来源追溯；并非本提案已被证明或问题尚未解决的凭据。
