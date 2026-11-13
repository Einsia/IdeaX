# 回滚感知的MoE专家缓存：分开验证期必需访问与提交后复用

*示例06｜Free exploration。系统研究提案，无模型训练或硬件基准结果。*

## 摘要

稀疏MoE投机解码会为多个候选token加载专家，其中部分候选最终被拒绝。专家访问频率既表示本轮验证的真实计算需求，也可能作为下一轮缓存价值的预测，但这两个用途并不相同。本提案在不改变目标路由、专家权重或采样规则的条件下，研究是否应把专家页面的“本轮必须执行”与“提交后值得保留”分成两个状态。验证期间服务所有实际需要的专家；验证结束后利用接受前缀、回退分支和跨步复用统计决定缓存准入与保留。已有系统已使用草稿前瞻、生命周期驱逐和提交概率加权，故新颖性不能建立在这些单项概念上。潜在价值在于严格保持目标模型行为时，回滚信息是否能减少无效缓存驻留并改善实际暴露的传输等待。

## 1. 自由探索如何形成问题

本例从efficiency领域概览进入MoE动态访存，并未预先要求某种机制组合。最初候选是“用投机草稿预测专家需求”；查新发现MoE-SpAc已经明确把投机解码用作内存管理传感器[1]。进一步考虑按候选接受概率加权时，又发现AcceptMoE已有提交概率加权需求[2]。SpecMD也已区分当前周期与陈旧专家，并提供Least-Stale驱逐[3]。

这些发现迫使问题转向一个执行语义上的区别：**某个候选最终不被接受，并不意味着验证这个候选时不需要它调用的专家；但完成验证以后，这次访问是否应继续提高专家的缓存优先级？** 本提案只研究后一个问题，不再重复前瞻信号或加权路由的概念。

## 2. 保持目标行为的约束

固定目标模型的原始top-k路由和专家计算。所有在当前验证图中实际请求的专家均必须以规定精度执行；缺页时按需读取，不能因低提交概率而跳过、替换或改变路由logit。缓存策略只决定数据驻留位置和传输时序。

AcceptMoE原文明确说明，其可选专家集合会改变router logits，因此属于近似方法[2]。CECAR与CommitMoE同样涉及路由或专家选择的改变[4,5]，不能直接用它们的速度作同语义优势证明。反过来，保持模型语义本身也不新：SpecMD的standard routing+fetch和ZipMoE均提供相关基线[3,6]。

若改变批处理顺序导致非确定性数值差异，应单独测量；不声称任意调度下都自动逐位一致。

## 3. 两种专家价值

令 $\mathcal V_t$为本轮验证的候选图，$R(n)$为候选节点 $n$实际调用的专家集合。当前执行所需专家为

$$E_t^{exec}=\bigcup_{n\in\mathcal V_t}R(n).\tag{1}$$

式(1)由实际验证计划决定，不能乘以接受概率后就删除低权重专家。树验证的互斥路径在最终输出上互斥，但其验证计算可能同时发生。

验证得到已提交前缀 $H_t$和回退/bonus token后，定义未来短窗口内保留专家 $e$能减少的暴露等待为

$$V_t^{keep}(e)=\mathbb E[\Delta T_{stall}(e)\mid H_t,\text{路由历史与缓存状态}].\tag{2}$$

式(2)是未来用途的预测，不等于本轮访问次数。专家若仅被拒绝分支访问，可以降低其驻留优先级，但不能断言其下步不会再次被用到。已提交前缀使用过的专家也未必有高复用价值。学习目标应是下一窗口的实际访问和等待，而不是把“被提交”硬编码成永远保留的标签。

## 4. 候选策略：临时服务与提交后准入

系统在统一缓存内维护两个逻辑状态，而非必然划出两个固定物理区：

- **执行状态。** 当前验证仍需使用的页面被暂时固定，优先满足执行依赖；预测错误不改变模型计算。
- **保留状态。** 最后一次当前使用结束后，页面依据式(2)和存储字节、预计搬运/解压成本进入长期缓存竞争。

候选保留分数可写成

$$S_t(e)=\frac{\widehat{\Pr}(e\text{在下一窗口被使用})\;\widehat{C}_{miss}(e)-\widehat C_{admit}(e)}{\operatorname{bytes}(e)}.
\tag{3}$$

这是常见缓存价值/成本思想的实例，不是新公式。真正待检验的特征是：验证期实际访问、提交前缀访问、仅拒绝分支访问，以及新的回退token是否对专家需求预测提供了额外信息。先用少量计数与简单模型检验，不以复杂学习器遮盖信号不足。

验证结果在整块结束后才可知；提前调度只能使用此前观测或预测，不能偷用未来真实接受结果。若采用在线学习，记录特征可用时刻，验证后的实际结果只用于下一决策或训练标签。相同专家的多次访问合并生命周期，避免过早释放仍被其他token使用的页面。

## 5. 与最近邻的实质关系

|工作|已覆盖|本提案需额外证明|
|---|---|---|
|MoE-SpAc[1]|投机频率、预取/驱逐统一效用、异构调度|将验证使用与未来保留分离是否提供增量收益|
|AcceptMoE[2]|提交概率加权专家需求、缓存感知裁减|只用于准入/驱逐且不改路由时是否仍有收益；权重思想本身不新|
|SpecMD[3]|standard/fetch及Least-Stale生命周期管理|回滚标签是否超越周期/层位置与时间局部性|
|CECAR、CommitMoE[4,5]|缓存相关路由和避免错误预取回退|在固定原目标计算下比较，不能通过换模型买速度|
|ZipMoE[6]|无损压缩、调度与分层缓存|传输/解压成本与层次存储必须计入|
|Cascade[7]|根据token收益和验证成本调节草稿长度|首先固定草稿策略，防止把窗口调度收益算成缓存收益|

