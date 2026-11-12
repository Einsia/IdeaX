你是一位独立研究者，在一个持续的会话内提出五个研究想法，不使用其他 agent。本轮是历史截断重建：目标是依据截止日之前的文献，判断接下来几个月最可能出现、并会发展成持续研究方向的论文；每条是一篇论文的核心贡献（新机制、新方法或新问题设定），不是增量改进、综述或新增 benchmark。方法、机制、问题设定和解释性研究一视同仁，按出现的可能性取舍，不预设类型偏好。你不需要证明尚未做过的大规模实验一定成功；需要把“待验证的科学假设”与“尚未定义的方法”分开。重要且可检验的冒险值得保留，缺少核心步骤不能靠未来实验补齐。

你会依次完成五轮：理解材料、提出候选、写研究卡、核查、修订交付。每轮完成后结束，等待下一轮。研究笔记保持简洁，把时间用于机制、论文和反例。最终五条按出现可能性从高到低排序（第 1 条最可能），彼此要有实质区别，尽量来自领域里不同的方向；候选类型不设配额。

domain 定义研究范围；insight 是前作的机制、事实或观察及其适用条件；problem 是文献中记录的限制，未必今天仍未解决。它们不是新颖性标签，也不是待拼装的功能清单。supporting_papers 仅是来源导航，一个归并条目的不同主张未必得到每篇来源共同支持。引用编号不等于读过全文。

目标领域全部 insights/problems 原样注入本轮输入，同时保存在只读 /work/full_domain_context.jsonl。先综合所有材料再选择有希望的方向，不能用 top-k 代替全量。insight 是“已观察到的机制/事实/边界”，problem 是“文献记录的限制或未决问题”；先写出它们之间的模式、冲突和条件，再决定候选。每条最终卡至少要能指出一个具体条目如何改变了问题、机制或实验设计。最有用的用法是：从材料中的问题、机制和近期发展，判断这个领域接下来最可能出现的工作。构造想法时按 IdeaX 的基本做法：选一个目标 problem，借用一个 insight（可以来自其他领域），写清原有机制和适配步骤。每个候选必须先写“为什么这篇论文会在接下来几个月出现”，再写方法；不要为了体现用了库而给每个想法添加更多模块。

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

写简洁 DOMAIN_SYNTHESIS.md 和 SOURCE_TENSIONS.json（这里记录领域动向，每个主要机制簇至少一条）：{"tensions":[{"id":"t1","entry_ids":[],"observed_facts":"材料确实支持的事实","scope":"对象与条件","tension":"这个方向正在推进、但尚未解决的限制或明显的下一步","why_it_matters":"解决后带来什么新能力或改变什么做法","uncertainty":"哪些尚未核实"}]}。

特别寻找：领域里正在推进的方向和它们尚未解决的限制；相邻领域已经成熟、可以迁移过来的方法；哪些问题其实已被截止前的后作解决。事实、推论、假设分开。不要把“还没有论文同时考虑 A+B+C”本身当作研究问题。完成三份产物后结束。

<!-- STAGE 2 -->
基于完整材料构造约 20 个候选，覆盖 DOMAIN_MAP 里每个主要机制簇（每簇至少一个），写 CANDIDATE_FUNNEL.json：{"candidates":[{"id":"h01","rank":1,"title":"...","problem":"...","mechanism":"...","source_entry_ids":{"problems":[],"insights":[]},"novel_core":"...","why_paper":"...","hardest_baseline":"...","reason":"...","decision":"revise|drop","final_index":null}]}。这是对象包装格式。

先广后精：先写出这个领域接下来最可能出现的工作，包括直接、自然的下一步，再排序。每个候选按 IdeaX 的基本做法构造：选一个目标 problem，借用一个 insight（可以来自其他领域），写清原有机制和适配步骤。title 写一句论文标题；mechanism 写清实际要做什么；novel_core 写相对截止前工作的新步骤；why_paper 写为什么这篇论文会在接下来几个月出现；hardest_baseline 用一句话写最直接的已有做法；rank 是出现可能性的名次（1 最可能，不重复）。

新颖性预筛只淘汰一种情况：用 LitGraph 检索核实，截止前已经有论文完成了相同的核心贡献，这时 decision 为 drop，reason 写明论文编号。只是有相近工作时不要淘汰：decision 写 revise，并在 novel_core 写清差别。不要因为想法简洁、直接或与已有工作相近就拒绝它。

不要过早固定最终五个候选。保存候选后结束。
<!-- STAGE 3 -->
按 rank 从前往后取五个未淘汰的候选（查到截止前已有相同核心贡献的跳过，换下一个），写成五张研究卡 DRAFT_IDEAS.json。**顶层必须直接是 JSON 数组 `[...]`，恰好五个对象；不要使用 `{"drafts":[...]}`、`{"ideas":[...]}` 或任何其他包装键。**每项有 candidate_id、title、scientific_question、why_paper、problem、mechanism、previous_work、novelty_check、experiment、failure_conditions、scientific_potential、contribution_delta、decisive_test、source_entry_ids、entry_usage、litgraph_queries。此时还不是最终交付；下一轮将只针对这五条完整文本进行反驳。

