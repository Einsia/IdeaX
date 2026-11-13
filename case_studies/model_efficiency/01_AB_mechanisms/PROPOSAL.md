# 谱下降与权重谱约束的协同：面向W4A4训练的研究提案

*探索模式：A+B mechanisms。本文为研究提案，无实验结果；联合谱球面机制归属于已有SSO工作[1]，拟研究贡献是该机制在W4A4计算中的作用与适用边界。*

## 摘要

低精度训练的稳定性同时受到参数更新与前向数值表示的影响。谱范数约束下的矩阵更新能够控制单步变化，却不单独保证训练过程中权重的放大尺度保持固定；权重归一化能够限制尺度，但未必在更新方向的求解中利用这一约束。本提案以谱球面优化器SSO[1]为A+B机制实例，将谱最陡下降与权重谱约束放入同一个局部优化问题，并研究这种耦合能否降低W4A4训练的额外损失。核心假设是，切向可行的谱更新能够减少增益漂移与尺度失配，其收益应超过简单的更新后归一化。由于连续权重约束不必被量化后的实际计算继承，我们将分别测量主权重、量化权重与激活的变化，并通过精度因子实验和等成本对照识别协同作用及失效条件。

## 1. 研究问题与相关工作

对线性层 $y=Wx$，谱范数给出输入输出增益上界 $\|Wx\|_2\le\|W\|_2\|x\|_2$。对更新施加谱范数约束，控制的是参数的一步变化；对权重施加约束，控制的是当前映射的放大尺度。这两个对象在长期训练中并不等价。

Muon类方法可解释为谱范数下的局部最陡下降或非欧信赖域更新[2]。Scion将范数球上的线性最小化预言机用于神经网络优化，同时包含受约束与无约束版本[3]。Nero则通过逐神经元的零均值与L2约束说明，优化器可以显式维护权重可行域[4]；这种逐神经元约束与矩阵谱范数约束不同。SSO已经把更新谱尺度、权重谱尺度、切向方向求解与回缩结合起来[1]。

本提案不重新主张上述机制的原创性，而考察一个具体问题：**在相同量化器与预算下，谱更新和权重谱约束的联合求解，能否比两者的简单串联更有效地缩小W4A4相对高精度训练的差距？**

这一问题不能由已有SSO结果直接回答。其原文主要采用BF16训练，并将FP8/NVFP4列为未来方向[1]。与此同时，QuEST已通过分布变换与信任梯度稳定低比特权重和激活训练[5]，TetraJet-v2已处理NVFP4中的权重振荡与离群值[6]，归一化架构也已有4-bit训练结果[7]。因此，验证必须隔离优化器耦合、量化规则和架构变化的作用。

## 2. A+B机制与联合更新

设 $W\in\mathbb R^{d_{out}\times d_{in}}$，$M$为局部动量矩阵，$\langle\cdot,\cdot\rangle$为Frobenius内积，矩阵 $\|\cdot\|_2$表示谱范数。

**机制A：谱范数下的方向选择。** 在单位谱范数预算中选择

$$
\Phi_A\in\arg\max_{\|\Phi\|_2\le1}\langle M,\Phi\rangle.
$$

典型方向是矩阵极因子 $\operatorname{msign}(M)=U_rV_r^\top$，其中 $r$为秩。它利用矩阵结构决定更新，但这个子问题没有要求 $W$留在固定谱尺度上。

**机制B：权重谱尺度的可行性。** 令

$$
\mathcal S_R=\{W:\|W\|_2=R\},\qquad
R=c\sqrt{d_{out}/d_{in}},
$$

其中 $c$为模块尺度参数。此约束限制线性层的最大增益，但不能直接保证整个非线性残差网络稳定，也不能保证激活分布适合4-bit表示。

**耦合方式。** 当 $W$的最大奇异值单重时，令 $\Theta=u_1v_1^\top$。沿 $-\Phi$的更新若满足 $\langle\Theta,\Phi\rangle=0$，则权重谱范数的一阶变化为零。于是局部更新满足

$$
\max_\Phi\langle M,\Phi\rangle
\quad\text{s.t.}\quad
\|\Phi\|_2\le1,\qquad
\langle\Theta,\Phi\rangle=0.
\tag{1}
$$

式(1)为便于处理退化情形采用单位球表述；SSO原文使用单位谱范数方向，在通常非退化条件下于边界求解。其典型求解形式为

$$
\Phi(\lambda)=\operatorname{msign}(M+\lambda\Theta),\qquad
\langle\Theta,\Phi(\lambda)\rangle\approx0.
\tag{2}
$$

得到方向后，用谱回缩修正有限步长误差。以更新后回缩的概念形式表示为

$$
\widetilde W=W-\eta R\Phi(\lambda),\qquad
W^+=R\,\widetilde W/\|\widetilde W\|_2.
\tag{3}
$$

式(2)–(3)说明了组合的实质：**B改变A的可行域和方向解，而非仅在A之后增加归一化。** 实现复现应遵循原文的回缩安排、动量与求解精度；不把概念形式当作逐行相同的实现。最大奇异值重合时谱范数一般不光滑，有限谱间隙、幂迭代与极分解近似也会影响约束残差。

## 3. 从连续谱约束到W4A4计算

记实际前向使用的反量化权重与激活为 $\widehat W=Q_4(W)$、$\widehat x=Q_4(x)$，相应误差为 $E_W=\widehat W-W$、$e_x=\widehat x-x$。在精确累加的理想化下，

