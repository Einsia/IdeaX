"""Fail-closed activation for a fresh, common-corpus offline protocol."""
from pathlib import Path
import argparse
import hashlib
import json
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parent
COMMON_CHECKS={'corpus_frozen','public_research_network_denied','model_api_only',
               'shared_250_admission','old_online_runs_hidden','server_search_tools_rejected'}
METHOD_CHECKS={'fresh_context','native_pipeline_preserved','offline_literature_adapter','model_astra_xhigh'}
EVALUATION_CHECKS={'offline_evidence_bound','frozen_rubric','own_five_panel_only','model_astra_xhigh'}


def read(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return default


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def receipt(reference,required,root):
    if not isinstance(reference,dict):return ['missing receipt reference']
    path=Path(reference.get('path',''))
    if not path.is_absolute():path=root/path
    if not path.is_file() or sha(path)!=reference.get('sha256'):return ['receipt missing or SHA mismatch: '+str(path)]
    value=read(path,{})
    errors=[]
    if value.get('passed') is not True:errors.append('receipt not passed: '+str(path))
    if value.get('protocol_id')!='offline-common-corpus-20261117':errors.append('wrong protocol: '+str(path))
    checks=value.get('checks',{})
    errors += ['missing/false check '+name+' in '+str(path) for name in sorted(required) if checks.get(name) is not True]
    bindings=value.get('bindings',{})
    if not bindings:errors.append('empty receipt bindings: '+str(path))
    for name,digest in bindings.items():
        target=Path(name)
        if not target.is_absolute():target=root/target
        if not target.is_file() or sha(target)!=digest:errors.append('bound artifact changed: '+str(target))
    return errors


def check(root=ROOT):
    root=Path(root);activation=read(root/'state/activation.json',{});protocol=read(root/'protocol.json',{});methods=read(root/'state/methods.json',{})
    errors=[]
    if activation.get('protocol_sha256')!=sha(root/'protocol.json'):errors.append('protocol not bound to activation')
    if activation.get('ready') is not True:errors.append('activation has not been marked ready')
    if activation.get('mode') not in ('smoke','full'):errors.append('activation mode must be smoke or full')
    errors+=receipt(activation.get('common_receipt'),COMMON_CHECKS,root)
    enabled=[m for m,spec in methods.items() if spec.get('enabled')]
    if not enabled:errors.append('no native offline method enabled')
    for method in enabled:
        required=METHOD_CHECKS|({'agent_turn_cap_removed'} if method=='dr_claw' else set())
        reference=activation.get('method_receipts',{}).get(method)
        errors+=receipt(reference,required,root)
        if not methods[method].get('command'):errors.append('missing verified launch command: '+method)
        if isinstance(reference,dict):
            path=Path(reference.get('path',''))
            if not path.is_absolute():path=root/path
            if read(path,{}).get('command')!=methods[method].get('command'):errors.append('launch command differs from verified method receipt: '+method)
        if activation.get('mode')=='smoke' and not methods[method].get('eligible_domains'):errors.append('smoke must restrict eligible domains: '+method)
        if activation.get('mode')=='smoke' and not methods[method].get('eligible_slots'):errors.append('smoke must restrict eligible slots: '+method)
    if activation.get('mode')=='full' or any(methods[m].get('scoring_approved') for m in enabled):
        errors+=receipt(activation.get('evaluation_receipt'),EVALUATION_CHECKS,root)
    control=read(root/'state/control.json',{})
    if control.get('request_concurrency')!=250:errors.append('shared model limit must remain250')
    if (root/'state/request_slots').resolve()!=Path(protocol.get('shared_admission_pool','/missing')).resolve():errors.append('admission path does not share originalpool')
    return {'at':datetime.now(timezone.utc).isoformat(),'passed':not errors,'errors':errors,'protocol_id':protocol.get('protocol_id'),
            'enabled_methods':enabled,'mode':activation.get('mode'),'model_calls':0,'network_calls':0}


if __name__=='__main__':
    result=check();target=ROOT/'state/activation_gate_state.json';target.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 2)
