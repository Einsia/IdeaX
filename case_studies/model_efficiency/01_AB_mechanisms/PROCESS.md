# 示例 01｜A+B mechanisms：谱球面优化器的全过程

整理日期：2026年11月13日（Asia/Shanghai）。本次材料整理基于已经完成的检索与阅读，没有新增文献搜索，也没有训练模型。研究全过程由单agent完成，未调用子agent；检索未设置历史截止日。

## 1. 任务输入与案例定位

研究方向是稳定的W4A4训练优化器，要求机制级变化；当前目标是为六种探索模式分别制作案例。用户指定第一个A+B案例为“谱球面优化器”。因此，这次工作从已知目标出发，检查能否通过LitGraph追溯问题、组成机制与来源，再形成论文中的研究提案。

**本例属于已有方法的证据重构。** SSO是已有论文贡献。当前图谱的问题与洞见条目已经包含该方法，不能把本轮过程描述为未知答案下独立发明SSO，也不能把它当作无泄漏的发现能力评测。

本例的两个组成机制被确定为：A是谱范数约束下的矩阵最陡下降，B是权重本身的谱范数约束。研究重点是B如何改变A的方向求解。它们同属神经网络优化，故主模式是A+B；不需要把它解释为跨领域迁移。

## 2. 真实执行顺序

以下时刻由已保存的HTTP请求时间换算为北京时间，表示请求开始时间，不表示全文阅读完成时间。后面为了说明概念而整理的“问题→机制→组合”路线，与实际执行顺序分开记录。

|阶段|请求时间（2026-11-13）|实际动作|形成的证据或调整|
|---|---|---|---|
|连接|02:07|访问stats、llms.txt、openapi.json|三项均HTTP200；确认只读、无需key、字段和分页规则|
|初步定位|02:08|检索优化器/量化领域，以及中英文谱球面、谱范数关键词；同时读取上轮真实API缓存|获得候选ID；中文“谱球面”未命中，英文能导航至相关条目|
|核验已知目标|02:08|按已有响应中的ID读取SSO及相关优化器论文详情|确认98525为SSO；这是已知目标核验，发生在后续问题导向补检之前|
|展开领域与机制|02:09|读取领域详情、分页insights；检索Muon、Nero、Sphere等；读取问题/洞见详情；获取公开原文|定位I0054、I0012和P0158，开始对照聚合卡片与原文|
|补齐问题路径与低精度边界|02:12|分页获取problems；用“谱范数”“权重谱”“激活”等补检；查W4A4/FP4近邻|实际找回P0158；确认低精度扩展不能由SSO结论直接推出|
|检查最近邻|02:13–02:14|查Scion、Normalized Architectures、低精度spectral以及sphere量化；读取相关论文卡片|区分受约束Scion、归一化4-bit架构、谱缩放与球面量化码本|
|路径重放|02:17|从领域查询开始实际运行独立脚本|18次只读请求，自动从返回字段取得ID，追溯到四篇核心论文|

首轮连接3次、探索请求78次、重放18次，共99次只读服务访问；另获取5篇公开HTML。服务访问均成功，本轮没有API重试。通用web工具未返回可用内容，因此论文原文通过实际HTTP读取。所有分页查询均读到has_more=false；完整请求账本见附录。

## 3. 从API定位问题与两个机制

### 3.1 定位领域与问题

先调用：

```text
GET /api/v1/domains?q=优化器&limit=20
```

请求参数实际经过URL编码，返回领域`practical-adaptive-optimizers`。该领域包含145条problem、96条insight和524篇论文。读取领域详情后，采用以下针对性查询：

```text
GET /api/v1/search?q=谱范数&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20
```

返回7条，其中 [practical-adaptive-optimizers-P0158](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-P0158) 记录了更新谱尺度与权重谱尺度可能失控的问题。读取它的`statement`、`mechanism`、`scope`、`techniques`和`supporting_papers`后，目标被具体化为：**限制单步更新，并不自动限制长期累积后的权重放大尺度。**

其来源已经包含SSO，这一步提供问题背景与来源导航，不证明问题尚未解决。[实际查询](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E8%8C%83%E6%95%B0&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20)

### 3.2 机制A：矩阵谱更新

