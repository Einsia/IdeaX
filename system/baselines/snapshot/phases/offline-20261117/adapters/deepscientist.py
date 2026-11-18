"""Native DeepScientist idea stage with an explicit proposal-only baseline waiver."""
from pathlib import Path
import argparse,json,os,sys,dataclasses
from common import ROOT,AstraClient,NativeFailure,InfrastructureFailure,read,save,now,single_prompt,safe,credentials,MODEL,BASE_URL,admission
from offline_support import require_offline, environment_text
SOURCE=ROOT/'sources/deepscientist'
sys.path.insert(0,str(SOURCE/'src'))

def prepare(domain,output_dir):
    from deepscientist.home import ensure_home_layout
    from deepscientist.config import ConfigManager
    from deepscientist.skills import SkillInstaller
    from deepscientist.quest import QuestService
    from deepscientist.artifact import ArtifactService
    from deepscientist.shared import write_yaml
    out=require_offline(output_dir,fresh_markers=('native_home','provider_config','api_requests','result.json'));out.mkdir(parents=True,exist_ok=True)
    home=out/'native_home';ensure_home_layout(home)
    config=ConfigManager(home);config.ensure_files()
    provider=out/'provider_config';provider.mkdir(exist_ok=True)
    (provider/'config.toml').write_text('''model = "gpt-6-astra"
model_provider = "benchmark_astra"
model_reasoning_effort = "xhigh"
web_search = "disabled"
[features]
shell_snapshot = false
[shell_environment_policy]
exclude = ["AR_BASELINE_API_KEY"]
[model_providers.benchmark_astra]
name = "Benchmark Astra"
base_url = "http://127.0.0.1:8765/v1"
wire_api = "responses"
env_key = "AR_BASELINE_API_KEY"
requires_openai_auth = false
''')
    runners=config.load_runners_config();runners['codex'].update({'binary':'/mnt/einsia/aws01-nvme/liuhanzuo/ai-home/.local/lib/ai-tools/codex-pkg/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex','config_dir':str(provider),'model':MODEL,'model_reasoning_effort':'xhigh','approval_policy':'never','sandbox_mode':'danger-full-access'})
    write_yaml(home/'config/runners.yaml',runners)
    installer=SkillInstaller(SOURCE,home,runners_config=runners)
    qs=QuestService(home,skill_installer=installer)
    goal=single_prompt(domain)
    contract='''\n\nBenchmark execution contract: This quest ends after one complete native research proposal has passed the idea-stage candidate comparison and selection gates. Use the native idea stage, native literature retrieval, candidate development, critique, and selection. The baseline gate is explicitly waived because this is proposal generation, not experimental reproduction. Do not invent baseline results. Stop once artifacts/idea/selected_idea.md and the native selected-idea submission are complete; do not implement the proposal, run training, conduct experiments, or write a paper. Keep the proposal, literature survey, candidate drafts and selection reasoning as durable artifacts. Do not ask the user for decisions; make ordinary research choices within the supplied domain. Do not access unrelated user files or other benchmark runs.'''
    contract += '\n\n' + environment_text(out)
    quest_id='00001'
    qroot=home/'quests'/quest_id
    if not qroot.exists():
        qs.create(goal=goal+contract,quest_id=quest_id,runner='codex',startup_contract={'need_research_paper':True,'workspace_mode':'autopilot','decision_policy':'autonomous'})
        waiver=ArtifactService(home).waive_baseline(qroot,reason='Proposal-only 38-domain benchmark. No experimental reproduction or measurements are requested; no comparator results are being asserted.',auto_advance=True)
        save(out/'baseline_waiver.json',waiver)
    save(out/'native_config.json',{'source_commit':'b36624417f0c6b8238ec02db37b94d6db2faa5b0','home':str(home),'quest_id':quest_id,'stage':'idea','model':MODEL,'reasoning_effort':'xhigh','message':goal+contract,'baseline_gate':'waived','provider':BASE_URL})
    return out,home,qroot,quest_id,goal+contract

