# 示例04全过程｜诊断与重新归因：FP4振荡中的权重与共享尺度

执行与整理日期：2026年11月13日（Asia/Shanghai）。本轮单agent独立完成，没有调用子agent；未给文献检索另设历史截止日。范围是efficiency领域的训练内存、低精度数值稳定性、投机解码与MoE执行。本文记录外部可核查的检索行动、证据与候选调整；不是作者历史创作过程或模型内部思维实录。

本例与另外三例共用初始领域探索，随后按模式分别检索和查新。章节按证据用途组织；真实请求顺序在附录中按时间列出。下载或分页获取不等于全部精读，原文选读也不等于逐页全文阅读。

## 1. 输入与选题

从低精度训练问题进入，选择一个可通过干预推翻的诊断问题，而不是预先设计新优化器。研究对象是已有振荡现象的来源构成，不能为满足“重新归因”而预设旧解释错误。

## 2. 连接、领域浏览与阅读边界

实际访问stats、llms.txt和openapi.json；llms.txt于2026-11-13 03:07:35读取，HTTP200。核对只读接口、URL编码及两类分页游标。领域列表和搜索/paper_count排序按next_offset继续；领域论文列表按next_after继续。本轮全部已启动查询均读取到has_more=false。

- `efficient-model-compression/insights`：获取105条、3页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。
- `efficient-model-compression/problems`：获取107条、3页，最终has_more=false。只对相关statement筛读，并对下列entry读取详情；不声称逐条精读所有来源论文。

大段概览输出曾截断，后续按领域、相关字段和选定论文逐项读取；没有将第一次打印算成完整阅读。paper_count只是导航量，不作为引用数或质量证据。

## 3. 实际机制查询与转向

|查询|参数/范围|返回数与分页|关键返回ID|
|---|---|---|---|
|[scale oscillation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=scale+oscillation&kind=insight&mode=all&limit=20)|kind=insight；全库|2条/1页|`network-expressivity-I0014`, `neural-quantization-I0004-s1`|
|[量化 尺度 振荡](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%B0%BA%E5%BA%A6+%E6%8C%AF%E8%8D%A1&kind=insight&mode=all&limit=20)|kind=insight；全库|1条/1页|`neural-quantization-I0004-s1`|
|[threshold oscillation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=threshold+oscillation&kind=problem&mode=all&limit=20)|kind=problem；全库|0条/1页|无|
|[activation scale](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+scale&kind=insight&mode=all&limit=20)|kind=insight；全库|49条/3页|`signal-propagation-init-norm-residual-I0150`, `multimodal-medical-diagnosis-I0058`, `attention-redesign-I0140`, `action-recognition-detection-I0034`, `weakly-supervised-localization-I0158`|
|[microscaling](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=microscaling&kind=insight&mode=all&limit=20)|kind=insight；全库|2条/1页|`efficient-model-compression-I0036`, `neural-quantization-I0118`|

另对已返回的真实domain_id做题名检索；全部实际URL和分页在附录。零命中没有用于宣称新颖。

## 4. 证据如何改变提案

领域题名搜索Oscillation直接返回TetraJet和TetraJet-v2；从来源追溯又核对了Overcoming Oscillations和OFQ。OFQ卡片已指出可学习缩放因子会加剧振荡，因此撤回“尺度首次被发现是原因”这一宽泛主张。

实际选读TetraJet§4–6和TetraJet-v2§3。原文中的潜在变量是w/s，量化轨迹和主权重轨迹不同，并已有Q-EMA、Q-Ramping和OsciReset。这将候选引向更具体的干预：把同一w/s变化的分子和分母分开，在同输入下交换权重与尺度状态。

Half-S与Quartet II说明尺度的表示质量、舍入无偏性本身就会改善结果。最终提案必须同时排除“只是更低单步MSE”“只是裁剪变化”和“共同的激活离群值”这些解释。

保留的不是一款未经验证的尺度平滑器，而是局部四点重放、整网短窗口干预及长期复核组成的诊断协议。对称分解和交互差分是已有统计工具，不称作新公式。

## 5. problem/insight及用途

- **[efficient-model-compression-P0033](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0033)**｜目标problem。深度网络与线性模型的低精度训练难以保持收敛与准确率，有限范围和有效位无法适应动态分布，溢出、微小更新丢失及系统性量化偏差沿反向传播和参数递推累积。

  本例用途：动态范围、细小更新丢失和系统量化误差影响收敛。 原始范围：CNN、残差网络、GAN和语言模型的低精度训练数值稳定性与最终精度。

