"""A fresh, score-blind selector fixes Top1 without changing any generated card."""
from common import *

def select(root, domain):
    import single
    from light import invoke, validate_selection
    from multi_source import validate_source
    source = read(root/'evaluation_source.json'); validate_source(source)
    saved = root/'selector_top1.json'
    if saved.exists():
        receipt = read(saved); verify(receipt['files']); return receipt
    run = root/'selector'
    if not (run/'run.json').exists():
        single.prepare_work(run, domain)
        save(run/'run.json', dict(domain_id=domain, access=ACCESS, model='gpt-6-astra', effort='xhigh', created=now()))
    cards = read(source['ideas'])
    pool = [dict(card, id=f'idea-{i:02}') for i,card in enumerate(cards,1)]
    freeze(run/'work/debate/final_pool.json', pool)
    prompt = '''你是独立 selector，与构思作者没有共享会话。阅读 /work/debate/final_pool.json 的五张原卡，选择唯一最佳 idea，并给出五张卡的推荐顺序。
按 Novelty、Importance 优先，再检查 Soundness（逻辑自洽）；大胆而有依据的想法可以胜出，不因尚无实验结果、预算未定或实现难度直接扣分。判断前作覆盖、核心机制、问题价值与贡献边界。
只能使用本轮卡片及本组允许的检索渠道；没有任何外部裁判评分。不要改写、合并或替换原卡。
写 /work/out/TOP5.json，结构 {"top5":[{"rank":1,"card":"idea-01","reason":"基于卡片内容的明确选择理由"},...]}。
正好五个不同的原始 ID，rank 严格为 1 至 5；rank=1 即冻结 Top1，外部评测不会重新选卡。不能调用子代理。
'''
    prompt += {'full':'本组已提供完整领域材料 /work/full_domain_context.jsonl，可用 LitGraph API 和公开网络。',
               'api':'本组无预注入完整材料；可按需查询 LitGraph API，公开网络可选。',
               'web':'本组仅允许公开网络；不提供且禁止调用 LitGraph 或其他实验组材料。'}[ACCESS]
    output=run/'work/out/TOP5.json'
    receipt=invoke(run,'single-select',prompt,output,lambda x:validate_selection(x,pool))
    if receipt['session'] == read(root/'session.json')['session_id']: raise ValueError('Selector reused author session')
    first=read(output)['top5'][0]['card']; rank=int(first.split('-')[-1])
    files={str(output):sha(output),str(root/'evaluation_source.json'):sha(root/'evaluation_source.json'),source['ideas']:source['ideas_sha256']}
    result=dict(at=now(),original_rank=rank,card=first,session=receipt['session'],files=files,
                policy='Independent score-blind selector fixed before external review; original five cards unchanged')
    freeze(saved,result);return result
