"""Keep the original native workflow; normalize nested reports only at delivery."""
from pathlib import Path
import sys
from common import ROOT, REPO, read, load_module
from isci_delivery import can_finalize, finalize

# Native generation remains the already deployed retrieval-recovery runtime.
sys.path.insert(1,str(REPO/'baselines/runtime'))
worker=load_module('native_baseline_worker',Path(__file__).parent/'native_worker.py')
original_one=worker.isci_one
original_batch=worker.run_isci

def isci_one(run,domain,index):
    native=run/'native'/f'run-{index:02}'
    if (native/'idea_card.json').exists():return
    if can_finalize(native):
        finalize(native,domain,index);return
    try:original_one(run,domain,index)
    except Exception:
        if not can_finalize(native):raise
        finalize(native,domain,index)

worker.isci_one=isci_one
def run_isci(run,domain):
    for native in sorted((run/'native').glob('run-*')):
        if not (native/'idea_card.json').exists() and can_finalize(native):
            finalize(native,domain,int(native.name.rsplit('-',1)[1]))
    worker.aggregate(run)
    return original_batch(run,domain)
worker.run_isci=run_isci
# run_isci launches the same wrapper for subsequent independent proposals.
worker.__file__=str(Path(__file__).resolve())

if __name__=='__main__':raise SystemExit(worker.main())