def generate(domain,output_dir,client=None):
    from deepscientist.artifact import ArtifactService
    from deepscientist.quest import QuestService
    from deepscientist.prompts import PromptBuilder
    from deepscientist.runners import CodexRunner,RunRequest
    from deepscientist.runtime_logs import JsonlLogger
    out,home,qroot,qid,message=prepare(domain,output_dir)
    os.environ['AR_BASELINE_API_KEY']=credentials()[1]
    os.environ['DEEPSCIENTIST_REPO_ROOT']=str(SOURCE)
    class CompatibleCodexRunner(CodexRunner):
        def _build_command(self,*args,**kwargs):
            command=super()._build_command(*args,**kwargs)
            # Native runner hard-codes --search, which overrides web_search=disabled.
            command=[part for part in command if part!='--search']
            command[-1:-1]=['-c','web_search="disabled"']
            return command
        @staticmethod
        def _mcp_block(*args,**kwargs):
            # Native DeepScientist emits an obsolete explicit transport field; current Codex infers stdio from command.
            return CodexRunner._mcp_block(*args,**kwargs).replace('transport = \"stdio\"\n','')
    runner=CompatibleCodexRunner(home=home,repo_root=SOURCE,binary='/mnt/einsia/aws01-nvme/liuhanzuo/ai-home/.local/lib/ai-tools/codex-pkg/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex',logger=JsonlLogger(home/'logs',level='info'),prompt_builder=PromptBuilder(SOURCE,home),artifact_service=ArtifactService(home))
    req=RunRequest(quest_id=qid,quest_root=qroot,worktree_root=QuestService(home).active_workspace_root(qroot),run_id='native-idea',skill_id='idea',message=message,model=MODEL,reasoning_effort='xhigh',approval_policy='never',sandbox_mode='danger-full-access')
    result=runner.run(req)
    save(out/'native_runner_result.json',{k:str(v) if isinstance(v,Path) else v for k,v in dataclasses.asdict(result).items()})
    if not result.ok:raise InfrastructureFailure('Native Codex runner exited '+str(result.exit_code)+': '+safe(result.stderr_text))
    return validate_output(out,home,qroot)

def validate_output(out,home,qroot):
    from deepscientist.quest import QuestService
    from deepscientist.artifact import ArtifactService
    state=QuestService(home).read_research_state(qroot)
    active_id=state.get('active_idea_id')
    if not active_id:raise NativeFailure('No native accepted active_idea_id; transcript preserved')
    recent=ArtifactService(home).recent(qroot,limit=1000)
    artifacts=[read(x['path'],{}) if x.get('path') else x for x in recent]
    accepted=[x for x in artifacts if isinstance(x,dict) and x.get('flow_type')=='idea_submission' and x.get('idea_id')==active_id and x.get('status')=='completed']
    if not accepted:raise NativeFailure('No completed native idea_submission artifact for active idea')
    detail=accepted[-1].get('details') or {}
    missing=[k for k in ('title','problem','hypothesis','mechanism') if not str(detail.get(k) or '').strip()]
    if missing:raise NativeFailure('Accepted native idea missing core proposal fields: '+', '.join(missing))
    work=QuestService(home).active_workspace_root(qroot)
    evidence_roots=list(dict.fromkeys([work,qroot]))
    candidates=[p for base in evidence_roots for p in base.glob('artifacts/idea/candidates.md') if p.stat().st_size>100]
    drafts=[p for base in evidence_roots for p in base.glob('artifacts/idea/pre_idea_drafts/*.md') if p.stat().st_size>100]
    surveys=[p for base in evidence_roots for p in base.rglob('*.md') if '.codex' not in p.parts and '.ds' not in p.parts and p.stat().st_size>100 and ('survey' in p.name.lower() or 'related_work' in p.name.lower())]
    save(out/'native_acceptance.json',{'active_idea_id':active_id,'submission':accepted[-1],'candidates':[str(p) for p in candidates],'drafts':[str(p) for p in drafts],'surveys':[str(p) for p in surveys]})
    if not candidates or not drafts or not surveys:raise NativeFailure('Native idea ended without durable candidate frontier, pre-idea draft, or literature survey required by idea-stage selection gate')
    files=list(dict.fromkeys([p for base in [work,qroot] for p in base.glob('artifacts/idea/selected_idea.md')]))
    if not files:
        files=list(qroot.glob('.ds/worktrees/**/artifacts/idea/selected_idea.md'))
    if not files:raise NativeFailure('Native idea stage ended without selected_idea.md; complete transcript preserved')
    selected=files[0];md=selected.read_text()
    if len(md.strip())<100:raise NativeFailure('Native selected idea is empty or incomplete')
    (out/'proposal.md').write_text(md)
    return {'status':'completed','proposal_markdown':md,'native_output_paths':[str(selected),str(out/'native_runner_result.json'),str(out/'proposal.md')],'terminal_reason':None,'completed_at':now()}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--domain-json',required=True);ap.add_argument('--output-dir',required=True);ap.add_argument('--prepare-only',action='store_true');ap.add_argument('--validate-only',action='store_true');a=ap.parse_args();d=read(a.domain_json);out=Path(a.output_dir)
    if a.prepare_only:
        prepare(d,out);print('Native DeepScientist prepared');return
    try:
        result=validate_output(out,out/'native_home',out/'native_home/quests/00001') if a.validate_only else generate(d,out)
    except InfrastructureFailure as e:result={'status':'infrastructure_failure','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e)}
    except NativeFailure as e:result={'status':'native_failure','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e)}
    except Exception as e:result={'status':'adapter_failure','proposal_markdown':None,'native_output_paths':[],'terminal_reason':safe(e),'error_type':type(e).__name__}
    save(out/'result.json',result);print(json.dumps({'status':result['status'],'terminal_reason':result['terminal_reason']}))
if __name__=='__main__':main()
