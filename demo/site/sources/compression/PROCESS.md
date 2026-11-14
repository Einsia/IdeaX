# 示例02｜Cross-domain transfer：将量化与剪枝作为任务适配操作的全过程

整理日期：2026年11月13日（Asia/Shanghai）。本轮独立单agent完成，没有调用子agent；没有人为设置历史文献截止日。正式交付为本文件和PROPOSAL.md；原始响应与阅读材料保存在工作区中间目录。

## 1. 用户输入与研究边界

用户观察到随机扰动或可训练操作可以用于优化，希望研究能否把量化与剪枝变成模型微调手段。这一描述不足以唯一确定某篇论文，因此本轮没有假定用户指的就是某一个方法，而调查了三个相符的方向：连续零阶扰动、随机候选筛选、可训练状态/操作参数化。

沿用前例的工作方式：实际访问LitGraph，核验ID与来源，公开原文补查最近邻；随后只形成“全过程”和“论文idea提案”。本轮从一般问题出发，检索中发现了已经覆盖大量初始直觉的工作，不能把这些贡献重新包装为新颖方案。

研究重点随证据变为：**在固定部署预算下，基础权重的舍入和删除/恢复操作能否到达有用的任务适配模型；联合选择是否值得额外查询成本？** W4A4不是用户本条的新硬约束，故先把权重位宽和激活精度分开，避免将仅权重压缩说成全4-bit训练。

## 2. 连接与初步检索

实际读取服务`/api/v1/stats`、`/llms.txt`和`/openapi.json`，均HTTP200。客户端对关键词进行URL编码，搜索/领域列表使用next_offset，领域论文列表使用next_after。每个已执行分页查询均到has_more=false。

定位领域的查询包括`pruning`、`剪枝`、`quantization`、`zeroth-order`、`evolution`、`参数高效`、`优化器`。实际得到的相关domain_id为：

- `zeroth-order-optimization`：零阶优化，27条insight。
- `network-pruning`：网络剪枝与稀疏化，103条insight。
- `peft-structural-sparse-adaptation`：参数高效微调的结构化参数化与稀疏更新，65条insight。
- `neural-quantization`：神经网络量化。

本轮对前三个领域分页取得全部195条insight，并筛读statement；只对采用的条目深入读取详情。全库“随机 扰动”返回345条，18页；这是宽泛导航，未将其中所有无关材料算作精读。后续用MeZO、Nero以外的操作式适配、具体量化/掩码题名等限定目标。

## 3. 检索阶段与候选调整

以下按证据用途合并相关动作；查询之间存在交叉执行，真实请求时间顺序见附录A，不将叙事顺序当作严格执行顺序。

### 3.1 确定相符的源域机制

检索`MeZO`得到 [zeroth-order-optimization-I0040](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0040)，其techniques关联 [《196237》Fine-Tuning Language Models with Just Forward Passes](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/196237)。这是把前向扰动反馈转为更新的成熟路线。读取一般离散黑盒条目 [zeroth-order-optimization-I0036](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0036)，进一步找到 [《193966》PROTES: Probabilistic Optimization with Tensor Sampling](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/193966)，机制是学习紧凑候选分布并提高较优候选的概率。

