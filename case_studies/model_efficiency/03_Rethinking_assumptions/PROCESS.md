# 示例03全过程｜重审默认假设：激活压缩与随机精确回放

执行与整理日期：2026年11月13日（Asia/Shanghai）。本轮单agent独立完成，没有调用子agent；未给文献检索另设历史截止日。范围是efficiency领域的训练内存、低精度数值稳定性、投机解码与MoE执行。本文记录外部可核查的检索行动、证据与候选调整；不是作者历史创作过程或模型内部思维实录。

本例与另外三例共用初始领域探索，随后按模式分别检索和查新。章节按证据用途组织；真实请求顺序在附录中按时间列出。下载或分页获取不等于全部精读，原文选读也不等于逐页全文阅读。

## 1. 输入与选题

用户允许在efficiency自由选题。本轮先从训练峰值内存的问题进入，选中“是否需要每步精确保真”的默认要求。没有用户预指定某篇论文；发现RAD后，明确将默认假设的首次挑战归于已有研究。

## 2. 连接、领域浏览与阅读边界

实际访问stats、llms.txt和openapi.json；llms.txt于2026-11-13 03:07:35读取，HTTP200。核对只读接口、URL编码及两类分页游标。领域列表和搜索/paper_count排序按next_offset继续；领域论文列表按next_after继续。本轮全部已启动查询均读取到has_more=false。

- `efficient-model-compression/insights`：获取105条、3页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。
- `efficient-model-compression/problems`：获取107条、3页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。

大段概览输出曾截断，后续按领域、相关字段和选定论文逐项读取；没有将第一次打印算成完整阅读。paper_count只是导航量，不作为引用数或质量证据。

## 3. 实际机制查询与转向

|查询|参数/范围|返回数与分页|关键返回ID|
|---|---|---|---|
|[activation compression](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+compression&kind=insight&mode=all&limit=20)|kind=insight；全库|25条/2页|`image-depth-estimation-I0325`, `distributed-training-comm-async-straggler-I0012-s3`, `network-pruning-I0058`, `learned-image-compression-I0002`, `sparse-mixture-of-experts-I0045`|
|[randomized automatic differentiation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=randomized+automatic+differentiation&kind=insight&mode=all&limit=20)|kind=insight；全库|1条/1页|`automatic-and-physics-differentiation-I0026`|
|[multifidelity gradient](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=multifidelity+gradient&kind=insight&mode=all&limit=20)|kind=insight；全库|0条/1页|无|
|[无偏 激活](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%97%A0%E5%81%8F+%E6%BF%80%E6%B4%BB&kind=insight&mode=all&limit=20)|kind=insight；全库|8条/1页|`latent-model-generalization-I0247`, `network-expressivity-I0237`, `efficient-model-compression-I0168`, `rnn-long-range-dependency-I0010`, `training-dynamics-feature-learning-I0138`|
|[重计算 校正](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8D%E8%AE%A1%E7%AE%97+%E6%A0%A1%E6%AD%A3&kind=insight&mode=all&limit=20)|kind=insight；全库|0条/1页|无|
|[control variate](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=control+variate&kind=insight&mode=all&limit=20&unit=efficient-model-compression)|kind=insight；限定压缩领域|0条/1页|无|

另对已返回的真实domain_id做题名检索；全部实际URL和分页在附录。零命中没有用于宣称新颖。

## 4. 证据如何改变提案

初稿是允许有损激活而用周期性精确计算修复。读取RAD卡片后，撤回“首次不用精确小批次梯度”的主张；其原文HTML路径404，随后摘要页HTTP200，未伪称已读全文。

读取GACT原文§3.2发现，其已经明确区分压缩器无偏与一般非线性梯度的偏差，并用线性化给出误差项。因此，“无偏量化仍可能产生偏差”也不是新诊断。候选被收紧为同参数、同批次、同随机状态下的完整梯度残差校正。

