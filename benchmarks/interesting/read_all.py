VERSION='interesting-read-all-then-score-v2'

PROTOCOL='''每位评委独立完成一轮：先通读本批全部 idea 并做笔记，再开始任何评分。本批可以只有 1 张或 5 张，不要求凑满 10 或 15 张。
材料较多时，预读按每批最多 5 张拆分；必须完成所有预读批次，才能进入评分。预读只记录机制、优点、局限和证据，不给数字分数，不排名。
全部预读结束后，按冻结顺序每批最多 5 张正式评分，覆盖本批每一张卡。此前的完整原文、预读笔记和尺度笔记会显式传递。每张卡的首次评分必须完整可交付。
本人记忆独立传递，不看其他评委或其他重复的评分。其他卡只帮助理解和校准，不能替本卡补足证据，不强制分布、名额或排名。
评分 loop 可以不改分，最多回改一张此前已经评分的卡；不得回改当前批首次评分卡。必须说明旧判断的具体偏差、当前批触发卡片和被改卡自身原文证据，不为凑分布改分。
只返回严格 JSON，顶层恰为 notes, calibration_note, assessments, revisions。
notes 恰为当前批每卡一个对象，字段 card_id, mechanism, strength, limitation, evidence_quote（本卡正文逐字至少 8 字符，不含行号）。
calibration_note 是非空字符串，记录本人对 Interesting 尺度的理解，不规定分布。预读的 notes 和 calibration_note 不得包含数字评分或排名。
assessments 在预读时为空数组；评分时恰为当前批每卡一份。
每份 assessment 恰含 card_id, score（0–100 整数或 null）, reason（具体理由）, departure（相对常规模板的转折）, evidence_quote（本卡正文逐字至少 8 字符）, uncertainty（未核实条件）, revision_from_notes（相对预读笔记的修正或无）。
revisions 预读时为空；评分时为 0 或 1 个对象，字段 card_id, reason, trigger_card_ids（当前批非空卡 ID 数组）, assessment（被改旧卡的完整新评分）。分数必须确实改变。
'''

def stages(ids):
    if not ids or len(ids)!=len(set(ids)):raise ValueError('Need nonempty unique cards')
    chunks=[ids[i:i+5] for i in range(0,len(ids),5)]
    return [{'stage_id':f'{i:02d}-{kind}','kind':kind,'card_ids':chunk}
            for i,(kind,chunk) in enumerate([(kind,c) for kind in ('read','score') for c in chunks],1)]
