# 示例06全过程｜自由探索：回滚事件与MoE专家缓存生命周期

执行与整理日期：2026年11月13日（Asia/Shanghai）。本轮单agent独立完成，没有调用子agent；未给文献检索另设历史截止日。范围是efficiency领域的训练内存、低精度数值稳定性、投机解码与MoE执行。本文记录外部可核查的检索行动、证据与候选调整；不是作者历史创作过程或模型内部思维实录。

本例与另外三例共用初始领域探索，随后按模式分别检索和查新。章节按证据用途组织；真实请求顺序在附录中按时间列出。下载或分页获取不等于全部精读，原文选读也不等于逐页全文阅读。

## 1. 输入与选题

没有预指定结果，从MoE动态访存问题和投机解码成本条目自由浏览。最初的看似新想法连续被前作覆盖，最终从执行语义而非新的路由算法形成候选。

## 2. 连接、领域浏览与阅读边界

实际访问stats、llms.txt和openapi.json；llms.txt于2026-11-13 03:07:35读取，HTTP200。核对只读接口、URL编码及两类分页游标。领域列表和搜索/paper_count排序按next_offset继续；领域论文列表按next_after继续。本轮全部已启动查询均读取到has_more=false。

- `sparse-mixture-of-experts/insights`：获取96条、2页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。
- `sparse-mixture-of-experts/problems`：获取76条、2页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。
- `speculative-decoding/insights`：获取25条、1页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。
- `speculative-decoding/problems`：获取35条、1页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。

大段概览输出曾截断，后续按领域、相关字段和选定论文逐项读取；没有将第一次打印算成完整阅读。paper_count只是导航量，不作为引用数或质量证据。

## 3. 实际机制查询与转向

|查询|参数/范围|返回数与分页|关键返回ID|
|---|---|---|---|
|[speculative activation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=speculative+activation&kind=insight&mode=all&limit=20)|kind=insight；全库|6条/1页|`efficient-long-context-attention-I0149`, `child-computer-interaction-I0048`, `persona-simulation-I0030`, `efficient-long-context-attention-I0023-s1`, `adaptive-compute-termination-I0076`|
|[cache pollution](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=cache+pollution&kind=problem&mode=all&limit=20)|kind=problem；全库|0条/1页|无|
|[expert cache acceptance](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=expert+cache+acceptance&kind=insight&mode=all&limit=20)|kind=insight；全库|0条/1页|无|
|[rejected draft](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=rejected+draft&kind=insight&mode=all&limit=20)|kind=insight；全库|0条/1页|无|
|[投机 专家 缓存](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%8A%95%E6%9C%BA+%E4%B8%93%E5%AE%B6+%E7%BC%93%E5%AD%98&kind=insight&mode=all&limit=20)|kind=insight；全库|1条/1页|`speculative-decoding-I0047`|

另对已返回的真实domain_id做题名检索；全部实际URL和分页在附录。零命中没有用于宣称新颖。

## 4. 证据如何改变提案

浏览MoE领域与题名Cache/Prefetch/Speculat/Offload时，首先想到用草稿预测未来专家需求。MoE-SpAc原文明确把投机激活频率当成内存管理传感器，所以撤回这一初稿。

随后考虑提交概率加权。公开原文AcceptMoE已使用离线提交概率和router需求来调整验证器可选专家集合，而且正文明确该logit mask改变目标路由、属于近似。该证据又排除了把“提交概率加权”本身当作创新。

SpecMD原文已有standard routing+fetch和Least-Stale的当前周期/陈旧页面管理，ZipMoE已有无损压缩与缓存亲和调度；CECAR与CommitMoE则提供改变路由/专家选择以换速度的近邻。Cascade还会动态调节甚至关闭投机。因此，最终比较必须固定目标语义与草稿策略，不能借它们的变化制造优势。

剩余候选区分当前验证必需的专家执行与验证结束后的页面保留。一个token最终被拒绝，不等于验证时可跳过它需要的专家；但这次访问是否应增加下轮缓存权重，是独立、可检验的问题。提案只在原路由完整执行的条件下研究提交/回滚标签的增量预测价值。

最终交付不声称实现了新系统。若等信息Least-Stale或MoE-SpAc已解释全部收益，或标签并无预测价值，则作为自由探索的否定结果保留，而不换名称维持创新叙事。