- **[efficient-model-compression-I0036](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0036)**｜机制与近邻insight。神经网络端到端低精度训练可通过随机舍入、采样平均、容量补偿和敏感步骤保高精度维持训练质量；额外采样、加宽和硬件支持会增加成本。

  本例用途：包含TetraJet、Half-S、Quartet等数值来源，需逐篇核验。 原始范围：神经网络前向、反向和参数更新的低精度训练；不以此覆盖专用模型、配置搜索或特定理论问题。

problem是来源问题记录，可能已有部分或完整解法；本例用它定位背景，不将其直接当作开放性证明。insight是已有知识，不自动构成本提案贡献。

## 6. 来源身份、阅读深度和逐篇比较

### Oscillation-reduced mxfp4 training for vision transformers

[《91569》Oscillation-reduced mxfp4 training for vision transformers](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91569) · [原文](https://arxiv.org/html/2502.20853)

阅读：`fulltext_selected`；原文§4–6，式(10)及Q-Ramping说明；API卡片。

已经覆盖：TetraJet已识别主权重小变而量化权重大跳变，以及Q-EMA/Q-Ramping。

剩余差异/风险：本提案不主张首次发现振荡，进一步对w/s中的分子与分母做干预归因。

### TetraJet-v2: Accurate NVFP4 Training for Large Language Models with Oscillation Suppression and Outlier Control

[《103182》TetraJet-v2: Accurate NVFP4 Training for Large Language Models with Oscillation Suppression and Outlier Control](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103182) · [原文](https://arxiv.org/html/2510.27527)

阅读：`fulltext_selected`；原文§3.1–3.3、Algorithm 1；API卡片。

已经覆盖：TetraJet-v2已有OsciRisk轨迹比和OsciReset中心重置。

剩余差异/风险：指标能检测症状，但本提案拟检查不同尺度事件的成因；不能预设原方法错误。

### Overcoming Oscillations in Quantization-Aware Training

[《87671》Overcoming Oscillations in Quantization-Aware Training](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/87671) · [原文](https://arxiv.org/html/2203.11086)

阅读：`source_card`；API abstract/insight/technique/boundaries。

已经覆盖：Overcoming Oscillations已有阻尼与迭代冻结，并分析BN统计污染。

剩余差异/风险：不要把所有不稳定归为尺度；BN与权重阈值机制是竞争解释。

### Oscillation-free Quantization for Low-bit Vision Transformers

[《96191》Oscillation-free Quantization for Low-bit Vision Transformers](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/96191) · [原文](https://arxiv.org/html/2302.02210)

阅读：`source_card`；API abstract/insight/technique/boundaries。

已经覆盖：OFQ已指出可学习缩放因子会加剧振荡。

剩余差异/风险：“尺度会影响振荡”不是新发现；剩余是共享微尺度事件的因果份额与功能扰动评估。

### Half-{S}: Halving the Scale for Near-Lossless 4-Bit {LLM} Training

[《239846》Half-{S}: Halving the Scale for Near-Lossless 4-Bit {LLM} Training](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/239846)

阅读：`source_card`；API abstract/insight/technique/boundaries；来源摘要。

已经覆盖：Half-S已针对max-scaling与重尾表示失配提出尺度改进。

剩余差异/风险：尺度改善可能只是降低单步MSE，须与动态时序机制分离。

### Quartet II: Accurate LLM Pre-Training in NVFP4 by Improved Unbiased Gradient Estimation

[《102046》Quartet II: Accurate LLM Pre-Training in NVFP4 by Improved Unbiased Gradient Estimation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102046) · [原文](https://arxiv.org/html/2601.22813)

阅读：`source_card`；API abstract/insight/technique/boundaries。

已经覆盖：Quartet II已有微尺度上的随机校正与前后向不同量化规则。

剩余差异/风险：无偏梯度和尺度设计是强基线，不把它们的改善误归因给新诊断。

## 7. 错配、工具失败与覆盖缺口

搜索结果中所谓S-QAT与arXiv 2605.00396无法对应：实际HTTP标题为Riemannian Optimization over Symmetric Positive Definite Matrices with the Alpha-Procrustes Geometry。该条从量化证据中剔除。未通过这一不匹配来证明不存在其他尺度振荡工作。

by-arxiv的404只表示该接口本轮未匹配，不表示论文不存在或未被其他字段收录。对未匹配调用最多两次后停止；未伪造ID。公开论文HTML成功下载后先核对标题，再决定是否引用。实际标题错配的论文保留在工作记录中，但不作为该研究的支持证据。

现有前作已经处理权重阈值和缩放影响。剩余空间是共享微尺度事件、物理输出变化与训练损失之间的可干预归因，并非首次发现振荡或首次改变尺度。

## 8. 已完成验证与未完成工作

四种Q(W,s)的数值枚举验证了权重份额与尺度份额之和等于总变化；另验证相同整数标签2在尺度0.1与0.11下对应0.2和0.22。没有做真实FP4训练。

已完成API身份与字段核验、分页、指定原文章节阅读、近邻比较、提案和可证伪计划。没有完成模型训练、真实GPU速度比较或形式化全模型证明；未将数值恒等式或小例子说成实验成果。其余研究任务在提案中以未来验证列出，而不影响本次“案例与提案整理”的交付范围。

## 附录A：本例相关的真实API账本

共享初始浏览及本例相关请求共53条，按开始时间排序；与其他例重复的共享请求不视为重复研究证据。llms.txt连接另见第2节。完整本轮请求记录保存在工作区，不删除失败项。

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
|26|2026-11-13 03:10:58|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0036](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0036)|200|
|27|2026-11-13 03:11:00|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0033](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0033)|200|
|28|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Activation&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Activation&limit=20)|200；{"count":20,"limit":20,"has_more":true,"next_after":"252811"}|
|29|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Checkpoint&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Checkpoint&limit=20)|200；{"count":4,"limit":20,"has_more":false,"next_after":null}|
|30|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Randomized&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Randomized&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|31|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=KEAP&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=KEAP&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|32|2026-11-13 03:11:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=GACT&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=GACT&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|33|2026-11-13 03:11:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=ActNN&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=ActNN&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|34|2026-11-13 03:11:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Oscillation&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Oscillation&limit=20)|200；{"count":2,"limit":20,"has_more":false,"next_after":null}|
|35|2026-11-13 03:11:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Scale&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Scale&limit=20)|200；{"count":5,"limit":20,"has_more":false,"next_after":null}|
|36|2026-11-13 03:11:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Activation&limit=20&after=252811](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Activation&limit=20&after=252811)|200；{"count":14,"limit":20,"has_more":false,"next_after":null}|
|37|2026-11-13 03:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91569](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91569)|200|
|38|2026-11-13 03:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103182](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103182)|200|
|39|2026-11-13 03:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/239846](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/239846)|200|
|40|2026-11-13 03:14:11|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2605.00396](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2605.00396)|HTTP Error 404: Not Found|
|41|2026-11-13 03:14:12|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2605.00396](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2605.00396)|HTTP Error 404: Not Found|
|42|2026-11-13 03:14:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=scale+oscillation&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=scale+oscillation&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|43|2026-11-13 03:14:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%B0%BA%E5%BA%A6+%E6%8C%AF%E8%8D%A1&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%B0%BA%E5%BA%A6+%E6%8C%AF%E8%8D%A1&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|44|2026-11-13 03:14:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=threshold+oscillation&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=threshold+oscillation&kind=problem&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|45|2026-11-13 03:14:37|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+scale&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+scale&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|46|2026-11-13 03:14:38|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+scale&kind=insight&mode=all&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+scale&kind=insight&mode=all&limit=20&offset=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":40}|
|47|2026-11-13 03:14:40|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+scale&kind=insight&mode=all&limit=20&offset=40](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=activation+scale&kind=insight&mode=all&limit=20&offset=40)|200；{"limit":20,"count":9,"has_more":false,"sort":"relevance","next_offset":null}|
|48|2026-11-13 03:14:41|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=microscaling&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=microscaling&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|49|2026-11-13 03:19:54|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/87671](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/87671)|200|
|50|2026-11-13 03:19:56|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/96191](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/96191)|200|
|51|2026-11-13 03:19:57|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102046](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102046)|200|
|52|2026-11-13 03:22:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Gradient+Prediction&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Gradient+Prediction&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|53|2026-11-13 03:22:12|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Scale+Oscillation&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Scale+Oscillation&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|

## 附录B：原文HTTP访问与标题校验

- 2026-11-13 03:14:28，[GET](https://arxiv.org/html/2605.00396)：200；实际标题：Riemannian Optimization over Symmetric Positive Definite Matrices with the Alpha-Procrustes Geometry。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:30，[GET](https://arxiv.org/html/2502.20853)：200；实际标题：Oscillation-Reduced MXFP4 Training for Vision Transformers。是否采用与阅读深度见第6–7节。
- 2026-11-13 03:14:31，[GET](https://arxiv.org/html/2510.27527)：200；实际标题：TetraJet-v2: Accurate NVFP4 Training for Large Language Models with Oscillation Suppression and Outlier Control。是否采用与阅读深度见第6–7节。

检索时间没有人为历史截止；但数据库快照、关键词召回和未公开稿件均限制覆盖。题名核验不证明新颖性，样本实验也不能替代完整正确性证明。