领域内搜索`Scion`，`kind=insight`、`mode=all`，返回 [practical-adaptive-optimizers-I0054](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0054)。展开`techniques`后，可追溯：

- [《200716》Understanding Gradient Orthogonalization for Deep Learning via Non-Euclidean Trust-Region Optimization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200716)：将Muon类正交化方向纳入非欧信赖域分析。
- [《92541》Training Deep Learning Models with Norm-Constrained LMOs](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/92541)：范数球上的线性最小化预言机（LMO），同时包含受约束SCG和无约束uSCG。

这使A具有明确含义：在矩阵谱范数步长预算中选择局部下降方向。Scion原文的受约束分支也已控制权重范数，因此后续不能写成“此前所有谱优化器都只控制更新”。

### 3.3 机制B：权重硬约束

领域内搜索`Nero`，返回 [practical-adaptive-optimizers-I0012](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0012)，其中Nero技术项关联 [《81314》Learning by Turning: Neural Architecture Aware Optimisation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/81314)。原文§3.1和§4表明，它通过逐神经元零均值和L2范数约束维持平衡网络。

这提供“把权重可行域写进优化器”的机制启发。但是，逐神经元长度固定，不等于整个矩阵的谱范数固定。为与A的几何一致，案例将B具体化为矩阵谱球面约束。这个组织方式用于解释A+B，不声称Nero是SSO作者真实创作过程中的直接来源。

### 3.4 核验已知组合

领域论文题名搜索`Spectral Sphere`返回 [《98525》Controlled LLM Training on Spectral Sphere](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/98525)。进一步读取论文卡片和原文§2–4，确认其组合包括谱更新、权重谱球面、切向约束、拉格朗日乘子求解和回缩。

用于理解的证据依赖线为：

```text
优化器领域
  ├─ 谱范数问题 → P0158：区分更新控制与权重控制
  ├─ Scion → I0054 → 200716 / 92541：机制A
  └─ Nero  → I0012 → 81314：机制B的相关启发
                         ↓
             98525 / SSO原文：核验联合机制
                         ↓
         W4A4近邻与原文限制：确定剩余研究问题
```

## 4. 检索转向与失败查询

本轮使用了多组中英文表达，但关键词并不总能直接导航到目标。

|实际查询|结果|采取的动作|
|---|---|---|
|全库insight：谱球面|0条|换用英文Spectral Sphere|
|全库insight：Spectral Sphere|5条，含I0054|限定优化器领域后得到1条相关结果|
|领域insight：spectral norm|只返回I0145|没有把它写成直接找到Muon；改读领域概览与Scion来源|
|领域insight：球面、切向|均0条|通过Nero、Sphere及论文原文寻找约束机制|
|领域论文题名：MuonSphere|0条|原文§3.4实际找到MuonSphere对照|
|Spectral Sphere quantization、SSO FP4、谱球面 量化|均0条|不据此认定W4A4方向新颖；继续读SSO原文限制及低精度近邻|

分页上，优化器insights按50条一页读了2页，共96条；problems读了3页，共145条。前者做statement概览，后者获取完整列表并筛选相关项。全库`spectral norm`读了3页，共41条；领域problem的“权重谱”读了2页，共22条。没有把完整下载等同逐条深入阅读，也没有把paper_count当成外部引用数。

## 5. 原文如何改变方案表述

### 5.1 从“两个优化器相加”收紧为“两个约束联合求解”

最初可以把方向概括成谱更新加权重归一化。SSO原文§3.4提供了更严格的区分：MuonSphere已经代表不含完整切向求解的归一化对照；SSO在求方向时加入谱球面的一阶可行性条件。

据此，案例的核心不再是“先运行A，再运行B”，而是**B改变A的可行域与解**。这也决定了实验必须包括MuonSphere，不能只比较完整方法与AdamW。

### 5.2 区分不同几何约束

阅读Nero、Scion和Pion后，保留了以下边界：Nero的逐神经元L2约束不同于矩阵谱球面；受约束Scion已有范数控制；Pion的理想正交变换保持整个奇异值谱，SSO主要固定最大奇异值。因此，不把它们统一称为同一个“旋转优化器”，也不声称权重约束本身首次出现。

