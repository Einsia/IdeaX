# FounderBench 提示词协议 v2

原则：所有系统拿到逐字相同的任务描述，只有少数几个位置按固定规则变化；每个系统只追加自己原生的材料，原生材料保持原来的语言。每次运行都记录渲染结果的 sha256，用于复现和核对。

渲染代码：`founder_recon/prompts_v2.py`。预览命令：`python3 -m founder_recon.prompts_v2 preview <task_id>`，结果写入 `preview/`。

## 1. 共同任务模板（`task.en.txt`）

| 槽位 | 规则 |
| --- | --- |
| `{today}` / `{cutoff}` | 截止日前一天 / 截止日（不含当天） |
| `{domain_name}` / `{domain_id}` | litgraph 的领域名和领域 ID |
| `{k}` | 该系统一次运行原生交出的想法数：IdeaX-API、普通文本和 IdeaX 消融为 10，IdeaScientist 和 CoI 为 1 |
| `{if_multi:…}` / `{if_single:…}` | 按 k 是否大于 1 二选一。k>1 时用复数措辞，并加上"按可能性排序、彼此有实质区别" |

k=1 时，渲染结果与 v1 交给 IdeaScientist/CoI 的单想法文本逐字节相同，58 个任务都已核对。所以已有的 IdeaScientist（开思考）和 CoI 运行可以原样作为 v2 运行复用。

**语言**：任务描述统一用英文。理由如下：

- IdeaScientist、CoI 和普通文本的文献库检索只认英文词。
- 如果改用中文任务，已有运行就都不能复用。
- IdeaX 的原生材料保持中文：系统提示（来自 IdeaX 的 llms.txt）和领域条目（库本身是中文）。它的检索同时支持中英文，Claude 也能处理"中文材料 + 英文任务"。这和 IdeaScientist、CoI 使用各自的英文框架提示是同一条规则：任务相同，原生材料用原生语言。

**已知取舍**：模板沿用 v1 的措辞"not … an added benchmark"，而 69 个目标里有 12 个首篇是 benchmark 型论文。这句话对所有系统一视同仁，所以不影响系统间比较，但可能压低 benchmark 型目标的绝对命中率。排行榜会单独报告去掉这类目标后的结果。

## 2. 各系统追加的原生材料（只允许这些）

| 系统 | 原生入口 | 追加内容 |
| --- | --- | --- |
| IdeaX-API | Claude agent：system + 第一条 user 消息 + 只读 API 工具 | system 用 `ideax_system.zh.txt`（由 IdeaX 公网 llms.txt 的 agent 提示词改写，见第 4 节）。user 先给目标领域截止前的全部 insights 和 problems（全量探索模式），再给共同任务。卡片字段由 submit_cards 工具规定 |
| 消融：IdeaX 仅领域条目 | 单次调用，无工具 | 同样的领域全量条目、共同任务和卡片格式说明（`generate.CARD_FORMAT_EN`） |
| 普通文本 | 两次调用：先写检索词，再生成 | 共同任务，加检索步骤的固定说明、BM25 检索到的 ≤60 篇题名和摘要，以及卡片格式说明（`generate.PLAIN_WRAPPERS["en"]`） |
| IdeaScientist | 原生框架的 `--problem-file` | 无，共同任务就是 problem 文件 |
| CoI | 原生 CoI-Agent 的 `--topic-file` | 无，共同任务就是 topic 文件 |

**领域条目的压缩规则**：上限 13 万字，约 7 万 token。先给全文（陈述、机制、范围、技术）；超出就省略范围和技术；再超出就每条只保留第一篇来源。58 个任务中 51 个用全文，7 个省略了范围和技术。完整条目都能通过 `/api/v1/entries/{id}` 读取，消融版除外。

## 3. 输出到卡片的映射（评分只看公共字段）

公共字段：title、core_claim、problem、mechanism、why_now、predicted_contribution、evidence。裁判看除 evidence 以外的字段。

- **IdeaX-API**：用 submit_cards 提交公共字段。source_entry_ids 和 entry_usage 放在 provenance 里，另存为 `provenance.json`，不交给裁判。
- **普通文本和 IdeaX 消融**：输出 JSON 卡片。字符串里有未转义的引号时，先自动修复再解析。
- **IdeaScientist**：最终报告按固定规则映射成卡片（`isci_cell.report_card`）。
- **CoI**：idea 文本按章节标题映射成卡片（`run_coi.card_from`）。

评分时每次运行单独交给裁判，一次只评一个系统的卡片。v1 提示词下的 IdeaX/普通文本参考结果是例外，保留原来两两一起评的记录。

## 4. IdeaX 公网 agent 提示词的改写

原文是 IdeaX 公网 `llms.txt` 里"可直接交给 agent 的提示词"。改写如下：

