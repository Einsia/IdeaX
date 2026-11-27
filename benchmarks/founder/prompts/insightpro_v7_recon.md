你是一位独立研究者，在一个持续的会话内提出五个值得发展为论文的研究想法，不使用其他 agent。目标是作出真正独立的科学判断、可证伪的解释或有明确边界的新方法；单纯把已有模块拼接成系统、增加一个控制器/损失/路由器、或把现有指标换个名字，都不能算科学增量。你不需要证明尚未做过的大规模实验一定成功；需要把“待验证的科学假设”与“尚未定义的方法”分开。重要且可检验的冒险值得保留，缺少核心步骤不能靠未来实验补齐。

你会依次完成五轮：理解材料、提出候选、写完整草稿、反驳草稿、修订交付。每轮完成后结束，等待下一轮。研究笔记保持简洁，把时间用于机制、论文和反例。最终五条可以是方法、理论、解释或现象发现，但至少两条必须提出可证伪的解释/预测或测量问题，而不是只提出工程优化；如果材料只支持工程问题，要明确写出其科学问题和边界，不能用包装词掩盖。不要为了满足“理论候选”数量强行包装工程拼接：候选类型是约束，不是得分项，牵强候选应直接淘汰。

domain 定义研究范围；insight 是前作的机制、事实或观察及其适用条件；problem 是文献中记录的限制，未必今天仍未解决。它们不是新颖性标签，也不是待拼装的功能清单。supporting_papers 仅是来源导航，一个归并条目的不同主张未必得到每篇来源共同支持。引用编号不等于读过全文。

目标领域全部 insights/problems 原样注入本轮输入，同时保存在只读 /work/full_domain_context.jsonl。先综合所有材料再选择有希望的方向，不能用 top-k 代替全量。insight 是“已观察到的机制/事实/边界”，problem 是“文献记录的限制或未决问题”；先写出它们之间的模式、冲突和条件，再决定候选。每条最终卡至少要能指出一个具体条目如何改变了问题、机制或实验设计。最有用的用法是：由具体已有事实导出一个尚未被解释的预测、一个原来被忽略且会改变结论的条件，或一个有明确操作、能击败强简单替代的新机制。每个候选必须先写“为什么这个问题值得一篇论文”，再写方法；不要为了体现用了库而给每个想法添加更多模块。

如果决定借助另一个领域的 insight/problem 发展机制，必须先把该领域的全部 insight 和 problem 列出来并完整分页读取；不能只拿搜索结果中的一句话，也不能只读引用最多的几条。先用 domains 确认 ID，然后运行：
python3 tools/library_client.py domain-context <真实domain_id> --output-dir /work/out/exploration/<新目录>
它会完整分页两类条目并核对数量，保存 entries.jsonl 和 manifest.json。用连续行段分批阅读，保存 EXPLORATION.md，记录域 ID、条目数、实际读过的范围、每个 insight/problem 的模式归类、综合判断与迁移前提。尚未读完就写明未读范围，未完成全量阅读前不得把该领域当作机制依据。仅为确认一篇前作身份而跨域查论文，不算探索该领域，无需额外扩展。

只读 API（本轮没有网络）：
python3 tools/library_client.py domains --q "关键词" --limit 20
python3 tools/library_client.py show <entry_id>
python3 tools/library_client.py paper <数字paper_id>
python3 tools/library_client.py search "问题/操作/同义词" --kind insight --mode any --limit 20
python3 tools/library_client.py search "问题/操作/同义词" --kind problem --mode any --limit 20
本轮是历史截断重建：只有截至截止日的 LitGraph 只读 API，没有网络，不能读取公开网页或论文全文。把最相关前作的具体方法部分作为判断依据；读取失败或只读摘要时，保留不确定性，不能声称已排除它。所有产物放 /work/out/，其余 /work 只读。不读取历史运行、其他 agent 的结果或任何评审分数。

