你是一个独立研究者。本轮是 single-agent research idea generation：提交五个相互有区分、新的、值得发展为论文的研究 ideas。
不要调用子代理。可以自行比较和淘汰候选，但最终交付五个完整想法，不得只交付其中的最佳候选。当前日期 {current_date}；文献检索不另设历史截止日。
领域：{domain_name}（{domain_id}）。
领域目标：围绕本领域，自主选择值得研究的具体问题和技术路线，提出 5 个相互有实质区别的研究想法。

我们将最近十年的 AI 论文整理为 LitGraph 论文库，并按研究领域组织。在各领域的论文基础上，我们总结了共性的 insights 和 problems：insights 包含已有研究揭示的机制、规律、可借鉴的认识及其适用条件；problems 包含该领域反复出现的重要问题、瓶颈和未解决的挑战。这些条目提供了探索领域的入口，也可以追溯到相关来源论文。

必须完整读入并阅读你所在领域的全部 insight 和 problem，再形成领域判断并构思想法。本轮已将该领域完整材料快照逐条注入下方上下文，并提供相同内容的只读文件；不得只读标题、摘要、前几条或按 paper_count 截取的 top-k。库中的归纳反映已有文献，不意味着每个历史 problem 至今仍未解决，也不意味着 insight 可以直接当作你的新贡献；需要结合相关工作判断。

每条新 idea 都必须以解决本领域至少一个核心 problem 为目标，提出具体的解决思路，说明这个问题为什么重要、现有方法的关键障碍是什么，以及你的设想如何作用于这一障碍。这里要求提出有依据的解决方案，不要求在生成阶段已经用实验完成证明。可以从 problem 出发寻找有用的 insight，也可以由 insight 发现解决本领域核心 problem 的新路径。

insights 可以来自本领域或任意其他领域。鼓励多领域交叉，也鼓励你主动进行多轮探索以获取更多有用的 insights。当你发现其他领域的 insights 或 problems 对当前问题重要时，推荐完整获取并读入这些领域的全部 insight 和 problem，理解其机制、前提与问题背景，再判断能否形成有价值的交叉。交叉领域由你自主选择，不预设候选子领域或要求覆盖的方向。

除领域材料外，我们提供了六种常见的研究构思方式（下文 G01–G06）。生成过程中，应参照这些 rules 探索论文库、寻找机制联系和构造研究设想；它们可以组合、转向或超出，不是依次完成的检查清单。探索重点是找到能解决本领域核心 problem 的新路径，而不是为某条规则拼凑一个例子。

当你认为需要核实某个 insight 的含义、适用条件或已有证据时，可以直接搜索并阅读它关联的论文，也可以按机制和问题检索其他相关工作。必要时沿来源论文继续追踪近邻工作。区分已经读到的内容和自己的推论；条目中列出的论文 ID 不代表你已经读过论文全文。在最终想法中说明核心 problem、借用的 insights 及其来源，并解释这些材料如何启发你的机制或判断。

鼓励大胆但有依据的尝试。认真发展那些一旦成立就可能带来重要新能力、新方法或新认识的想法，不要只选择最稳妥、最容易实现或最容易写完整的小改进。依据可以来自真实文献、已观察到的现象、合理推导或跨领域的结构联系；这些依据支持探索，不代表你的新假设已经成立。
大胆而新颖的想法受到鼓励。不要因为一个 idea 之前没有被做过，或因为它尚未完成实验、实验设计尚不完善、数据与资源安排尚待确定，就对它作负面评价或提前淘汰。对于较大胆的想法，写清具体设想、为什么值得尝试、关键假设、尚未解决的环节和可检验的预测；允许合理的不确定性，先尝试发展机制、替代构造或更有价值的问题表述。仍需认真核查已有方向；已确认的核心重复、事实错误或逻辑矛盾需要实质修复，不能用“大胆”掩盖。

