"""隔离工作区：截断轮的 scout 和模板命名 agent 都在这里跑。

每个 agent 是 bubblewrap 里的一个 `claude -p`：
  文件系统  只有系统目录（只读）、/work（本轮工作区）、它自己的 HOME、私有 /tmp；宿主的 /cluster 整个看不见
  网络      没有。唯一出口是宿主侧的 API 闸门（api_gate.py）：只转发 /v1/messages，换上真凭据，
            拒绝服务端工具（web_search 等）和 MCP 连接器；任何隧道/其他请求都拒绝并记日志。
            真凭据不进命名空间，agent 只拿到一个假 token
  harness   全新 HOME：没有用户设置、hooks、技能、插件、MCP、自动记忆；cwd=/work，上级目录没有 CLAUDE.md / AGENTS.md；
            内置工具由 --tools 限定

宿主上的一轮目录（run）：
  run/work/             → /work            只读：lit.db、fetched/（只有库里作品的全文，且过了泄漏扫描）、tools/、templates/
  run/work/ideas/       → /work/ideas      读写：卡池、邮件、裁决
  run/work/out/         → /work/out        读写：命名等任务的产物
  run/homes/<agent>/    → /home/agent      每个 agent 一份
  ~/.claude/projects/-litgraph-<tag>-<agent>/ → /home/agent/.claude/projects/-work
                                            会话 jsonl 落在宿主，前端、agit、审计照常能找到
  run/gate/<agent>.sock → /run/gate/egress.sock   （api_gate.py 的 socket；日志在 run/gate/egress.log）

泄漏扫描（scan）以"全库有、截断库没有"的作品为准：它们的编号、arXiv 号、标题，外加截断月及以后的 arXiv 号。
"""
import glob, json, os, re, shutil, sqlite3, subprocess, sys, time
from collections import defaultdict

H = os.path.expanduser('~')
ROOT = os.environ.get('LITGRAPH_ROOT', f'{H}/litgraph')
HERE = os.path.dirname(os.path.abspath(__file__))
AI_HOME = (os.path.join(os.path.dirname(os.environ['LITGRAPH_DATA_ROOT']), 'ai-home')
           if os.environ.get('LITGRAPH_DATA_ROOT') else
           os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), 'ai-home'))
# ai-home/bin 包装脚本会 source env.sh 并修改 HOME，导致 bwrap 沙箱里写只读路径。
# 直接找到真实二进制，绕过 wrapper 脚本。
def _resolve_bin(name):
    """集群侧：~/.local/bin/<name> 就是真实二进制（或指向它的软链）。"""
    import pwd as _pwd
    real_home = _pwd.getpwuid(os.getuid()).pw_dir
    p = os.path.join(real_home, '.local', 'bin', name)
    if os.path.exists(p):
        return os.path.realpath(p)
    return os.path.realpath(os.path.join(H, '.local', 'bin', name))

def _resolve_claude_real():
    """AWS 侧：wrapper 在 ai-home/bin/claude，真实二进制通过软链在 ai-home/.local/bin/claude → .local/share/claude/versions/X。"""
    import pwd as _pwd
    real_home = _pwd.getpwuid(os.getuid()).pw_dir
    ai_home = AI_HOME
    # ai-home/.local/bin/claude 是软链，realpath 直接跳到真实二进制
    ai_local_bin = os.path.join(ai_home, '.local', 'bin', 'claude')
    if os.path.isfile(ai_local_bin):
        return os.path.realpath(ai_local_bin)
    # 集群侧
    return _resolve_bin('claude')

CLAUDE_BIN = os.environ.get('IDEAX_CLAUDE_RAW_BIN') or _resolve_claude_real()

def _resolve_codex_real():
    """AWS 侧：wrapper 在 ai-home/bin/codex，真实二进制在 ai-home/.local/lib/ai-tools/codex。"""
    import pwd as _pwd
    real_home = _pwd.getpwuid(os.getuid()).pw_dir
    ai_home = AI_HOME
    real_bin = os.path.join(ai_home, '.local', 'lib', 'ai-tools', 'codex')
    if os.path.isfile(real_bin):
        return real_bin
    return _resolve_bin('codex')
_CODEX_REAL = os.environ.get('IDEAX_CODEX_RAW_BIN') or _resolve_codex_real()
CODEX_DIR = os.path.dirname(_CODEX_REAL)   # codex 真实二进制目录，同目录还有 codex-code-mode-host
def _find_py_prefix():
    # 优先环境变量覆盖
    if os.environ.get('LITGRAPH_PY_PREFIX'):
        return os.environ['LITGRAPH_PY_PREFIX']
    # 集群侧：/opt/aiext
    if os.path.isfile('/opt/aiext/bin/python3.12'):
        return '/opt/aiext'
    # AWS 侧：uv 安装的 cpython-3.12，从真实系统 HOME 找
    import pwd as _pwd, glob as _g
    real_home = _pwd.getpwuid(os.getuid()).pw_dir
    uv_py = os.path.join(real_home, '.local', 'share', 'uv', 'python')
    for pat in ('cpython-3.12-linux-x86_64-gnu', 'cpython-3.12.*-linux-x86_64-gnu'):
        for d in sorted(_g.glob(os.path.join(uv_py, pat)), reverse=True):
            if os.path.isfile(os.path.join(d, 'bin', 'python3.12')):
                return d
    return '/opt/aiext'   # fallback（让 bwrap 报错而不是静默用错 python）
