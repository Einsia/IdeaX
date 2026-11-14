# 压缩验证状态还能保持参考分布吗？带证书与精确回退的投机解码

*示例05｜Extending capability boundaries。算法与边界研究提案，无模型实验结果。*

## 摘要

精确投机解码通过草稿提案与目标分布校正加速生成，通常依赖目标验证器提供可信的条件概率。量化缓存和分级验证已经减少计算，但接近原模型的任务质量并不等同于精确保持其输出分布。本提案研究：当验证器也使用压缩或近似状态时，能否通过可信概率区间判定部分接受事件，并在不确定时恢复参考计算，从而把精确投机采样的能力边界扩展到受内存与带宽限制的验证过程。核心困难不仅是当前token的判定，还包括拒绝后的残差采样和已接受token的后续缓存状态。提案将这三部分作为同一正确性目标；证书构造成本或回放频率过高时，即判定效率路线失败。

## 1. 既有保证及其边界

标准投机采样对草稿分布 $q$与目标分布 $p$采用 $\min(1,p/q)$接受概率，并在拒绝时从正残差分布采样，保证输出来自目标分布[1]。QuantSpec已有分层INT4/INT8 KV缓存及回滚缓冲；其原文验证目标采用INT8 KV，并以任务质量接近FP16作评估[2]。FAFO已有有损缓存候选与无损验证[3]。因此，“压缩加验证”和“动态精度”本身不是新贡献。

我们要跨越的边界更窄：**目标验证器的近似状态能否直接支持某些严格正确的接受/拒绝事件，而非每次都加载完整参考状态？** 这不同于根据置信度预测接受率，也不同于MARS等放宽接受准则的方法[4,5]。

首先定义参考：固定权重、数值格式、算子、缓存构造和采样后处理的指定实现 $p_{ref}(\cdot|h)$。研究保证针对这一参考分布，不声称等于实数无限精度模型，也不把不同数值目标的PPL接近称作分布相同。

## 2. 接受事件的区间判定

草稿实际按 $q(y|h)$生成候选 $y$，其概率必须正确记录；压缩验证器提供保证包含 $p_{ref}(y|h)$的区间 $[\ell_y,u_y]$。定义

$$
a_L=\min(1,\ell_y/q_y),\qquad a_U=\min(1,u_y/q_y).
\tag{1}
$$

抽取并固定一次 $U\sim\operatorname{Uniform}(0,1)$：

- $U\le a_L$：可确认与精确规则相同的接受。
- $U>a_U$：可确认与精确规则相同的拒绝。
- 其他情况：提高精度、取回状态或重放参考计算，缩小区间；始终复用同一个 $U$。

若无法进一步得到有效区间，则调用完整参考验证器。重复抽取 $U$、依据结果选择新的阈值或用经验置信区间替代保证区间，都不能直接继承精确性。

例如已获得全词表logit包络 $L_v\le z_v\le U_v$，可构造

$$
\ell_y=\frac{e^{L_y}}{e^{L_y}+\sum_{v\ne y}e^{U_v}},\quad
u_y=\frac{e^{U_y}}{e^{U_y}+\sum_{v\ne y}e^{L_v}}.
\tag{2}
$$

区间算术与softmax单调性是已知工具，不作为新发现；需要研究的是如何从缓存误差得到够紧、成本够低且覆盖实际数值实现的包络。不能只约束候选logit而忽略归一化分母。top-k/top-p、温度、屏蔽等采样处理也须纳入包络；第一版可固定温度且禁用支持集合不确定的截断，以验证基础条件，最终不能将该限制隐去。

## 3. 三个必须同时闭合的正确性环节

**当前判定。** 包络有效时，式(1)与原始拒绝采样使用同一事件。退化区间 $[0,1]$虽然正确，但可能完全无用。

**拒绝后的token。** 一旦拒绝，需要从

$$r(v)=\frac{[p_{ref}(v|h)-q(v|h)]_+}{\sum_w[p_{ref}(w|h)-q(w|h)]_+}$$

采样。知道候选被拒绝并不够。初始正确实现对此直接恢复精确目标向量；只有另有严格的区间分类采样算法时，才进一步节省这一成本。全部接受后的bonus token也需要来自参考分布；可以选择不额外生成bonus token、进入下一轮，但必须明算失去的吞吐收益。

**后续缓存。** 当前接受事件正确，不意味着近似运行生成的KV就等于参考KV。若将这些KV不加管理地写回，下一步的目标已经改变。系统需区分精确checkpoint、附误差包络的暂存状态，以及可重放的token/RNG历史。未来判定必须把累计误差纳入证书；证书变松时，从最近精确状态重放合法前缀。不能假设从未算过的高精度残差免费存在。

只有这三部分都成立，才能在逐步条件分布上建立保持 $p_{ref}$的归纳论证。若证书仅以概率 $1-\delta$成立，得到的是可能带误差的概率保证，不应继续称为严格分布精确。

## 4. 候选系统与成本条件

