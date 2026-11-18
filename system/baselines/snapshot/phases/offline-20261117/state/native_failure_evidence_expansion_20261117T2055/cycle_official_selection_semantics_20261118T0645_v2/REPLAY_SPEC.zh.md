# CycleResearcher 上游解析与选择确定性恢复规范

159个原`native_failure`的原生性结论撤回。上游允许未解析的候选评分返回内部0.0并继续选择；我方v4 adapter.py 266–268另加“全部10份review均有可评分且compatible”条件并抛出NativeFailure，阻断了上游max。既有独审重演了该我方guard，只能证明原始响应、请求、缓存及我方运行轨迹一致，不能据此认定benchmark原生失败0。原proof、raw、失败记录、费用均保留，分类由协调方以显式supersession记录撤回，不回写旧证据。

本规范统一覆盖159个被该guard阻断的槽及30个原成功槽。另一基础设施未完成槽不混入189个完整缓存槽，不补齐为零。B负责全189槽实际重放；A负责本独立源规范和4个真实样本，避免重复执行。

## 固定来源与调用边界

上游commit为`8c1b253092f3f41b3efc414fb189004855bb49f8`。`ai_researcher/deep_reviewer.py`中`DeepReviewer._parse_review`、`ai_researcher/cycle_researcher.py`、`ai_researcher/utils.py`和`Tutorial/tutorial_3.ipynb`均逐字匹配该commit的tracked文件。未跟踪的历史`__pycache__`保留，不将其误报成源码改动。

对每槽保持原10候选、原10份Standard Mode评审、reviewer_num=4、生成19000/评审35000上限、Astra/xhigh、原topic、固定5篇references、候选顺序、原完整响应与成功物理attempt不变。Standard4是当前明确披露的组合配置，不改成教程演示中的3位评审；不声称恢复了未公开的IS实验配置。

从原完整provider响应重放原`CycleResearcher.generate_paper`和`DeepReviewer.evaluate`。每个cached调用须核对原请求完整字段、逻辑request_id、成功receipt、完整`finish_reason=stop`响应、raw文本及用量；任何缺失、未完成、载荷不符或适配异常仍未知，不能生成零分。保留旧失败物理attempt及其未知用量，不以成功响应覆盖失败账本。不调用模型，不访问公共研究网络。

reviewer输入必须仍为当时实际收到的原carrier字节。原paper carrier必要输入包装和对应source spans保留并核对；不得为了采用不同论文解析结果而改写reviewer user消息。此修复只撤除评审输出兼容映射在候选选择中的作用及额外全池guard。

## 单一规范选择规则

1. 将每份原reviewer完整raw text送入冻结上游`DeepReviewer._parse_review`，不先翻译、补标签、改格式、抽数字或使用`effective_reviews.json`。输出应等于原保存的`native_reviews.json`；不符即待适配复核。
2. 使用tutorial_3 cell13的原`extract_average_rating`函数AST：先尝试可转换float的meta_review.rating；否则对个别可转换float的review.rating取原np.mean；没有可解析评分时返回0.0。严格保留上游的异常捕获、数值转换和优先级，不新增“四份均须成功”“须有confidence”“须在某范围”等限制。
3. 在原`enumerate(zip(papers, reviews))`顺序中保留全部10候选。执行cell13原`best_paper = max(paper_ratings, key=lambda x: x['avg_rating'])`赋值AST。同分取原顺序第一项；全部0.0时取original_index=0。不得删除缺分候选、改排序、让兼容parser重新破同分、比较后选更高分的变体或重生成。
4. 从被选中候选当时已发给评审的原carrier导出提案，字节与该carrier完全一致。内部0.0只是候选排序fallback，不是外部C/I/S或Novelty零分，也不是benchmark失败值。

这里复用原评分函数及max选择语义，不执行整份notebook展示代码。cell13还读取展示用`paper['title']`并打印；部分现存原论文对象缺少该键，整段执行会在展示处KeyError。已披露的运行adapter本就不以标题作为选择输入。本修复不猜标题，也不把展示KeyError新增为槽失败。

兼容映射可并列记录作诊断，但不参与规范parser、排序、导出或是否恢复成功的判定。不能在官方与兼容结果之间按得分或质量择优。

## 协议字段必须显式派生

原冻结`configuration.json`包含`missing_score_policy=retain_tutorial_zero_diagnostic_but_block_selection`，并非上游原生规则。原文件与SHA不得重写，也不能宣称修复后选择规则与旧配置完全相同。建议统一派生字段如下：

```json
{
  "selection_semantics_revision": "cycleresearcher-upstream-parser-tutorial-fallback-v5-20261118",
  "review_parser": "frozen_upstream_DeepReviewer._parse_review",
  "selection": "original_tutorial_3_cell13_rating_AST_then_first_max",
  "missing_score_policy": "upstream_internal_zero_then_first_max",
  "review_output_compatibility_used_for_selection": false,
  "original_configuration_sha256": "<原configuration文件SHA256>",
  "original_deployment_manifest_sha256": "<原或原恢复运行的部署清单SHA256>",
  "old_result_sha256": "<保留的原canonical结果SHA256>",
  "same_original_requests_and_responses": true,
  "new_model_calls": 0
}
```

语料版本、corpus身份、原配置n10/Standard4和原提示保持。将旧review-format版本作为历史来源字段保留；新选择语义单独披露，不以旧`format_compatibility_revision`掩盖差异。新配置/manifest、候选result、完整replay证明与输入hash链写入独立路径；canonical、registry、scoring release仅由协调方在锁下发布。

## 30个原成功槽及评分归属

30个原成功槽也执行上述同一版本，逐槽记录原/新selected_original_index、完整proposal SHA、原10分与新10分、fallback数量。少量源级样本已确认agent-memory01原index5→上游index0，提案不同；adaptive01原index0→0且提案字节相同。因此不能只恢复159个失败而保留30个成功的旧兼容选择。

提案改变时旧C/I/S保留为旧提案历史，不能转贴到新提案；任何包含改变提案的自有五样本Novelty panel也须按新五份输入重新确定资格。新评分当前仍待协调方的正常独立评分流程与调用解冻，源规范不触发任何评审请求。

提案字节未变也不能仅凭相同槽号复用评分。若后续决定复用，必须证明完整judge输入、rubric、材料和panel字节一致并建立新的来源绑定；不得直接覆盖旧result或旧score。所有旧生成、评审与失败成本保留，确定性重放额外模型成本为0。

## 独立验收要求

规范来源和4个真实对照见`source_semantics_acceptance.json`：14项源级检查通过，40份原review raw与保存native parser输出精确一致，原评分AST/max赋值AST和first-max参考结果一致。两个失败样本、一个改变选中候选的成功样本和一个保持提案字节的成功样本全部按同一规则处理。

此证明不代替B的全189槽20响应全链重放、物理gateway/账本连续性和候选发布证明，也不宣布canonical已修复。待全覆盖证据形成后协调方统一发布、更新完成/零分投影，并保留本次错误归因的历史说明。
