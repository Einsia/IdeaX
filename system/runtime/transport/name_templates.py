"""在隔离工作区里给截断库上挖出的锚点命名，生成 D* 模板。

  python3 tools/iso/name_templates.py --sandbox sandbox/jul --cutoff 2026-07 [--workers 6] [--model opus]

步骤
  1. 用沙箱自己的 lit.db 重挖锚点（mine_templates.py --db 沙箱库），得到 anchors 和命名提示词
  2. 新建 run 目录 sandbox/<名>/runs/name-<时间戳>：工作区只有沙箱库、过了扫描的全文、工具
  3. 每个锚点一个 agent，在隔离里写 /work/out/named_<i>.json；提示词里直接给路径，不用自己去找
  4. 开跑前扫工作区和每份提示词；跑完审计会话、扫产物。全部干净才装进 sandbox/<名>/templates/，
     旧的 named_*.json 先挪到 archive/
"""
import argparse, glob, json, os, shutil, subprocess, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isolate as I                                    # noqa: E402

ENV_NOTE = """

## 环境（隔离工作区；本任务没有网络，也没有 WebSearch / WebFetch）

- 库：`sqlite3 /work/lit.db`，只含 {CUTOFF} 之前的作品。表 works（work_id, title, earliest, abstract）、
  contributions（contrib_id, work_id, operator, delta …）、slots（contrib_id, slot, work_id, raw …）
- 全文：`/work/fetched/<作品编号>.txt`（不是每篇都有）
- 判断某个空位"有没有人做过"只能靠库和全文：查了什么、查到什么、没查到什么都写进 why_empty / how_to_check。
  库里查不到的，不要凭印象断定"已经有人做过"。
- 输出文件：`/work/out/named_{I}.json`，其中 `template_id` 写 `"{TID}"`。写完用 python3 json.load 校验一次。
"""

REQUIRED = ('template_id', 'generic_name', 'domain_variants', 'transferability', 'operator',
            'slots', 'empty_cells', 'filled_cells', 'examples')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sandbox', required=True)
    ap.add_argument('--cutoff', required=True, help='YYYY-MM')
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--model', default='opus')
    ap.add_argument('--run', default=None, help='续跑已有的 run 目录（只补没产出的）')
    a = ap.parse_args()
    sb = os.path.abspath(a.sandbox)
    name = os.path.basename(sb)
    db = f'{sb}/lit.db'
    M = I.Markers(f'{I.ROOT}/lit.db', db, a.cutoff)

    if a.run:
        run = os.path.abspath(a.run)
    else:
        run = f'{sb}/runs/name-{time.strftime("%Y%m%d-%H%M")}'
        os.makedirs(run)
        subprocess.run([sys.executable, f'{I.ROOT}/tools/mine_templates.py', '--db', db, '--out', f'{run}/mined'],
                       check=True, stdout=subprocess.DEVNULL)
        rep = I.prepare(run, db, M)
        print(f"工作区：全文保留 {rep['fetched_kept']} 篇，剔除 {len(rep['fetched_dropped'])} 篇（含截断后标记）")
    tag = f'{name}-{os.path.basename(run)}'
    n = len(glob.glob(f'{run}/mined/prompt_name_*.md'))
    jobs = []
    for i in range(n):
        tid = f'D{i:02d}'
        p = open(f'{run}/mined/prompt_name_{i}.md').read() + ENV_NOTE.replace('{CUTOFF}', a.cutoff) \
            .replace('{I}', str(i)).replace('{TID}', tid)
        jobs.append((i, tid, f'name-{i:02d}', p))

    hard, soft = I.preflight(run, M, [(j[2], j[3]) for j in jobs])
    hard_mined = I.scan_paths([f'{run}/mined'], M)
    hard_mined = {f: M.hard(h) for f, h in hard_mined.items()}
    hard.update({f: h for f, h in hard_mined.items() if h})
    if hard:
        print('开跑前扫描发现截断后标记，停止：')
        for f, h in hard.items():
            print('  ', f, h[:5])
        sys.exit(2)
    print(f'开跑前扫描：工作区与 {len(jobs)} 份提示词都没有截断后标记' + (f'（提示级命中 {len(soft)} 处，见 preflight.json）' if soft else ''))

    spent = [0.0]

    def one(job):
        i, tid, agent, prompt = job
        out = f'{run}/work/out/named_{i}.json'
        if os.path.exists(out):
            try:
                json.load(open(out))
                return f'{agent} 已有产物，跳过'
            except Exception:
                pass
        r = I.run_claude(run, tag, agent, prompt, str(uuid.uuid4()), model=a.model, timeout=2700)
        spent[0] += r['cost']
        ok = os.path.exists(out)
        return f"{agent} {'ok ' if ok else 'FAIL'} ${r['cost']:.2f} {r['tail'][-60:]!r}"

    with I.Gate(run, [j[2] for j in jobs]):
        with ThreadPoolExecutor(a.workers) as ex:
            for msg in ex.map(one, jobs):
                print('  ' + msg, flush=True)
    print(f'命名花费 ${spent[0]:.2f}')

    # 审计会话 + 扫产物 + 字段校验
    rep = I.audit(run, tag, [j[2] for j in jobs], M)
    dirty = {k: v for k, v in rep.items() if not v['clean']}
    outs = sorted(glob.glob(f'{run}/work/out/named_*.json'))
    leak = {f: M.hard(h) for f, h in I.scan_paths(outs, M).items()}
    leak = {f: h for f, h in leak.items() if h}
    bad = []
    for f in outs:
        try:
            d = json.load(open(f))
            miss = [k for k in REQUIRED if not d.get(k)]
            if miss:
                bad.append((f, f'缺字段 {miss}'))
        except Exception as e:
            bad.append((f, f'JSON 解析失败 {e}'))
    print(f'产物 {len(outs)}/{len(jobs)} 份；会话审计不干净 {len(dirty)} 个；产物含截断后标记 {len(leak)} 份；字段不全 {len(bad)} 份')
    for k, v in dirty.items():
        print('  会话', k, v['n_leaks'], v['leaks'][:3], v['egress_denied'][:3])
    for f, h in leak.items():
        print('  产物', os.path.basename(f), h[:5])
    for f, why in bad:
        print('  产物', os.path.basename(f), why)
    if dirty or leak or bad or len(outs) < len(jobs):
        print('有问题，不安装。修好后用 --run 续跑。')
        sys.exit(3)

    # 安装：旧命名挪走，新命名 + 重挖的锚点装进沙箱模板目录
    dst = f'{sb}/templates'
    old = sorted(glob.glob(f'{dst}/named_*.json'))
    if old:
        arch = f'{I.ROOT}/archive/{name}_templates_named_{time.strftime("%Y%m%d-%H%M")}'
        os.makedirs(arch)
        for f in old:
            shutil.move(f, arch)
        print(f'旧的 {len(old)} 份命名挪到 {arch}')
    os.makedirs(dst, exist_ok=True)
    for f in outs:
        shutil.copy2(f, dst)
    for f in ('anchors.json', 'generic.json'):
        if os.path.exists(f'{run}/mined/{f}'):
            shutil.copy2(f'{run}/mined/{f}', dst)
    print(f'已装入 {len(outs)} 份 D* 模板 → {dst}')


if __name__ == '__main__':
    main()
