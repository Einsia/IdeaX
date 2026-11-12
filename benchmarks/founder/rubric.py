import json

import random

from pathlib import Path

RUBRIC = """匹配等级（卡片 vs 目标论文的核心贡献）：
3 = 实质相同：同一个问题，同一个关键机制；若这张卡在截止日发表，会被视为提前提出了这篇论文的核心贡献。
2 = 关键机制相同或高度相近，但问题设定/适用范围明显不同，或缺少目标的一个关键组成。
1 = 同一问题或方向，但机制不同；或只命中了目标的次要部分。
0 = 无关，或只在宽泛主题上相关（如同属"高效推理"）。
只看机制与问题是否对应，不因措辞相似或领域相同给分；卡片泛泛而谈（没有具体机制）时最多 1 分。"""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["matches"],
          "properties": {"matches": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["card", "target", "level", "rationale"],
              "properties": {"card": {"type": "string"}, "target": {"type": "string"},
                             "level": {"type": "integer", "enum": [0, 1, 2, 3]}, "rationale": {"type": "string"}}}}}}

def build_prompt(cell_key: str, targets: list[dict], cards_by_system: dict[str, list[dict]], seed: int):
    """The judge prompt shared by every judge model: truth, the rubric and the cards under seeded letters."""
    truth = truth_for(targets)
    systems = sorted(cards_by_system)
    random.Random(f"{seed}:{cell_key}").shuffle(systems)
    labels = {sys_: chr(ord("A") + i) for i, sys_ in enumerate(systems)}
    shown = []
    for sys_ in systems:
        for i, card in enumerate(cards_by_system[sys_], 1):
            shown.append({"card": f"{labels[sys_]}{i}", **{k: v for k, v in card.items() if k != "evidence"}})
    prompt = (f"你是研究想法重建评测的评委。下面是若干张在文献截止日之前生成的研究卡片，以及截止后真实出现的目标论文。"
              f"请对每一对（卡片, 目标）给出匹配等级与一句话理由。\n\n{RUBRIC}\n\n"
              f"## 目标论文\n{json.dumps(truth, ensure_ascii=False, indent=1)}\n\n## 卡片\n{json.dumps(shown, ensure_ascii=False, indent=1)}\n\n"
              "输出 matches：覆盖所有卡片与所有目标的组合。")
    return prompt, labels, truth

def truth_for(targets):
    return [dict(target=f'T{i}',paper_id=str(t['founder_paper_id']),arxiv=t.get('arxiv'),
                 title=t['title'],**t['truth']) for i,t in enumerate(targets,1)]