### 5.3 用原文校正卡片

SSO卡片的`boundaries`提示伪码可能用梯度奇异值缩放权重。实际读取的当前原文Algorithm 1第8行是`PowerIteration(W_t)`，与权重谱回缩一致。提案按原文解释，记录卡片差异，未把卡片当成全文或最终事实。

### 5.4 撤回对W4A4效果的预设

原文§6.1使用BF16混合精度；§5.2的msign使用FP32；§5.3将FP8/NVFP4列为未来工作，并指出残差流仍有离群值。于是研究问题被收紧为：**连续谱约束能否传递到实际量化计算，以及何时不能？**

原文Table 2在对应设置下报告SSO单步开销高于Muon。该证据使验证计划同时采用同token和同墙钟比较，不把减少训练步数等同实际加速。

## 6. 阅读证据与作用

本轮读取/筛选15篇论文详情，并获取5篇公开HTML。对SSO、Nero、Scion做指定原文章节选读；其他材料按实际卡片阅读深度标记，不把下载视为通读。

- **[《98525》Controlled LLM Training on Spectral Sphere](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/98525)**。阅读：`fulltext_selected`；原文§2–4、Algorithm 1、§5.1–5.3、§6.1、§6.2/6.3/6.4文字描述；API abstract/insight/technique/boundaries。作用：本案例主体；谱步、谱球面、切向求根与回缩均属已有SSO贡献。 边界：不是本轮新优化器；W4A4假设需单独实验，原文已列低精度未来工作。

- **[《200716》Understanding Gradient Orthogonalization for Deep Learning via Non-Euclidean Trust-Region Optimization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200716)**。阅读：`source_card`；API abstract、insight、technique、boundaries；原文已获取，本轮不计全文精读。作用：谱范数信赖域与Muon解释，支持A。 边界：没有因此自动得到固定权重谱球面；但不能声称非欧信赖域是新概念。

- **[《92541》Training Deep Learning Models with Norm-Constrained LMOs](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/92541)**。阅读：`fulltext_selected`；原文§3、Algorithm 1/2、§3.1–3.2；API abstract/insight/technique/boundaries。作用：范数LMO、受约束SCG与无约束uSCG、尺度选择。 边界：Scion已有权重范数控制；与SSO比较球内/球面、凸组合/切向最陡更新，不能偷换成完全无约束基线。

- **[《81314》Learning by Turning: Neural Architecture Aware Optimisation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/81314)**。阅读：`fulltext_selected`；原文§3.1–3.2、§4、Algorithm 1；API abstract/insight/technique/boundaries。作用：权重硬约束与旋转式相对更新，支持B的机制启发。 边界：逐神经元L2/零均值约束不同于矩阵谱约束；本文不主张SSO作者的历史来源就是Nero。

- **[《200213》Pion: A Spectrum-Preserving Optimizer via Orthogonal Equivalence Transformation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200213)**。阅读：`source_card`；API abstract、insight、technique、boundaries。作用：Pion以左右正交变换保持权重谱，属于当前检索不能遗漏的近邻。 边界：其理想更新固定整个奇异值谱；SSO只固定最大奇异值而允许其余谱结构改变。近似指数实现不能直接当作精确保谱。

- **[《101195》NorMuon: Making Muon more efficient and scalable](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/101195)**。阅读：`source_card`；API abstract、insight、technique、boundaries。作用：NorMuon已将正交化与神经元级自适应结合，也是A+B优化器。 边界：它校正更新行幅度，不等于权重谱球面及对应切向约束。

- **[《205104》Normalized Architectures are Natively 4-Bit](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205104)**。阅读：`source_card`；API abstract、insight、technique、boundaries。作用：归一化架构已有NVFP4训练证据，提示几何约束与低精度存在相关路径。 边界：约束权重和隐藏表示、修改残差结构，不等于只替换优化器；因此作为架构参考另列。

- **[《91868》Quest: Stable training of llms with 1-bit weights and activations](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91868)**。阅读：`source_card`；本轮API abstract、insight、boundaries；上轮原文§3已读但本轮按卡片标记。作用：QuEST已稳定低比特权重与激活训练，使用Hadamard和信任梯度。 边界：SSO约束谱几何，不直接处理所有量化梯度偏差；必须做相同量化器下优化器对照。

