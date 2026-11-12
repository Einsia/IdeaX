"""Explicit workers; domain barriers remain inside each light-multi run."""
import argparse
import fcntl
import sys
from common import *

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['domain','blueprint','prepare-blueprint'])
    p.add_argument('--root',type=Path,required=True);p.add_argument('--domain');p.add_argument('--id');p.add_argument('--source',type=Path)
    a=p.parse_args();os.umask(0o007)
    if a.action=='prepare-blueprint':
        import blueprint
        blueprint.prepare_domain(a.source,a.root,a.domain);return
    a.root.mkdir(parents=True,exist_ok=True)
    name='domain.lock' if a.action=='domain' else a.id+'.lock'
    with (a.root/name).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if a.action=='blueprint':
            import blueprint
            blueprint.worker(a.root,a.id)
        elif RELEASE['kind']=='single':
            import single
            from single_selector import select
            code=single.worker(a.root)
            if code:sys.exit(code)
            select(a.root,a.domain)
        else:
            import light
            light.domain_worker(a.root,a.domain)

if __name__=='__main__':main()