公开检索还找到 [《库外/未核实库内编号》Neural Thickets: Diverse Task Experts Are Dense Around Pretrained Weights](https://arxiv.org/html/2603.12228)。实际阅读§4及Algorithm 1后确认：RandOpt并不进行同样的顺序梯度更新，而是随机采样候选、筛选top-K并集成预测。因此，不能把其集成效果免费移植成“一个压缩模型”的效果。

对于“可训练操作”这一描述，[peft-structural-sparse-adaptation-I0188](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/peft-structural-sparse-adaptation-I0188) 导航到 [《90596》From Weight-Based to State-Based Fine-Tuning: Further Memory Reduction on LoRA with Parallel Control](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/90596) 和 [《426652》Parameter-Free Fine-tuning via Redundancy Elimination for Vision Foundation Models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/426652)。前者训练计算图状态扰动，后者通过通道重映射和候选评分适配视觉模型。这说明优化变量可以是操作/状态，但没有证明任意操作都能成为有效优化器。

### 3.2 剪枝侧已经有直接的任务适配

领域题名与API详情核验到 [《70207》Masking as an Efficient Alternative to Finetuning for Pretrained Language Models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/70207)：冻结预训练权重、学习任务掩码并不是新的想法。公开原文进一步发现 [《库外/未核实库内编号》The Surprising Effectiveness of Deleting Weights in LLM Post-Training](https://arxiv.org/html/2611.10866)，arXiv摘要页显示首次公开为2026年11月7日。本轮没有额外历史截止，因此纳入比较。

Deletion Tuning原文§4表明，其训练使用gate投影的可微软掩码，评估/部署使用硬掩码，且不固定最终稀疏率。因此，它直接覆盖“只删除权重也能适配”的广义主张，但不能被解释为无需反向、无需训练状态或任意高稀疏度下均有效。

该证据使初稿从“把剪枝变成微调”改为更窄的问题：在明确预算和操作可达集合下，能否与码字选择共同进行任务适配。

### 3.3 量化侧也不只是压缩后恢复

搜索`Quantization`、`Fine-Tuning`、`Rounding`和相关题名，核验了：

- [《195498》Memory-Efficient Fine-Tuning of Compressed Large Language Models via sub-4-bit Integer Quantization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/195498) 与 [《65009》A lpha T uning: Quantization-Aware Parameter-Efficient Adaptation of Large-Scale Pre-Trained Language Models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/65009)：量化尺度就是可训练适配参数。
- [《257840》Fine-tuning Quantized Neural Networks with Zeroth-order Optimization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/257840)：对量化尺度使用纯前向零阶优化。
- [《66903》Q u ZO : Quantized Zeroth-Order Fine-Tuning for Large Language Models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/66903)：量化扰动与低精度权重更新已经结合。
- [《176709》Pv-tuning: Beyond straight-through estimation for extreme llm compression](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/176709)：直接更新离散量化代码已是既有方法的一部分。

因此，初稿中的“学量化参数”“不用反传”“直接改码字”分别已有先例。当前提案冻结尺度、限制为基础权重相邻舍入结果，并把可达性作为研究对象；这种限制是需要验证的设计选择，不是天然的新颖性证明。

### 3.4 发现最危险近邻：MaskPro与QOP

[《176792》Maskllm: Learnable semi-structured sparsity for large language models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/176792) 已学习严格N:M模式并支持任务/领域定制。进一步读 [《256802》Maskpro: Linear-space probabilistic learning for strict (n: M)-sparsity on large language models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/256802) 原文§4.2，明确看到仅前向即可计算的策略梯度，以及同批次损失残差基线。因此，“前向反馈学习压缩操作分布”已经有直接目标域实例，不能作为本提案的首创贡献。

沿 [network-pruning-P0055](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0055) 的成员来源追溯，又找到 [《205662》Unifying Sparsity and Discreteness: One-Shot Pruning for Quantized LLMs via Discrete Optimization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205662)：它已经联合优化稀疏支持与离散权重。此处仅取得摘要级结构化卡片，尚不足以排除完整方法的重合，列为高风险近邻。

提案由此改为以科学问题为主：压缩操作的可达解密度、联合与独立选择的差距，以及能否用有限查询获得实质收益；算法作为检验这些问题的工具。

### 3.5 交互分析也必须查重

公开检索初期有来源不可靠的聚合页面，未用它作为证据；随后实际访问IJCAI官方页面，核对得到 [《库外/未核实库内编号》Interaction Effects in Hybrid Compression of Small Language Models](https://ijcai.org/proceedings/2026/631)。页面中的§3.4已经使用四种配置的交互分析。官方页给出的题名与初始检索片段不同，最终以官方题名为准。

因此，四点差分 $J_{11}-J_{10}-J_{01}+J_{00}$只作为诊断，不列作新统计量。剩余待检验的是将可复现的局部交互用于在线候选分配，是否比等查询随机联合搜索更有效。

## 4. 迁移映射与适配过程

源域机制是“采样可执行候选—前向反馈—筛选或学习分布”。目标域状态是固定基座的量化端点选择与稀疏支持。迁移需要完成三项改变：

1. **改变候选空间。** 高斯向量替换为合法舍入翻转和支持交换；每个候选都可部署，且预算明确。
2. **改变理论对象。** 不假设这些离散、有方向偏好的操作是无偏连续梯度；研究有限可达集合及给定分布下的好候选概率。
3. **改变评价。** 下游任务损失替代单纯权重/输出重构；最终模型必须单独评价，集成或额外浮点适配器另计。

目标使用式为 $\widehat W_i=m_i s_g[(1-r_i)\ell_i+r_i u_i]$。剪枝交换保持活动预算，舍入位置限制在前后掩码的共同活动支持上，避免平凡的“删除使舍入无效”。这些是提案的可执行约束，不是已经验证的最优设计。

为检查机制是否自洽，做了一个确定性的三维线性代数例子：单独支持交换或舍入翻转使损失升高，联合动作使损失降低。该例仅说明可能存在局部互补，不能代替模型训练、证明规模化可达性或新颖性。

## 5. 问题与insight证据的实际用途

- **[zeroth-order-optimization-I0040](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0040)**｜源域机制：把前向反馈用于适配；明确MeZO与量化零阶方法已有来源。 原始范围：LLM全参数及部分参数微调，含LoRA多任务；混合方法要求梯度访问，量化需控制舍入偏差，卸载收益依赖互连；偏好优化与API软提示适配不属本族。

- **[zeroth-order-optimization-I0036](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0036)**｜源域机制：从一般离散黑盒优化迁移候选分布学习，而不是假设压缩操作有连续梯度。 原始范围：高维离散最小化，包括QUBO及离散化控制；Tensor Train实现依赖秩等参数，实验优势不是全局最优保证。

- **[peft-structural-sparse-adaptation-I0188](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/peft-structural-sparse-adaptation-I0188)**｜源域补充：可训练状态/操作能够成为适配自由度，但不等同具体优化器或无反向算法。 原始范围：ViT、RoBERTa、LLaMA、LLaVA 等视觉、语言与视觉语言模型的 PEFT。

- **[network-pruning-P0055](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0055)**｜目标问题：单项压缩效果难预测联合效果，候选评估昂贵；提案必须控制搜索预算。 原始范围：深度模型联合剪枝与量化、语言模型量化—蒸馏—剪枝组合及压缩超参数搜索。

- **[network-pruning-P0167](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0167)**｜目标问题：严格N:M掩码优化的组合与状态成本；固定部署开销不能忽略训练开销。 原始范围：Adam 下从头学习的 N:M 稀疏掩码与大语言模型的可转置 N:M 剪枝。

- **[network-pruning-P0240](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0240)**｜目标问题：完整微调与压缩串行仍有高成本；为操作空间适配提供动机。 原始范围：资源受限环境下的大语言模型下游微调与 LoRA 模型结构化剪枝。

- **[network-pruning-I0011](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0011)**｜已有知识/边界：可恢复的剪枝已用于动态稀疏训练，不能将恢复连接当作新机制。 原始范围：CNN和全连接网络的固定掩码或动态稀疏训练，主要用于图像分类与语言模型训练；收益依赖稀疏率、掩码更新开销和硬件支持。

- **[network-pruning-I0019](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0019)**｜部署边界：稀疏必须匹配布局、索引与内核；零值增加不自动产生加速。 原始范围：CNN、LLM、状态空间模型及矩阵乘法的硬件感知稀疏推理；OPT前馈层等事后旋转、分解、置换属于失效条件。

- **[neural-quantization-I0006-s8](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/neural-quantization-I0006-s8)**｜查重边界：剪枝和量化联合优化已存在，剩余贡献要落在任务反馈、可达性及查询成本。 原始范围：图像分类、目标检测等视觉及通用前馈网络的权重存储压缩（含亚比特与向量量化）。可重训与训练后两种条件下的结论不可互换。不含语言与语音模型专用方案。

- **[peft-structural-sparse-adaptation-I0031](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/peft-structural-sparse-adaptation-I0031)**｜评估边界：候选选择易受开发集复用影响；训练搜索集、选择集、测试集须分开。 原始范围：语言、视觉及多模态 PEFT 基准的比较评估与方法选择；结论受任务、评价目标和表示层影响。

## 6. 前作逐项比较与阅读层级

`fulltext_selected`仅指实际选读的原文部分，不表示逐页通读；`source_card`指API摘要与所列结构化字段。库外工作没有编造LitGraph编号。部分原文虽然下载成功，仍按卡片阅读深度记载。

### Neural Thickets: Diverse Task Experts Are Dense Around Pretrained Weights

[《库外/未核实库内编号》Neural Thickets: Diverse Task Experts Are Dense Around Pretrained Weights](https://arxiv.org/html/2603.12228)

阅读：`fulltext_selected`；原文摘要、§2.1–2.2相关描述、§4及Algorithm 1。

对构思的影响：与用户描述相符的随机扰动路线：采样、任务筛选、top-K预测集成。

重合与剩余差异：本提案不能继承连续扰动中的好解密度，也不把集成收益算成单模型适配收益。

### Fine-Tuning Language Models with Just Forward Passes

[《196237》Fine-Tuning Language Models with Just Forward Passes](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/196237)

阅读：`source_card`；API abstract、insight；有效维度和提示条件。

对构思的影响：MeZO说明仅用前向反馈也能推进模型适配。

重合与剩余差异：连续随机方向的梯度估计不能不加证明地搬到删除/离散舍入操作。

### PROTES: Probabilistic Optimization with Tensor Sampling

[《193966》PROTES: Probabilistic Optimization with Tensor Sampling](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/193966)

阅读：`source_card`；API abstract、insight；候选分布、elite选择、TT表示。

对构思的影响：PROTES提供离散黑盒候选分布学习机制，是明确的源域来源。

重合与剩余差异：分布学习本身已知；我们不直接声称TT参数化适合所有压缩掩码。

### From Weight-Based to State-Based Fine-Tuning: Further Memory Reduction on LoRA with Parallel Control

[《90596》From Weight-Based to State-Based Fine-Tuning: Further Memory Reduction on LoRA with Parallel Control](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/90596)

阅读：`source_card`；API abstract、technique。

对构思的影响：State-Based Fine-Tuning对应用户提到的可训练操作/状态扰动路线。

重合与剩余差异：它把参数化扰动加入计算图状态，不是“任意操作自动成为优化器”，也不天然无需反向。

### Parameter-Free Fine-tuning via Redundancy Elimination for Vision Foundation Models

[《426652》Parameter-Free Fine-tuning via Redundancy Elimination for Vision Foundation Models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/426652)

阅读：`source_card`；API abstract、technique、boundaries。

对构思的影响：已有通过前向评分和通道重映射进行视觉模型适配的工作。

重合与剩余差异：原文对象是视觉特征通道，不是量化码字/权重掩码；限制了泛称“操作即微调”的新颖性。

### Masking as an Efficient Alternative to Finetuning for Pretrained Language Models

[《70207》Masking as an Efficient Alternative to Finetuning for Pretrained Language Models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/70207)

阅读：`source_card`；API abstract、insight、technique、boundaries；原文已获取，未把下载计作精读。

对构思的影响：早在2020年的Masking已冻结预训练权重、学习任务二值掩码。

重合与剩余差异：学习掩码替代权重微调不是新概念；该方法还训练任务头并使用STE。

### The Surprising Effectiveness of Deleting Weights in LLM Post-Training

[《库外/未核实库内编号》The Surprising Effectiveness of Deleting Weights in LLM Post-Training](https://arxiv.org/html/2611.10866)

阅读：`fulltext_selected`；原文摘要、§4；arXiv摘要页核对2026-11-07首次公开。

对构思的影响：Deletion Tuning已经把删除作为LLM任务适配，训练gate投影软掩码并部署硬掩码。

重合与剩余差异：只删少量权重实现后训练已经有直接前作；其训练仍反传且不固定稀疏率，不等于严格预算的纯前向联合搜索。

### Memory-Efficient Fine-Tuning of Compressed Large Language Models via sub-4-bit Integer Quantization

[《195498》Memory-Efficient Fine-Tuning of Compressed Large Language Models via sub-4-bit Integer Quantization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/195498)

阅读：`fulltext_selected`；原文§3.1–3.2；API abstract、technique、boundaries。

对构思的影响：PEQA冻结整数权重、训练量化尺度以进行任务适配。

重合与剩余差异：“训练量化参数就是微调”已完成；本候选冻结尺度，学习舍入和掩码选择。

### A lpha T uning: Quantization-Aware Parameter-Efficient Adaptation of Large-Scale Pre-Trained Language Models

[《65009》A lpha T uning: Quantization-Aware Parameter-Efficient Adaptation of Large-Scale Pre-Trained Language Models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/65009)

阅读：`source_card`；API abstract、technique、boundaries。

对构思的影响：AlphaTuning冻结二值编码，只优化部分缩放因子。

重合与剩余差异：不能把尺度微调当作新迁移；且该来源未量化激活。

### Fine-tuning Quantized Neural Networks with Zeroth-order Optimization

[《257840》Fine-tuning Quantized Neural Networks with Zeroth-order Optimization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/257840)

阅读：`fulltext_selected`；原文§3.1–3.2、Algorithm 1；API abstract、technique、boundaries。

对构思的影响：QZO已将零阶优化迁移到量化尺度，固定离散码字并使用前向损失。

重合与剩余差异：“量化+无反向微调”本身已有；本提案把自由度限制为离散压缩操作，需与其直接比较。

### Q u ZO : Quantized Zeroth-Order Fine-Tuning for Large Language Models

[《66903》Q u ZO : Quantized Zeroth-Order Fine-Tuning for Large Language Models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/66903)

阅读：`source_card`；API abstract、technique、boundaries；无可靠库外arXiv映射。

对构思的影响：QuZO已用量化扰动、前向损失和随机舍入更新低精度权重。

重合与剩余差异：不能声称第一个直接更新量化权重的零阶方法；本候选必须显示严格操作可达集与联合选择的独立价值。

### Pv-tuning: Beyond straight-through estimation for extreme llm compression

[《176709》Pv-tuning: Beyond straight-through estimation for extreme llm compression](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/176709)

阅读：`fulltext_selected`；原文§3.1、Algorithm 1、§3.2；API abstract、technique、boundaries。

对构思的影响：PV-Tuning已交替优化连续量化值与离散代码。

重合与剩余差异：离散码字更新已有；其梯度驱动框架与本文受限的前向候选搜索不同，但前者搜索空间通常更大。

### Maskllm: Learnable semi-structured sparsity for large language models

[《176792》Maskllm: Learnable semi-structured sparsity for large language models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/176792)

阅读：`source_card`；API abstract、technique、boundaries。

对构思的影响：MaskLLM已有冻结权重的N:M模式分布学习，以及任务/领域定制掩码。

重合与剩余差异：概率掩码、固定稀疏模式及任务适配都不新；其使用可微采样与反向传播。

### Maskpro: Linear-space probabilistic learning for strict (n: M)-sparsity on large language models

[《256802》Maskpro: Linear-space probabilistic learning for strict (n: M)-sparsity on large language models](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/256802)

阅读：`fulltext_selected`；原文§4.1–4.2、式(9)–(12)、Algorithm 1；API abstract、technique、boundaries。

对构思的影响：MaskPro已用纯前向损失、同批次残差基线与策略梯度学习严格N:M掩码。

重合与剩余差异：这是最强近邻之一；无反向掩码学习、同批次评分和分布更新均不得冒充新贡献。

### Dynamic Sparse No Training: Training-Free Fine-tuning for Sparse LLMs

[《243615》Dynamic Sparse No Training: Training-Free Fine-tuning for Sparse LLMs](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/243615)

阅读：`source_card`；API abstract、technique、boundaries。

对构思的影响：DSnoT已在不反传、不改权重值时迭代剪除/恢复连接。

重合与剩余差异：可逆剪枝和固定稀疏度不是新；本候选用下游任务损失而非只重构原模型，并同时允许舍入编辑。

### Breaking through Deterministic Barriers: Randomized Pruning Mask Generation and Selection

[《72818》Breaking through Deterministic Barriers: Randomized Pruning Mask Generation and Selection](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/72818)

阅读：`source_card`；API abstract、technique、boundaries。

对构思的影响：已有随机生成并筛选剪枝掩码的方法。

重合与剩余差异：不能仅把高斯候选替换成随机掩码作为贡献；该来源使用额外微调与候选评估。

### Unifying Sparsity and Discreteness: One-Shot Pruning for Quantized LLMs via Discrete Optimization

[《205662》Unifying Sparsity and Discreteness: One-Shot Pruning for Quantized LLMs via Discrete Optimization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205662)

阅读：`source_card`；API abstract、technique、boundaries；卡片来源为摘要。

对构思的影响：QOP直接在稀疏性与离散性约束下联合选择支持集和量化权重。

重合与剩余差异：“联合优化掩码与码字”亦已有；仅摘要材料不足以排除其完整算法与本候选的等价。

### Interaction Effects in Hybrid Compression of Small Language Models

[《库外/未核实库内编号》Interaction Effects in Hybrid Compression of Small Language Models](https://ijcai.org/proceedings/2026/631)

阅读：`fulltext_selected`；官方页面标题/摘要、提供的自动提取正文§3.3–3.4；未读原PDF。

对构思的影响：已有剪枝/量化的2×2非加性交互分析。

重合与剩余差异：四点交互差分不是本提案的新统计量；原文是压缩管线评价，本文拟检验能否用于局部任务适配决策。

## 7. 检索失败、覆盖缺口与最终判断

- `RandOpt`条目检索为0；`Deletion Tuning`只返回无关聚合条目。两篇正确arXiv ID按API查询均404，故使用原文，不编造库内paper_id。
- `PEQA`题名查询为0，但完整题名检索及来源追溯找到195498；缩写无结果不等于没有论文。
- 两个初始候选arXiv编号2502.05995、2610.15179未完成目标身份核验，API均404；它们没有作为QuZO或其他方法的有效引文。另有2604.11236、2606.12651试探页面未作为匹配目标的证据。后续以实际API返回的66903、257840和原文替代，未为这些线索补造标题或编号。
- “剪枝 量化 相互作用”“mask rounding”等查询为0，但官方论文已存在交互分析；零命中没有用于证明新颖性。
- 聚合条目包含多种范围，优先用具体paper接口及原文核验。QOP、QuZO等近邻仍只有卡片级材料，完整等价风险尚未排除。对PROTES、自然扰动及可训练状态方法的范围也未宣称普遍保证。
- 检索不是全网穷举；没有证明截至执行日不存在完全相同的联合操作搜索方法。精确研究贡献需在后续查新和实验中进一步确认。

problem条目是来源问题的历史归并，部分障碍已被MaskPro、QOP等工作处理；它们不单独证明问题仍未解决或提案具有新颖性。

最终判断：用户的广义直觉已被多类前作支持。保留的研究提案是“压缩可达的任务适配与预算受限联合搜索”，不再以“量化/剪枝也能微调”作为原创主张。本轮没有模型训练，没有任务提升、显存节省或加速的实测结果。

## 附录A：API请求账本

本轮共记录167次服务请求尝试，其中157次HTTP200、10次404；404均为按arXiv查询未匹配的有限重试。openapi响应没有ok字段，但HTTP成功。只读接口连接可用，没有将未匹配论文伪装为已检索成功。时间统一转换为Asia/Shanghai。

|序号|请求时间|实际GET请求|HTTP/分页|
|---|---|---|---|
|1|2026-11-13 02:37:17|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/stats](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/stats)|200|
|2|2026-11-13 02:37:20|[https://kevin-wake-stuffed-anti.trycloudflare.com/llms.txt](https://kevin-wake-stuffed-anti.trycloudflare.com/llms.txt)|200|
|3|2026-11-13 02:37:21|[https://kevin-wake-stuffed-anti.trycloudflare.com/openapi.json](https://kevin-wake-stuffed-anti.trycloudflare.com/openapi.json)|200|
|4|2026-11-13 02:38:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=pruning&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=pruning&limit=20)|200；{"count":1,"total":1,"limit":20,"has_more":false,"next_offset":null}|
|5|2026-11-13 02:38:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E5%89%AA%E6%9E%9D&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E5%89%AA%E6%9E%9D&limit=20)|200；{"count":2,"total":2,"limit":20,"has_more":false,"next_offset":null}|
|6|2026-11-13 02:38:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=quantization&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=quantization&limit=20)|200；{"count":1,"total":1,"limit":20,"has_more":false,"next_offset":null}|
|7|2026-11-13 02:38:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=zeroth-order&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=zeroth-order&limit=20)|200；{"count":1,"total":1,"limit":20,"has_more":false,"next_offset":null}|
|8|2026-11-13 02:38:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=evolution&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=evolution&limit=20)|200；{"count":2,"total":2,"limit":20,"has_more":false,"next_offset":null}|
|9|2026-11-13 02:38:23|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E5%8F%82%E6%95%B0%E9%AB%98%E6%95%88&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E5%8F%82%E6%95%B0%E9%AB%98%E6%95%88&limit=20)|200；{"count":1,"total":1,"limit":20,"has_more":false,"next_offset":null}|
|10|2026-11-13 02:38:23|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E4%BC%98%E5%8C%96%E5%99%A8&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains?q=%E4%BC%98%E5%8C%96%E5%99%A8&limit=20)|200；{"count":1,"total":1,"limit":20,"has_more":false,"next_offset":null}|
|11|2026-11-13 02:38:23|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|12|2026-11-13 02:38:23|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=MeZO&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=MeZO&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":1,"has_more":false,"sort":"relevance","next_offset":null}|
|13|2026-11-13 02:38:23|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Piggyback&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Piggyback&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":3,"has_more":false,"sort":"relevance","next_offset":null}|
|14|2026-11-13 02:38:24|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Diff+Pruning&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Diff+Pruning&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":6,"has_more":false,"sort":"relevance","next_offset":null}|
|15|2026-11-13 02:38:24|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|16|2026-11-13 02:38:24|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|17|2026-11-13 02:38:25|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":40}|
|18|2026-11-13 02:38:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":40}|
|19|2026-11-13 02:38:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=RandOpt&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=RandOpt&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|20|2026-11-13 02:38:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Deletion+Tuning&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=Deletion+Tuning&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":3,"has_more":false,"sort":"relevance","next_offset":null}|
|21|2026-11-13 02:38:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=40](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=40)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":60}|
|22|2026-11-13 02:38:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":40}|
|23|2026-11-13 02:38:27|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=40](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=40)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":60}|
|24|2026-11-13 02:38:27|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%8F%AF%E5%AD%A6%E4%B9%A0+%E4%BC%98%E5%8C%96%E5%99%A8&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%8F%AF%E5%AD%A6%E4%B9%A0+%E4%BC%98%E5%8C%96%E5%99%A8&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":7,"has_more":false,"sort":"relevance","next_offset":null}|
|25|2026-11-13 02:38:27|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantization+fine+tuning&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantization+fine+tuning&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|26|2026-11-13 02:38:27|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=60](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=60)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":80}|
|27|2026-11-13 02:38:27|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=40](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=40)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":60}|
|28|2026-11-13 02:38:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=60](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=60)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":80}|
|29|2026-11-13 02:38:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=80](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=80)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":100}|
|30|2026-11-13 02:38:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=60](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=60)|200；{"limit":20,"count":8,"has_more":false,"sort":"relevance","next_offset":null}|
|31|2026-11-13 02:38:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantization+fine+tuning&kind=insight&mode=all&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantization+fine+tuning&kind=insight&mode=all&limit=20&offset=20)|200；{"limit":20,"count":4,"has_more":false,"sort":"relevance","next_offset":null}|
|32|2026-11-13 02:38:29|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=80](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=80)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":100}|
|33|2026-11-13 02:38:29|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=100](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=100)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":120}|
|34|2026-11-13 02:38:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=120](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=120)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":140}|
|35|2026-11-13 02:38:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=100](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20&offset=100)|200；{"limit":20,"count":2,"has_more":false,"sort":"relevance","next_offset":null}|
|36|2026-11-13 02:38:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=140](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=140)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":160}|
|37|2026-11-13 02:38:33|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=160](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=160)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":180}|
|38|2026-11-13 02:38:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=180](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=180)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":200}|
|39|2026-11-13 02:38:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=200](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=200)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":220}|
|40|2026-11-13 02:38:37|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=220](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=220)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":240}|
|41|2026-11-13 02:38:38|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=240](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=240)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":260}|
|42|2026-11-13 02:38:40|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=260](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=260)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":280}|
|43|2026-11-13 02:38:41|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=280](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=280)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":300}|
|44|2026-11-13 02:38:42|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=300](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=300)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":320}|
|45|2026-11-13 02:38:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=320](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=320)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":340}|
|46|2026-11-13 02:38:46|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=340](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E9%9A%8F%E6%9C%BA+%E6%89%B0%E5%8A%A8&kind=insight&mode=all&limit=20&offset=340)|200；{"limit":20,"count":5,"has_more":false,"sort":"relevance","next_offset":null}|
|47|2026-11-13 02:38:47|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2611.10866](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2611.10866)|HTTP Error 404: Not Found|
|48|2026-11-13 02:38:49|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2611.10866](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2611.10866)|HTTP Error 404: Not Found|
|49|2026-11-13 02:38:50|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2603.12228](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2603.12228)|HTTP Error 404: Not Found|
|50|2026-11-13 02:38:50|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2603.12228](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2603.12228)|HTTP Error 404: Not Found|
|51|2026-11-13 02:39:59|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization)|200|
|52|2026-11-13 02:40:00|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning)|200|
|53|2026-11-13 02:40:02|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation)|200|
|54|2026-11-13 02:40:03|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/insights?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/insights?sort=paper_count&limit=50)|200；{"limit":50,"count":27,"has_more":false,"sort":"paper_count","next_offset":null}|
|55|2026-11-13 02:40:03|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/insights?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/insights?sort=paper_count&limit=50)|200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":50}|
|56|2026-11-13 02:40:03|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/insights?sort=paper_count&limit=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/insights?sort=paper_count&limit=50)|200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":50}|
|57|2026-11-13 02:40:03|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=MeZO&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=MeZO&limit=20)|200；{"count":3,"limit":20,"has_more":false,"next_after":null}|
|58|2026-11-13 02:40:03|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=Sparse&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=Sparse&limit=20)|200；{"count":3,"limit":20,"has_more":false,"next_after":null}|
|59|2026-11-13 02:40:04|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=Quant&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=Quant&limit=20)|200；{"count":8,"limit":20,"has_more":false,"next_after":null}|
|60|2026-11-13 02:40:04|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=Neural&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=Neural&limit=20)|200；{"count":5,"limit":20,"has_more":false,"next_after":null}|
|61|2026-11-13 02:40:04|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/insights?sort=paper_count&limit=50&offset=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/insights?sort=paper_count&limit=50&offset=50)|200；{"limit":50,"count":15,"has_more":false,"sort":"paper_count","next_offset":null}|
|62|2026-11-13 02:40:04|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=Evolution&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/zeroth-order-optimization/papers?q=Evolution&limit=20)|200；{"count":8,"limit":20,"has_more":false,"next_after":null}|
|63|2026-11-13 02:40:04|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/insights?sort=paper_count&limit=50&offset=50](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/insights?sort=paper_count&limit=50&offset=50)|200；{"limit":50,"count":50,"has_more":true,"sort":"paper_count","next_offset":100}|
|64|2026-11-13 02:40:05|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Piggyback&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Piggyback&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|65|2026-11-13 02:40:05|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Tuning&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Tuning&limit=20)|200；{"count":20,"limit":20,"has_more":true,"next_after":"56186"}|
|66|2026-11-13 02:40:05|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Mask&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Mask&limit=20)|200；{"count":20,"limit":20,"has_more":true,"next_after":"259363"}|
|67|2026-11-13 02:40:05|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/insights?sort=paper_count&limit=50&offset=100](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/insights?sort=paper_count&limit=50&offset=100)|200；{"limit":50,"count":3,"has_more":false,"sort":"paper_count","next_offset":null}|
|68|2026-11-13 02:40:05|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20)|200；{"count":20,"limit":20,"has_more":true,"next_after":"173206"}|
|69|2026-11-13 02:40:06|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Deletion&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Deletion&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|70|2026-11-13 02:40:06|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Mask&limit=20&after=259363](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Mask&limit=20&after=259363)|200；{"count":16,"limit":20,"has_more":false,"next_after":null}|
|71|2026-11-13 02:40:06|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Tuning&limit=20&after=56186](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Tuning&limit=20&after=56186)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|72|2026-11-13 02:40:06|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=173206](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=173206)|200；{"count":20,"limit":20,"has_more":true,"next_after":"247236"}|
|73|2026-11-13 02:40:07|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Gradient-Free&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Gradient-Free&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|74|2026-11-13 02:40:07|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Quantization&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Quantization&limit=20)|200；{"count":13,"limit":20,"has_more":false,"next_after":null}|
|75|2026-11-13 02:40:07|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=PEQA&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=PEQA&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|76|2026-11-13 02:40:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=247236](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=247236)|200；{"count":20,"limit":20,"has_more":true,"next_after":"31245"}|
|77|2026-11-13 02:40:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Piggyback&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Piggyback&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|78|2026-11-13 02:40:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Diff+Pruning&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Diff+Pruning&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|79|2026-11-13 02:40:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Mask&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Mask&limit=20)|200；{"count":9,"limit":20,"has_more":false,"next_after":null}|
|80|2026-11-13 02:40:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Random&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Random&limit=20)|200；{"count":6,"limit":20,"has_more":false,"next_after":null}|
|81|2026-11-13 02:40:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=31245](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=31245)|200；{"count":20,"limit":20,"has_more":true,"next_after":"418475"}|
|82|2026-11-13 02:40:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Operation&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/peft-structural-sparse-adaptation/papers?q=Operation&limit=20)|200；{"count":2,"limit":20,"has_more":false,"next_after":null}|
|83|2026-11-13 02:40:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=PEQA&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=PEQA&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|84|2026-11-13 02:40:09|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Fine-Tuning&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Fine-Tuning&limit=20)|200；{"count":13,"limit":20,"has_more":false,"next_after":null}|
|85|2026-11-13 02:40:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=418475](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=418475)|200；{"count":20,"limit":20,"has_more":true,"next_after":"8862"}|
|86|2026-11-13 02:40:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Fine+Tuning&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Fine+Tuning&limit=20)|200；{"count":13,"limit":20,"has_more":false,"next_after":null}|
|87|2026-11-13 02:40:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Rounding&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Rounding&limit=20)|200；{"count":8,"limit":20,"has_more":false,"next_after":null}|
|88|2026-11-13 02:40:10|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=QuZO&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=QuZO&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|89|2026-11-13 02:40:11|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Tuning&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Tuning&limit=20)|200；{"count":15,"limit":20,"has_more":false,"next_after":null}|
|90|2026-11-13 02:40:11|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=8862](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Pruning+as&limit=20&after=8862)|200；{"count":6,"limit":20,"has_more":false,"next_after":null}|
|91|2026-11-13 02:40:12|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=1801.06519](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=1801.06519)|HTTP Error 404: Not Found|
|92|2026-11-13 02:40:13|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=1801.06519](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=1801.06519)|HTTP Error 404: Not Found|
|93|2026-11-13 02:40:14|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2012.07463](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2012.07463)|200|
|94|2026-11-13 02:40:15|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2004.10568](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2004.10568)|200|
|95|2026-11-13 02:40:16|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2309.05516](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2309.05516)|200|
|96|2026-11-13 02:40:18|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2502.05995](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2502.05995)|HTTP Error 404: Not Found|
|97|2026-11-13 02:40:19|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2502.05995](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2502.05995)|HTTP Error 404: Not Found|
|98|2026-11-13 02:40:20|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.15179](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.15179)|HTTP Error 404: Not Found|
|99|2026-11-13 02:40:21|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.15179](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/by-arxiv?id=2610.15179)|HTTP Error 404: Not Found|
|100|2026-11-13 02:41:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/66903](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/66903)|200|
|101|2026-11-13 02:41:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/257840](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/257840)|200|
|102|2026-11-13 02:41:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/199864](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/199864)|200|
|103|2026-11-13 02:41:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/201332](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/201332)|200|
|104|2026-11-13 02:41:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/186859](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/186859)|200|
|105|2026-11-13 02:41:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/215620](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/215620)|200|
|106|2026-11-13 02:41:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/176792](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/176792)|200|
|107|2026-11-13 02:41:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/256802](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/256802)|200|
|108|2026-11-13 02:41:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/72818](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/72818)|200|
|109|2026-11-13 02:41:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/181779](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/181779)|200|
|110|2026-11-13 02:41:31|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/224792](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/224792)|200|
|111|2026-11-13 02:41:31|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/70207](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/70207)|200|
|112|2026-11-13 02:41:31|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/85915](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/85915)|200|
|113|2026-11-13 02:41:31|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/142661](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/142661)|200|
|114|2026-11-13 02:41:31|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/236811](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/236811)|200|
|115|2026-11-13 02:41:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/65009](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/65009)|200|
|116|2026-11-13 02:41:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/195498](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/195498)|200|
|117|2026-11-13 02:41:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/176709](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/176709)|200|
|118|2026-11-13 02:41:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/94870](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/94870)|200|
|119|2026-11-13 02:41:33|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/63386](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/63386)|200|
|120|2026-11-13 02:41:33|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/95571](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/95571)|200|
|121|2026-11-13 02:41:33|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/193742](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/193742)|200|
|122|2026-11-13 02:41:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/243615](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/243615)|200|
|123|2026-11-13 02:41:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0040](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0040)|200|
|124|2026-11-13 02:41:37|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-P0025](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-P0025)|200|
|125|2026-11-13 02:41:38|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/peft-structural-sparse-adaptation-I0188](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/peft-structural-sparse-adaptation-I0188)|200|
|126|2026-11-13 02:41:39|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0240](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0240)|200|
|127|2026-11-13 02:41:40|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/neural-quantization-P0210](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/neural-quantization-P0210)|200|
|128|2026-11-13 02:41:42|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/neural-quantization-P0151](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/neural-quantization-P0151)|200|
|129|2026-11-13 02:44:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0036](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0036)|200|
|130|2026-11-13 02:44:47|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0054](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0054)|200|
|131|2026-11-13 02:44:48|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0053](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0053)|200|
|132|2026-11-13 02:44:50|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0011](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0011)|200|
|133|2026-11-13 02:44:51|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0034](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0034)|200|
|134|2026-11-13 02:44:52|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/peft-structural-sparse-adaptation-I0031](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/peft-structural-sparse-adaptation-I0031)|200|
|135|2026-11-13 02:44:53|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/neural-quantization-I0006-s8](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/neural-quantization-I0006-s8)|200|
|136|2026-11-13 02:44:55|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/196237](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/196237)|200|
|137|2026-11-13 02:44:56|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/193966](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/193966)|200|
|138|2026-11-13 02:44:57|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/98098](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/98098)|200|
|139|2026-11-13 02:44:58|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=joint+pruning+quantization&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=joint+pruning+quantization&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":8,"has_more":false,"sort":"relevance","next_offset":null}|
|140|2026-11-13 02:44:59|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantization+pruning+finetuning&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantization+pruning+finetuning&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":3,"has_more":false,"sort":"relevance","next_offset":null}|
|141|2026-11-13 02:45:00|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E9%87%8F%E5%8C%96+%E5%BE%AE%E8%B0%83&kind=problem&mode=all&limit=20)|200；{"limit":20,"count":7,"has_more":false,"sort":"relevance","next_offset":null}|
|142|2026-11-13 02:45:02|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=compression+operator&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=compression+operator&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":12,"has_more":false,"sort":"relevance","next_offset":null}|
|143|2026-11-13 02:45:03|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=mask+rounding&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=mask+rounding&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|144|2026-11-13 02:45:04|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantization+black+box&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=quantization+black+box&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":4,"has_more":false,"sort":"relevance","next_offset":null}|
|145|2026-11-13 02:45:05|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E9%87%8F%E5%8C%96+%E7%9B%B8%E4%BA%92%E4%BD%9C%E7%94%A8&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=%E5%89%AA%E6%9E%9D+%E9%87%8F%E5%8C%96+%E7%9B%B8%E4%BA%92%E4%BD%9C%E7%94%A8&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":0,"has_more":false,"sort":"relevance","next_offset":null}|
|146|2026-11-13 02:45:06|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=operator+search&kind=insight&mode=all&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=operator+search&kind=insight&mode=all&limit=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|147|2026-11-13 02:45:08|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=operator+search&kind=insight&mode=all&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/search?q=operator+search&kind=insight&mode=all&limit=20&offset=20)|200；{"limit":20,"count":8,"has_more":false,"sort":"relevance","next_offset":null}|
|148|2026-11-13 02:46:57|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Interaction&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Interaction&limit=20)|200；{"count":2,"limit":20,"has_more":false,"next_after":null}|
|149|2026-11-13 02:48:19|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0019](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0019)|200|
|150|2026-11-13 02:48:21|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0064](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0064)|200|
|151|2026-11-13 02:48:22|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0176](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-I0176)|200|
|152|2026-11-13 02:48:24|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/peft-structural-sparse-adaptation-I0005-s2](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/peft-structural-sparse-adaptation-I0005-s2)|200|
|153|2026-11-13 02:48:26|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0014](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/zeroth-order-optimization-I0014)|200|
|154|2026-11-13 02:48:27|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E6%8E%A9%E7%A0%81&mode=any&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E6%8E%A9%E7%A0%81&mode=any&limit=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|155|2026-11-13 02:48:28|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E6%8E%A9%E7%A0%81&mode=any&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E6%8E%A9%E7%A0%81&mode=any&limit=20&offset=20)|200；{"limit":20,"count":6,"has_more":false,"sort":"relevance","next_offset":null}|
|156|2026-11-13 02:48:30|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E7%BB%84%E5%90%88&mode=any&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E7%BB%84%E5%90%88&mode=any&limit=20)|200；{"limit":20,"count":11,"has_more":false,"sort":"relevance","next_offset":null}|
|157|2026-11-13 02:48:31|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E5%BE%AE%E8%B0%83&mode=any&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E5%BE%AE%E8%B0%83&mode=any&limit=20)|200；{"limit":20,"count":20,"has_more":true,"sort":"relevance","next_offset":20}|
|158|2026-11-13 02:48:32|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E5%BE%AE%E8%B0%83&mode=any&limit=20&offset=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/problems?q=%E5%BE%AE%E8%B0%83&mode=any&limit=20&offset=20)|200；{"limit":20,"count":8,"has_more":false,"sort":"relevance","next_offset":null}|
|159|2026-11-13 02:48:33|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Quantifying&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/neural-quantization/papers?q=Quantifying&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|160|2026-11-13 02:48:34|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Quantifying&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/network-pruning/papers?q=Quantifying&limit=20)|200；{"count":1,"limit":20,"has_more":false,"next_after":null}|
|161|2026-11-13 02:48:36|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Quantifying&limit=20](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/domains/efficient-model-compression/papers?q=Quantifying&limit=20)|200；{"count":0,"limit":20,"has_more":false,"next_after":null}|
|162|2026-11-13 02:52:35|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0055](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0055)|200|
|163|2026-11-13 02:52:37|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0167](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0167)|200|
|164|2026-11-13 02:52:38|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0007](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/network-pruning-P0007)|200|
|165|2026-11-13 02:53:45|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205662](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/205662)|200|
|166|2026-11-13 02:53:46|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/426652](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/426652)|200|
|167|2026-11-13 02:53:48|[https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/90596](https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/papers/90596)|200|

