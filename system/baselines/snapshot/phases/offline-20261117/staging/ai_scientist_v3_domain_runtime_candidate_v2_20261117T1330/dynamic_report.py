"""Interpret all registered methods; never mutate jobs or worker handles."""
import collections,datetime,json,os
from pathlib import Path
from contracts import P,METHOD,read

def summarize(state,methods,root=P):
 rows=[];warnings=[]
 for method,spec in methods.items():
  jobs=[j for j in state['jobs'].values() if j['method']==method]
  gen=[j for j in jobs if j['kind']=='generation'];groups={}
  for job in gen:
   scope='current'
   if method=='sciagents':
    path=root/'runs'/method/job['domain']/f"slot-{job['slot']:02}"/'result.json'
    try:result=read(path) if path.exists() else {}
    except (OSError,ValueError):result={};warnings.append('Unreadable result: '+str(path))
    actual=result.get('comparison_scope')
    scope='legacy-original-graph-transfer' if actual and actual!='matched-domain-abstract-graph' or (not actual and job['domain']=='agent-memory' and job['slot']==1 and job.get('launches',0)>0) else 'matched-domain-abstract-graph'
   elif method=='ai_researcher':scope='retired-original-history'
   elif method==METHOD:scope='additional-native-ideation-not-main'
   elif method=='insightagents':scope=spec.get('comparison_scope','new-native-method')
   groups.setdefault(scope,[]).append(job)
  if method=='sciagents':groups.setdefault('matched-domain-abstract-graph',[])
  breakdown={}
  for scope,members in groups.items():
   identities={(j['domain'],j['slot']) for j in members}
   breakdown[scope]={'generation':dict(collections.Counter(j['status'] for j in members)),'registered_slots':len(members),'target_slots':None if 'transfer' in scope or 'history' in scope else 190,'cis_completed':sum(j['kind']=='card' and j['status']=='completed' and (j['domain'],j.get('slot')) in identities for j in jobs)}
  retired=method=='ai_researcher'
  rows.append({'method':method,'source_status':spec.get('status'),'enabled':spec.get('enabled',False),'generation':dict(collections.Counter(j['status'] for j in gen)),'terminal_infrastructure_exclusions':sum(bool(j.get('terminal_infrastructure_exclusion')) for j in gen),'target':190,'cis_completed':sum(j['kind']=='card' and j['status']=='completed' for j in jobs),'novelty_panels_completed':sum(j['kind']=='novelty' and j['status']=='completed' for j in jobs),'registered_generation_slots':len(gen),'active_registered_generation_slots':sum(v['registered_slots'] for v in breakdown.values() if v['target_slots'] is not None),'target_generation_slots':0 if retired else 190,'main_comparison_included':False if method in ('ai_researcher',METHOD) else spec.get('main_comparison_included',True),'retired_history_only':retired,'blocker':spec.get('blocker'),'live_stage_note':spec.get('live_stage_note'),'scope_breakdown':breakdown})
 return {'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'protocol_id':'offline-common-corpus-20261117','methods':rows,'scheduler':state.get('scheduler'),'expected_slots':1330,'legacy_expected_slots_note':'Original seven-method field retained for readers; dynamic targets exclude retired history and SciAgents transfer history.','registered_generation_slots':sum(r['registered_generation_slots'] for r in rows),'active_registered_generation_slots':sum(r['active_registered_generation_slots'] for r in rows),'target_generation_slots':sum(r['target_generation_slots'] for r in rows),'main_comparison_target_generation_slots':sum(r['target_generation_slots'] for r in rows if r['main_comparison_included']),'additional_target_generation_slots':sum(r['target_generation_slots'] for r in rows if not r['main_comparison_included'] and not r['retired_history_only']),'registered_methods':len(rows),'active_target_methods':sum(not r['retired_history_only'] for r in rows),'read_warnings':warnings}

def render(value):
 lines=['# Offline AR baselines: 38 domains × 5 slots','',f"Updated UTC: {value['at']}. Registered methods: {value['registered_methods']}; active target methods: {value['active_target_methods']}.",'','|Method / scope|State|Completed|Running|Awaiting acceptance|Registered|Target|C/I/S|','|---|---|---:|---:|---:|---:|---:|---:|']
 notes=[]
 for r in value['methods']:
  groups=r['scope_breakdown'] if r['method']=='sciagents' else {r['method']+(' (retired history)' if r['retired_history_only'] else ' (additional; not main)' if r['method']==METHOD else ''):{'generation':r['generation'],'registered_slots':r['registered_generation_slots'],'target_slots':None if r['retired_history_only'] else r['target_generation_slots'],'cis_completed':r['cis_completed']}}
  for scope,v in groups.items():
   c=v['generation'];label='sciagents / '+scope if r['method']=='sciagents' else scope
   lines.append(f"|{label}|{r['source_status']}|{c.get('completed',0)}|{c.get('running',0)}|{c.get('native_terminal_pending_acceptance',0)}|{v['registered_slots']}|{v['target_slots'] if v['target_slots'] is not None else 'historical'}|{v['cis_completed']}|")
  if r['blocker']:notes.extend(['',r['method']+': '+r['blocker']])
  if r['live_stage_note']:notes.extend(['',r['method']+': '+r['live_stage_note']])
 return '\n'.join(lines+notes+['','Native outputs awaiting independent acceptance are withheld from scoring. Missing or failed usage remains unknown. All live calls share the original 250 request pool. Registered slots and target coverage are separate; historical SciAgents transfer does not count toward matched-domain coverage.',''])

def report(state):
 value=summarize(state,read(P/'state/methods.json'))
 for path,data in [(P/'state/progress.json',json.dumps(value,ensure_ascii=False,indent=2)+'\n'),(P/'STATUS.md',render(value))]:
  temp=path.with_name(path.name+f'.report-{os.getpid()}.tmp');temp.write_text(data);os.replace(temp,path)
 return value['methods']