## 5. problem/insight及用途

- **[sparse-mixture-of-experts-P0020](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/sparse-mixture-of-experts-P0020)**｜目标problem。稀疏MoE的训练与推理中，理论上的计算节省被动态调度、重复访存、跨设备通信及中间张量显存占用抵消，专家规模变大后难以保持低延迟、高吞吐与大批量

  本例用途：动态调度与重复访存可能抵消稀疏计算的理论收益。 原始范围：单设备与分布式的稀疏MoE训练、推理及部署，包括大规模GPU训练中的显存瓶颈。

- **[speculative-decoding-P0068](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0068)**｜目标problem。稀疏混合专家模型投机解码的验证成本难以由批大小和专家饱和度准确预测，路由共享、阶段重叠及设备执行动态使静态估计失准

  本例用途：路由共享、阶段重叠与GPU动态使验证成本难预测。 原始范围：稀疏MoE语言模型投机解码的性能预测，尤其是低批量条件。

- **[sparse-mixture-of-experts-I0116](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/sparse-mixture-of-experts-I0116)**｜主要insight。大规模MoE推理服务中，专家复制、缓存和调度应依据访问热点及边际收益联合配置；在显存和带宽受限时，优先分散热点请求可改善吞吐或延迟，但收益不会随副本或缓存规模线性增长。

  本例用途：专家缓存/调度与边际收益来源导航。 原始范围：大规模MoE异构内存推理服务；低命中率、带宽不足和复制收益递减会限制效果。

- **[speculative-decoding-I0047](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0047)**｜成本insight。细粒度稀疏MoE的投机解码验证成本由激活专家权重、跨草稿token路由重叠及GPU执行动态共同决定，低批大小下可获得超出仅按专家权重预测的加速。

  本例用途：细粒度MoE验证成本取决于跨token路由重叠和实际执行。 原始范围：稀疏MoE的验证成本建模，主要针对低批量和细粒度专家；不外推至稠密模型。

- **[speculative-decoding-I0003-s4](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0003-s4)**｜评估边界。高并发批处理下，单请求接受率不足以决定吞吐：保留变长结果、消除填充、跨请求调配验证预算并按成本调度候选，才能把投机收益转化为服务吞吐，而批增大时相对收益会下降（BASS、AdaTree、CAST、SPEED-Bench）。

  本例用途：接受率不能单独决定吞吐，需统一实际负载和成本。 原始范围：多请求批处理、高并发生产服务及负载感知的投机解码；结论受批大小、请求差异、到达率、硬件与实现版本限制，单请求加速比不能直接外推。

problem是来源问题记录，可能已有部分或完整解法；本例用它定位背景，不将其直接当作开放性证明。insight是已有知识，不自动构成本提案贡献。

## 6. 来源身份、阅读深度和逐篇比较

### MoE-SpAc: Efficient MoE Inference Based on Speculative Activation Utility in Heterogeneous Edge Scenarios