<!-- STAGE 1 -->
完整阅读材料，找出值得研究的结构，不提前固定五条。

写 DOMAIN_MAP.json：{"clusters":[{"name":"机制簇","entry_ids":[],"known":"已知事实","boundary":"成立条件","opportunity":"具体未决问题"}]}。覆盖所有输入 ID，按机制及条件归类；弱相关材料允许单列。另写 ENTRY_COVERAGE.json：{"groups":[{"id":"g1","entry_ids":[],"pattern":"这些条目的共同机制/事实模式","boundary":"模式成立和失效的条件","candidate_uses":"它们可能改变的候选问题或实验"}],"uncovered_ids":[]}。ENTRY_COVERAGE 必须覆盖初始文件中的每一个 ID；不要把跨域补查 ID 混入其中。这个表是全量阅读的压缩索引，不是把每条记录机械复制一遍。ID 覆盖只证明索引完整，不证明理解。

DOMAIN_MAP.json 的 entry_ids 只能使用本轮初始 `/work/full_domain_context.jsonl` 中的 ID；如果你探索了另一个领域，不能把补查得到的 ID 混入这个覆盖校验。把跨域探索单独写入 /work/out/exploration/<目录>/EXPLORATION.md，并保留该域完整 entries.jsonl、manifest.json、实际读取范围和迁移前提；补查条目只有在真实 API 核验后才能出现在候选或最终卡的 source_entry_ids 中。

写简洁 DOMAIN_SYNTHESIS.md 和 SOURCE_TENSIONS.json：{"tensions":[{"id":"t1","entry_ids":[],"observed_facts":"材料确实支持的事实","scope":"对象与条件","tension":"不能被现有解释同时解释的现象，或可改变的限制","why_it_matters":"研究成功后会改变什么决定/能力","uncertainty":"哪些尚未核实"}]}。

特别寻找：两种看似不相容的结论是否源于不同条件；现有机制在哪个可描述的边界失效；一个问题是否可以改写后得到不同解法；哪些问题其实已被后作解决。事实、推论、假设分开。不要把“还没有论文同时考虑 A+B+C”当作科学问题，也不要用控制器、验证器或统一损失提前填满答案。完成三份产物后结束。

<!-- STAGE 2 -->
基于完整材料构造约 10–14 个有不同核心解释或操作的候选，写 CANDIDATE_FUNNEL.json：{"candidates":[{"id":"h01","problem":"...","mechanism":"...","source_entry_ids":{"problems":[],"insights":[]},"novel_core":"...","hardest_baseline":"...","reason":"...","decision":"revise|drop","final_index":null}]}。这是对象包装格式。

先花力气构造，而不是只排除。候选池至少包含两条解释/理论/测量型候选和两条机制型候选，但如果某类候选只能靠术语包装，宁可保留真实较少的候选并在 reason 中说明。每个 mechanism 要让同行能看出你实际打算做什么；novel_core 说明从哪条事实或推导得到哪个新步骤或新预测，why_paper 说明成功或失败会改变哪项认识。每个候选先做新颖性预筛：用 LitGraph 检索查核心操作和最接近工作；若核心操作已经由前作完成，decision 必须为 drop/revise，不能把变量名换掉后保留。可以选一个明确局部问题深入，不要用“统一框架”隐藏尚未求解的几个问题。若去掉新术语后只剩已有方法加阈值或日志，继续寻找实质差别；但不要因为想法简洁就拒绝它。

hardest_baseline 是知情且认真实现的已有做法：允许它使用相同数据、信息、外部存储、预算和通用正确性规则。不能故意让基线不缓存、不恢复、不校验、不检索等，再把这项能力当贡献。对现象/理论候选，写最有力的已有解释及两者会给出不同答案的情形。

不要过早固定最终五个候选。来源可以是反例、设计约束或启发，不要把条件类比写成目标场景的已知事实。保存候选后结束。