- **[《91569》Oscillation-reduced mxfp4 training for vision transformers](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91569)**。阅读：`source_card`；本轮API abstract、insight、boundaries。作用：TetraJet已有Q-EMA/Q-Ramping，量化权重振荡不能当作新发现。 边界：其目标是舍入与更新频率；不等于谱球面可行性。

- **[《103182》TetraJet-v2: Accurate NVFP4 Training for Large Language Models with Oscillation Suppression and Outlier Control](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103182)**。阅读：`source_card`；本轮API abstract、insight、boundaries。作用：TetraJet-v2已有NVFP4的振荡重置与离群值控制。 边界：SSO本身未解决同样的离散跳变和残差离群值，需要公平对照。

- **[《102046》Quartet II: Accurate LLM Pre-Training in NVFP4 by Improved Unbiased Gradient Estimation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102046)**。阅读：`source_card`；API abstract、insight、boundaries。作用：Quartet II提供NVFP4前后向量化与梯度估计参考。 边界：数值格式/量化器与优化器机制正交；不能把内核或舍入改进混成SSO贡献。

- **[《102082》Rank-Aware Spectral Bounds on Attention Logits for Stable Low-Precision Training](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102082)**。阅读：`source_card`；API abstract、insight、boundaries。作用：已有利用注意力交互矩阵谱与秩制定低精度缩放的工作。 边界：不应把“用权重谱信息控制低精度激活溢出”笼统宣称首次；它是尺度设计，不是SSO切向更新。

## 7. 最终形成的提案与核查

提案保留“谱最陡下降×权重谱约束”的A+B结构，将已知SSO作为组合实例，把未验证部分限定为W4A4中的机制与适用边界。关键检验是：完整切向耦合是否优于简单归一化，并且是否缩小相对于各优化器自身BF16基线的量化损失差距。

已经完成的验证仅包括：API身份核对、分页完整性、原文机制核对、18请求路径重放，以及一个2×2矩阵的确定性代数检查。没有模型训练，没有W4A4性能或加速结果。重放脚本确实从真实响应解析ID，追溯到81314、92541、98525和200716四篇论文。

查新结论是：SSO本体及其低精度动机均已有来源；“SSO用于W4A4”本身不足以构成原创算法贡献。新的研究价值取决于是否发现量化有效几何与连续谱约束之间的重要差异，并以严格对照形成机制或边界结论。当前检索不排除后续相关工作，零命中不证明新颖性。

## 附录：实际请求账本

以下为全部99次服务访问的真实URL。参数在实际请求中均经过编码。分页栏保留服务返回的游标；默认每页limit不代表全体数量。请求时间统一显示为Asia/Shanghai。正文中的证据依赖线不替代本账本。

### 首次连接

