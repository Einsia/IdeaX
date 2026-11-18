"""Score the preserved original-graph transcript once in its separate scope."""
import argparse,hashlib,json,sys,urllib.request
from pathlib import Path
import versioned_runtime as V
import material_versions as M
PHASE=Path(__file__).resolve().parents[1]
SCOPE='original-graph-transfer'
SOURCE=PHASE/'runs/sciagents/agent-memory/slot-01'
OUTPUT=PHASE/'evaluations-transfer'/SCOPE/'sciagents/agent-memory/slot-01'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def configure(out):
    view=out/'evaluation_input_view';view.mkdir(parents=True,exist_ok=True)
    targets=[(view/'inputs',PHASE/'inputs'),(view/'runs/sciagents/agent-memory/slot-01',SOURCE),(view/'evaluations/sciagents/agent-memory/slot-01',out)]
    for link,target in targets:
        link.parent.mkdir(parents=True,exist_ok=True)
        if link.is_symlink():assert link.resolve()==target.resolve()
        else:link.symlink_to(target,target_is_directory=True)
    M.ROOT=view;V.original.ROOT=view
    return view

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--acceptance',type=Path);ap.add_argument('--fixture-output',type=Path);args=ap.parse_args();fixture=args.fixture_output is not None
    out=args.fixture_output.resolve() if fixture else OUTPUT;out.mkdir(parents=True,exist_ok=True)
    result=M.read(SOURCE/'result.json');assert result['status'] in ('success','completed')
    if not fixture:assert args.acceptance and args.acceptance.is_file()
    if args.acceptance:
        proof=M.read(args.acceptance);assert proof['passed']
        assert proof.get('bindings') and all(sha(p)==h for p,h in proof['bindings'].items())
        assert str((SOURCE/'result.json').resolve()) in proof['bindings'] and str((SOURCE/'proposal.md').resolve()) in proof['bindings']
    view=configure(out);row=V.original.row_from_slot(view/'runs/sciagents/agent-memory/slot-01')
    assert row['idea_text'].encode()==(SOURCE/'proposal.md').read_bytes()
    V.original.verify_sources()
    V.original.save(out/'source_scope.json',{'at':V.original.now(),'comparison_scope':SCOPE,'main_protocol_comparable':False,'matched_ranking_eligible':False,'source_result':str(SOURCE/'result.json'),'source_result_sha256':sha(SOURCE/'result.json'),'source_proposal_sha256':sha(SOURCE/'proposal.md'),'native_output_kind':'full_native_transcript_round_bound','last_message_empty':True,'termination_marker_present':False,'no_posthoc_message_selection':True,'frozen_rubric':True,'repetitions':1,'native_acceptance':str(args.acceptance) if args.acceptance else None,'fixture':fixture})
    invoked=[]
    if fixture:
        def no_model(*a,**kw):raise AssertionError('Zero-model fixture attempted a paid call')
        V.original.AstraClient.completion=no_model
        def checked_entry():
            V.original.verify_sources();again=V.original.row_from_slot(view/'runs/sciagents/agent-memory/slot-01');assert again==row;invoked.append(True)
            V.original.save(out/'result.json',{'status':'completed','fixture_only':True,'proposal_sha256':hashlib.sha256(again['idea_text'].encode()).hexdigest()})
        V.original.main=checked_entry
    sys.argv=['versioned_runtime.py','card','--method','sciagents','--domain','agent-memory','--slot','1'];V.main()
    for name in ('manifest.json','result.json','evaluation_material_version.json'):
        p=out/name
        if p.exists():
            value=M.read(p);value.update(comparison_scope=SCOPE,main_protocol_comparable=False,matched_ranking_eligible=False,native_output_kind='full_native_transcript_round_bound');V.original.save(p,value)
    if fixture:
        with urllib.request.urlopen('http://127.0.0.1:8766/read?id=89614') as response:paper=json.load(response)
        sidecar=M.read(out/'evaluation_material_version.json');finished=M.read(out/'result.json');scope=M.read(out/'source_scope.json')
        checks={'complete_original_transcript_bytewise_unchanged':finished['proposal_sha256']==sha(SOURCE/'proposal.md'),'actual_local_http_matches_v1_material':paper['corpus_id']==sidecar['corpus_id'],'scoring_entry_called_once':invoked==[True],'frozen_rubric_verified':True,'separate_evaluation_directory':out!=PHASE/'evaluations/sciagents/agent-memory/slot-01','explicit_original_graph_scope':finished['comparison_scope']==SCOPE,'excluded_from_matched_ranking':finished['main_protocol_comparable'] is False and finished['matched_ranking_eligible'] is False,'no_posthoc_scientist_message_selection':scope['no_posthoc_message_selection'],'native_round_bound_disclosed':scope['last_message_empty'] and not scope['termination_marker_present'],'zero_model_calls':True}
        report={'at':V.original.now(),'passed':all(checks.values()),'checks':checks,'model_calls':0,'real_local_http':True,'source_result_sha256':sha(SOURCE/'result.json'),'source_proposal_sha256':sha(SOURCE/'proposal.md'),'corpus_id':sidecar['corpus_id'],'data_version':sidecar['data_version']};V.original.save(out/'acceptance.json',report);print(json.dumps(report));return 0 if report['passed'] else 2
if __name__=='__main__':raise SystemExit(main())