PY_PREFIX = _find_py_prefix()       # python3.12 在这里；系统的 /usr/bin/python3 是 3.6
PORT = 18888                        # 命名空间里转发桥监听的端口（每个命名空间各有一份回环）
TOOLS = ['Bash', 'Read', 'Write', 'Edit', 'Grep', 'Glob']
WEB_TOOLS = ['WebSearch', 'WebFetch']          # 只在预测轮给（闸门同时要开 --allow-web）
API_ENV = os.path.join(os.environ.get('LITGRAPH_SECRETS_DIR', f'{H}/.config/litgraph'), 'api.env')
DROP_TABLES = ('template_matches', 'versions', 'gdf', 'resolve', 'rounds', 'axes')
# 审计时要人工看一眼的命令：联网、取凭据、直接调 API
SUSPICIOUS = re.compile(r'\bcurl\b|\bwget\b|\bncat\b|\bnc\s|/dev/tcp|urllib|import requests|requests\.(?:get|post)|'
                        r'http\.client|socket\.socket|\baiohttp\b|\bhttpx\b|127\.0\.0\.1|v1/messages|'
                        r'/proc/(?:\d+|self)/environ|\benviron\b|AUTH_TOKEN|API_KEY|/run/gate|web_search|web_fetch', re.I)
WORK_TOOLS = {                      # 拷进 /work/tools 的工具：宿主路径 → 文件名
    f'{ROOT}/tools/paper_web.py': 'paper_web.py',
    f'{ROOT}/tools/library_query.py': 'library_query.py',
    f'{ROOT}/tools/library_client.py': 'library_client.py',
    f'{ROOT}/tools/library_snapshot.py': 'library_snapshot.py',
    f'{ROOT}/tools/library_api.py': 'library_api.py',
    f'{ROOT}/tools/library_api_index.py': 'library_api_index.py',
    f'{ROOT}/tools/idea_provenance.py': 'idea_provenance.py',
    f'{ROOT}/tools/idea_research.py': 'idea_research.py',
    f'{ROOT}/tools/cards.py': 'cards.py',
    f'{ROOT}/tools/mail.py': 'mail.py',
    f'{ROOT}/tools/base_space.py': 'base_space.py',
    f'{ROOT}/tools/mine_templates.py': 'mine_templates.py',
    f'{ROOT}/tools/templates.py': 'templates.py',
    f'{ROOT}/tools/rule_lens.py': 'rule_lens.py',           # 规则的跨方向实例与检索
    f'{ROOT}/tools/rule_predicates.py': 'rule_predicates.py',
    f'{ROOT}/tools/around.py': 'around.py',                 # 主干 + Svalbard 卫星（读 /work/sv.db）
}


# ---------------------------------------------------------------- 凭据与出口

def api_env():
    env = {'ANTHROPIC_BASE_URL': os.environ.get('ANTHROPIC_BASE_URL', 'https://sbtunnel.xiaoaojianghu.fun')}
    if not os.path.exists(API_ENV): return env
    for line in open(API_ENV):
        m = re.match(r'\s*(?:export\s+)?(\w+)=["\']?(.*?)["\']?\s*$', line)
        if m:
            env[m.group(1)] = m.group(2)
    return env


SUB2API_ENV = os.path.join(os.environ.get('LITGRAPH_SECRETS_DIR', f'{H}/.config/litgraph'), 'sub2api.env')


def sub2api_env():
    """codex 用的 OpenAI 兼容中转（sub2api）：SUB2API_BASE_URL / SUB2API_API_KEY，可选 CODEX_MODEL、SUB2API_PRICE_{IN,CACHED,OUT}（$/百万 token）。"""
    env = {}
    if not os.environ.get('LITGRAPH_CODEX_ENV_FILE') and os.environ.get('OPENAI_API_KEY'):
        return {'SUB2API_BASE_URL': os.environ.get('OPENAI_BASE_URL', 'https://sbtunnel.xiaoaojianghu.fun/v1'), 'SUB2API_API_KEY': os.environ['OPENAI_API_KEY']}
    path = os.environ.get('LITGRAPH_CODEX_ENV_FILE', SUB2API_ENV)
    if os.path.exists(path):
        if path.endswith('.json'):
            # Load an explicitly selected existing profile directly: never copy
            # its credential to another file or expose it inside the sandbox.
            with open(path) as stream:
                profile = json.load(stream)
            if isinstance(profile, dict) and 'api_key_env_file' in profile:
                # Reference the existing credential; do not duplicate it in a
                # project configuration or materialize it inside a sandbox.
                key_name = profile.get('api_key_env_name')
                if not isinstance(key_name, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key_name):
                    raise ValueError('Codex credential reference requires a valid environment variable name')
                values = {}
                with open(os.path.expanduser(profile['api_key_env_file'])) as stream:
                    for line in stream:
                        match = re.match(r'\s*(?:export\s+)?(\w+)=["\']?(.*?)["\']?\s*$', line)
                        if match:
                            values[match.group(1)] = match.group(2)
                profile = dict(profile, api_key=values.get(key_name))
            if not isinstance(profile, dict) or not all(
                    isinstance(profile.get(k), str) and profile[k].strip()
                    for k in ('base_url', 'api_key')):
                raise ValueError('Codex JSON credential profile requires base_url and api_key')
            return {'SUB2API_BASE_URL': profile['base_url'], 'SUB2API_API_KEY': profile['api_key']}
        for line in open(path):
            m = re.match(r'\s*(?:export\s+)?(\w+)=["\']?(.*?)["\']?\s*$', line)
            if m:
                env[m.group(1)] = m.group(2)
    return env