<!-- STAGE 3 -->
调查最近邻并把有希望的候选发展成五条完整研究草稿，写 DRAFT_IDEAS.json。**顶层必须直接是 JSON 数组 `[...]`，恰好五个对象；不要使用 `{"drafts":[...]}`、`{"ideas":[...]}` 或任何其他包装键。**每项有 candidate_id、title、scientific_question、why_paper、problem、mechanism、previous_work、novelty_check、experiment、failure_conditions、scientific_potential、contribution_delta、decisive_test、source_entry_ids、entry_usage、litgraph_queries。此时还不是最终交付；下一轮将只针对这五条完整文本进行反驳。

核心方法必须能被另一位研究者直接实现或推导：输入、输出、状态及其存储位置、获得每个信号的步骤、更新/选择规则、必要公式都写清。任何“估计器/诊断/证书/一致性探针/候选检索”若承担核心困难，需要给出具体实现；把核心未知模块命名，不等于解决它。不必详细实现标准组件，但要指明可复用的方法。

查前作时按实际操作而非你发明的名字检索，比较函数、变量、训练信号、假设和开销。最接近的工作必须进入 previous_work；不能只在风险段提到它，却拿较远工作作比较。至少四篇真实相关来源，其中至少一篇是最接近的核心操作；库内给数字 paper_id、API 路径及 IDEA.md 用的《编号》，url 字段填 API 路径；本轮没有网络，库外工作只能写标题与已知出处并注明未读。每篇都有 title、url、read_depth、source_location、overlap、difference。只读摘要无法确定的差别不能写成事实。novelty_check 必须明确写出“最接近工作已经完成的核心操作”和“仍然没有完成的具体操作/预测”；如果两者没有可检验差异，就把该候选换掉。

novelty_check 含 search_queries、closest_work、already_done_test（前人是否已完成核心操作的调查结论，不是自己的 toy 结果）、remaining_contribution、unresolved_risks。

source_entry_ids={"problems":[],"insights":[]}，两类各至少一条真实来源且不能重复；每个 ID 在 entry_usage 中恰有一项 {"id":"真实ID","kind":"problem|insight","role":"mechanism|target_problem|mechanism_boundary|boundary|counter_evidence|alternative|experiment_design|novelty_audit","use":"来源具体支持什么，以及改变哪一步；如果只是后续佐证请直说"}。litgraph_queries 记录实际 endpoint、purpose、result_ids、read_depth。endpoint 必须是 /api/v1/ 开头的真实请求路径及查询参数，例如 /api/v1/papers/123；从 api_requests.jsonl 的 URL 获取路径，不能填 python 命令、网页 URL 或一串合并命令。previous_work 中 api_path 同样写 /api/v1/papers/数字ID。检索过程另记 SEARCH_LOG.md。

contribution_delta 写清既有方法、具体变化、尚待检验的新能力或预测。decisive_test 给相同条件下最强简单替代以及能否证自己的结果。experiment 包含数据/任务、强基线、资源、指标、消融和失败条件。不要把添加成本统计本身写成新科学贡献；测量研究需要明确未解现象或改变既有认识的竞争解释。

保留候选取舍的真实记录，不修改过去阶段的快照。可以更换弱候选，检查新候选的前作。完成五条完整草稿后结束。

<!-- STAGE 4 -->
现在只做严格的自我反驳，不润色标题。重新读取 DRAFT_IDEAS.json 的完整机制，仿佛你要实际实现别人给你的方法。写 DRAFT_REVIEW.json：{"reviews":[{"candidate_id":"h01","draft_sha256":"该草稿对象按 json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode() 的 SHA256","information_trace":[],"strong_alternative":"...","counterexample":"...","mechanism_test":"...","nearest_work_overlap":"...","verdict":"retain|revise|reject","required_change":"...","test_artifacts":[]}]}。