mechanism 写清输入、输出和关键步骤，让同行看得出实际要做什么；不必展开到公式和实现细节。各字段简洁即可。

查前作时按实际操作而非你发明的名字检索，比较函数、变量、训练信号、假设和开销。最接近的工作必须进入 previous_work；不能只在风险段提到它，却拿较远工作作比较。至少三篇真实相关来源，其中至少一篇是最接近的核心操作；库内给数字 paper_id、API 路径及 IDEA.md 用的《编号》，url 字段填 API 路径；本轮没有网络，库外工作只能写标题与已知出处并注明未读。每篇都有 title、url、read_depth、source_location、overlap、difference。只读摘要无法确定的差别不能写成事实。novelty_check 必须明确写出“最接近工作已经完成的核心操作”和“仍然没有完成的具体操作/预测”；如果截止前已有论文完成了相同的核心贡献，就换成下一个候选。

novelty_check 含 search_queries、closest_work、already_done_test（前人是否已完成核心操作的调查结论，不是自己的 toy 结果）、remaining_contribution、unresolved_risks。

source_entry_ids={"problems":[],"insights":[]}，两类各至少一条真实来源且不能重复；每个 ID 在 entry_usage 中恰有一项 {"id":"真实ID","kind":"problem|insight","role":"mechanism|target_problem|mechanism_boundary|boundary|counter_evidence|alternative|experiment_design|novelty_audit","use":"来源具体支持什么，以及改变哪一步；如果只是后续佐证请直说"}。litgraph_queries 记录实际 endpoint、purpose、result_ids、read_depth。endpoint 必须是 /api/v1/ 开头的真实请求路径及查询参数，例如 /api/v1/papers/123；从 api_requests.jsonl 的 URL 获取路径，不能填 python 命令、网页 URL 或一串合并命令。previous_work 中 api_path 同样写 /api/v1/papers/数字ID。检索过程另记 SEARCH_LOG.md。

contribution_delta 写清既有方法、具体变化、尚待检验的新能力或预测。decisive_test 给相同条件下最强简单替代以及能否证自己的结果。experiment 包含数据/任务、强基线、资源、指标、消融和失败条件。不要把添加成本统计本身写成新科学贡献；测量研究需要明确未解现象或改变既有认识的竞争解释。

保留候选取舍的真实记录，不修改过去阶段的快照。可以更换弱候选，检查新候选的前作。完成五条完整草稿后结束。

<!-- STAGE 4 -->
现在核查五张研究卡，不润色标题。重新读取 DRAFT_IDEAS.json。写 DRAFT_REVIEW.json：{"reviews":[{"candidate_id":"h01","draft_sha256":"该草稿对象按 json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode() 的 SHA256","information_trace":[],"strong_alternative":"...","counterexample":"...","mechanism_test":"...","nearest_work_overlap":"...","verdict":"retain|revise|reject","required_change":"...","test_artifacts":[]}]}。

只核查两件事。一是截止前是否已有论文完成了相同的核心贡献：用 LitGraph 查最接近的工作，nearest_work_overlap 写它的编号、重合和差别。二是截止时是否可行：information_trace 逐项写关键数据、信号或模型在截止时是否可得，mechanism_test 用一两句话判断主要步骤能否实现。strong_alternative 写最直接的已有做法；counterexample 写最可能让它不成立的情况。

verdict：截止前已被完成写 reject；有可以修的问题写 revise，并在 required_change 写怎么改；否则写 retain，required_change 写“无”。不需要写脚本，test_artifacts 只列已存在文件的相对路径，没有就写空数组。完成五条精确对应草稿的核查后结束。

<!-- STAGE 5 -->
依据核查修订并交付五条最终研究想法，按接下来几个月出现的可能性从高到低排序。被 reject 的换成漏斗里下一个未淘汰的候选，并完成同样的两项核查；revise 的按 required_change 修改。保留真实失败记录；不足五条时明确报告，不能编造成功。

写 IDEAS.json：**顶层必须直接是 JSON 数组 `[...]`，恰好五个对象；不要使用任何包装键。**字段沿用 DRAFT_IDEAS.json，candidate_id 保留。每条必须直接写出 `scientific_question` 和 `why_paper`，分别说明这篇论文要解决的研究问题，以及为什么它会在接下来几个月出现。数组顺序就是出现可能性的排序，第 1 条最可能。mechanism 在本条卡中完整自足，不能依赖评审看中间笔记。生成未执行的实验只写计划，不报虚构数值。确保“精确、证明、无偏、因果、必要、充分”这些词与实际支持一致。最接近工作仍列入 previous_work，库内编号可直接通过 API 取得。

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
