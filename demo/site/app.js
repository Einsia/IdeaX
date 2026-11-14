'use strict';

const $ = (s) => document.querySelector(s);
const stages = [
  ['Problem', 'Start with a question worth asking.'],
  ['Insights', 'Connect useful knowledge across the literature.'],
  ['Novelty check', 'Let previous work change the candidate.'],
  ['Idea Card', 'Make the mechanism and its limits explicit.'],
  ['Develop', 'Turn the proposal into a testable research plan.'],
];
const state = {catalog: null, caseId: 'residency', stage: 0, playing: false, frame: null, toastTimer: null, brief: null, document: null, documentRequest: 0,
  elapsed: 0, lastTick: 0, speed: 1, cue: -1, cues: [], duration: 0, replayStarted: false, replayComplete: false};
const escapeHTML = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeURL = (value) => {try {const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) ? u.href : '#';} catch {return '#';}};
const link = (url, text, cls='') => `<a class="${cls}" href="${escapeHTML(safeURL(url))}" target="_blank" rel="noopener noreferrer">${escapeHTML(text)}</a>`;
const currentCase = () => state.catalog.cases.find((c) => c.id === state.caseId);

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').classList.add('visible');
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 3500);
}
async function copy(text) {
  try {await navigator.clipboard.writeText(text); toast('Copied to clipboard.');}
  catch {
    const box=document.createElement('textarea'); box.value=text; document.body.append(box); box.select();
    const success=document.execCommand('copy'); box.remove();
    toast(success ? 'Copied to clipboard.' : 'Clipboard unavailable. Use the download option instead.');
  }
}
function download(filename, content, mime='text/plain;charset=utf-8') {
  const url=URL.createObjectURL(new Blob([content], {type:mime}));
  const a=document.createElement('a'); a.href=url; a.download=filename; document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function storeBrief() {
  const value={case_id:state.caseId,domain:$('#domain').value,question:$('#question').value,critique:$('#critique').value,
    access:$('input[name=access]:checked').value,include_reference:$('#include-reference').checked};
  try {localStorage.setItem('ideax.demo.brief.v1', JSON.stringify(value));} catch {}
}
function fillBrief(c, restore=false) {
  let saved=null;
  if (restore) {try {saved=JSON.parse(localStorage.getItem('ideax.demo.brief.v1'));} catch {}}
  if (saved && saved.case_id===c.id && state.catalog.domains.some((d) => d.id===saved.domain)) {
    $('#domain').value=saved.domain;
    $('#question').value=typeof saved.question==='string' ? saved.question.slice(0,4000) : c.question;
    $('#critique').value=typeof saved.critique==='string' ? saved.critique.slice(0,4000) : '';
    $(`input[name=access][value=${saved.access==='full' ? 'full' : 'api'}]`).checked=true;
    $('#include-reference').checked=saved.include_reference!==false;
  } else {
    $('#domain').value=c.domain; $('#question').value=c.question; $('#critique').value='';
    $('#include-reference').checked=true;
  }
}
function sourceActions(c) {
  return '<div class="source-actions"><button class="button small" data-document="PROPOSAL">Read the complete case ↗</button><button class="button small" data-document="PROCESS">Explore the full process ↗</button></div>';
}
function section(title, text) {
  return `<section class="panel-section"><h3>${escapeHTML(title)}</h3><p>${escapeHTML(text)}</p></section>`;
}
function renderPanel() {
  const c=currentCase(); let html='';
  if (state.stage===0) {
    html=`<p class="panel-kicker">01 / FIND THE PROBLEM</p><h3 class="panel-title">${escapeHTML(c.topic)}<br>has an open question.</h3><p class="panel-copy">${escapeHTML(c.problem)}</p><blockquote class="question-box">${escapeHTML(c.question)}</blockquote><div class="connection-strip"><span aria-hidden="true">↳</span><p>A problem in the library is a starting point. The agent still needs to check what is already solved and what remains.</p></div>${sourceActions(c)}`;
  } else if (state.stage===1) {
    html=`<p class="panel-kicker">02 / CONNECT THE INSIGHTS</p><h3 class="panel-title">A useful connection,<br>with the evidence attached.</h3>`;
    html+=c.insights.map((i,n)=>`<button class="evidence-card" data-insight="${n}" aria-label="Inspect source: ${escapeHTML(i.title)}"><span class="evidence-kind">${i.id.includes('-P') ? 'PROBLEM' : 'INSIGHT'} · LITGRAPH <span aria-hidden="true">↗</span></span><h3>${escapeHTML(i.title)}</h3><p>${escapeHTML(i.text)}</p><span class="evidence-id">${escapeHTML(i.id)}</span></button>`).join('');
    html+=`<div class="reasoning-bridge"><p class="eyebrow">THE DESIGN MOVE</p>${escapeHTML(c.connection)}</div>`;
  } else if (state.stage===2) {
    html=`<p class="panel-kicker">03 / CHECK THE NEAREST WORK</p><h3 class="panel-title">New to us<br>isn’t necessarily new.</h3><div class="review-row"><h3>INITIAL CANDIDATE</h3><p>${escapeHTML(c.initial)}</p></div><div class="review-row"><h3>WHAT THE LITERATURE CHANGED</h3><p>${escapeHTML(c.finding)}</p>${c.neighbors.map(p=>link(p.url,p.title+' ↗','paper-link')).join('')}</div><div class="review-row revision"><h3>REVISED CONTRIBUTION</h3><p>${escapeHTML(c.revision)}</p></div><div class="note-box">This is the recorded revision, not a new novelty verdict. Remaining overlap and reading limits are preserved in the source record.</div>${sourceActions(c)}`;
  } else if (state.stage===3) {
    html=`<div class="idea-card-heading"><span>IDEA CARD / ${escapeHTML(c.number)}</span><span class="rule"></span><span>PROPOSAL</span></div><h3 class="panel-title">${escapeHTML(c.card_title)}</h3>`;
    html+=section('The question',c.question)+section('Why this idea',c.connection)+section('Core mechanism',c.mechanism);
    html+=`<div class="equation">${escapeHTML(c.equation)}</div>`;
    html+=section('Remaining contribution',c.contribution)+section('How to test it',c.validation)+section('What would make it fail',c.failure);
    html+=`<div class="source-actions"><button class="button dark small" data-document="PROPOSAL">Read the complete case ↗</button><button class="button small" id="download-card">Download overview ↓</button><button class="button small" data-document="PROCESS">Full process ↗</button></div><div class="note-box">The overview above is a reading guide. Open the complete original case for every equation, implementation detail, prior-work comparison, and reference.</div>`;
  } else {
    html=`<p class="panel-kicker">05 / DEVELOP THE PROPOSAL</p><h3 class="panel-title">An idea is a beginning.</h3><p class="panel-copy">A Research Blueprint makes the motivation, evidence, design decisions, and tests explicit. Here is the development path described in this source proposal.</p><ol class="blueprint-list">${c.blueprint.map(t=>`<li>${escapeHTML(t)}</li>`).join('')}</ol><div class="note-box">${escapeHTML(c.blueprint_note)}</div><div class="reasoning-bridge"><p class="eyebrow">WHERE YOU COME IN</p>Challenge an assumption, add a constraint, or ask a different question. Export your research brief and let a local agent explore the next version.</div>${sourceActions(c)}`;
  }
  $('#stage-panel').innerHTML=`<div class="panel-inner">${html}</div>`;
  $('#stage-panel').setAttribute('aria-labelledby',`stage-${state.stage}`);
  $('#stage-summary').textContent=`Step ${state.stage+1} of 5 · ${stages[state.stage][1]}`;
  $('#next-stage').innerHTML=state.stage===4 ? 'Prepare my research brief <span aria-hidden="true">↗</span>' : `Next: ${escapeHTML(stages[state.stage+1][0])} <span aria-hidden="true">→</span>`;
  document.querySelectorAll('.stage-tab').forEach((b,n)=>{b.setAttribute('aria-selected',String(n===state.stage));b.tabIndex=n===state.stage?0:-1;});
  document.querySelectorAll('[data-insight]').forEach((b)=>b.addEventListener('click',()=>showInsight(Number(b.dataset.insight))));
  document.querySelectorAll('[data-document]').forEach((b)=>b.addEventListener('click',()=>showDocument(b.dataset.document)));
  $('#download-card')?.addEventListener('click',()=>download(`ideax-${c.id}-card.md`,cardMarkdown(c)));
  prepareWalkthrough(c);
}
function markdownRenderer() {
  const md=window.markdownit({html:false,linkify:false,typographer:false});
  md.validateLink=(url)=>/^https?:\/\//i.test(url);
  md.renderer.rules.link_open=(tokens,idx,options,env,self)=>{tokens[idx].attrSet('target','_blank');tokens[idx].attrSet('rel','noopener noreferrer');return self.renderToken(tokens,idx,options);};
  md.block.ruler.before('fence','math_block',(s,start,end,silent)=>{
    const first=s.src.slice(s.bMarks[start]+s.tShift[start],s.eMarks[start]);
    if(!first.startsWith('$$'))return false;
    let content=first.slice(2),next=start+1;
    if(content.includes('$$'))content=content.slice(0,content.indexOf('$$'));
    else {
      let closed=false;
      for(;next<end;next++){
        const line=s.src.slice(s.bMarks[next]+s.tShift[next],s.eMarks[next]);
        if(line.includes('$$')){content+='\n'+line.slice(0,line.indexOf('$$'));next++;closed=true;break;}
        content+='\n'+line;
      }
      if(!closed)return false;
    }
    if(silent)return true;
    const t=s.push('math_block','',0);t.content=content.trim();t.map=[start,next];s.line=next;return true;
  });
  md.inline.ruler.before('escape','math_inline',(s,silent)=>{
    if(s.src[s.pos]!=='$'||s.src[s.pos+1]==='$')return false;
    let end=s.pos+1;
    while((end=s.src.indexOf('$',end))!==-1&&s.src[end-1]==='\\')end++;
    if(end<0||end===s.pos+1)return false;
    if(!silent){const t=s.push('math_inline','',0);t.content=s.src.slice(s.pos+1,end);}
    s.pos=end+1;return true;
  });
  for(const kind of ['math_block','math_inline'])md.renderer.rules[kind]=(tokens,i)=>window.katex.renderToString(tokens[i].content,{displayMode:kind==='math_block',throwOnError:false,trust:false,strict:'ignore',maxExpand:1000});
  return md;
}
async function showDocument(kind) {
  if(!['PROPOSAL','PROCESS'].includes(kind))return;
  stopReplay();const c=currentCase(),request=++state.documentRequest;
  state.document=null;
  $('#document-title').textContent=c.card_title;
  $('#document-caption').textContent=kind==='PROPOSAL'?'Complete original proposal: motivation, equations, implementation, previous work, validation, and limitations.':'Complete recorded exploration: source queries, reading depth, candidate revisions, and request records. This is not a private reasoning transcript.';
  $('#document-body').innerHTML='<p>Loading the complete source…</p>';
  $('#download-original').disabled=true;
  $('#original-on-github').href=kind==='PROPOSAL'?c.proposal_url:c.process_url;
  $('#document-dialog').showModal();
  try {
    const response=await fetch(`sources/${encodeURIComponent(c.id)}/${kind}.md`);
    if(!response.ok)throw new Error('Source unavailable');
    const text=await response.text();
    if(request!==state.documentRequest)return;
    state.document={name:`ideax-${c.id}-${kind.toLowerCase()}.md`,text};
    $('#document-body').innerHTML=markdownRenderer().render(text);
    $('#download-original').disabled=false;
    $('#document-dialog').scrollTop=0;
  } catch {
    if(request===state.documentRequest)$('#document-body').innerHTML='<p>The local copy could not load. Use “Open on GitHub” to read the complete original source.</p>';
  }
}
function cardMarkdown(c) {
  return `# ${c.card_title}\n\nRecorded proposal · ${c.recorded_on}\n\n${[
    ['Research question',c.question],['Problem',c.problem],['Problem → insight → mechanism',c.connection],
    ['Mechanism',c.mechanism+'\n\n'+c.equation],['Previous-work check',c.finding],['Remaining contribution',c.contribution],
    ['Validation',c.validation],['Failure conditions',c.failure],['Status','Research proposal; no new model or hardware experiments reported.'],
  ].map(([h,t])=>`## ${h}\n\n${t}`).join('\n\n')}\n\n## Sources\n\n${c.neighbors.map(p=>`- [${p.title}](${p.url})`).join('\n')}\n\n[Full proposal](${c.proposal_url}) · [Process record](${c.process_url})\n`;
}
function showInsight(index) {
  stopReplay();
  const c=currentCase(), i=c.insights[index];
  $('#source-title').textContent=i.title;
  $('#source-detail').innerHTML=`<span class="evidence-id">${escapeHTML(i.id)}</span><p>${escapeHTML(i.text)}</p><div class="note-box">This is an editorial summary of its role in the recorded exploration. The source entry and process record contain the original wording, scope, and reading-depth annotations.</div><h3 class="panel-section">Nearby papers in this case</h3>${c.neighbors.map(p=>link(p.url,p.title+' ↗','paper-link')).join('')}${link('https://kevin-wake-stuffed-anti.trycloudflare.com/api/v1/entries/'+encodeURIComponent(i.id),'Read the LitGraph entry ↗','button small')} ${link(c.process_url,'Inspect the full record ↗','button small')}<p class="small-note">The public LitGraph endpoint uses a temporary tunnel. The archived process record remains available if that endpoint changes.</p>`;
  $('#source-dialog').showModal();
}
function updateHash() {
  const params=new URLSearchParams({case:state.caseId,step:String(state.stage+1)});
  history.replaceState(null,'','#'+params.toString());
}
function prepareWalkthrough(c) {
  state.cues=[]; state.cue=-1; state.elapsed=0; state.duration=0; state.replayComplete=false;
  const add=(element,title,note,duration=4800)=>{
    if(!element)return;
    element.classList.add('walkthrough-target');
    state.cues.push({element,title,note,start:state.duration,end:state.duration+duration});
    state.duration+=duration;
  };
  const panel=$('#stage-panel');
  const find=(s)=>panel.querySelector(s);
  if(state.stage===0) {
    add(find('.panel-copy'),'Find the unresolved problem',`Start with the limitation in ${c.topic.toLowerCase()}.`);
    add(find('.question-box'),'Turn the gap into a research question','This question gives the literature exploration a direction.');
  } else if(state.stage===1) {
    panel.querySelectorAll('.evidence-card').forEach((el,i)=>add(el,`Read ${c.insights[i].id.includes('-P')?'problem':'insight'} ${i+1} of ${c.insights.length}`,c.insights[i].title));
    add(find('.reasoning-bridge'),'Connect the insights to a design choice','The contribution starts with how these observations fit together.',5600);
  } else if(state.stage===2) {
    const rows=panel.querySelectorAll('.review-row');
    add(rows[0],'Start with the initial candidate','An appealing starting point still needs a close prior-work check.');
    add(rows[1],'Let the nearest papers challenge it','Compare the actual mechanism and conclusions, then identify the overlap.',6200);
    add(rows[2],'Revise the remaining contribution','See what changes after that comparison. This is the recorded revision.',5600);
  } else if(state.stage===3) {
    const sections=panel.querySelectorAll('.panel-section');
    add(sections[1],'Explain why this idea follows','Connect the literature observations to the proposed intervention.');
    add(sections[2],'Make the core mechanism explicit','Identify what the proposal actually changes and why it could work.',6200);
    add(find('.equation'),'Make the design concrete','The compact expression summarizes the proposed operation.');
    add(sections[3],'State the remaining contribution','Keep the claim distinct from the nearest existing work.');
    add(sections[4],'Describe a discriminating test','Ask what observation would separate this explanation from alternatives.');
    add(sections[5],'Keep the failure conditions visible','A useful proposal states what would make its central claim fail.');
  } else {
    const steps=panel.querySelectorAll('.blueprint-list li');
    steps.forEach((el,i)=>add(el,`Develop the plan · ${i+1} of ${steps.length}`,'Follow the development steps recorded in the complete proposal.'));
    add(find('.reasoning-bridge'),'Your turn: challenge the proposal','Add a question or critique, then export your brief for a local research run.',5600);
  }
  $('#stage-panel').classList.remove('walkthrough-guided');
  updatePlayer();
}
function followElement(element) {
  if(!state.playing||!element)return;
  const guide=$('#walkthrough-guide').getBoundingClientRect(),rect=element.getBoundingClientRect();
  const top=Math.max(16,guide.height+24);
  if(rect.top<top||rect.bottom>innerHeight-32) {
    const y=rect.top+scrollY-top;
    window.scrollTo({top:Math.max(0,y),behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
  }
}
function updatePlayer() {
  const guide=$('#walkthrough-guide'),active=state.playing||state.replayStarted;
  guide.classList.toggle('is-playing',state.playing);
  guide.classList.toggle('has-started',active);
  $('#play-replay').setAttribute('aria-pressed',String(state.playing));
  $('#play-replay').innerHTML=state.playing?'<span aria-hidden="true">Ⅱ</span> Pause':state.replayComplete?'<span aria-hidden="true">↺</span> Replay':state.replayStarted?'<span aria-hidden="true">▶</span> Resume':'<span aria-hidden="true">▶</span> Play walkthrough';
  $('#walkthrough-status').textContent=state.replayComplete?'Complete · Your turn to explore':state.playing?'Playing · Recorded case':state.replayStarted?'Paused · Read at your pace':'Ready · Recorded case';
  if(!active) {
    $('#walkthrough-focus').textContent='Follow the connections.';
    $('#walkthrough-note').textContent='Play to follow the question, evidence, and design choices in this case.';
  } else if(state.replayComplete) {
    $('#walkthrough-focus').textContent='From a literature question to a research proposal.';
    $('#walkthrough-note').textContent='Explore the complete case, or add your own question and critique.';
  }
  $('#skip-replay').textContent=state.stage===4?'Prepare my brief →':'Next step →';
  updatePlayback();
}
function updatePlayback() {
  const fraction=state.duration?Math.min(1,state.elapsed/state.duration):0;
  $('#walkthrough-fill').style.transform=`scaleX(${fraction})`;
  $('#walkthrough-progress').setAttribute('aria-valuenow',String(Math.round(fraction*100)));
  const remaining=Math.ceil((state.duration-state.elapsed)/state.speed/1000);
  $('#walkthrough-time').textContent=state.replayComplete?'5 steps explored':`Step ${state.stage+1} of 5 · ${remaining}s ${state.stage===4?'to finish':'to next step'}`;
  document.querySelectorAll('.stage-tab').forEach((b,n)=>{
    b.style.setProperty('--step-progress',n<state.stage?'100%':n===state.stage?`${fraction*100}%`:'0%');
  });
  if(!state.replayStarted&&!state.playing)return;
  const next=state.cues.findIndex(c=>state.elapsed<c.end);
  const index=next===-1?state.cues.length-1:next;
  const current=state.cues[index];
  if(current)current.element.style.setProperty('--cue-progress',`${Math.min(100,(state.elapsed-current.start)/(current.end-current.start)*100)}%`);
  if(state.replayComplete||index===state.cue)return;
  state.cue=index;
  $('#stage-panel').classList.add('walkthrough-guided');
  state.cues.forEach((c,i)=>{
    c.element.classList.toggle('walkthrough-seen',i<index);
    c.element.classList.toggle('walkthrough-focus',i===index);
    c.element.classList.toggle('walkthrough-ahead',i>index);
  });
  const cue=state.cues[index];
  $('#walkthrough-focus').textContent=`${index+1}/${state.cues.length} · ${cue.title}`;
  $('#walkthrough-note').textContent=cue.note;
  followElement(cue.element);
}
function accumulatePlayback() {
  if(!state.playing)return;
  const now=performance.now();
  state.elapsed=Math.min(state.duration,state.elapsed+(now-state.lastTick)*state.speed);
  state.lastTick=now;
}
function stopReplay() {
  accumulatePlayback();
  cancelAnimationFrame(state.frame);state.frame=null;state.playing=false;
  updatePlayer();
}
function setStage(n, continuePlaying=false) {
  const resume=continuePlaying&&state.playing;
  stopReplay();state.replayStarted=resume;
  state.stage=Math.max(0,Math.min(4,n));renderPanel();updateHash();
  if(resume)startPlayback();
}
function playbackTick() {
  if(!state.playing)return;
  accumulatePlayback();
  if(state.elapsed>=state.duration) {
    if(state.stage<4){setStage(state.stage+1,true);return;}
    state.replayComplete=true;state.playing=false;state.frame=null;
    $('#stage-panel').classList.remove('walkthrough-guided');
    state.cues.forEach(c=>c.element.classList.remove('walkthrough-focus','walkthrough-ahead'));
    updatePlayer();return;
  }
  updatePlayback();state.frame=requestAnimationFrame(playbackTick);
}
function startPlayback() {
  state.playing=true;state.replayStarted=true;state.lastTick=performance.now();
  updatePlayer();followElement(state.cues[state.cue]?.element);
  state.frame=requestAnimationFrame(playbackTick);
}
function play() {
  if(state.playing){stopReplay();return;}
  if(state.replayComplete)setStage(0);
  startPlayback();
}
function selectCase(id, restore=false, stage=0) {
  if(!state.catalog.cases.some(c=>c.id===id))return;
  stopReplay();state.replayStarted=false;state.caseId=id;state.stage=stage;
  const c=currentCase();
  $('#case-title').textContent=c.title;$('#case-perspective').textContent=c.perspective.toUpperCase();$('#case-topic').textContent=c.topic;
  document.querySelectorAll('.case-choice').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.case===id)));
  fillBrief(c,restore);renderPanel();updateHash();
}
function buildBrief() {
  const c=currentCase();
  const brief={schema:'ideax.research-brief.v1',domain:$('#domain').value,access:$('input[name=access]:checked').value,
    question:$('#question').value.trim(),critique:$('#critique').value.trim()};
  if($('#include-reference').checked)brief.reference_case={id:c.id,title:c.card_title,question:c.question,
    mechanism:c.mechanism,previous_work_check:c.finding,remaining_contribution:c.contribution,
    source_url:c.proposal_url,process_url:c.process_url,source_sha256:c.source_sha256.proposal};
  return brief;
}
function briefAppendix(brief) {
  let text=`\n\n## 用户研究简报（本次自定义任务）\n研究问题：${brief.question || '围绕所选领域自主探索。'}\n用户的 critique / 约束：${brief.critique || '未指定额外约束。'}\n`;
  if(brief.reference_case)text+='\n用户明确提供的起点案例（尚未验证，不得将其当作新检索结果；请围绕核心贡献作实质改进，并重新核查前作）：\n'+JSON.stringify(brief.reference_case,null,2)+'\n';
  return text+'\n仍须交付五个相互有实质区别的完整 idea。区分来源事实、用户提供的观点和新假设，不要只重述起点案例。记录用户反馈如何影响选题或机制。本次为自定义探索，不是原论文 benchmark 的复现。\n';
}
function renderBrief() {
  state.brief=buildBrief(); storeBrief();
  const d=state.catalog.domains.find(d=>d.id===state.brief.domain);
  $('#brief-summary').textContent=`${d.name} · Single ${state.brief.access==='full'?'Full':'API'} · Five complete Idea Cards`;
  $('#run-command').textContent='git clone https://github.com/Einsia/IdeaX.git\ncd IdeaX\n# Install dependencies and load your configuration (see running guide).\n# Place the downloaded ideax-request.json here.\npython demo/run_local.py --request ideax-request.json --out runs/my-idea\n\n# Start real generation after inspecting the prepared request:\npython demo/run_local.py --request ideax-request.json --out runs/my-idea --run';
  let prompt=state.catalog.api_prompt.replace('【在这里填写你希望研究的领域】',d.name);
  if(state.brief.access==='full') {
    const marker='本轮不预先注入领域 insights/problems，也不要求先获取全域材料。';
    prompt=prompt.replace(marker,'本轮使用 Full 访问方式。开始构思前，请通过 LitGraph 核对主领域 ID，读取该领域全部 insights 和 problems（完整分页），核验总数并实际阅读。');
    prompt=prompt.replace('本轮无需强制全量读取领域。','本轮必须完整读取并核验主领域全部 insights/problems。');
    prompt=prompt.replace('不应把全量读取作为强制前置步骤','主领域的全量读取是本轮的强制前置步骤');
    prompt=prompt.replace('额外资源：只读 live LitGraph API（本轮无预注入领域材料，按需主动检索条目和原始证据）。','额外资源：只读 live LitGraph API；主领域须先完成全量读取，跨领域按需探索。');
  }
  $('#prompt-preview').value=prompt+briefAppendix(state.brief);
  $('#prompt-note').textContent=state.brief.access==='full' ? 'This portable Full adaptation asks your agent to fetch and read all domain insights/problems. The repository runner instead injects its frozen complete snapshot. This adaptation has not been separately benchmarked.' : 'The complete Single API prompt includes the public LitGraph interface, six research perspectives, prior-work checks, and your brief. Your agent needs HTTP access and its own model configuration.';
}
function openBrief(event) {event?.preventDefault();stopReplay();renderBrief();$('#brief-dialog').showModal();}
function switchInstructionTab(which) {
  for(const name of ['local','prompt']) {
    $(`#${name}-tab`).setAttribute('aria-selected',String(name===which));
    $(`#${name}-instructions`).hidden=name!==which;
  }
}
function installEvents() {
  $('#play-replay').addEventListener('click',play);
  $('#reset-replay').addEventListener('click',()=>setStage(0,state.playing));
  $('#skip-replay').addEventListener('click',()=>state.stage===4?openBrief():setStage(state.stage+1,state.playing));
  $('#replay-speed').addEventListener('change',()=>{accumulatePlayback();state.speed=Number($('#replay-speed').value);updatePlayer();});
  $('#next-stage').addEventListener('click',()=>state.stage===4?openBrief():setStage(state.stage+1));
  $('#brief-form').addEventListener('submit',openBrief);
  $('#brief-form').addEventListener('focusin',()=>{if(state.playing)stopReplay();});
  $('#brief-form').addEventListener('input',storeBrief);
  $('#brief-form').addEventListener('change',storeBrief);
  $('#suggest-critique').addEventListener('click',()=>{$('#critique').value=currentCase().critique;storeBrief();$('#critique').focus();});
  $('#reset-brief').addEventListener('click',()=>{fillBrief(currentCase());storeBrief();toast('Brief reset to this case.');});
  for(const id of ['open-local','open-local-bottom'])$(`#${id}`).addEventListener('click',openBrief);
  $('#share-case').addEventListener('click',()=>copy(location.href));
  $('#copy-command').addEventListener('click',()=>copy($('#run-command').textContent));
  $('#download-request').addEventListener('click',()=>download('ideax-request.json',JSON.stringify(state.brief,null,2)+'\n','application/json'));
  $('#copy-prompt').addEventListener('click',()=>copy($('#prompt-preview').value));
  $('#download-prompt').addEventListener('click',()=>download('ideax-prompt.md',$('#prompt-preview').value));
  $('#download-original').addEventListener('click',()=>{if(state.document)download(state.document.name,state.document.text);});
  $('#local-tab').addEventListener('click',()=>switchInstructionTab('local'));
  $('#prompt-tab').addEventListener('click',()=>switchInstructionTab('prompt'));
  document.querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',()=>document.getElementById(b.dataset.close).close()));
  document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',event=>{if(event.target===d){const r=d.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)d.close();}}));
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stopReplay();});
  window.addEventListener('hashchange',()=>{const p=new URLSearchParams(location.hash.slice(1));if(state.catalog.cases.some(c=>c.id===p.get('case')))selectCase(p.get('case'),false,Math.max(0,Math.min(4,(Number(p.get('step'))||1)-1)));});
}
async function init() {
  try {
    const response=await fetch('catalog.json'); if(!response.ok)throw new Error('Unable to load the case library.');
    state.catalog=await response.json();
    $('#case-list').innerHTML=state.catalog.cases.map(c=>`<button class="case-choice" data-case="${escapeHTML(c.id)}" aria-pressed="false"><span class="case-number">${escapeHTML(c.number)}</span><span><strong>${escapeHTML(c.perspective)}</strong><small>${escapeHTML(c.topic)}</small></span></button>`).join('');
    document.querySelectorAll('.case-choice').forEach(b=>b.addEventListener('click',()=>selectCase(b.dataset.case)));
    $('#stage-tabs').innerHTML=stages.map(([name],n)=>`<button class="stage-tab" id="stage-${n}" role="tab" aria-controls="stage-panel" aria-selected="false" data-stage="${n}"><span class="step-index">${n+1}</span>${escapeHTML(name)}</button>`).join('');
    document.querySelectorAll('.stage-tab').forEach(b=>{
      b.addEventListener('click',()=>setStage(Number(b.dataset.stage)));
      b.addEventListener('keydown',e=>{if(['ArrowRight','ArrowLeft','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?4:(state.stage+(e.key==='ArrowRight'?1:4))%5;setStage(n);$(`#stage-${n}`).focus();}});
    });
    $('#domain').innerHTML=state.catalog.domains.map(d=>`<option value="${escapeHTML(d.id)}">${escapeHTML(d.name)} · ${escapeHTML(d.id)}</option>`).join('');
    const p=new URLSearchParams(location.hash.slice(1));const id=state.catalog.cases.some(c=>c.id===p.get('case'))?p.get('case'):state.catalog.default_case;
    selectCase(id,true,Math.max(0,Math.min(4,(Number(p.get('step'))||1)-1)));installEvents();
  } catch(error) {
    $('#case-title').textContent='The case library could not load.';
    $('#stage-panel').innerHTML='<p class="loading-error">Please refresh the page. If you opened the file directly, start it with <code>python demo/serve.py</code>. The original cases are also available on GitHub.</p>';
    for(const b of document.querySelectorAll('button'))b.disabled=true;
    console.error(error);
  }
}
init();