|序号|时间|实际GET请求|结果与分页|
|---|---|---|---|
|1|2026-11-13 02:07:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/stats](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/stats)|HTTP 200|
|2|2026-11-13 02:07:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/llms.txt](https://kevin-wake-stuffed-anti.trycloudflare.com/llms.txt)|HTTP 200|
|3|2026-11-13 02:07:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/openapi.json](https://kevin-wake-stuffed-anti.trycloudflare.com/openapi.json)|HTTP 200|

### 探索与追溯

|序号|时间|实际GET请求|结果与分页|
|---|---|---|---|
|1|2026-11-13 02:08:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E4%BC%98%E5%8C%96%E5%99%A8&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E4%BC%98%E5%8C%96%E5%99%A8&limit=20)|HTTP 200；{"count":1,"total":1,"limit":20,"has_more":false,"next_offset":null}|
|2|2026-11-13 02:08:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=quantization&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=quantization&limit=20)|HTTP 200；{"count":1,"total":1,"limit":20,"has_more":false,"next_offset":null}|
|3|2026-11-13 02:08:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E7%90%83%E9%9D%A2&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E7%90%83%E9%9D%A2&kind=insight&mode=all&limit=20)|HTTP 200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|4|2026-11-13 02:08:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Spectral+Sphere&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Spectral+Sphere&kind=insight&mode=all&limit=20)|HTTP 200；{"limit":20,"count":5,"has_more":false,"sort":"relevance","next_offset":null}|
|5|2026-11-13 02:08:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%9F%A9%E9%98%B5+%E6%9D%83%E9%87%8D+%E8%B0%B1&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%9F%A9%E9%98%B5+%E6%9D%83%E9%87%8D+%E8%B0%B1&kind=problem&mode=all&limit=20)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|6|2026-11-13 02:08:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+norm&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+norm&kind=insight&mode=all&limit=20)|HTTP 200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|7|2026-11-13 02:08:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20)|HTTP 200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|8|2026-11-13 02:08:37|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+norm&kind=insight&mode=all&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+norm&kind=insight&mode=all&limit=20&offset=20)|HTTP 200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":40}|
|9|2026-11-13 02:08:38|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=20)|HTTP 200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":40}|
|10|2026-11-13 02:08:39|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=40](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=40)|HTTP 200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":60}|
|11|2026-11-13 02:08:40|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+norm&kind=insight&mode=all&limit=20&offset=40](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+norm&kind=insight&mode=all&limit=20&offset=40)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|12|2026-11-13 02:08:40|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=60](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=60)|HTTP 200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":80}|
|13|2026-11-13 02:08:42|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=80](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=80)|HTTP 200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":100}|
|14|2026-11-13 02:08:43|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=100](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2+%E7%BA%A6%E6%9D%9F&kind=insight&mode=all&limit=20&offset=100)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|15|2026-11-13 02:08:51|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/98525](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/98525)|HTTP 200|
|16|2026-11-13 02:08:51|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/92541](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/92541)|HTTP 200|
|17|2026-11-13 02:08:51|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/101195](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/101195)|HTTP 200|
|18|2026-11-13 02:08:51|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/99213](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/99213)|HTTP 200|
|19|2026-11-13 02:08:51|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102876](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102876)|HTTP 200|
|20|2026-11-13 02:08:52|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200213](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200213)|HTTP 200|
|21|2026-11-13 02:08:52|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200716](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200716)|HTTP 200|
|22|2026-11-13 02:08:52|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/81314](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/81314)|HTTP 200|
|23|2026-11-13 02:08:52|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205104](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205104)|HTTP 200|
|24|2026-11-13 02:09:44|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers)|HTTP 200|
|25|2026-11-13 02:09:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/problems?q=%E8%B0%B1&mode=any&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/problems?q=%E8%B0%B1&mode=any&limit=20)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|26|2026-11-13 02:09:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/insights?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/insights?sort=paper_count&limit=50)|HTTP 200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":50}|
|27|2026-11-13 02:09:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Muon&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Muon&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":12,"has_more":false,"sort":"relevance","next_offset":null}|
|28|2026-11-13 02:09:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Nero&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Nero&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|29|2026-11-13 02:09:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Spectral+Sphere&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Spectral+Sphere&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|30|2026-11-13 02:09:46|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+norm&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+norm&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|31|2026-11-13 02:09:47|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E7%90%83%E9%9D%A2&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|32|2026-11-13 02:09:47|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/insights?sort=paper_count&limit=50&offset=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/insights?sort=paper_count&limit=50&offset=50)|HTTP 200；{"limit":50,"count":46,"has_more":false,"sort":"paper_count","next_offset":null}|
|33|2026-11-13 02:09:47|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%88%87%E5%90%91&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%88%87%E5%90%91&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|34|2026-11-13 02:09:47|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%9D%83%E9%87%8D+%E6%BC%82%E7%A7%BB&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%9D%83%E9%87%8D+%E6%BC%82%E7%A7%BB&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|35|2026-11-13 02:09:47|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Spectral+Sphere&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Spectral+Sphere&limit=20)|HTTP 200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|36|2026-11-13 02:09:48|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=MuonSphere&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=MuonSphere&limit=20)|HTTP 200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|37|2026-11-13 02:09:48|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Manifold&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Manifold&limit=20)|HTTP 200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|38|2026-11-13 02:09:48|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Spectral&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Spectral&limit=20)|HTTP 200；{"count":10,"limit":20,"has_more":false,"next_after":null}|
|39|2026-11-13 02:09:49|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Spherical&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Spherical&limit=20)|HTTP 200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|40|2026-11-13 02:09:49|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Sphere&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Sphere&limit=20)|HTTP 200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|41|2026-11-13 02:09:50|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Norm-Constrained&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Norm-Constrained&limit=20)|HTTP 200；{"count":2,"limit":20,"has_more":false,"next_after":null}|
|42|2026-11-13 02:09:50|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Tensor+Programs&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Tensor+Programs&limit=20)|HTTP 200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|43|2026-11-13 02:09:51|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-P0158](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-P0158)|HTTP 200|
|44|2026-11-13 02:09:52|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0054](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0054)|HTTP 200|
|45|2026-11-13 02:09:54|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0012](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0012)|HTTP 200|
|46|2026-11-13 02:09:55|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0168](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0168)|HTTP 200|
|47|2026-11-13 02:12:14|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/problems?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/problems?sort=paper_count&limit=50)|HTTP 200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":50}|
|48|2026-11-13 02:12:14|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E8%8C%83%E6%95%B0&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E8%8C%83%E6%95%B0&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20)|HTTP 200；{"limit":20,"count":7,"has_more":false,"sort":"relevance","next_offset":null}|
|49|2026-11-13 02:12:14|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%9D%83%E9%87%8D%E8%B0%B1&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%9D%83%E9%87%8D%E8%B0%B1&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20)|HTTP 200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|50|2026-11-13 02:12:14|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%BF%80%E6%B4%BB&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%BF%80%E6%B4%BB&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20)|HTTP 200；{"limit":20,"count":6,"has_more":false,"sort":"relevance","next_offset":null}|
|51|2026-11-13 02:12:14|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20)|HTTP 200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|52|2026-11-13 02:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=tangent&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=tangent&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|53|2026-11-13 02:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%9D%83%E9%87%8D%E8%B0%B1&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E6%9D%83%E9%87%8D%E8%B0%B1&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20&offset=20)|HTTP 200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|54|2026-11-13 02:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/problems?sort=paper_count&limit=50&offset=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/problems?sort=paper_count&limit=50&offset=50)|HTTP 200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":100}|
|55|2026-11-13 02:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=sphere&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=sphere&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|56|2026-11-13 02:12:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=MuonSphere&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=MuonSphere&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|57|2026-11-13 02:12:17|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=W4A4&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=W4A4&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|58|2026-11-13 02:12:17|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=FP4&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=FP4&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|59|2026-11-13 02:12:17|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Spectral+Sphere+quantization&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Spectral+Sphere+quantization&mode=all&limit=20)|HTTP 200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|60|2026-11-13 02:12:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=SSO+FP4&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=SSO+FP4&mode=all&limit=20)|HTTP 200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|61|2026-11-13 02:12:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E7%90%83%E9%9D%A2+%E9%87%8F%E5%8C%96&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E7%90%83%E9%9D%A2+%E9%87%8F%E5%8C%96&mode=all&limit=20)|HTTP 200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|62|2026-11-13 02:12:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+low+precision&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=spectral+low+precision&mode=all&limit=20)|HTTP 200；{"limit":20,"count":3,"has_more":false,"sort":"relevance","next_offset":null}|
|63|2026-11-13 02:12:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/problems?sort=paper_count&limit=50&offset=100](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/problems?sort=paper_count&limit=50&offset=100)|HTTP 200；{"limit":50,"count":45,"has_more":false,"sort":"paper_count","next_offset":null}|
|64|2026-11-13 02:12:19|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=normalized+4-bit&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=normalized+4-bit&mode=all&limit=20)|HTTP 200；{"limit":20,"count":3,"has_more":false,"sort":"relevance","next_offset":null}|
|65|2026-11-13 02:12:21|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0061](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0061)|HTTP 200|
|66|2026-11-13 02:12:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0033](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-P0033)|HTTP 200|
|67|2026-11-13 02:12:23|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0036](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/efficient-model-compression-I0036)|HTTP 200|
|68|2026-11-13 02:12:25|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/neural-quantization-P0190](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/neural-quantization-P0190)|HTTP 200|
|69|2026-11-13 02:12:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91868](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91868)|HTTP 200|
|70|2026-11-13 02:12:27|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91569](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/91569)|HTTP 200|
|71|2026-11-13 02:12:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103182](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/103182)|HTTP 200|
|72|2026-11-13 02:12:29|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102046](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102046)|HTTP 200|
|73|2026-11-13 02:13:53|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Scion&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Scion&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|74|2026-11-13 02:13:53|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Normalized+Architectures&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Normalized+Architectures&limit=20)|HTTP 200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|75|2026-11-13 02:13:53|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=spectral&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=spectral&limit=20)|HTTP 200；{"count":4,"limit":20,"has_more":false,"next_after":null}|
|76|2026-11-13 02:13:53|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=sphere&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=sphere&limit=20)|HTTP 200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|77|2026-11-13 02:14:52|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102082](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/102082)|HTTP 200|
|78|2026-11-13 02:14:53|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/203871](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/203871)|HTTP 200|