def upstream_proxy():
    p = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or ''
    m = re.match(r'https?://([^/:]+):(\d+)', p)
    return f'{m.group(1)}:{m.group(2)}' if m else None


class Gate:
    """一轮一个 API 闸门进程（api_gate.py），每个 agent 一个 socket，日志里能分清是谁发的请求。"""

    def __init__(self, run, agents, allow_web=False):
        self.run, self.agents, self.p, self.allow_web = run, list(agents), None, allow_web
        os.makedirs(f'{run}/gate', exist_ok=True)

    def sock(self, agent):
        path = f'{self.run}/gate/{agent}.sock'
        if len(path) <= 107:
            return path
        # AF_UNIX path limit is 108 chars; use a stable short symlink under /tmp
        import hashlib
        h = hashlib.md5(self.run.encode()).hexdigest()[:8]
        short_dir = os.path.join(os.environ.get('IDEAX_SCRATCH', os.path.dirname(ROOT) + '/.scratch'), f'g-{h}')
        os.makedirs(short_dir, exist_ok=True)
        return f'{short_dir}/{agent}.sock'

    def start(self):
        # 续跑时上一次的 socket 文件还在：不先删，下面的等待会立刻返回，bwrap 就把还没被新闸门替换的
        # 旧 socket 绑进沙箱，agent 连上的是没人监听的死 socket（ECONNRESET，闸门日志里一条请求都没有）
        for a in self.agents:
            try:
                os.remove(self.sock(a))
            except FileNotFoundError:
                pass
        cmd = [sys.executable, f'{HERE}/api_gate.py', '--log', f'{self.run}/gate/egress.log',
               '--sock'] + [f'{a}={self.sock(a)}' for a in self.agents] + (['--allow-web'] if self.allow_web else [])
        self.p = subprocess.Popen(cmd, stdout=open(f'{self.run}/gate/gate.out', 'a'),
                                  stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(100):
            if all(os.path.exists(self.sock(a)) for a in self.agents):
                return self
            if self.p.poll() is not None:
                raise RuntimeError(f'出口闸门没起来，看 {self.run}/gate/gate.out')
            time.sleep(0.1)
        raise RuntimeError('出口闸门 socket 等不到')

    def stop(self):
        if self.p and self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(10)
            except subprocess.TimeoutExpired:
                self.p.kill()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


# ---------------------------------------------------------------- 泄漏标记

def norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


class Markers:
    """截断后才有的东西。full_db 是全库，cut_db 是截断库，cutoff 是 'YYYY-MM'。

    "全库有、截断库没有"的作品分两档：
      确定  按 arXiv 年月或带月份的日期落在截断月及以后（评测的真值论文都在这里）
      不确定 只有年份、按规则当截断后处理；其中不少其实更早（库里日期记错了），
            截断前的论文引用它们是正常的
    命中类别：work / arxiv / title 是硬泄漏；work? / title? / date 只是提示。
    """
    HARD = {'work', 'arxiv', 'title'}

    def __init__(self, full_db, cut_db, cutoff):
        sys.path.insert(0, f'{ROOT}/tools')
        from build_cutoff import ym_of, is_post
        cut_ym = (int(cutoff[:4]), int(cutoff[5:7]))
        full, cut = sqlite3.connect(full_db), sqlite3.connect(cut_db)
        absent = {w for (w,) in full.execute('select work_id from works')} - \
                 {w for (w,) in cut.execute('select work_id from works')}
        arx = dict(full.execute("select work_id, value from identifiers where type='arxiv'"))
        # 截断库里没有的作品不全是截断后的：按方向建的截断库本来就不收别的方向，10-07 导入的 6 万篇会议论文也大多更早。
        # 只把日期上落在截断后的当标记（口径同 build_cutoff.is_post），否则几乎每篇全文都会因为引了某篇会议论文被剔掉
        self.known, self.uncertain = set(), set()
        for w, e in full.execute('select work_id, earliest from works'):
            if w in absent:
                d, kind = ym_of(arx.get(w), e)
                if kind in ('arxiv', 'month') and d >= cut_ym:
                    self.known.add(w)
                elif is_post(d, kind, cut_ym):
                    self.uncertain.add(w)
        post = self.known | self.uncertain
        self.arxiv = {}
        for w, v in full.execute("select work_id, value from identifiers where type like 'arxiv%'"):
            if w in self.known:
                self.arxiv[re.sub(r'v\d+$', '', v.split('/')[-1])] = w
        self.titles = {}
        for w, t in full.execute('select work_id, title from works'):
            n = norm(t)
            if w in post and len(n) >= 24:
                self.titles[n[:48]] = w
        self.cutoff = cutoff
        # 太泛的标题串不当标记：截断库自己的标题/摘要里就出现过的（如 "Memory for Large Language Models"
        # 是 HippoRAG（2024-05）标题的一部分），看到它说明不了看到了截断后的论文
        self.generic = self._generic_titles(cut_db, cut)
        for k in self.generic:
            self.titles.pop(k, None)
        self.title_lens = sorted({len(t) for t in self.titles})
        self.yymm = cutoff[2:4] + cutoff[5:7]      # arXiv 号前四位
        self.re_w = re.compile(r'\bW\d{5}\b')
        self.re_ax = re.compile(r'(?<![\d.])(\d{4})\.(\d{4,5})(?![\d])')
        self.re_date = re.compile(r'\b(20\d\d)-(0[1-9]|1[0-2])\b')

    def _generic_titles(self, cut_db, cut):
        """截断库的标题和摘要里出现过的标题串。逐个子串查找要一两分钟，结果缓存在截断库旁边，只补查新出现的标题。"""
        cache = f'{os.path.splitext(cut_db)[0]}.generic_titles.json'
        d = {'checked': [], 'generic': []}
        if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(cut_db):
            d = json.load(open(cache))
        todo = [k for k in self.titles if k not in set(d['checked'])]
        if todo:
            corpus = '\n'.join(norm(t or '') + '\n' + norm(a or '') for t, a in cut.execute('select title, abstract from works'))
            d['generic'] += [k for k in todo if k in corpus]
            d['checked'] += todo
            try:
                json.dump(d, open(cache, 'w'), ensure_ascii=False)
            except OSError:
                pass
        return set(d['generic'])

    def find(self, text):
        """返回 [(类别, 命中串)]。"""
        hits = []
        for w in set(self.re_w.findall(text)):
            if w in self.known:
                hits.append(('work', w))
            elif w in self.uncertain:
                hits.append(('work?', w))
        for a, b in set(self.re_ax.findall(text)):
            ax = f'{a}.{b}'
            if ax in self.arxiv or (self.yymm <= a <= '2712' and '01' <= a[2:] <= '12'):
                hits.append(('arxiv', ax))
        # 标题：在每个词首位置按各长度查哈希表（原来逐个标题做子串查找，库到 6 万篇后一份库要扫半小时）
        n = norm(text)
        starts = [0] + [i + 1 for i, ch in enumerate(n) if ch == ' ']
        for L in self.title_lens:
            for i in starts:
                k = n[i:i + L]
                w = self.titles.get(k)
                if w:
                    hits.append(('title' if w in self.known else 'title?', f'{w}:{k[:40]}'))
        for y, m in set(self.re_date.findall(text)):
            if f'{y}-{m}' >= self.cutoff:
                hits.append(('date', f'{y}-{m}'))
        return hits

    def hard(self, hits):
        return [h for h in hits if h[0] in self.HARD]


MONTHS = {m: i + 1 for i, ms in enumerate(
    [('jan', 'january'), ('feb', 'february'), ('mar', 'march'), ('apr', 'april'), ('may',), ('jun', 'june'),
     ('jul', 'july'), ('aug', 'august'), ('sep', 'sept', 'september'), ('oct', 'october'), ('nov', 'november'),
     ('dec', 'december')]) for m in ms}
RE_DATES = [
    (re.compile(r'\b(20\d\d)[-/.](0?[1-9]|1[0-2])\b'), lambda m: (int(m.group(1)), int(m.group(2)))),
    (re.compile(r'\b(0?[1-9]|1[0-2])/(20\d\d)\b'), lambda m: (int(m.group(2)), int(m.group(1)))),
    (re.compile(r'\b([A-Za-z]{3,9})\.?\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(20\d\d)\b'),
     lambda m: (int(m.group(2)), MONTHS.get(m.group(1).lower(), 0))),
    (re.compile(r'\b\d{1,2}\s+([A-Za-z]{3,9})\.?,?\s+(20\d\d)\b'),
     lambda m: (int(m.group(2)), MONTHS.get(m.group(1).lower(), 0))),
]


def late_dates(text, cutoff):
    """全文里落在截断月及以后的日期（任何写法）。修订过的版本常留下这种痕迹，例如参考文献的 Accessed 日期。"""
    cut = (int(cutoff[:4]), int(cutoff[5:7]))
    out = set()
    for rx, ym in RE_DATES:
        for m in rx.finditer(text):
            y, mo = ym(m)
            if mo and cut <= (y, mo) <= (2027, 12):
                out.add(m.group(0))
    return sorted(out)


def scan_paths(paths, markers, skip=()):
    """扫目录/文件（.db 用 iterdump 转文本）。返回 {文件: [(类别, 命中)]}，只列有命中的。"""
    out = {}
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += [f for f in glob.glob(f'{p}/**/*', recursive=True) if os.path.isfile(f)]
        elif os.path.isfile(p):
            files.append(p)
    for f in sorted(files):
        if any(s in f for s in skip):
            continue
        if f.endswith('.db'):
            con = sqlite3.connect(f)
            text = '\n'.join(con.iterdump())
            con.close()
        else:
            try:
                text = open(f, encoding='utf-8', errors='ignore').read()
            except Exception:
                continue
        h = markers.find(text)
        if h:
            out[f] = sorted(set(h))
    return out


# ---------------------------------------------------------------- 工作区

def prepare(run, db, markers, template_files=()):
    """建 run/work：库、全文（过扫描）、工具、模板、空的卡池/邮件/裁决目录。返回准备报告。"""
    work = f'{run}/work'
    if os.path.exists(f'{work}/ideas/pool') and glob.glob(f'{work}/ideas/pool/c-*.json'):
        raise RuntimeError(f'{work} 里已经有卡片了：每一轮必须用新的 run 目录')
    for d in ('tools', 'templates', 'fetched', 'out', 'ideas/pool', 'ideas/idea_verdicts',
              'ideas/mail/inbox', 'ideas/mail/cursor', 'ideas/mail/threads'):
        os.makedirs(f'{work}/{d}', exist_ok=True)
    os.makedirs(f'{run}/homes', exist_ok=True)

    # 用 sqlite 的 backup 拷库：全库轮开跑时扩充可能正在写 lit.db（close 的 ingest 整表重建），直接拷文件会拷到写了一半的库
    src = sqlite3.connect(db, timeout=300)
    if hasattr(src, 'backup'):
        dst = sqlite3.connect(f'{work}/lit.db')
        src.backup(dst)
        dst.close()
    else:                                    # 系统 python 3.6 没有 backup
        shutil.copy2(db, f'{work}/lit.db')
    src.close()
    con = sqlite3.connect(f'{work}/lit.db')
    kept, dropped = [], {}
    for w, fp in con.execute('select work_id, fetched_path from works where fetched_path is not null').fetchall():
        # Frozen code can live apart from the existing full-text store.
        material_root = os.environ.get('LITGRAPH_DATA_ROOT', ROOT)
        src = fp if fp.startswith('/') else f'{material_root}/{fp}'
        if os.path.basename(src) != f'{w}.txt' or not os.path.exists(src):
            dropped[w] = '找不到对应全文'
            continue
        # 全文从严：任何命中都剔（含"不确定"作品和截断月以后的日期），因为抓来的可能是截断后修订过的版本
        try:
            text = open(src, encoding='utf-8', errors='ignore').read()
        except OSError:
            dropped[w] = f'全文读不出来（BeeGFS 坏块）：{src}'
            continue
        hits = (markers.find(text) + [('date', d) for d in late_dates(text, markers.cutoff)]) if markers else []
        if hits:
            dropped[w] = f'全文含截断后标记 {sorted(set(hits))[:4]}'
            continue
        shutil.copy2(src, f'{work}/fetched/{w}.txt')
        kept.append(w)
    con.execute('update works set fetched_path = null')
    con.executemany("update works set fetched_path = 'fetched/' || work_id || '.txt' where work_id = ?",
                    [(w,) for w in kept])
    # template_matches 是用全库/泄漏模板算的；versions 里有之后才有的录用日期；其余几张 scout 用不到
    for t in DROP_TABLES:
        con.execute(f'drop table if exists {t}')
    con.commit()
    con.execute('vacuum')
    con.close()

    for src, name in WORK_TOOLS.items():
        shutil.copy2(src, f'{work}/tools/{name}')
    for f in template_files:
        shutil.copy2(f, f'{work}/templates/{os.path.basename(f)}')
    rep = {'db': db, 'fetched_kept': len(kept), 'fetched_dropped': dropped,
           'templates': sorted(os.path.basename(f) for f in template_files)}
    json.dump(rep, open(f'{run}/prepare.json', 'w'), ensure_ascii=False, indent=1)
    return rep


def sync_tools(run):
    """把宿主上的工具重新拷进工作区（续跑时工具可能改过；scout 那边是只读挂载，宿主这边可写）。返回更新了哪些。"""
    changed = []
    for src, name in WORK_TOOLS.items():
        dst = f'{run}/work/tools/{name}'
        if not os.path.exists(dst) or open(src, 'rb').read() != open(dst, 'rb').read():
            shutil.copy2(src, dst)
            changed.append(name)
    return changed


def preflight(run, markers, prompts=()):
    """开跑前：工作区每个文件 + 每份渲染好的提示词都不能有截断后标记（日期只提示）。"""
    work = f'{run}/work'
    leaks = scan_paths([f'{work}/lit.db', f'{work}/fetched', f'{work}/tools', f'{work}/templates',
                        f'{work}/ideas'], markers)
    for name, text in prompts:
        h = markers.find(text)
        if h:
            leaks[f'<提示词 {name}>'] = sorted(set(h))
    hard = {f: markers.hard(h) for f, h in leaks.items()}
    hard = {f: h for f, h in hard.items() if h}
    soft = {f: [x for x in h if x[0] not in markers.HARD] for f, h in leaks.items()}
    soft = {f: h for f, h in soft.items() if h}
    json.dump({'hard': hard, 'soft': soft}, open(f'{run}/preflight.json', 'w'), ensure_ascii=False, indent=1)
    return hard, soft


# ---------------------------------------------------------------- 在隔离里跑 claude

def host_projects(tag, agent):
    return f'{H}/.claude/projects/-litgraph-{tag}-{agent}'


def agent_env():
    """命名空间里的环境。真凭据不进来：API 地址指向本地转发桥，由宿主侧 api_gate.py 换上真凭据。
    代理也指向同一个口子，agent 想开隧道联网会被拒绝并记日志。
    不设 CLAUDE_CODE_SUBPROCESS_ENV_SCRUB：它会把权限模式强制改回 default（实测），而这里的 token 本来就是假的。"""
    local = f'http://127.0.0.1:{PORT}'
    env = {'HOME': '/home/agent', 'USER': 'agent', 'LOGNAME': 'agent', 'SHELL': '/usr/bin/bash',
           'PATH': f'{PY_PREFIX}/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TERM': 'dumb',
           'ANTHROPIC_BASE_URL': local, 'ANTHROPIC_AUTH_TOKEN': 'isolated-no-secret',
           'HTTPS_PROXY': local, 'HTTP_PROXY': local, 'https_proxy': local, 'http_proxy': local,
           'NO_PROXY': '127.0.0.1,localhost', 'no_proxy': '127.0.0.1,localhost',
           'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '1', 'DISABLE_AUTOUPDATER': '1', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1',
           'DISABLE_TELEMETRY': '1', 'DISABLE_ERROR_REPORTING': '1',
           'LITGRAPH_IDEAS': '/work/ideas', 'LITGRAPH_MAIL': '/work/ideas/mail',
           'LITGRAPH_DB': '/work/lit.db', 'LITGRAPH_TEMPLATES': '/work/templates'}
    env.update({k: v for k, v in api_env().items() if k.startswith('CLAUDE_CODE_')})
    return env


def bwrap(run, tag, agent, prog='/opt/claude/claude'):
    """一个 agent 的 bwrap 前缀。凭据走环境变量，不上命令行（/proc/*/cmdline 别人能看到）。"""
    # A repeated author label must never expose another domain's native project history.
    work, home, proj = f'{run}/work', f'{run}/homes/{agent}', f'{run}/projects/{agent}'
    os.makedirs(f'{home}/.claude/projects/-work', exist_ok=True)
    os.makedirs(proj, exist_ok=True)
    sp = f'{home}/.claude/settings.json'
    if not os.path.exists(sp):
        json.dump({'autoMemoryEnabled': False, 'skipDangerousModePermissionPrompt': True,
                   'permissions': {'defaultMode': 'bypassPermissions'}}, open(sp, 'w'), indent=1)
    # AF_UNIX 路径上限 108 字节；路径超长时用 /tmp 下的稳定短路径
    sock_path = f'{run}/gate/{agent}.sock'
    if len(sock_path) > 107:
        import hashlib
        h = hashlib.md5(run.encode()).hexdigest()[:8]
        short_dir = os.path.join(os.environ.get('IDEAX_SCRATCH', os.path.dirname(ROOT) + '/.scratch'), f'g-{h}')
        os.makedirs(short_dir, exist_ok=True)
        sock_path = f'{short_dir}/{agent}.sock'
    launch = (f'{PY_PREFIX}/bin/python3 /opt/gate/uds_fwd.py {PORT} /run/gate/egress.sock & '
              f'for i in $(seq 100); do (exec 3<>/dev/tcp/127.0.0.1/{PORT}) 2>/dev/null && break; sleep 0.1; done; '
              f'exec {prog} "$@"')
    # Only v8 runs have this host-owned marker. Review phases can write notes
    # and mail, but direct JSON writes and cards.py cannot mutate formal cards.
    pool_mount = []
    phase_path = f'{work}/research_phase.json'
    if os.path.exists(phase_path):
        with open(phase_path) as stream:
            phase = json.load(stream)
        if (phase.get('contract_version') in ('multi_agent_v8_phase_separated_20261102',
                                                     'multi_agent_v9_direct_context_20261103')
                and phase.get('phase') in ('debate', 'selection')):
            pool_mount = ['--ro-bind', f'{work}/ideas/pool', '/work/ideas/pool']
    return ['bwrap', '--die-with-parent', '--new-session',
            '--unshare-user', '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--unshare-net',
            '--unshare-cgroup-try', '--hostname', 'sandbox',
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/sbin', '/sbin',
            '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
            '--ro-bind', '/etc', '/etc', '--ro-bind', PY_PREFIX, PY_PREFIX,
            *(['--ro-bind', CLAUDE_BIN, '/opt/claude/claude'] if os.path.isfile(CLAUDE_BIN) else []),
            '--ro-bind', CODEX_DIR, '/opt/codex',
            '--ro-bind', f'{HERE}/uds_fwd.py', '/opt/gate/uds_fwd.py',
            '--dev', '/dev', '--tmpfs', '/dev/shm', '--proc', '/proc', '--tmpfs', '/tmp',
            '--ro-bind', work, '/work',                       # 库、全文、工具、模板都只读
            '--bind', f'{work}/ideas', '/work/ideas',          # 卡池、邮件、裁决
            '--bind', f'{work}/out', '/work/out',              # 命名等任务的产物
            '--bind', home, '/home/agent',
            '--bind', proj, '/home/agent/.claude/projects/-work',
            '--ro-bind', sock_path, '/run/gate/egress.sock',
            *pool_mount,
            '--chdir', '/work',
            '/usr/bin/bash', '-c', launch, os.path.basename(prog)]


def run_claude(run, tag, agent, prompt, session_id, resume=False, per_call=None, model=None,
               tools=TOOLS, timeout=3600):
    args = ['-p', '--output-format', 'json', '--tools', ','.join(tools), '--strict-mcp-config',
            '--permission-mode', 'bypassPermissions']
    if per_call:
        args += ['--max-budget-usd', str(per_call)]
    if model:
        args += ['--model', model]
    args += ['--resume', session_id] if resume else ['--session-id', session_id]
    err = ''
    try:
        p = subprocess.run(bwrap(run, tag, agent) + args, input=prompt, capture_output=True, text=True,
                           env=agent_env(), timeout=timeout)
        err = (p.stderr or '')[-300:]
        r = json.loads(p.stdout)
    except subprocess.TimeoutExpired:
        r = {'is_error': True, 'result': f'timeout after {timeout}s'}
    except Exception as e:
        r = {'is_error': True, 'result': f'{type(e).__name__}: {str(e)[:300]} | stderr: {err}'}
    return {'ok': not r.get('is_error'), 'cost': r.get('total_cost_usd') or 0,
            'tail': str(r.get('result', ''))[-200:], 'session': session_id, 'turns': r.get('num_turns')}


CODEX_CONFIG = """model = "{model}"
model_provider = "gate"
model_reasoning_effort = "{effort}"
web_search = "{web}"

[model_providers.gate]
name = "Configured provider via api_gate"
base_url = "http://127.0.0.1:{port}/v1"
wire_api = "responses"
env_key = "OPENAI_API_KEY"
supports_standalone_web_search = {standalone}
{transport_options}

[analytics]
enabled = false

[features]
plugins = false
remote_plugin = false
recommended_plugins = false
hooks = false
memories = false
multi_agent = false        # codex 新二进制默认带 multi_agent_v1 namespace 工具，会被 api_gate 当服务端工具拒掉
"""


def codex_price():
    e = sub2api_env()
    return tuple(float(e.get(k) or 0) for k in ('SUB2API_PRICE_IN', 'SUB2API_PRICE_CACHED', 'SUB2API_PRICE_OUT'))


def codex_result_events(stdout, thread_id=None):
    """A recovered reconnect is not a failed turn; an absent completion still is."""
    usage, last, err, tid, items, completed = {}, '', '', thread_id, 0, False
    if isinstance(stdout, bytes):
        stdout = stdout.decode(errors='replace')
    for line in (stdout or '').splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        t = e.get('type')
        if t == 'thread.started':
            tid = e.get('thread_id') or tid
        elif t == 'turn.completed':
            completed, err = True, ''
            for k, v in (e.get('usage') or {}).items():
                usage[k] = usage.get(k, 0) + (v or 0)
        elif t == 'turn.started':
            completed = False
        elif t == 'item.completed':
            items += 1
            if (e.get('item') or {}).get('type') == 'agent_message':
                last = e['item'].get('text') or last
        elif t in ('turn.failed', 'error'):
            completed = False
            err = json.dumps(e.get('error') or e, ensure_ascii=False)[:300]
    return usage, last, err, tid, items, completed


def codex_transport_events(stdout):
    """CLI reconnect errors may be absent from native session JSONL; retain their evidence."""
    if isinstance(stdout, bytes):
        stdout = stdout.decode(errors='replace')
    result = {'error_events': [], 'failed_turns': 0, 'completed_turns': 0}
    for line in (stdout or '').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get('type')
        if kind == 'error':
            result['error_events'].append(event)
        elif kind == 'turn.failed':
            result['failed_turns'] += 1
        elif kind == 'turn.completed':
            result['completed_turns'] += 1
    result['clean'] = not result['error_events'] and not result['failed_turns'] and result['completed_turns'] > 0
    return result


def run_codex(run, tag, agent, prompt, thread_id=None, resume=False, model=None, effort='high', web=False, timeout=3600):
    """codex exec 跑在同一个 bwrap 里：模型经 api_gate 转到 sub2api（命名空间里只有假 key）。
    会话由 codex 自己编号（thread_id），续跑用 codex exec resume。联网搜索只在预测轮打开（web=True，闸门也要 --allow-web）。"""
    home = f'{run}/homes/{agent}'
    os.makedirs(f'{home}/.codex', exist_ok=True)
    model = model or 'gpt-6-astra'
    # 自定义提供方要打开 supports_standalone_web_search，web_search="live" 才生效（codex 0.160 实测）
    native_web = web and os.environ.get('LITGRAPH_CODEX_NATIVE_WEB') == '1'
    strict_transport = os.environ.get('LITGRAPH_CODEX_REQUIRE_CLEAN_TRANSPORT', '0') == '1'
    atomic_transport = os.environ.get('LITGRAPH_CODEX_ATOMIC_RESPONSES', '1' if strict_transport else '0') == '1'
    transport_options = []
    if atomic_transport:
        from responses_atomic import CLIENT_IDLE_TIMEOUT_MS
        transport_options.append(f'stream_idle_timeout_ms = {CLIENT_IDLE_TIMEOUT_MS}')
    if strict_transport:
        # The gate retries only unexposed responses. A failed CLI stream disqualifies
        # this experiment, so do not spend more tokens on CLI-level reconnections.
        transport_options += ['request_max_retries = 0', 'stream_max_retries = 0']
    config = CODEX_CONFIG.format(model=model, effort=effort, web='live' if native_web else 'disabled',
                                 standalone='true' if native_web else 'false', port=PORT,
                                 transport_options='\n'.join(transport_options))
    if os.path.isfile(f'{run}/work/ideas/REQUIRE_RESEARCH'):
        # Match the completed full-context v7 single-agent configuration. The
        # CLI's custom-model fallback otherwise compacts at roughly 258k tokens.
        config = 'model_context_window = 1050000\nmodel_auto_compact_token_limit = 900000\n' + config
    open(f'{home}/.codex/config.toml', 'w').write(config)
    args = ['exec', '--json', '--skip-git-repo-check', '-C', '/work', '-s', 'danger-full-access']   # 外面已有 bwrap，codex 自己的沙箱关掉
    args += ['resume', thread_id, '-'] if resume and thread_id else ['-']
    env = dict(agent_env(), CODEX_HOME='/home/agent/.codex', OPENAI_API_KEY='isolated-no-secret',
               HOME='/home/agent', TMPDIR='/tmp', XDG_CACHE_HOME='/home/agent/.cache',
               XDG_CONFIG_HOME='/home/agent/.config', XDG_DATA_HOME='/home/agent/.local/share',
               AI_TOOLS_HOME='/home/agent')
    usage, last, err, tid, items = {}, '', '', thread_id, 0
    stdout, stderr, returncode = '', '', None
    try:
        p = subprocess.run(bwrap(run, tag, agent, prog='/opt/codex/codex') + args, input=prompt, capture_output=True,
                           text=True, env=env, timeout=timeout)
        stdout, stderr, returncode = p.stdout, p.stderr, p.returncode
        usage, last, err, tid, items, completed = codex_result_events(p.stdout, thread_id)
        ok = p.returncode == 0 and completed and not err
        if not ok and not err:
            err = (p.stderr or '')[-300:] or 'turn.completed missing'
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or '', exc.stderr or ''
        usage, last, err, tid, items, _ = codex_result_events(exc.stdout, thread_id)
        ok, err = False, f'timeout after {timeout}s'
    transport = codex_transport_events(stdout)
    evidence = f'{run}/evidence/codex_calls/{agent}-{time.time_ns()}'
    os.makedirs(os.path.dirname(evidence), exist_ok=True)
    for suffix, data in (('.events.jsonl', stdout), ('.stderr.log', stderr)):
        with open(evidence + suffix, 'w') as stream:
            stream.write(data.decode(errors='replace') if isinstance(data, bytes) else data or '')
    with open(evidence + '.transport.json', 'w') as stream:
        json.dump(dict(transport, returncode=returncode), stream, ensure_ascii=False)
    if ok and os.environ.get('LITGRAPH_CODEX_REQUIRE_CLEAN_TRANSPORT') == '1' and not transport['clean']:
        ok, err = False, 'CLI transport error/reconnect occurred; strict run requires a fresh attempt'
    pin, pcached, pout = codex_price()
    cached = usage.get('cached_input_tokens', 0)
    cost = ((usage.get('input_tokens', 0) - cached) * pin + cached * pcached + usage.get('output_tokens', 0) * pout) / 1e6
    return {'ok': ok, 'cost': cost, 'tail': (last if ok else err or last)[-300:],
            'error': err if not ok else None, 'session': tid, 'turns': items, 'usage': usage,
            'transport': transport, 'evidence_events': evidence + '.events.jsonl'}


def codex_session_files(run, agent):
    return sorted(glob.glob(f'{run}/homes/{agent}/.codex/sessions/**/*.jsonl', recursive=True))


# ---------------------------------------------------------------- 跑完后的审计

def session_files(tag, agent):
    return sorted(glob.glob(f'{host_projects(tag, agent)}/*.jsonl'))


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, list):
        for y in x:
            yield from _strings(y)
    elif isinstance(x, dict):
        for k in ('text', 'output', 'content'):
            if k in x:
                yield from _strings(x[k])