Checkmate让系统约束进一步收紧：参考步骤也必须通过可行的重计算计划满足峰值内存，而非用低概率掩盖OOM。ActNN、AC-GC与STAC-R则要求与自适应精度和梯度保真/内存前沿比较，不能把任何激活字节减少当作进步。

最终保留逆概率校正为研究工具，同时明确它属于已知估计原理。拟议贡献转为硬显存约束下的概率—压缩—重计算计划联合设计，以及何时被方差或Adam二阶状态否决。

## 5. problem/insight及用途

- **[efficient-model-compression-P0039](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0039)**｜目标problem。深度模型反向传播的高维梯度与长生命周期激活共同推高计算和峰值内存，减少缓存又增加重计算或近似误差，难以满足受限训练预算。

  本例用途：长生命周期激活、重计算与近似误差共同制约受限训练预算。 原始范围：普通、循环、分支、合并及跳连网络，包括需要双重反向传播的训练。

- **[efficient-model-compression-P0172](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0172)**｜成本边界problem。语言及视觉语言模型的低内存训练难以公平比较，不一致的预算与成本口径掩盖额外计算和收敛代价，使内存收益不能直接代表训练效率。

  本例用途：低内存方法需统一预算和收敛代价，避免只看存储字节。 原始范围：语言模型与视觉语言模型低内存训练方法的横向评估。

- **[efficient-model-compression-I0069](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0069)**｜目标insight。神经网络训练中的中间激活可通过压缩、可逆恢复、检查点重计算或计算图重排降低峰值驻留；不同方案分别以量化误差、额外计算或结构约束换取存储节省。

  本例用途：激活压缩、重计算与可逆恢复提供不同误差/计算取舍。 原始范围：通用深度网络训练与XLA/HLO计算图；不以通用性吸收具有独立任务约束的专用方法。

- **[automatic-and-physics-differentiation-I0026](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/automatic-and-physics-differentiation-I0026)**｜随机导数机制来源。在含分支、量化或随机/不连续节点的计算图与动力学系统中，单一点态导数不可靠也不足以优化：可按结构传播逐片或广义次梯度，或对不连续处做噪声平滑并自适应混合一阶、零阶估计器，在正确性、偏差-方差与内存之间取舍（Clarke 次导数、PAP、AoBG）。

  本例用途：聚合条目提供随机AD等来源；具体RAD机制仍由242175卡片核验。 原始范围：覆盖带浮点舍入与量化的网络、PAP 非光滑程序、连续选择程序、概率计算图、强化学习与离散时间物理控制、内存受限反向传播和在线 RNN 训练。保证依赖机器可表示参数、约束资格、噪声假设与退火条件；图深度、路径重叠、Kronecker 结构或动力学正则性变差时，无偏性与低方差都不再有保证。

problem是来源问题记录，可能已有部分或完整解法；本例用它定位背景，不将其直接当作开放性证明。insight是已有知识，不自动构成本提案贡献。

## 6. 来源身份、阅读深度和逐篇比较

### Randomized Automatic Differentiation

