# 示例05全过程｜扩展能力边界：压缩验证状态下的参考分布保持

执行与整理日期：2026年11月13日（Asia/Shanghai）。本轮单agent独立完成，没有调用子agent；未给文献检索另设历史截止日。范围是efficiency领域的训练内存、低精度数值稳定性、投机解码与MoE执行。本文记录外部可核查的检索行动、证据与候选调整；不是作者历史创作过程或模型内部思维实录。

本例与另外三例共用初始领域探索，随后按模式分别检索和查新。章节按证据用途组织；真实请求顺序在附录中按时间列出。下载或分页获取不等于全部精读，原文选读也不等于逐页全文阅读。

## 1. 输入与选题

从长上下文和投机验证的计算/缓存成本进入。目标是扩展精确验证的适用条件，不把“质量接近”当成“分布精确”，也不把greedy正确当成随机采样正确。

## 2. 连接、领域浏览与阅读边界

实际访问stats、llms.txt和openapi.json；llms.txt于2026-11-13 03:07:35读取，HTTP200。核对只读接口、URL编码及两类分页游标。领域列表和搜索/paper_count排序按next_offset继续；领域论文列表按next_after继续。本轮全部已启动查询均读取到has_more=false。

- `speculative-decoding/insights`：获取25条、1页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。
- `speculative-decoding/problems`：获取35条、1页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。

大段概览输出曾截断，后续按领域、相关字段和选定论文逐项读取；没有将第一次打印算成完整阅读。paper_count只是导航量，不作为引用数或质量证据。

## 3. 实际机制查询与转向

|查询|参数/范围|返回数与分页|关键返回ID|
|---|---|---|---|
|[quantized verification](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantized+verification&kind=insight&mode=all&limit=20)|kind=insight；全库|1条/1页|`temporal-logic-I0050`|
|[lossless cache](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=lossless+cache&kind=insight&mode=all&limit=20)|kind=insight；全库|2条/1页|`vlm-distillation-I0002`, `efficient-long-context-attention-I0023-s2`|
|[certified decoding](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=certified+decoding&kind=insight&mode=all&limit=20)|kind=insight；全库|1条/1页|`process-verification-search-I0062`|
|[精确 缓存 验证](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%B2%BE%E7%A1%AE+%E7%BC%93%E5%AD%98+%E9%AA%8C%E8%AF%81&kind=problem&mode=all&limit=20)|kind=problem；全库|0条/1页|无|
|[early exit verification](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=early+exit+verification&kind=insight&mode=all&limit=20)|kind=insight；全库|1条/1页|`adaptive-compute-termination-I0076`|

另对已返回的真实domain_id做题名检索；全部实际URL和分页在附录。零命中没有用于宣称新颖。

## 4. 证据如何改变提案

题名Cache/Quant搜索找到QuantSpec和FAFO；聚合insight还引向经典投机采样、Speculative Verification、MARS和VIA-SD。FAFO直接覆盖“有损缓存起草加无损验证”，所以撤回这一级别的泛化主张。

选读经典论文§2与Algorithm 1，确认接受、拒绝后的正残差采样及bonus三处概率。接着读取QuantSpec§4与Table 2，发现其较高精度目标是INT8 KV，文中以性能接近FP16作比较。因此，提案必须先指定参考数值实现，不能声称任何分层缓存自动保持FP16分布。

MARS和VIA-SD的卡片显示相关验证规则有有损性质；Speculative Verification主要预测接受率而调节长度。候选被收紧为“保证包含真实参考概率的区间能否直接决定同一随机接受事件”。

进一步审查发现只保当前token事件仍不够：拒绝后的残差分布要准确，已接受token产生的近似KV也会污染下一步目标。最终把数值证书、精确回退与缓存状态闭合列为不可分割要求，同时明确成本过高即效率失败。

## 5. problem/insight及用途

- **[speculative-decoding-P0013](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0013)**｜目标problem。大语言模型在跳层、提前退出、投机解码和有损KV缓存压缩等加速下，因历史注意力状态缺失或失真与训练-推理分布失配产生质量退化，误差沿生成链传播累积，使生成可靠性难以保证。

  本例用途：有损缓存/跳层与历史状态失真影响生成可靠性。 原始范围：大语言模型在知识密集问答、指令跟随、数学推理和代码生成中的动态跳层、提前退出以及投机/对比解码；不覆盖只影响吞吐、不引入质量退化的解码加速场景。

- **[speculative-decoding-P0030](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0030)**｜效率problem。长上下文语言模型生成受持续增长的注意力计算、缓存访问和通信成本制约，上下文越长每轮开销越难摊薄，解码加速收益随之下降

  本例用途：长上下文注意力与缓存读写使验证越来越昂贵。 原始范围：长上下文语言模型常规与投机推理，包括多设备NPU及约20K至128K词元场景。