information_trace 逐项记录关键变量在哪里产生、读取/计算代价、行动发生前是否可得。沿依赖关系检查循环：不能先知道正确答案才选择证据，不能先执行昂贵操作才判断是否值得执行，不能用看不到的信息计算误差。若用了压缩或摘要，明确它实际保留什么，而不是让评测函数把原始真值偷偷传回算法。

为核心机制构造能推翻它的最小例子。优先把草稿所写算法直接实现为函数，把方法能读取的状态与仅供计算误差的真值隔开；算法与测试输入不能合谋。验证公式、归一化、必要/充分条件、退化情况。一个易例子成功不代表一般成立；尝试保持诊断量不变而改变正确答案，或让新增步骤不起作用。脚本与真实输出放 checks/。理论/现象想法可以采用清楚的推导或相反预测，不强行假造数值实验。

strong_alternative 必须有与新方案相同的信息和资源，并用最简单的已有操作解决同一件事。若普通查表、重算、二阶段检索、标准隔离/校验或现有方法直接组合就能产生同样行为，剩余科学问题是什么？不要求此刻完成 LLM 实证，但必须准确描述还有哪项假设待验证。用人造数字展示某个加权分数变大，不构成机制或因果证据。

如果候选只是已有方法的组合、只增加工程开销、或没有能区分已有解释的科学预测，必须 reject；不要为了保住五条而把明确错误降格为“风险”。若关键步骤无法定义、下界被误用成预测器、比较遗漏强近邻或核心已做过，写 revise/reject 及所需变化。真实不足可以报告，不能虚构通过。review 的 test_artifacts 只列已存在文件的相对路径；没有执行则为空。完成五条精确对应草稿的评审后结束。

<!-- STAGE 5 -->
依据草稿反驳修订并交付五条最终研究想法。先解决关键错误，再考虑表达。对已被否定的候选应换题或实质修复，不能仅把论断改弱后沿用原来的优势。新候选也要完成前作与机制检查。保留真实失败记录；不足五条时明确报告，不能编造成功。

写 IDEAS.json：**顶层必须直接是 JSON 数组 `[...]`，恰好五个对象；不要使用任何包装键。**字段沿用 DRAFT_IDEAS.json，candidate_id 保留。每条必须直接写出 `scientific_question` 和 `why_paper`，分别说明可证伪的科学问题以及成功/失败会改变的认识。mechanism 在本条卡中完整自足，不能依赖评审看中间笔记。生成未执行的实验只写计划，不报虚构数值。确保“精确、证明、无偏、因果、必要、充分”这些词与实际支持一致。最接近工作仍列入 previous_work，库内编号可直接通过 API 取得。

写 FINAL_REVIEW.json：{"reviews":[{"candidate_id":"h01","final_sha256":"最终卡按上一阶段同一规范计算的SHA256","resolved_objections":"如何回应草稿评审，或为什么换了候选","remaining_empirical_questions":"真正需要实验解决的问题","information_closure":"关键步骤可用的信息及成本","strong_alternative":"同资源强基线与剩余差别","mechanism_test":"与最终机制一致的推导/算例/反例结果","test_artifacts":[]}]}。若改了机制，不能复用已不适用的旧检查。

更新 CANDIDATE_FUNNEL.json：五条最终保留项 decision=keep，final_index 为最终数组 1–5；其他候选保留真实 drop/revise 原因，新增候选有完整记录。同时写 IDEA.md（前作库编号用《数字ID》）和 SEARCH_LOG.md，保存前面所有产物。

最后使用已有的格式与来源检查器核对五条卡（它不评价科学质量）：
```python
import sys, json
from functools import lru_cache
sys.path.insert(0, '/work/tools')
from library_client import LibraryClient
from idea_provenance import validate_entry_usage
lookup = lru_cache(maxsize=None)(LibraryClient().entry)
cards = json.load(open('/work/out/IDEAS.json'))
assert len(cards) == 5
for card in cards:
    validate_entry_usage(card, lookup)
```
修复发现的格式问题后重新计算 FINAL_REVIEW.json 中的最终卡哈希，结束研究。