[《201507》MoE-SpAc: Efficient MoE Inference Based on Speculative Activation Utility in Heterogeneous Edge Scenarios](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/201507) · [原文](https://arxiv.org/html/2603.09983)

阅读：`fulltext_selected`；原文§3.2及Algorithm 1、§3.4；API详情。

已经覆盖：MoE-SpAc已经用投机专家频率作为预取与驱逐的统一效用。

剩余差异/风险：不能再提出“用草稿预测访存”；拟区分验证必需访问与提交后缓存保留用途。

### SpecMD: A Comprehensive Study On Speculative Expert Prefetching

[《102873》SpecMD: A Comprehensive Study On Speculative Expert Prefetching](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102873) · [原文](https://arxiv.org/html/2602.03921)

阅读：`fulltext_selected`；原文§3.1.1–3.1.4、§4.1–4.2；API详情。

已经覆盖：SpecMD已有原路由Fetch模式、混合策略空间与Least-Stale生命周期驱逐。

剩余差异/风险：仅改缓存队列不够；需证明验证回滚事件提供额外可预测信息，胜过同成本Least-Stale。

### AcceptMoE: Commitment-Weighted Self-Sizing Verifier Expert Sets for Efficient MoE Speculative Decoding

[《库外/编号未匹配》AcceptMoE: Commitment-Weighted Self-Sizing Verifier Expert Sets for Efficient MoE Speculative Decoding](https://arxiv.org/html/2608.02989)

阅读：`fulltext_selected`；原文Method、Verifier-Side Expert Selection、Commitment-Weighted Demand、式(1)–(6)。

已经覆盖：已经对专家需求使用提交概率加权，并裁减验证器可选专家集合。

剩余差异/风险：原文明确改变router logits属于近似；候选不再声称权重新颖，仅研究不改路由的缓存准入/保留与本轮必需工作隔离。

### ZipMoE: Efficient on-device MoE serving via lossless compression and cache-affinity scheduling

[《104027》ZipMoE: Efficient on-device MoE serving via lossless compression and cache-affinity scheduling](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/104027) · [原文](https://arxiv.org/html/2601.21198)

阅读：`source_card`；API abstract/insight/technique/boundaries。

已经覆盖：ZipMoE已有无损权重压缩、缓存与调度协同。

剩余差异/风险：复用收益、传输/解压成本必须计入；不宣称单纯保留模型行为是新贡献。

### CECAR: Cache & Expert Co-Aware Routing Accelerates On-Device Inference of MoE LLMs

[《205528》CECAR: Cache & Expert Co-Aware Routing Accelerates On-Device Inference of MoE LLMs](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205528)

阅读：`source_card`；API abstract/insight/technique/boundaries；来源摘要。

已经覆盖：CECAR已有重用距离预测与缓存感知路由。

剩余差异/风险：本提案只改变存放和搬运，不更改原路由；不能直接拿不同模型语义下速度作公平优越比较。

### CommitMoE: Efficient Fallback-Free MoE Inference with Offloading Under GPU Memory Constraints

[《426525》CommitMoE: Efficient Fallback-Free MoE Inference with Offloading Under GPU Memory Constraints](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/426525)

阅读：`source_card`；API abstract/insight/technique/boundaries；来源摘要。

已经覆盖：CommitMoE通过直接提交专家选择避免错误预取后的回退。

剩余差异/风险：减少回退已有；本提案保留必要Fetch以不改变目标模型。

### Why Speculative Decoding Works Better Than Predicted on Sparse MoE Models

[《201555》Why Speculative Decoding Works Better Than Predicted on Sparse MoE Models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/201555)

阅读：`source_card`；API abstract/insight/technique/boundaries；来源摘要。

已经覆盖：MoE投机验证成本受路由重叠和GPU动态影响，不能只数专家。

剩余差异/风险：收益须以实测暴露等待衡量，命中率或理论字节数不直接等于速度。

### Utility-Driven Speculative Decoding for Mixture-of-Experts

[《库外/编号未匹配》Utility-Driven Speculative Decoding for Mixture-of-Experts](https://arxiv.org/html/2506.20675)

阅读：`fulltext_selected`；原文摘要、§4–5的效用/测试窗口/禁用与自适应策略说明。

已经覆盖：Cascade已有按token收益/验证成本调节甚至禁用投机。

剩余差异/风险：本提案先固定草稿策略隔离缓存作用，再检查联合策略；不得把动态窗口收益误算成缓存收益。

## 7. 错配、工具失败与覆盖缺口

2610.34721实际读取为Prefetch-Steered Routing，因此在本例中只作路由近邻的身份核对，不作为“早退验证”来源。AcceptMoE与Cascade按arXiv查询未得到库内编号，采用已核对的原文链接，不编造paper_id。

by-arxiv的404只表示该接口本轮未匹配，不表示论文不存在或未被其他字段收录。对未匹配调用最多两次后停止；未伪造ID。公开论文HTML成功下载后先核对标题，再决定是否引用。实际标题错配的论文保留在工作记录中，但不作为该研究的支持证据。

前瞻预取、提交概率权重、生命周期驱逐和语义保持均已有相关方法。剩余问题是其在不改路由条件下的两阶段准入/保留，是否提供新信息和等成本效率。

## 8. 已完成验证与未完成工作

用执行集合{a,b,c}与提交前缀集合{a,b}说明：c当前仍必须执行；之后能否驱逐c只能由未来复用预测决定，不能把“本轮未提交”当作永不复用的证明。只是状态不变量检查，无硬件性能数据。

已完成API身份与字段核验、分页、指定原文章节阅读、近邻比较、提案和可证伪计划。没有完成模型训练、真实GPU速度比较或形式化全模型证明；未将数值恒等式或小例子说成实验成果。其余研究任务在提案中以未来验证列出，而不影响本次“案例与提案整理”的交付范围。

## 附录A：本例相关的真实API账本

共享初始浏览及本例相关请求共65条，按开始时间排序；与其他例重复的共享请求不视为重复研究证据。llms.txt连接另见第2节。完整本轮请求记录保存在工作区，不删除失败项。

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
|12|2026-11-13 03:08:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts)|200|
|13|2026-11-13 03:08:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/insights?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/insights?sort=paper_count&limit=50)|200；{"limit":50,"count":25,"has_more":false,"sort":"paper_count","next_offset":null}|
|14|2026-11-13 03:08:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/problems?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/problems?sort=paper_count&limit=50)|200；{"limit":50,"count":35,"has_more":false,"sort":"paper_count","next_offset":null}|
|15|2026-11-13 03:08:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/insights?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/insights?sort=paper_count&limit=50)|200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":50}|
|16|2026-11-13 03:08:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/problems?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/problems?sort=paper_count&limit=50)|200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":50}|
|17|2026-11-13 03:08:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/insights?sort=paper_count&limit=50&offset=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/insights?sort=paper_count&limit=50&offset=50)|200；{"limit":50,"count":46,"has_more":false,"sort":"paper_count","next_offset":null}|
|18|2026-11-13 03:08:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/problems?sort=paper_count&limit=50&offset=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/problems?sort=paper_count&limit=50&offset=50)|200；{"limit":50,"count":26,"has_more":false,"sort":"paper_count","next_offset":null}|
|19|2026-11-13 03:08:37|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+recomputation&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+recomputation&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|20|2026-11-13 03:08:38|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=unbiased+compression+gradient&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=unbiased+compression+gradient&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":3,"has_more":false,"sort":"relevance","next_offset":null}|
|21|2026-11-13 03:08:40|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E9%87%8D%E8%AE%A1%E7%AE%97&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E9%87%8D%E8%AE%A1%E7%AE%97&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":6,"has_more":false,"sort":"relevance","next_offset":null}|
|22|2026-11-13 03:08:41|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=multi+fidelity+gradient&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=multi+fidelity+gradient&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":13,"has_more":false,"sort":"relevance","next_offset":null}|
|23|2026-11-13 03:08:42|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E6%8C%AF%E8%8D%A1+%E5%B0%BA%E5%BA%A6&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E6%8C%AF%E8%8D%A1+%E5%B0%BA%E5%BA%A6&kind=problem&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|24|2026-11-13 03:08:43|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantized+verification&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantized+verification&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|25|2026-11-13 03:08:44|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=exact+speculative&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=exact+speculative&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|26|2026-11-13 03:08:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=expert+optimizer&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=expert+optimizer&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|27|2026-11-13 03:11:04|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0047](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0047)|200|
|28|2026-11-13 03:11:05|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0068](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-P0068)|200|
|29|2026-11-13 03:11:06|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/sparse-mixture-of-experts-I0116](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/sparse-mixture-of-experts-I0116)|200|
|30|2026-11-13 03:11:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Cache&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Cache&limit=20)|200；{"count":4,"limit":20,"has_more":false,"next_after":null}|
|31|2026-11-13 03:11:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Verify&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Verify&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|32|2026-11-13 03:11:11|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Quant&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Quant&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|33|2026-11-13 03:11:11|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Exact&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Exact&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|34|2026-11-13 03:11:11|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=MoE&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=MoE&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|35|2026-11-13 03:11:12|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Cost&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Cost&limit=20)|200；{"count":2,"limit":20,"has_more":false,"next_after":null}|
|36|2026-11-13 03:11:12|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Cache&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Cache&limit=20)|200；{"count":2,"limit":20,"has_more":false,"next_after":null}|
|37|2026-11-13 03:11:12|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Prefetch&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Prefetch&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|38|2026-11-13 03:11:12|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Optimizer&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Optimizer&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|39|2026-11-13 03:11:13|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Momentum&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Momentum&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|40|2026-11-13 03:11:13|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Speculat&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Speculat&limit=20)|200；{"count":3,"limit":20,"has_more":false,"next_after":null}|
|41|2026-11-13 03:11:13|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Offload&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=Offload&limit=20)|200；{"count":2,"limit":20,"has_more":false,"next_after":null}|
|42|2026-11-13 03:11:21|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721)|HTTP Error 404: Not Found|
|43|2026-11-13 03:11:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721)|HTTP Error 404: Not Found|
|44|2026-11-13 03:12:17|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/201555](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/201555)|200|
|45|2026-11-13 03:12:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/104027](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/104027)|200|
|46|2026-11-13 03:12:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205528](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205528)|200|
|47|2026-11-13 03:12:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102873](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102873)|200|
|48|2026-11-13 03:12:19|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/201507](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/201507)|200|
|49|2026-11-13 03:12:19|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/426525](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/426525)|200|
|50|2026-11-13 03:14:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721)|HTTP Error 404: Not Found|
|51|2026-11-13 03:14:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.34721)|HTTP Error 404: Not Found|
|52|2026-11-13 03:14:24|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2608.02989](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2608.02989)|HTTP Error 404: Not Found|
|53|2026-11-13 03:14:25|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2608.02989](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2608.02989)|HTTP Error 404: Not Found|
|54|2026-11-13 03:14:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2506.20675](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2506.20675)|HTTP Error 404: Not Found|
|55|2026-11-13 03:14:27|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2506.20675](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2506.20675)|HTTP Error 404: Not Found|
|56|2026-11-13 03:14:48|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=speculative+activation&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=speculative+activation&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":6,"has_more":false,"sort":"relevance","next_offset":null}|
|57|2026-11-13 03:14:49|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=cache+pollution&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=cache+pollution&kind=problem&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|58|2026-11-13 03:14:50|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=expert+cache+acceptance&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=expert+cache+acceptance&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|59|2026-11-13 03:14:51|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=rejected+draft&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=rejected+draft&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|60|2026-11-13 03:14:53|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%8A%95%E6%9C%BA+%E4%B8%93%E5%AE%B6+%E7%BC%93%E5%AD%98&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%8A%95%E6%9C%BA+%E4%B8%93%E5%AE%B6+%E7%BC%93%E5%AD%98&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|61|2026-11-13 03:14:55|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0003-s4](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/speculative-decoding-I0003-s4)|200|
|62|2026-11-13 03:20:39|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/sparse-mixture-of-experts-P0020](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/sparse-mixture-of-experts-P0020)|200|
|63|2026-11-13 03:22:06|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=AcceptMoE&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/sparse-mixture-of-experts/papers?q=AcceptMoE&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|64|2026-11-13 03:22:07|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Utility-Driven&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=Utility-Driven&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|65|2026-11-13 03:22:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=VeriCache&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/speculative-decoding/papers?q=VeriCache&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|