- **[speculative-decoding-I0003-s1](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0003-s1)**｜核心机制insight。文本自回归语言模型的解码加速可用外部草稿加目标验证、目标模型自适应省算、并行迭代求解或检索块直接接受等做法；收益由草稿—目标分布距离与接受长度能否覆盖起草与验证开销决定，各做法在分布精确性与加速比之间取舍（EAGLE-2、LayerSkip、Jacobi 并行解码、CD-LM）。

  本例用途：草稿—目标验证与多种解码机制的来源导航。 原始范围：token 级文本自回归语言模型的推理加速，涵盖通用单请求、长上下文/超长生成、多语言覆盖、低比特与在线请求流等条件，包括需要训练草稿或改造目标模型的设定与免训练的运行时策略。字节级等非标准 tokenization、RL rollout 与纯理论界限不属此族；分布精确性以各方法自身的验证规则为准。

- **[speculative-decoding-I0018](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0018)**｜理论边界insight。语言模型投机解码的无偏生成存在由草稿与目标条件分布总变差距离决定的期望拒绝次数下界；放松无偏约束后，可形成拒绝概率与最小分布偏差之间的线性权衡。

  本例用途：无偏生成与拒绝代价/分布偏差存在约束，不能任意放宽接受。 原始范围：拒绝采样式投机解码的理论效率界限；依赖草稿成本可忽略等理想假设，不直接保证真实硬件延迟。

problem是来源问题记录，可能已有部分或完整解法；本例用它定位背景，不将其直接当作开放性证明。insight是已有知识，不自动构成本提案贡献。

## 6. 来源身份、阅读深度和逐篇比较

### Fast Inference from Transformers via Speculative Decoding