压缩状态驻留加速设备，精确旧状态可置于较慢存储；新产生的近似状态保留可重放依赖。以小块/层级误差界指导精度提升，并优先精化最影响当前接受区间的部分。实际实现应记录证书计算、数据移动、精确重放、残差采样和缓存修复的全部成本。

必要的收益条件是

$$C_{approx}+C_{cert}+\Pr(\text{refine})C_{refine}+C_{state\ repair}<C_{full\ verification},$$

并满足峰值设备内存预算。该式只是成本核算，不是已证明速度优势。若每个已接受token最终都必须立即精确重算全部层，系统很可能比标准验证更慢；这正是需要先验证的停止条件。

## 5. Previous work比较

|工作|重合|本提案必须增加的部分|
|---|---|---|
|经典Speculative Decoding[1]|接受和残差采样保证|降低获得验证信息的成本，不改变目标|
|QuantSpec[2]|分层缓存、低精度草稿与较高精度目标|明确相对哪个参考分布精确；处理验证器自身状态误差|
|FAFO[3]|压缩缓存候选加无损验证|避免每次完整参考验证的可认证条件；全文覆盖仍待排除|
|Speculative Verification[4]|预测接受率、调整验证预算|数值包含证书不同于统计接受预测|
|MARS[5]|利用局部margin减小回退|不能放宽原始概率规则|
|VIA-SD[6]|多级验证器与计算分配|必须同时保持参考概率和缓存状态；分级本身不新|

## 6. 可证伪验证与停止条件

首先在可枚举的小词表模型上逐项证明/计算输出概率，检查接受、拒绝、bonus、随机数复用和状态重放。固定 $p=(0.6,0.3,0.1)$、$q=(0.2,0.5,0.3)$可精确枚举传统校正结果作为基本核对；这不等于Transformer上的保证。另做长序列状态测试，故意构造“当前判定相同但近似KV漂移”的反例。

然后测量真实模型的证书宽度、可直接判定比例、重放距离与端到端延迟。必须与完整参考验证、QuantSpec、仅使用缓存近似的有损版本、使用精确概率但人工省略计算的oracle上界分别比较。所有性能比较统一参考目标、采样规则、输入长度和并发。

若包络不包含真实参考结果、累计状态无法闭合、分布校正不完整，则正确性失败；若有效包络普遍过松或修复成本抵消收益，则效率失败。样本频率检验只能发现错误，不能替代数学保证。greedy一致性也不能代表随机采样分布一致。

## 7. 论文潜力

这是高风险的能力边界扩展：把“压缩只能在草稿或近似目标中使用”推进到“部分验证事件可在近似状态下认证”。现成区间公式不是贡献；关键是状态闭合、可用证书和成本边界。即使得到否定结果，若能明确证明在哪类压缩状态和带宽条件下无法获利，也有机制研究价值，但不能把失败的系统包装成已实现的无损加速。

## 参考文献与阅读范围

[1] **Fast Inference from Transformers via Speculative Decoding**。[来源](https://arxiv.org/html/2211.17192)；[LitGraph paper_id=95530](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/95530)。阅读：`fulltext_selected`，原文§2.1–2.3、Algorithm 1；API详情。

[2] **QuantSpec: Self-Speculative Decoding with Hierarchical Quantized KV Cache**。[来源](https://arxiv.org/html/2502.10424)；[LitGraph paper_id=91862](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91862)。阅读：`fulltext_selected`，原文§4.1–4.3、Table 2；API详情。

[3] **FAFO: Lossy KV Cache Compression for Lossless Inference Acceleration via Draftless Fumble Decoding**。[来源](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/99385)；[LitGraph paper_id=99385](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/99385)。阅读：`source_card`，API abstract/insight/technique；来源摘要。

[4] **Speculative Verification: Exploiting Information Gain for Speculative Decoding**。[来源](https://arxiv.org/html/2509.24328)；[LitGraph paper_id=241414](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/241414)。阅读：`source_card`，API abstract/insight/technique/boundaries。

[5] **{MARS}: Unleashing the Power of Speculative Decoding via Margin-Aware Verification**。[来源](https://arxiv.org/html/2601.15498)；[LitGraph paper_id=240026](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/240026)。阅读：`source_card`，API abstract/insight/technique/boundaries。

[6] **VIA-SD: Verification via Intra-Model Routing for Speculative Decoding**。[来源](https://arxiv.org/html/2606.12243)；[LitGraph paper_id=103786](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103786)。阅读：`source_card`，API abstract/insight/technique/boundaries。

整理日期：2026年11月13日（Asia/Shanghai）。检索、候选调整与覆盖缺口见同目录PROCESS.md。

## LitGraph证据索引

- [speculative-decoding-P0013](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0013)：有损缓存/跳层与历史状态失真影响生成可靠性。
- [speculative-decoding-P0030](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0030)：长上下文注意力与缓存读写使验证越来越昂贵。
- [speculative-decoding-I0003-s1](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0003-s1)：草稿—目标验证与多种解码机制的来源导航。
- [speculative-decoding-I0018](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0018)：无偏生成与拒绝代价/分布偏差存在约束，不能任意放宽接受。

以上条目用于来源追溯；并非本提案已被证明或问题尚未解决的凭据。