## 附录B：原文HTTP访问与标题校验

- 2026-11-13 03:14:29，[GET](https://arxiv.org/html/2610.34721)：200；实际标题：Prefetch-Steered Routing: Deterministic Cache-Aware Expert Selectionfor Offloaded Mixture-of-Experts Decoding。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:30，[GET](https://arxiv.org/html/2608.02989)：200；实际标题：AcceptMoE: Commitment-Weighted Self-Sizing Verifier Expert Sets for Efficient MoE Speculative Decoding。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:30，[GET](https://arxiv.org/html/2506.20675)：200；实际标题：Utility-Driven Speculative Decoding for Mixture-of-Experts。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:31，[GET](https://arxiv.org/html/2603.09983)：200；实际标题：MoE-SpAc: Efficient MoE Inference Based on Speculative Activation Utility in Heterogeneous Edge Scenarios。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:32，[GET](https://arxiv.org/html/2602.03921)：200；实际标题：SpecMD: A Comprehensive Study On Speculative Expert Prefetching。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:32，[GET](https://arxiv.org/html/2601.21198)：200；实际标题：ZipMoE: Efficient On-Device MoE Serving via Lossless Compression and Cache-Affinity Scheduling。是否采用与阅读深度见第6–7节。

检索时间没有人为历史截止；但数据库快照、关键词召回和未公开稿件均限制覆盖。题名核验不证明新颖性，样本实验也不能替代完整正确性证明。