[《95530》Fast Inference from Transformers via Speculative Decoding](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/95530) · [原文](https://arxiv.org/html/2211.17192)

阅读：`fulltext_selected`；原文§2.1–2.3、Algorithm 1；API详情。

已经覆盖：精确投机采样已有min(1,p/q)接受与正残差分布校正。

剩余差异/风险：本提案不修改其分布定理，研究获得足够精确的验证信息是否能更便宜。

### QuantSpec: Self-Speculative Decoding with Hierarchical Quantized KV Cache

[《91862》QuantSpec: Self-Speculative Decoding with Hierarchical Quantized KV Cache](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91862) · [原文](https://arxiv.org/html/2502.10424)

阅读：`fulltext_selected`；原文§4.1–4.3、Table 2；API详情。

已经覆盖：QuantSpec已有4/8-bit分层KV和回滚兼容缓冲；其验证目标使用INT8 KV。

剩余差异/风险：与FP16质量接近不等于参考分布逐步完全相同；提案明确指定参考数值实现。

### FAFO: Lossy KV Cache Compression for Lossless Inference Acceleration via Draftless Fumble Decoding

[《99385》FAFO: Lossy KV Cache Compression for Lossless Inference Acceleration via Draftless Fumble Decoding](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/99385)

阅读：`source_card`；API abstract/insight/technique；来源摘要。

已经覆盖：FAFO已有有损缓存候选加无损验证，限制“压缩+精确”广义新颖性。

剩余差异/风险：近邻全文未读，不能排除更广实现；拟研究验证状态本身的误差证书和后续状态闭合。

### Speculative Verification: Exploiting Information Gain for Speculative Decoding

[《241414》Speculative Verification: Exploiting Information Gain for Speculative Decoding](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/241414) · [原文](https://arxiv.org/html/2509.24328)

阅读：`source_card`；API abstract/insight/technique/boundaries。

已经覆盖：Speculative Verification已用伴随模型预测接受率、调整验证长度。

剩余差异/风险：预测接受概率不是包含真实p的数值证书；预算调度也不是本提案的新概念。

### {MARS}: Unleashing the Power of Speculative Decoding via Margin-Aware Verification

[《240026》{MARS}: Unleashing the Power of Speculative Decoding via Margin-Aware Verification](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/240026) · [原文](https://arxiv.org/html/2601.15498)

阅读：`source_card`；API abstract/insight/technique/boundaries。

已经覆盖：MARS已有按margin放宽验证以换取速度。

剩余差异/风险：本提案的margin来自误差区间是否足以确定同一规则，不是接受语义近似词元。

### VIA-SD: Verification via Intra-Model Routing for Speculative Decoding

[《103786》VIA-SD: Verification via Intra-Model Routing for Speculative Decoding](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103786) · [原文](https://arxiv.org/html/2606.12243)

阅读：`source_card`；API abstract/insight/technique/boundaries。

已经覆盖：VIA-SD已有多级瘦验证器和混合门控。

剩余差异/风险：卡片描述有损门控，不能当作严格参考分布保证；多级计算本身已存在。

## 7. 错配、工具失败与覆盖缺口

检索片段将2507.03356标作VeriCache，但实际原文标题是No Eigenvalues Outside the Limiting Support of Generally Correlated and Noncentral Sample Covariance Matrices，剔除。2610.34721实际为Prefetch-Steered Routing，而非早退验证论文；不拿它支持缓存认证。外部聚合站上无法追到主来源的认证推测概念也未作为论文证据。

by-arxiv的404只表示该接口本轮未匹配，不表示论文不存在或未被其他字段收录。对未匹配调用最多两次后停止；未伪造ID。公开论文HTML成功下载后先核对标题，再决定是否引用。实际标题错配的论文保留在工作记录中，但不作为该研究的支持证据。

区间算术、拒绝采样和分级验证均已有。剩余难点是可用的完整概率证书、长期状态闭合及真实节省；未排除更广的延迟接受/认证计算文献。

## 8. 已完成验证与未完成工作

在三分类p/q分布上精确枚举标准接受+正残差的输出，验证等于p；再检查[0.56,0.64]接受区间对固定U的三种分支。没有实现真实网络的误差证书或缓存修复。

已完成API身份与字段核验、分页、指定原文章节阅读、近邻比较、提案和可证伪计划。没有完成模型训练、真实GPU速度比较或形式化全模型证明；未将数值恒等式或小例子说成实验成果。其余研究任务在提案中以未来验证列出，而不影响本次“案例与提案整理”的交付范围。

## 附录A：本例相关的真实API账本

共享初始浏览及本例相关请求共55条，按开始时间排序；与其他例重复的共享请求不视为重复研究证据。llms.txt连接另见第2节。完整本轮请求记录保存在工作区，不删除失败项。

|序号|北京时间|实际GET|状态/分页|
|---|---|---|---|
|1|2026-11-13 03:07:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/stats](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/stats)|200|
|2|2026-11-13 03:07:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/openapi.json](https://kevin-wake-stuffed-anti.trycloudflare.com/openapi.json)|200|
|3|2026-11-13 03:07:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=efficient&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=efficient&limit=20)|200；{"count":3,"total":3,"limit":20,"has_more":false,"next_offset":null}|
|4|2026-11-13 03:07:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=compression&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=compression&limit=20)|200；{"count":5,"total":5,"limit":20,"has_more":false,"next_offset":null}|
|5|2026-11-13 03:07:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=activation&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=activation&limit=20)|200；{"count":0,"total":0,"limit":20,"has_more":false,"next_offset":null}|
|6|2026-11-13 03:07:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=speculative&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=speculative&limit=20)|200；{"count":1,"total":1,"limit":20,"has_more":false,"next_offset":null}|
|7|2026-11-13 03:07:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=checkpoint&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=checkpoint&limit=20)|200；{"count":0,"total":0,"limit":20,"has_more":false,"next_offset":null}|
|8|2026-11-13 03:07:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=memory&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=memory&limit=20)|200；{"count":1,"total":1,"limit":20,"has_more":false,"next_offset":null}|
|9|2026-11-13 03:07:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E7%A8%80%E7%96%8F&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E7%A8%80%E7%96%8F&limit=20)|200；{"count":11,"total":11,"limit":20,"has_more":false,"next_offset":null}|
|10|2026-11-13 03:07:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=MoE&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=MoE&limit=20)|200；{"count":0,"total":0,"limit":20,"has_more":false,"next_offset":null}|
|11|2026-11-13 03:08:31|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding)|200|
|12|2026-11-13 03:08:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/insights?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/insights?sort=paper_count&limit=50)|200；{"limit":50,"count":25,"has_more":false,"sort":"paper_count","next_offset":null}|
|13|2026-11-13 03:08:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/problems?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/problems?sort=paper_count&limit=50)|200；{"limit":50,"count":35,"has_more":false,"sort":"paper_count","next_offset":null}|
|14|2026-11-13 03:08:37|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+recomputation&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+recomputation&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|15|2026-11-13 03:08:38|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=unbiased+compression+gradient&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=unbiased+compression+gradient&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":3,"has_more":false,"sort":"relevance","next_offset":null}|
|16|2026-11-13 03:08:40|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E9%87%8D%E8%AE%A1%E7%AE%97&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E9%87%8D%E8%AE%A1%E7%AE%97&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":6,"has_more":false,"sort":"relevance","next_offset":null}|
|17|2026-11-13 03:08:41|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=multi+fidelity+gradient&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=multi+fidelity+gradient&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":13,"has_more":false,"sort":"relevance","next_offset":null}|
|18|2026-11-13 03:08:42|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E6%8C%AF%E8%8D%A1+%E5%B0%BA%E5%BA%A6&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E6%8C%AF%E8%8D%A1+%E5%B0%BA%E5%BA%A6&kind=problem&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|19|2026-11-13 03:08:43|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantized+verification&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantized+verification&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|20|2026-11-13 03:08:44|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=exact+speculative&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=exact+speculative&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|21|2026-11-13 03:08:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=expert+optimizer&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=expert+optimizer&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|22|2026-11-13 03:11:01|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0013](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0013)|200|
|23|2026-11-13 03:11:03|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0003-s1](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0003-s1)|200|
|24|2026-11-13 03:11:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Cache&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Cache&limit=20)|200；{"count":4,"limit":20,"has_more":false,"next_after":null}|
|25|2026-11-13 03:11:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Verify&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Verify&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|26|2026-11-13 03:11:11|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Quant&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Quant&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|27|2026-11-13 03:11:11|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Exact&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Exact&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|28|2026-11-13 03:11:11|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=MoE&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=MoE&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|29|2026-11-13 03:11:12|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Cost&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Cost&limit=20)|200；{"count":2,"limit":20,"has_more":false,"next_after":null}|
|30|2026-11-13 03:11:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2507.03356](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2507.03356)|HTTP Error 404: Not Found|
|31|2026-11-13 03:11:19|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2507.03356](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2507.03356)|HTTP Error 404: Not Found|
|32|2026-11-13 03:11:21|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721)|HTTP Error 404: Not Found|
|33|2026-11-13 03:11:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721)|HTTP Error 404: Not Found|
|34|2026-11-13 03:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91862](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91862)|200|
|35|2026-11-13 03:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/99385](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/99385)|200|
|36|2026-11-13 03:14:14|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2507.03356](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2507.03356)|HTTP Error 404: Not Found|
|37|2026-11-13 03:14:15|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2507.03356](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2507.03356)|HTTP Error 404: Not Found|
|38|2026-11-13 03:14:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721)|HTTP Error 404: Not Found|
|39|2026-11-13 03:14:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721)|HTTP Error 404: Not Found|
|40|2026-11-13 03:14:19|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2302.01318](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2302.01318)|HTTP Error 404: Not Found|
|41|2026-11-13 03:14:20|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2302.01318](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2302.01318)|HTTP Error 404: Not Found|
|42|2026-11-13 03:14:21|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2211.17192](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2211.17192)|200|
|43|2026-11-13 03:14:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/95530](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/95530)|200|
|44|2026-11-13 03:14:42|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantized+verification&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantized+verification&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|45|2026-11-13 03:14:43|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=lossless+cache&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=lossless+cache&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|46|2026-11-13 03:14:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=certified+decoding&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=certified+decoding&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|47|2026-11-13 03:14:46|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%B2%BE%E7%A1%AE+%E7%BC%93%E5%AD%98+%E9%AA%8C%E8%AF%81&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%B2%BE%E7%A1%AE+%E7%BC%93%E5%AD%98+%E9%AA%8C%E8%AF%81&kind=problem&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|48|2026-11-13 03:14:47|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=early+exit+verification&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=early+exit+verification&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|49|2026-11-13 03:14:58|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0018](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0018)|200|
|50|2026-11-13 03:17:51|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/241414](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/241414)|200|
|51|2026-11-13 03:17:53|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103786](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103786)|200|
|52|2026-11-13 03:17:54|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/240026](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/240026)|200|
|53|2026-11-13 03:20:01|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0030](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0030)|200|
|54|2026-11-13 03:22:07|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Utility-Driven&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Utility-Driven&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|55|2026-11-13 03:22:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=VeriCache&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=VeriCache&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|

## 附录B：原文HTTP访问与标题校验

- 2026-11-13 03:14:29，[GET](https://arxiv.org/html/2507.03356)：200；实际标题：No Eigenvalues Outside the Limiting Support of Generally Correlated and Noncentral Sample Covariance Matrices。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:29，[GET](https://arxiv.org/html/2610.34721)：200；实际标题：Prefetch-Steered Routing: Deterministic Cache-Aware Expert Selectionfor Offloaded Mixture-of-Experts Decoding。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:29，[GET](https://arxiv.org/html/2302.01318)：200；实际标题：Accelerating Large Language Model Decoding with Speculative Sampling。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:29，[GET](https://arxiv.org/html/2211.17192)：200；实际标题：Fast Inference from Transformers via Speculative Decoding。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:31，[GET](https://arxiv.org/html/2502.10424)：200；实际标题：QuantSpec: Self-Speculative Decoding with Hierarchical Quantized KV Cache。是否采用与阅读深度见第6–7节。

检索时间没有人为历史截止；但数据库快照、关键词召回和未公开稿件均限制覆盖。题名核验不证明新颖性，样本实验也不能替代完整正确性证明。