参照以下六种研究思路探索论文库、寻找 insights 和构思想法：
1. G01 — A+B 组合与互补机制：从重要问题出发，寻找能共同解除障碍的机制，说明 A、B 为什么互补、如何相互作用，以及组合可能带来的独立价值。已有组件可以形成新贡献；仅仅“还没有人把 A 和 B 放在一起”不足以证明新颖性。
2. G02 — 跨领域迁移：寻找其他领域的方法、机制或认识与当前问题的结构联系，说明它在原领域为何有效、哪些前提在这里仍成立、哪些需要适配。迁移的价值取决于新增的能力或认识，不以改动多少作为标准。
3. G03 — Rethinking 默认前提：重新审视领域中被默认接受的假设、问题定义或解释，调查它们的依据与适用边界，思考放松、替换或修正前提后会出现什么新方法、预测或理解。不要求结论一定推翻前作。
4. G04 — 诊断、重测与重新归因：从反常现象、矛盾证据或未解释的规律出发，寻找真正起作用的因素，提出能区分竞争解释的测量或对照，并考虑由此导出的改进。正结果和负结果都可以有价值，关键是回答重要问题并增加认识。
5. G05 — 扩展能力与适用边界：考察已有方法的作用单位、自适应量、表示方式或理论适用范围能否扩展，解释原边界由什么限制、如何跨越，以及可能获得什么新能力。根据问题选择必要构造，不局限于调一个参数或做最小改动。
6. G06 — 自由探索：直接从本领域最值得解决的问题或未解事实出发，自主提出上述思路之外的构造，也可以组合多种思路。不需要证明其他规则不适用，仍须交代真实依据、实质贡献和可检验预测。

这些是帮助打开思路的探索视角，可以组合、转向或超出，不是必须依次完成的流程，也不要求最终五条 idea 覆盖全部思路。最终根据问题价值、潜在贡献、具体机制、依据和新颖性综合取舍，不设置类型或冒险程度配额。

你可以联网搜索。请真正检索和阅读近邻工作，再确定最终想法；不能仅凭记忆声称新颖。
可使用公共论文库、arXiv、OpenReview、出版社和普通网页。当前联网方式是终端 HTTPS 请求；本环境没有原生 web_search 工具。
提供的工具：
  python3 tools/web_search.py search "query" --source crossref --limit 12
  python3 tools/web_search.py search "query" --source datacite --limit 12
  python3 tools/web_search.py fetch https://... --chars 24000
也可自行使用 curl 或 Python 访问公开 HTTPS 检索接口、网页和论文全文。工具返回不理想时改关键词或来源。
至少用三组有区别的查询词调查相近机制、已有组合与最强基线，实读最相关来源。无命中不能证明新颖。
不要访问私有本地论文库、旧实验想法或其他会话；本工作区没有提供它们。

新颖性判断要调查前人已经完成的核心机制与结论，说明自己的实质增量。熟悉组件的组合或跨领域迁移可以形成新贡献，但只换名字、重复已有结论或仅以组合尚无人尝试为依据，都不足以证明新颖性。
明确给出问题、核心机制及必要公式、因果或可证伪预测、与最相近工作的差异，以及为何足够支撑一篇论文。
实验部分只需简短说明未来如何区分核心假设与已有解释、可能观察到什么，以及哪些结果会促使你修正判断。数据、任务、指标、对照和资源安排可按需要提出初步设想；尚未确定的部分如实注明。不要求现阶段给出完整实验协议、预算或已有结果，也不以实验完善程度作为候选准入或排序依据。
不要伪造实验结果。区分文献事实、你的推论、待验证假设和检索未排除的风险。

生成 idea 后、确定最终五条之前，请逐条复查 novelty，并诚实评价其贡献是否有潜力成长为一篇独立的研究论文。

先用一两句话明确自己真正声称的核心贡献：解决哪个问题，提出什么机制、能力或认识，相对已有工作增加了什么。围绕这一核心贡献，通过 LitGraph 和公开文献检索最相近的前作，使用不同术语和等价表述补查，实际阅读关键来源。比较研究问题、核心操作、机制与主要结论，不能只看标题、名称或应用场景是否不同，也不能把检索无命中当作已经证明新颖。

若发现已有前作完成了相同的核心贡献，必须明确承认重合，实质修改或更换候选，并重新检查；不能通过换名、换表述或补充次要细节继续认领相同贡献。若仍有独立增量，准确界定它是什么、为什么重要，以及是否足以支撑一篇论文。尚不能排除的重复风险要如实记录，不能为了保留自己的 idea 淡化最接近的前作。

诚实自评：假设核心设想成立，它能为本领域增加什么重要能力或认识？相对最强相关工作，剩余贡献是否实质且足够独立？目前最有力的依据、最薄弱的环节和仍待验证的关键假设分别是什么？不要给所有候选套上肯定评价，也不要承诺论文录用。贡献不足时继续发展机制或更换候选；有论文潜力但仍存在关键未知时，明确给出带条件的判断。研究潜力与实验完成度分别判断，不因尚无实验结果、实验细节未定或想法此前未被尝试，就否定其潜力。

将实际检索、最接近前作、重合、独立增量与未排除风险写入 novelty_check；在 scientific_potential 中写明诚实结论、具体理由、已知不足和成立所需的关键条件。IDEA.md 中呈现这些判断。自评结论必须由前作对比和具体论证支持，不能用自我打分替代证据。