1. **BASE 换成本地截断服务**，每个截止日一个端口。公网地址是没截断的完整库，目标首篇就在里面。本地截断服务实现了原文用到的全部接口，包括 `sort=paper_count`。
2. **免责声明换成截断说明。**
3. **"定位领域 / 阅读领域"改为"全量探索模式"**：目标领域的全部条目已经在对话里；需要其他领域时按原文的接口去读。
4. **删去**：
   - 原文"用户的具体任务"一句，改用共同任务模板；
   - 知识蒸馏示例（knowledge-distillation 本身就是任务领域）；
   - 多 agent 辩论和 selector；
   - Python 客户端；
   - 临时域名的说明。
5. **保留研究想法的输出要求**：目标 problem、借用的 insight、适配步骤、与最接近工作的区别、可证伪预测、最小对照实验、失败条件、Previous work。提交时把这些内容映射到公共字段。

## 5. 调用方式

```bash
export FOUNDER_PLAN=benchmarks/founder_recon/targets_v2/per_target_plan.jsonl
TASKS=$(python3 -c "import json; print(' '.join(json.loads(l)['task_id'] for l in open('benchmarks/founder_bench/tasks.jsonl')))")
# IdeaX-API、普通文本、IdeaX 消融：每个任务跑 1 次，每次出 10 张卡
python3 -m founder_recon.run_all --protocol v2 --lang en --systems ideax_api plain ideax_ctx --no-judge --k 10 \
    --workers 6 --global-cap 300 --out benchmarks/founder_recon/bench_v2_ideax_plain --cells $TASKS
# IdeaScientist：每个任务独立跑 2 次（输出目录 _r1 / _r2），每次 1 个想法
python3 -m founder_recon.run_isci --protocol v2 --lang en --rounds 1 --cap 12 --max-reads 20 --max-reviews 1 \
    --reader-model claude-haiku-4-5-20251001 --thinking-effort medium --workers 6 --out <dir> --cells $TASKS
# CoI：每个任务独立跑 2 次，每次 1 个想法
python3 -m founder_recon.run_coi --protocol v2 --lang en --runs 1 --cheap-model claude-haiku-4-5-20251001 --low-cost \
    --workers 8 --out <dir> --cells $TASKS
# 打包与评分
python3 -m founder_recon.bench import && python3 -m founder_recon.bench judge && python3 -m founder_recon.bench report
```

**模型**：

- 主模型：截止日 ≤ 2026-01-01 用 claude-opus-4-6，≥ 2026-02-01 用 claude-opus-4-8。
- 读论文和辅助模型：claude-haiku-4-5-20251001，训练数据截至 2025-07。
- 生成侧所有模型的训练数据截止都早于任务截止日。

**思考**：

- IdeaX-API、普通文本、IdeaX 消融：adaptive thinking，effort high（普通文本的检索词那一步用 low）。
- IdeaScientist 和 CoI 的主模型：adaptive thinking，effort medium。
- Haiku 不开思考。

**中转并发上限**：本机所有 Claude 调用共用一组槽位（2026-11-05 前为 10 个，之后提高到 20 个），见 `recon_bench/adapters/relay_slots.py`，可用 `RELAY_MAX_CONCURRENCY` 调整。覆盖的调用方：IdeaScientist 走的模型网关、IdeaX / 普通文本用的 `founder_recon.claude`、CoI 的 Anthropic 传输层。每个请求在发出期间占用一个槽位，槽位满时排队等待。所以多开几个任务也不会超过上限，只会排队。

## 6. IdeaX 原版系统（封板版）与 recon 调整版

历史实验从当时的 IdeaX 封板系统导入代码，不修改源系统。下列入口记录历史实验协议；本发布版提供的评分入口见 `benchmarks/README.md`，不包含这些历史 campaign 的启动器或截断数据库。

| 系统 | 入口 | 提示词 | 与封板版的差别 |
|---|---|---|---|
| IdeaX v7（单代理） | `founder_recon/ideax_v7.py --variant sealed` | `ideax_v7_recon.md` | 只做 recon 规则要求的改动：截断库 API、无网络（删去联网措辞）、Claude（Opus 4.6/4.8，1M 上下文）、统一任务（k=5）、日期写截止日前一天；格式不过时最多 3 轮修正；库内论文的 url 可用 API 路径 |
| IdeaX v7-R | `founder_recon/ideax_v7.py --variant r` | `ideax_v7r_recon.md` | 在 v7 之上，把 IdeaX 自己的想法类型偏好换成统一任务的目标（见下） |
| IdeaX v7-G | `founder_recon/ideax_v7.py --variant g` | `ideax_v7g_recon.md` | 在 v7-R 之上，把 IdeaX-API 的生成思路放进 v7 的五个阶段（见下）；文件、字段和 IdeaX 的全部检查不变 |
| IdeaX v10（多代理） | `founder_recon/ideax_v10.py` | 封板提示词 + `recon_edits()` 的替换 | 同 v7 的 recon 改动；每视角 2 个 scout（共 12 个，封板为 30 个）；裁决者选 10 张（封板为 5 张） |

**v7-R 改了什么**：v7 提示词里有几条 IdeaX 自己的研究偏好，和统一任务（"接下来几个月最可能出现的论文"）冲突，v7-R 把它们换掉，五个阶段、全量条目、候选漏斗、前作核查、自我反驳和全部检查都不变：