$$
\widehat W\widehat x-Wx=We_x+E_Wx+E_We_x,
$$

从而

$$
\|\widehat W\widehat x-Wx\|_2
\le R\|e_x\|_2+\|E_W\|_2\|x\|_2+\|E_W\|_2\|e_x\|_2.
\tag{4}
$$

谱球面约束控制了误差放大系数 $R$，却没有独立控制量化误差、裁剪、尺度更新或残差流。实际低精度累加还会引入额外误差。与此同时，

$$
\big|\|Q_4(W)\|_2-R\big|\le\|E_W\|_2
$$

仅给出扰动界，不表示量化权重严格位于同一谱球面上。式(4)据此导出本提案的分析重点：连续几何约束改善的部分，是否恰好对应W4A4训练中的主要误差来源。

我们预先区分四项假设：

- **H1，尺度控制：** 联合约束减少权重谱尺度和相对更新尺度的漂移。
- **H2，数值传递：** 尺度控制能够降低实际量化权重与激活的误差或损失尖峰，而不只稳定高精度主权重。
- **H3，耦合增益：** 在相同谱半径与预算下，完整SSO优于只做归一化的MuonSphere。
- **H4，量化特异性：** 改进缩小量化损失差距，而非仅复制高精度下的一般优化优势。

其中量化损失差距定义为

$$
\Delta_q(o)=L_{\mathrm{W4A4}}(o)-L_{\mathrm{BF16}}(o),
$$

并为每种优化器 $o$建立相同预算下的高精度参照。

## 4. 验证方案

实验首先在小矩阵上以精确SVD验证切向残差、回缩误差和谱间隙效应，随后在小型decoder模型上比较BF16、W4A16、W16A4与W4A4。模型规模可从30–150M开始，是否扩展由实际资源和前期证据决定。INT4、MXFP4和NVFP4分别报告；反向计算、累加器、主权重与优化器状态的精度另行注明。第一阶段保持这些环节一致，以隔离前向量化。

|方法|承担的对照作用|
|---|---|
|AdamW|常用优化基线|
|Muon|机制A：谱更新|
|带相同谱回缩的SGD/动量SGD|机制B的诊断；匹配更新预算并说明几何差异|
|MuonSphere|A后接B的简单组合|
|完整SSO|A与B的联合方向求解|
|欧氏切向投影后再msign|检查操作顺序和约束失配|
|精确SVD与不同近似精度|分离算法机制和求解误差|

上述方法使用相同数据顺序、模块划分、量化规则和超参数搜索预算，并采用多个随机种子。QuEST与TetraJet类数值方案作为额外对照或共同训练配置[5,6]；nGPT/NVFP4由于改变架构，单列为相关参考[7]。只有前期机制成立，才进入原生低精度前后向及内核阶段。

主要指标包括验证loss/PPL、$\Delta_q$、发散比例、预先定义的loss-spike频率和稳定学习率区间；诊断指标包括主权重及量化权重谱范数、切向残差、量化信噪比、裁剪比例、码字切换率与残差激活的最大值/RMS比。所有结果同时按同token和同墙钟预算比较，计入求根、幂迭代、通信与高精度计算成本。

## 5. 可证伪性、预期贡献与限制

若主权重谱稳定而实际量化计算没有改善，则H2失败；若MuonSphere解释全部收益，则未证明额外切向耦合在W4A4中的价值；若两种精度的损失同步改善而 $\Delta_q$不变，则不支持量化特异性解释。收益在统一搜索预算或运行时间后消失，也应作为否定结果报告。

本研究拟形成的贡献是：识别联合谱约束作用于量化误差的具体环节；区分权重归一化与切向耦合的贡献；建立连续谱约束向实际量化计算传递的适用边界。SSO本体、谱LMO与权重硬约束均属于前作，不能列为本研究的新贡献。若仅得到某一任务上的迁移收益而无机制或边界发现，应将结果定位为应用验证。

主要风险包括量化误差由残差流或梯度偏差主导、固定谱半径限制有效表示、最大奇异值附近的数值不稳定，以及求解开销抵消训练收益。当前尚无实验支持上述假设，也未排除SSO低精度后续工作与相关量化控制方法的重合。

## 参考文献

[1] **Controlled LLM Training on Spectral Sphere**. [原文](https://arxiv.org/html/2601.08393)；[LitGraph paper_id=98525](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/98525)。

[2] **Understanding Gradient Orthogonalization for Deep Learning via Non-Euclidean Trust-Region Optimization**. [原文](https://arxiv.org/html/2503.12645)；[LitGraph paper_id=200716](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200716)。

[3] **Training Deep Learning Models with Norm-Constrained LMOs**. [原文](https://arxiv.org/html/2502.07529)；[LitGraph paper_id=92541](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/92541)。

[4] **Learning by Turning: Neural Architecture Aware Optimisation**. [原文](https://arxiv.org/html/2102.07227)；[LitGraph paper_id=81314](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/81314)。

[5] **Quest: Stable training of llms with 1-bit weights and activations**. [原文](https://arxiv.org/html/2502.05003)；[LitGraph paper_id=91868](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91868)。

[6] **TetraJet-v2: Accurate NVFP4 Training for Large Language Models with Oscillation Suppression and Outlier Control**. [原文](https://arxiv.org/html/2510.27527)；[LitGraph paper_id=103182](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103182)。

[7] **Normalized Architectures are Natively 4-Bit**. [原文](https://arxiv.org/html/2605.06067)；[LitGraph paper_id=205104](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205104)。