如果已有系统的策略在等信息、等内存下能够复现全部效果，应将结果定位为组合实现或负面边界，而非新机制。

## 6. 预测、实验与可证伪性

核心假设是：拒绝分支造成的访问会在某些模型和任务中污染后续缓存优先级，而提交/回退事件包含额外预测信息。该假设不是所有工作负载的事实。专家路由可能高度共享，使接受与拒绝分支几乎相同；此时新标签不应带来收益。

先收集原始路由与精确验证轨迹，进行不改变token序列的离线缓存回放。所有策略使用相同草稿、接受结果、缓存字节和传输模型；比较LRU/LFU、Least-Stale、未区分分支的投机频率效用、提交概率加权但忽略本轮生命周期、完整候选，以及知道未来访问的oracle上界。打乱“提交/拒绝”标签应削弱真正依赖该信息的收益。

离线回放只验证策略与轨迹关系，不能证明墙钟收益。通过后再实现在线准入策略，实测暴露等待、峰值缓存/暂存内存、总传输字节、优化器以外的调度CPU开销、tokens/s和尾部延迟。改变草稿准确率、树宽、拒绝位置、缓存容量及I/O带宽，报告收益何时消失。

必须核对原路由及目标分布保持：缺页只能等待/读取而不能替换；候选树、随机数与验证规则相同。在相同数值执行条件下，检查参考输出或参考logit。统计质量相近不能代替计算语义核对。

推翻条件包括：提交标签不能提升下一窗口需求预测；专家复用高度相同；收益只来自额外缓存或oracle未来信息；暂停/准入开销抵消省下的传输；或者要获得速度必须删掉本轮需要的专家。命中率增加而端到端更慢，也判定系统目标失败。

## 7. 论文潜力与限制

本例的自由探索并未要求结果属于单一类型：它也包含诊断和边界意识，但起点是跨领域概览中发现的执行成本矛盾。潜在贡献是一个保持目标行为的缓存准入机制，以及对投机轨迹信息价值的可验证分析。最薄弱处是与MoE-SpAc、SpecMD和AcceptMoE的剩余差异是否足够大；若缺乏新的预测证据和同成本性能，应诚实保留为工程组合而不声称独立算法突破。

## 参考文献与阅读范围

[1] **MoE-SpAc: Efficient MoE Inference Based on Speculative Activation Utility in Heterogeneous Edge Scenarios**。[来源](https://arxiv.org/html/2603.09983)；[LitGraph paper_id=201507](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/201507)。阅读：`fulltext_selected`，原文§3.2及Algorithm 1、§3.4；API详情。

[2] **AcceptMoE: Commitment-Weighted Self-Sizing Verifier Expert Sets for Efficient MoE Speculative Decoding**。[来源](https://arxiv.org/html/2608.02989)；未匹配可靠库内编号。阅读：`fulltext_selected`，原文Method、Verifier-Side Expert Selection、Commitment-Weighted Demand、式(1)–(6)。

[3] **SpecMD: A Comprehensive Study On Speculative Expert Prefetching**。[来源](https://arxiv.org/html/2602.03921)；[LitGraph paper_id=102873](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102873)。阅读：`fulltext_selected`，原文§3.1.1–3.1.4、§4.1–4.2；API详情。

[4] **CECAR: Cache & Expert Co-Aware Routing Accelerates On-Device Inference of MoE LLMs**。[来源](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205528)；[LitGraph paper_id=205528](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205528)。阅读：`source_card`，API abstract/insight/technique/boundaries；来源摘要。

[5] **CommitMoE: Efficient Fallback-Free MoE Inference with Offloading Under GPU Memory Constraints**。[来源](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/426525)；[LitGraph paper_id=426525](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/426525)。阅读：`source_card`，API abstract/insight/technique/boundaries；来源摘要。

[6] **ZipMoE: Efficient on-device MoE serving via lossless compression and cache-affinity scheduling**。[来源](https://arxiv.org/html/2601.21198)；[LitGraph paper_id=104027](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/104027)。阅读：`source_card`，API abstract/insight/technique/boundaries。

[7] **Utility-Driven Speculative Decoding for Mixture-of-Experts**。[来源](https://arxiv.org/html/2506.20675)；未匹配可靠库内编号。阅读：`fulltext_selected`，原文摘要、§4–5的效用/测试窗口/禁用与自适应策略说明。

整理日期：2026年11月13日（Asia/Shanghai）。检索、候选调整与覆盖缺口见同目录PROCESS.md。

## LitGraph证据索引

- [sparse-mixture-of-experts-P0020](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/sparse-mixture-of-experts-P0020)：动态调度与重复访存可能抵消稀疏计算的理论收益。
- [speculative-decoding-P0068](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0068)：路由共享、阶段重叠与GPU动态使验证成本难预测。
- [sparse-mixture-of-experts-I0116](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/sparse-mixture-of-experts-I0116)：专家缓存/调度与边际收益来源导航。
- [speculative-decoding-I0047](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0047)：细粒度MoE验证成本取决于跨token路由重叠和实际执行。
- [speculative-decoding-I0003-s4](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0003-s4)：接受率不能单独决定吞吐，需统一实际负载和成本。

以上条目用于来源追溯；并非本提案已被证明或问题尚未解决的凭据。
