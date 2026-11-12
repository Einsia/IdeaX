# IdeaX

LitGraph 驱动的研究 idea 生成系统及评测代码。此仓库整理了当前使用的 **Single Full / Single API、Multi Full / Multi API、IdeaScientist、CoI**，包含原始 prompt、38 个领域任务、生成流程、Research Blueprint 写作阶段和四套 benchmark。

## 目录

| 路径 | 内容 |
|---|---|
| `system/single-full/` | 单个独立研究者；完整领域 insights/problems + LitGraph API + 联网 |
| `system/single-api/` | 单个独立研究者；自主检索 LitGraph，联网可选，不预注入领域材料 |
| `system/multi-full/` | 6 位 Full 作者，每人 5 个候选；讨论 → 修订一轮 → 独立选 Top5 |
| `system/multi-api/` | 相同协作流程；作者使用 API 访问方式 |
| `system/runtime/` | 共享原生执行、阶段检查、失败重试、来源验证及 Blueprint 写作 |
| `baselines/ideascientist/` | IdeaScientist 原生多角色流程与适配源码 |
| `baselines/coi/` | CoI 论文链、查新及内部审阅流程与适配源码 |
| `benchmarks/reviewer/` | 三维 N/I/S Reviewer，权重 40% / 40% / 20% |
| `benchmarks/interesting/` | 同领域全部卡片通读后评分的 Interesting Bench |
| `benchmarks/founder/` | 截止日之前、禁止联网的 Founder 重建评测任务、答案及评分 |
| `benchmarks/ideascientist/` | IS 六维质量、新颖性及跨领域结构迁移评分 |
| `data/` | 38 个领域定义及 Full 使用的 7,641 条领域材料快照 |
| `provenance/` | 源文件与发布文件的校验信息 |

Multi 的讨论和修订合为一轮。Top1 取外部评审之前 selector 选择的第一名，不根据裁判分数事后择优。每个系统每域交付五张完整 idea card；可再运行 Blueprint 阶段。

## 直接复制 Prompt 使用

[中文 Single API Prompt](docs/single_api_copyable_zh.md) 已填入公开 LitGraph 地址。只需修改“领域”一行，即可交给支持联网 HTTP 请求的 agent；无需下载数据库或安装本仓库的专用脚本。它按需检索领域材料，保留六种探索视角、前作核查和五条完整 idea 的交付要求。

当前 LitGraph 公开只读入口：<https://kevin-wake-stuffed-anti.trycloudflare.com>，无需 LitGraph API key。[接口说明](https://kevin-wake-stuffed-anti.trycloudflare.com/llms.txt) 可直接提供给 agent。该入口于 2026-11-12 验证可用，使用临时隧道域名，后续可能变化；模型调用仍由使用者自己的 agent 环境提供。

该复制版仅适配直接 HTTP 调用、领域填写和输出目录；实验使用的原始 prompt 保留在 `system/single-api/prompts/generation.md`，没有替换其内容或哈希。完整领域预加载版见 [英文 Full Prompt](docs/single_full_copyable_en.txt)，使用 Full 时仍须提供对应领域的完整材料。

## 安装与配置

需要 Linux、Python 3.12、`bubblewrap` 和支持当前模型/effort 参数的 Codex、Claude CLI。生成使用原生 Codex 会话，评分使用独立的 Codex / Claude 会话。默认模型为 Astra / xhigh 与 Opus 5.5 / xhigh。

```bash
git clone git@github.com:Einsia/IdeaX.git
cd IdeaX
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 在 .env 中填写服务地址，并引用自己的受保护凭据。
set -a
source .env
set +a
```

Full 的领域快照随代码提供；运行中读取关联论文和跨领域材料仍需要有效 LitGraph API。API 组工作区不会获得 Full 的材料。完整 LitGraph 论文库、Svalbard 数据库、历史运行日志和个人凭据不在此仓库。

## IdeaX 生成

```bash
# 校验 38 领域材料、prompt 和运行依赖；不调用模型。
python system/run.py single-full check

# 准备一个领域；改成 --domains all 即为 38 个领域。
python system/run.py single-full prepare --domains agent-memory --out runs/single-full
python system/run.py single-full run --execution runs/single-full --gpt-budget 1 --external-gpt-reserved 0
python system/run.py single-full status --execution runs/single-full
python system/run.py single-full export --execution runs/single-full
```

将 `single-full` 换为其他三个目录名即可切换系统。Multi 的预算以 6 位作者的完整领域 run 为单位，`--gpt-budget` 至少为 6；阶段验证未通过时不推进下一阶段。`--external-gpt-reserved` 需填写同一账号在其他任务中已经占用的额度。运行会保存 prompt、工具访问、失败尝试、原生会话和来源校验。

可直接复制的英文 Full prompt 在 [docs/single_full_copyable_en.txt](docs/single_full_copyable_en.txt)。实际实验使用的中文原文在各系统 `prompts/generation.md`。英文版是便于使用的翻译，未作为单独实验条件测评。

Baseline、Blueprint 和评测命令见 [运行指南](docs/RUNNING.md)。评分版本及不可混排的协议见 [benchmark 说明](benchmarks/README.md)。来源与第三方许可见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 离线验证

```bash
python scripts/check_release.py
python -m unittest discover -s tests -v
```

检查覆盖四种配置、Full/API 材料隔离、prompt 哈希、协作阶段约束、评测输入准备和评分完整性。离线检查不发起生成或付费评审。发布整理调整了路径和调度入口，未用这些新入口重跑论文实验；不要把成功导入或通过离线检查理解为重现了论文分数。