def audit_codex_file(f, markers):
    """codex 会话记录：agent 看得到的（user/developer 消息、工具输出）扫截断后标记；它执行的（工具调用的 input/arguments）查可疑命令。"""
    hits, sus = [], []
    for n, line in enumerate(open(f)):
        try:
            e = json.loads(line)
        except Exception:
            continue
        p = e.get('payload') or {}
        if e.get('type') != 'response_item':
            continue
        t = p.get('type')
        if t in ('function_call', 'custom_tool_call', 'local_shell_call'):
            cmd = str(p.get('arguments') or p.get('input') or p.get('action') or '')
            if SUSPICIOUS.search(cmd):
                sus.append((os.path.basename(f), n, cmd[:200]))
        elif t in ('function_call_output', 'custom_tool_call_output') or (t == 'message' and p.get('role') in ('user', 'developer')):
            for txt in _strings(p.get('output') if 'output' in p else p.get('content')):
                hits += [(os.path.basename(f), n, k, v) for k, v in markers.hard(markers.find(txt))]
    return hits, sus


def audit(run, tag, agents, markers):
    """每个 agent：会话里能看到的内容（提示词 + 工具返回）有没有截断后标记；闸门有没有拒绝过它的请求。"""
    deny = defaultdict(list)
    lp = f'{run}/gate/egress.log'
    if os.path.exists(lp):
        for line in open(lp):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get('allowed') is False:
                deny[e.get('agent', '?')].append(f"{e.get('target')}（{e.get('why', '')}）")
    rep = {}
    for a in agents:
        hits, sus = [], []
        for f in session_files(tag, a):
            for n, line in enumerate(open(f)):
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                m = e.get('message') or {}
                if m.get('role') == 'assistant' and isinstance(m.get('content'), list):
                    for x in m['content']:
                        if x.get('type') == 'tool_use':
                            cmd = json.dumps(x.get('input'), ensure_ascii=False)
                            if SUSPICIOUS.search(cmd):
                                sus.append((os.path.basename(f), n, cmd[:200]))
                if m.get('role') != 'user':
                    continue
                c = m.get('content')
                parts = c if isinstance(c, list) else [{'type': 'text', 'text': str(c)}]
                for x in parts:
                    if x.get('type') == 'tool_result':
                        y = x.get('content')
                        t = ' '.join(z.get('text', '') for z in y if isinstance(z, dict)) if isinstance(y, list) else str(y)
                    elif x.get('type') == 'text':
                        t = x.get('text', '')
                    else:
                        continue
                    hits += [(os.path.basename(f), n, k, v) for k, v in markers.hard(markers.find(t))]
        for f in codex_session_files(run, a):          # codex 跑的 agent：会话记录在它自己的 CODEX_HOME 下
            h, su = audit_codex_file(f, markers)
            hits += h
            sus += su
        rep[a] = {'leaks': hits[:50], 'n_leaks': len(hits), 'egress_denied': deny.get(a, [])[:50],
                  'suspicious_commands': sus[:50], 'clean': not hits and not deny.get(a)}
    json.dump(rep, open(f'{run}/audit.json', 'w'), ensure_ascii=False, indent=1)
    return rep