- 删去"最终五条至少两条必须是解释/预测或测量问题"和"候选池至少两条解释/理论/测量型"两处配额，改为"候选类型不设配额"；
- 删去"把已有模块拼接成系统、增加控制器/损失/路由器都不算科学增量"，改为统一任务的说法（核心贡献，不是增量、综述或 benchmark），方法、机制、问题设定和解释性研究一视同仁；
- 反驳阶段的淘汰标准从"已有方法的组合、只增加工程开销、没有区分已有解释的科学预测"改为"截止前已有人做过、只是增量改进、截止时还不具备可行条件"；
- `why_paper` 从"成功/失败会改变哪项认识"改为"为什么这篇论文会在接下来几个月出现"；五条按出现可能性排序。

这个目标和 IdeaX 自己的重建模式（`idea_run.py --mode reconstruct`："重建下个月会出现的论文"）一致。改动依据是任务原文，不是逐个目标的命中情况。为避免在评测集上调参，v7-R 先在 6 个开发任务上试跑（`benchmarks/founder_recon/ideax_v7r_r1/DEV_TASKS.txt`，按固定规则选出），提示词冻结后再跑其余任务；排行榜单列不含开发任务的结果。

```bash
python3.12 -m founder_recon.run_ideax_v7_batch --variant r --tasks <task ids> --out benchmarks/founder_recon/ideax_v7r_r1
```

**v7-G 改了什么**（在 v7-R 的基础上；依据是漏斗诊断：v7 / v7-R 每个任务约 13 个候选只覆盖 47 个目标中的 5 个，瓶颈在生成候选）：

- 构造想法按 IdeaX 官方 agent 提示词（即 IdeaX-API 用的）的做法：选一个目标 problem，借用一个 insight（可以跨领域），写清原有机制和适配步骤；
- 阶段 1：`SOURCE_TENSIONS.json` 的文件和字段不变，内容从"现有解释说不通的现象"改为"领域动向"（正在推进但没解决的限制、相邻领域可迁移的方法），每个主要机制簇至少一条；
- 阶段 2：约 20 个候选，覆盖每个主要机制簇，每个带 title、why_paper 和出现可能性名次 rank；查新只淘汰"截止前已有相同核心贡献"的候选，有相近工作不淘汰；
- 阶段 3：按 rank 取前五个未淘汰的候选写成精简卡（机制写清输入、输出、关键步骤；前作至少三篇）；
- 阶段 4：只核查两件事：截止前是否已有人做过、截止时是否可行；不写脚本；
- 阶段 5：被否定的换成漏斗里的下一个候选，按出现可能性排序交付五张。

调参只用 v7 没跑过的 22 个任务（`benchmarks/founder_recon/ideax_v7g_dev/TUNING_TASKS.txt`），冻结后在 v7 跑过的 39 个任务上跑一次（`ideax_v7g_r1`），和 v7、v7-R、IdeaX-API 在同样的 47 个目标上比较。

## 7. IdeaX 单代理正式版（v4 提示词）与 recon 版

入口 `founder_recon/ideax_single.py`（导入 IdeaX `system/IdeaX single agent/current` 的运行代码与封板模板，模板哈希与发布记录一致）。recon 规则改动同 v7：截断库条目与 API、无网络（删联网段落与 web_search 工具，跳过"必须观察到联网"检查，库内论文 url 写 API 路径）、日期为截止日前一天、Claude Opus 4.6/4.8（1M 上下文，effort high）、领域目标换成统一任务（k=5）。会话方式、两次格式补救、其余检查都用 IdeaX 原版。IdeaX 的检查写死 5 张，所以每个任务独立跑 2 次合成 10 张。

| 版本 | `--variant` | 相对封板模板的改动 |
|---|---|---|
| 封板版 | `sealed` | 只有 recon 规则改动 |
| single-R | `r` | 把"新的、值得发展为论文""鼓励大胆、不要只选稳妥的小改进"等偏好换成统一任务的目标：接下来几个月最可能出现，按出现可能性排序（`R_EDITS`，9 处） |
| single-R2 | `r2` | single-R 加三处措辞（`R2_EDITS`）：先在 `/work/out/CANDIDATES.md` 列 15–20 个不同方向的候选并按出现可能性排序，再挑 5 条；把程序会检查的字段写成交付前自查清单；IDEA.md / SEARCH_LOG.md 从简 |
| 对照 | `api` | 框架不变，研究要求换成 IdeaX-API 的提示词（`ideax_system.zh.txt`） |

调参只用 v7 没跑过的 22 个任务；single-R2 冻结后（哈希见 `benchmarks/founder_recon/ideax_single_r2_r1/FROZEN_PROMPT.txt`）在 v7 跑过的 39 个任务上跑 2 次。另有一个诊断实验（single-R 的研究要求放进 IdeaX-API 的 API 调用方式，`prompts/ideax_single_r_api.zh.txt`），它不是 IdeaX 单代理系统，不进主表。