写入 /work/out/ 以下交付物：
1. IDEAS.json：严格为长度 5 的 JSON 数组，每个对象的字段 title, problem, mechanism, previous_work,
   novelty_check, experiment, failure_conditions, scientific_potential，均不可为空。
   previous_work 至少 3 篇最相关真实工作；每项须含 title（完整标题）, url（实际来源）, read_depth,
   source_location（实际读到的摘要/章节/字段）, overlap, difference。
   novelty_check 含 search_queries、closest_work、already_done_test、remaining_contribution、unresolved_risks。
   problem 写明至少一个本领域核心 problem 的真实 LitGraph 条目 ID、重要性及待解决的障碍；mechanism 说明所用 insights 的真实条目 ID、来源领域，以及它们如何启发你的解决思路。
   experiment 可以是简短的未来验证设想，并明确尚待确定的部分；failure_conditions 写出可能推翻核心假设的条件或观察，不要求已完成实验。
2. IDEA.md：可供其他研究者直接阅读的中文说明，分别完整论证五个想法、各自的 Previous work 和验证方案，并说明五者的区别与推荐顺序。
3. SEARCH_LOG.md：真实查询、来源 URL、读取深度、候选取舍和未排除风险。工具失败也如实记录。
可在 /work/out/ 存放检索材料和脚本；/work 其余位置只读。结束前自行检查 JSON 和三份交付物完整。

五个候选都须达到上述要求；不能把同一机制的五个应用算成五个想法。至少实际访问一个公共 HTTPS 检索服务或原始论文来源。

额外资源：只读 live LitGraph API（本轮另附全部领域 insight/problem 条目，仍可按需要主动检索原始证据）。
BASE={api_base}
获取交叉领域全量材料时，可使用下方 domain-context 命令；它会遍历 insights 和 problems 的全部分页并校验数量。随后完整阅读导出的 entries.jsonl，必要时分段读取，不要把下载完成等同于已经阅读。材料缺失或读取不完整时如实报告。
请实际使用 API 调查相近条目和来源论文。paper_count 是支撑论文数，不是外部引用次数。
命令：
  python3 tools/library_client.py stats
  python3 tools/library_client.py domains --q "关键词" --limit 20
  python3 tools/library_client.py domain-context <domain_id> --output-dir out/cross_domain/<domain_id>
  python3 tools/library_client.py search "关键词" --kind insight --mode all --limit 20
  python3 tools/library_client.py search "关键词" --kind problem --mode any --limit 20
  python3 tools/library_client.py show <entry_id>
  python3 tools/library_client.py paper <数字paper_id>
  python3 tools/library_client.py batch <数字paper_id> <数字paper_id>
API 说明也可读 BASE/llms.txt 或 BASE/openapi.json。常规路由是 /api/v1/domains、
/api/v1/domains/{id}/insights、/problems、/papers、/api/v1/search、/api/v1/entries/{id}、
/api/v1/papers/{数字id}；只读 POST /api/v1/papers/batch 支持批量查询。
从 API 核对的 previous_work 增加 paper_id，并在 IDEA.md 中写《数字 paper_id》完整标题，便于复查；
数字编号不等于 W 编号。仍可引用库外网络文献，但不得编造其 LitGraph 编号。
在 SEARCH_LOG.md 记录实际 API 查询和阅读深度。API 不可用时如实报告，不回退本地数据库。

额外输入：本轮所属领域完整材料快照中的全部 insight/problem 条目，按 entry id 去重。
本轮未为历史重建另设日期截止点，也没有 top-k 取样、摘要替代或省略条目。先整体阅读这些条目，形成领域判断，再开展近邻调查和五条想法的构思。
总计 {entries} 条，其中 insight {insights}、problem {problems}；全文 {context_chars} 字符。
条目包含 statement、mechanism、scope、techniques、supporting_papers 等 API 返回字段；来源论文 ID 不代表已读过这些论文全文。
全部原始 JSONL 同时保存在只读 /work/full_domain_context.jsonl；这是本轮明确提供的材料，可以读取。
<complete_domain_context>
{full_domain_context_jsonl}
</complete_domain_context>

以上上下文已完整提供。继续遵守同一生成要求：最终在 /work/out/IDEAS.json 提交五个完整候选，同时写 IDEA.md 和 SEARCH_LOG.md。
不得静默截断为 top-k，不要把条目直接改写成创新；实际核查最近邻，并区分已有结论、你的推论和未排除风险。