[《242175》Randomized Automatic Differentiation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/242175) · [原文](https://arxiv.org/abs/2007.10412)

阅读：`source_card`；API abstract/insight/technique；arXiv HTML 404，未计全文。

已经覆盖：RAD已经质疑随机优化为何需要逐次精确梯度，并用随机AD保持无偏。

剩余差异/风险：“不必精确反传”与逆概率估计不是新概念；本提案研究压缩残差回放的预算、方差和系统调度。

### Backprop with Approximate Activations for Memory-efficient Network Training

[《175012》Backprop with Approximate Activations for Memory-efficient Network Training](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/175012) · [原文](https://arxiv.org/html/1901.07988)

阅读：`source_card`；API abstract/insight/technique/boundaries。

已经覆盖：已有精确前向、近似存储激活用于反向的分工。

剩余差异/风险：本提案不能把这种分工声称首次；区别在随机精确回放与完整梯度残差校正。

### ActNN: Reducing Training Memory Footprint via 2-Bit Activation Compressed Training

[《80813》ActNN: Reducing Training Memory Footprint via 2-Bit Activation Compressed Training](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/80813) · [原文](https://arxiv.org/html/2104.14129)

阅读：`source_card`；API abstract/insight/technique/boundaries；原文已下载，本轮不计通读。

已经覆盖：ActNN已有随机激活量化、方差分析和混合精度。

剩余差异/风险：单纯低比特保存激活已完成；若其无偏方案已达到同样前沿，则新校正无价值。

### GACT: Activation Compressed Training for Generic Network Architectures

[《87292》GACT: Activation Compressed Training for Generic Network Architectures](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/87292) · [原文](https://arxiv.org/html/2206.11357)

阅读：`fulltext_selected`；原文§3.1–3.2、§4.2；API abstract/insight/technique/boundaries。

已经覆盖：GACT已在线估计梯度敏感性和分配位宽，并明确无偏压缩不保证一般反向梯度无偏。

剩余差异/风险：无需重新发现此偏差；拟用实际参考梯度差作随机校正，必须与其自适应压缩在同预算比较。

### Checkmate: Breaking the memory wall with optimal tensor rematerialization

[《48423》Checkmate: Breaking the memory wall with optimal tensor rematerialization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/48423) · [原文](https://arxiv.org/html/1910.02653)

阅读：`source_card`；API abstract/insight/technique/boundaries。

已经覆盖：Checkmate已有硬内存约束下的重计算执行调度。

剩余差异/风险：参考分支须沿可行重计算计划实现，不应把偶发峰值内存当成可平均资源。

### AC-GC: Lossy Activation Compression with Guaranteed Convergence

[《173423》AC-GC: Lossy Activation Compression with Guaranteed Convergence](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/173423)

阅读：`source_card`；API abstract/insight/technique/boundaries；来源摘要。

已经覆盖：AC-GC已经按允许损失上界自适应压缩率。

剩余差异/风险：自适应压缩强度不新；需比较其损失容忍方案与残差校正的真实成本—质量前沿。

### STAC-R: Subspace-Tracked Activation Compression with Residuals

[《205002》STAC-R: Subspace-Tracked Activation Compression with Residuals](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205002)

阅读：`source_card`；API abstract/insight/technique/boundaries；来源摘要。

已经覆盖：STAC-R已经同时考虑可替换的激活内存和梯度保真度，并有低秩加稀疏残差。

剩余差异/风险：它的表示残差不等于本提案的随机精确梯度差；但状态/峰值成本的评价不能遗漏。

## 7. 错配、工具失败与覆盖缺口

搜索片段曾把arXiv 2305.16424指向“Gradient Prediction with Control Variates”，但实际HTTP读取标题为SketchOGD: Memory-Efficient Continual Learning；2509.21794实际为生理信号疲劳检测论文。两者均剔除，不作为梯度校正或checkpoint前作。对应检索名称未完成可靠身份确认，不宣称这些方法存在或不存在。

by-arxiv的404只表示该接口本轮未匹配，不表示论文不存在或未被其他字段收录。对未匹配调用最多两次后停止；未伪造ID。公开论文HTML成功下载后先核对标题，再决定是否引用。实际标题错配的论文保留在工作记录中，但不作为该研究的支持证据。

RAD、激活近似反传与多保真估计原则均已存在；尚未证明本候选与所有多层蒙特卡洛/随机回放方法不同。若仅套用校正式而无新的成本/稳定性证据，不足以成为独立论文。

## 8. 已完成验证与未完成工作

枚举g=1、gc=2、p=1/4的两个结果：估计均值为1、方差为3，平方均值为4；用来说明无偏不等于Adam二阶状态保持。只是确定性代数检查。

已完成API身份与字段核验、分页、指定原文章节阅读、近邻比较、提案和可证伪计划。没有完成模型训练、真实GPU速度比较或形式化全模型证明；未将数值恒等式或小例子说成实验成果。其余研究任务在提案中以未来验证列出，而不影响本次“案例与提案整理”的交付范围。

## 附录A：本例相关的真实API账本

共享初始浏览及本例相关请求共61条，按开始时间排序；与其他例重复的共享请求不视为重复研究证据。llms.txt连接另见第2节。完整本轮请求记录保存在工作区，不删除失败项。

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
|11|2026-11-13 03:08:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression)|200|
|12|2026-11-13 03:08:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/insights?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/insights?sort=paper_count&limit=50)|200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":50}|
|13|2026-11-13 03:08:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/problems?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/problems?sort=paper_count&limit=50)|200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":50}|
|14|2026-11-13 03:08:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/problems?sort=paper_count&limit=50&offset=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/problems?sort=paper_count&limit=50&offset=50)|200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":100}|
|15|2026-11-13 03:08:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/insights?sort=paper_count&limit=50&offset=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/insights?sort=paper_count&limit=50&offset=50)|200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":100}|
|16|2026-11-13 03:08:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/insights?sort=paper_count&limit=50&offset=100](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/insights?sort=paper_count&limit=50&offset=100)|200；{"limit":50,"count":5,"has_more":false,"sort":"paper_count","next_offset":null}|
|17|2026-11-13 03:08:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/problems?sort=paper_count&limit=50&offset=100](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/problems?sort=paper_count&limit=50&offset=100)|200；{"limit":50,"count":7,"has_more":false,"sort":"paper_count","next_offset":null}|
|18|2026-11-13 03:08:37|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+recomputation&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+recomputation&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|19|2026-11-13 03:08:38|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=unbiased+compression+gradient&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=unbiased+compression+gradient&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":3,"has_more":false,"sort":"relevance","next_offset":null}|
|20|2026-11-13 03:08:40|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E9%87%8D%E8%AE%A1%E7%AE%97&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E9%87%8D%E8%AE%A1%E7%AE%97&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":6,"has_more":false,"sort":"relevance","next_offset":null}|
|21|2026-11-13 03:08:41|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=multi+fidelity+gradient&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=multi+fidelity+gradient&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":13,"has_more":false,"sort":"relevance","next_offset":null}|
|22|2026-11-13 03:08:42|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E6%8C%AF%E8%8D%A1+%E5%B0%BA%E5%BA%A6&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E6%8C%AF%E8%8D%A1+%E5%B0%BA%E5%BA%A6&kind=problem&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|23|2026-11-13 03:08:43|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantized+verification&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantized+verification&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|24|2026-11-13 03:08:44|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=exact+speculative&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=exact+speculative&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|25|2026-11-13 03:08:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=expert+optimizer&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=expert+optimizer&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|26|2026-11-13 03:10:55|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0069](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0069)|200|
|27|2026-11-13 03:10:56|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0039](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0039)|200|
|28|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Activation&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Activation&limit=20)|200；{"count":20,"limit":20,"has_more":true,"next_after":"252811"}|
|29|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Checkpoint&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Checkpoint&limit=20)|200；{"count":4,"limit":20,"has_more":false,"next_after":null}|
|30|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Randomized&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Randomized&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|31|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=KEAP&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=KEAP&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|32|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=GACT&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=GACT&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|33|2026-11-13 03:11:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=ActNN&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=ActNN&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|34|2026-11-13 03:11:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Oscillation&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Oscillation&limit=20)|200；{"count":2,"limit":20,"has_more":false,"next_after":null}|
|35|2026-11-13 03:11:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Scale&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Scale&limit=20)|200；{"count":5,"limit":20,"has_more":false,"next_after":null}|
|36|2026-11-13 03:11:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Activation&limit=20&after=252811](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Activation&limit=20&after=252811)|200；{"count":14,"limit":20,"has_more":false,"next_after":null}|
|37|2026-11-13 03:11:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2509.21794](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2509.21794)|HTTP Error 404: Not Found|
|38|2026-11-13 03:11:17|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2509.21794](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2509.21794)|HTTP Error 404: Not Found|
|39|2026-11-13 03:12:15|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/80813](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/80813)|200|
|40|2026-11-13 03:12:15|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/87292](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/87292)|200|
|41|2026-11-13 03:12:15|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/175012](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/175012)|200|
|42|2026-11-13 03:12:15|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205002](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205002)|200|
|43|2026-11-13 03:12:15|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/173423](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/173423)|200|
|44|2026-11-13 03:14:03|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2007.10412](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2007.10412)|200|
|45|2026-11-13 03:14:04|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/242175](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/242175)|200|
|46|2026-11-13 03:14:05|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2305.16424](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2305.16424)|HTTP Error 404: Not Found|
|47|2026-11-13 03:14:06|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2305.16424](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2305.16424)|HTTP Error 404: Not Found|
|48|2026-11-13 03:14:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2509.21794](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2509.21794)|HTTP Error 404: Not Found|
|49|2026-11-13 03:14:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2509.21794](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2509.21794)|HTTP Error 404: Not Found|
|50|2026-11-13 03:14:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+compression&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+compression&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|51|2026-11-13 03:14:27|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+compression&kind=insight&mode=all&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+compression&kind=insight&mode=all&limit=20&offset=20)|200；{"limit":20,"count":5,"has_more":false,"sort":"relevance","next_offset":null}|
|52|2026-11-13 03:14:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=randomized+automatic+differentiation&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=randomized+automatic+differentiation&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|53|2026-11-13 03:14:29|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=multifidelity+gradient&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=multifidelity+gradient&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|54|2026-11-13 03:14:31|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%97%A0%E5%81%8F+%E6%BF%80%E6%B4%BB&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%97%A0%E5%81%8F+%E6%BF%80%E6%B4%BB&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":8,"has_more":false,"sort":"relevance","next_offset":null}|
|55|2026-11-13 03:14:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8D%E8%AE%A1%E7%AE%97+%E6%A0%A1%E6%AD%A3&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8D%E8%AE%A1%E7%AE%97+%E6%A0%A1%E6%AD%A3&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|56|2026-11-13 03:14:33|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=control+variate&kind=insight&mode=all&limit=20&unit=efficient-model-compression](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=control+variate&kind=insight&mode=all&limit=20&unit=efficient-model-compression)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|57|2026-11-13 03:17:50|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/48423](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/48423)|200|
|58|2026-11-13 03:17:58|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/automatic-and-physics-differentiation-I0026](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/automatic-and-physics-differentiation-I0026)|200|
|59|2026-11-13 03:20:00|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0172](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0172)|200|
|60|2026-11-13 03:22:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Gradient+Prediction&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Gradient+Prediction&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|61|2026-11-13 03:22:12|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Scale+Oscillation&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Scale+Oscillation&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|

## 附录B：原文HTTP访问与标题校验

- 2026-11-13 03:14:28，[GET](https://arxiv.org/html/2007.10412)：HTTP Error 404: Not Found；实际标题：未取得文本。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:28，[GET](https://arxiv.org/html/2305.16424)：200；实际标题：SketchOGD: Memory-Efficient Continual Learning。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:28，[GET](https://arxiv.org/html/2509.21794)：200；实际标题：Exploring the Relationships Between Physiological Signals During Automated Fatigue Detection。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:30，[GET](https://arxiv.org/html/2104.14129)：200；实际标题：ActNN: Reducing Training Memory Footprintvia 2-Bit Activation Compressed Training。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:30，[GET](https://arxiv.org/html/2206.11357)：200；实际标题：GACT: Activation Compressed Training for Generic Network Architectures。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:28:20，[GET](https://arxiv.org/abs/2007.10412)：200；实际标题：[2007.10412] Randomized Automatic Differentiation。是否采用与阅读深度见第6–7节。

检索时间没有人为历史截止；但数据库快照、关键词召回和未公开稿件均限制覆盖。题名核验不证明新颖性，样本实验也不能替代完整正确性证明。