### 独立路径重放

|序号|时间|实际GET请求|结果与分页|
|---|---|---|---|
|1|2026-11-13 02:17:15|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/stats](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/stats)|HTTP 200|
|2|2026-11-13 02:17:17|[https://kevin-wake-stuffed-anti.trycloudflare.com/llms.txt](https://kevin-wake-stuffed-anti.trycloudflare.com/llms.txt)|HTTP 200|
|3|2026-11-13 02:17:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/openapi.json](https://kevin-wake-stuffed-anti.trycloudflare.com/openapi.json)|HTTP 200|
|4|2026-11-13 02:17:19|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E4%BC%98%E5%8C%96%E5%99%A8&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E4%BC%98%E5%8C%96%E5%99%A8&limit=20)|HTTP 200|
|5|2026-11-13 02:17:20|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers)|HTTP 200|
|6|2026-11-13 02:17:21|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E8%8C%83%E6%95%B0&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E8%8C%83%E6%95%B0&kind=problem&unit=practical-adaptive-optimizers&mode=any&limit=20)|HTTP 200|
|7|2026-11-13 02:17:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-P0158](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-P0158)|HTTP 200|
|8|2026-11-13 02:17:24|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Scion&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Scion&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200|
|9|2026-11-13 02:17:25|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0054](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0054)|HTTP 200|
|10|2026-11-13 02:17:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Nero&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Nero&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200|
|11|2026-11-13 02:17:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0012](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/practical-adaptive-optimizers-I0012)|HTTP 200|
|12|2026-11-13 02:17:29|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/81314](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/81314)|HTTP 200|
|13|2026-11-13 02:17:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/92541](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/92541)|HTTP 200|
|14|2026-11-13 02:17:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/98525](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/98525)|HTTP 200|
|15|2026-11-13 02:17:33|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200716](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/200716)|HTTP 200|
|16|2026-11-13 02:17:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Spectral+Sphere&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/practical-adaptive-optimizers/papers?q=Spectral+Sphere&limit=20)|HTTP 200|
|17|2026-11-13 02:17:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E7%90%83%E9%9D%A2&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E8%B0%B1%E7%90%83%E9%9D%A2&kind=insight&mode=all&limit=20)|HTTP 200|
|18|2026-11-13 02:17:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Spectral+Sphere&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Spectral+Sphere&kind=insight&unit=practical-adaptive-optimizers&mode=all&limit=20)|HTTP 200|

### 公开原文读取

- 2026-11-13 02:09:58，GET [https://arxiv.org/html/2601.08393](https://arxiv.org/html/2601.08393)，HTTP 200。阅读深度见正文第6节。
- 2026-11-13 02:09:58，GET [https://arxiv.org/html/2503.12645](https://arxiv.org/html/2503.12645)，HTTP 200。阅读深度见正文第6节。
- 2026-11-13 02:09:58，GET [https://arxiv.org/html/2102.07227](https://arxiv.org/html/2102.07227)，HTTP 200。阅读深度见正文第6节。
- 2026-11-13 02:09:58，GET [https://arxiv.org/html/2502.07529](https://arxiv.org/html/2502.07529)，HTTP 200。阅读深度见正文第6节。
- 2026-11-13 02:09:59，GET [https://arxiv.org/html/2605.12492](https://arxiv.org/html/2605.12492)，HTTP 200。阅读深度见正文第6节。