## 附录B：公开来源与关键词

- 2026-11-13 02:46:39，GET [https://arxiv.org/html/2603.12228](https://arxiv.org/html/2603.12228)，HTTP 200；原文读取范围见第6节。
- 2026-11-13 02:46:39，GET [https://arxiv.org/html/2611.10866](https://arxiv.org/html/2611.10866)，HTTP 200；原文读取范围见第6节。
- 2026-11-13 02:46:39，GET [https://arxiv.org/html/2506.12876](https://arxiv.org/html/2506.12876)，HTTP 200；原文读取范围见第6节。
- 2026-11-13 02:46:39，GET [https://arxiv.org/html/2505.13430](https://arxiv.org/html/2505.13430)，HTTP 200；原文读取范围见第6节。
- 2026-11-13 02:46:40，GET [https://arxiv.org/html/2405.14852](https://arxiv.org/html/2405.14852)，HTTP 200；原文读取范围见第6节。
- 2026-11-13 02:46:40，GET [https://arxiv.org/html/2305.14152](https://arxiv.org/html/2305.14152)，HTTP 200；原文读取范围见第6节。
- 2026-11-13 02:46:40，GET [https://arxiv.org/html/2004.12406](https://arxiv.org/html/2004.12406)，HTTP 200；原文读取范围见第6节。
- 2026-11-13 02:46:41，GET [https://ijcai.org/proceedings/2026/631](https://ijcai.org/proceedings/2026/631)，HTTP 200；原文读取范围见第6节。

公开搜索实际使用的关键词包括：`random perturbations optimizer 2026`、`fine-tuning trainable operations optimizer`、`The Surprising Effectiveness of Deleting Weights in LLM Post-Training`、`Neural Thickets`、`Piggyback`、`Parameter-Efficient Transfer Learning with Diff Pruning`、`PEQA arxiv`、`QuZO`、`quantization fine-tuning rounding decisions`、`pruning zeroth-order mask fine-tuning`、`joint pruning and quantization zeroth-order`、`quantization pruning interaction fine-tuning`。搜索结果只作导航，事实结论来自实际访问的原文或已核验的API卡片。

本次正文中的“阶段”反映证据如何修改提案，不是作者原始创作历史，也不是系统内部思维逐字记录。请求账本记录可外部复查的行动；最终提案单独成文，可用于论文案例或研究计划，但不能将预期效果改写成已完成结果。
