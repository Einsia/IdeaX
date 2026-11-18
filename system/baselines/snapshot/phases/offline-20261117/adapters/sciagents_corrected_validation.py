"""One authorized fresh validation after an invalid offline tool disclosure."""
import argparse
from pathlib import Path
from common import read,save,now,safe,NativeFailure,InfrastructureFailure
from offline_support import require_offline
import sciagents


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--domain-json',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args()
    out=require_offline(args.output_dir)
    marker=read(out/'corrected_validation_authorization.json',{})
    if marker.get('one_fresh_corrected_adapter_validation') is not True or marker.get('old_context_imported') is not False:raise RuntimeError('Missing explicit corrected validation authorization')
    if (out/'corrected_validation_started.json').exists():raise RuntimeError('Corrected validation already attempted; no further resampling')
    sentinel=read(out/'result.json',{})
    if sentinel.get('status')!='infrastructure_failure' or sentinel.get('classification')!='corrected_adapter_validation_pending':raise RuntimeError('Invalid scheduler-only pending marker')
    save(out/'corrected_validation_started.json',{'at':now(),'fresh_context':True,'old_context_imported':False,'one_authorized_validation':True,'native_prompts_and_selection_unchanged':True})
    (out/'result.json').unlink()
    try:result=sciagents.generate(read(args.domain_json),out)
    except InfrastructureFailure as exc:result={'status':'infrastructure_failure','terminal_reason':safe(exc),'proposal_markdown':None,'native_output_paths':[]}
    except NativeFailure as exc:result={'status':'native_failure','terminal_reason':safe(exc),'proposal_markdown':None,'native_output_paths':[]}
    except Exception as exc:result={'status':'adapter_failure','terminal_reason':safe(exc),'error_type':type(exc).__name__,'proposal_markdown':None,'native_output_paths':[]}
    result.update(validation_scope='one_fresh_corrected_adapter_validation',comparison_scope='original-graph-transfer',scoring_approved=False)
    save(out/'result.json',result);print({'status':result['status'],'terminal_reason':result.get('terminal_reason')})


if __name__=='__main__':main()
