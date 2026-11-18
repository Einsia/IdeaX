"""Verify worker HTTP/raw identity before executing a versioned generation or evaluation."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import urllib.request

PHASE=Path(__file__).resolve().parents[1]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--material-manifest',required=True);ap.add_argument('--output',required=True)
    ap.add_argument('command',nargs=argparse.REMAINDER);args=ap.parse_args()
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    manifest=json.loads(Path(args.material_manifest).read_text())
    canonical=PHASE/'inputs/corpus/corpus.sqlite'
    with sqlite3.connect('file:'+str(canonical)+'?mode=ro',uri=True) as db:
        local=json.loads(db.execute("select value from metadata where key='manifest'").fetchone()[0])
    with urllib.request.urlopen('http://127.0.0.1:8766/health',timeout=5) as response:
        health=json.load(response)
    mounted=json.loads((PHASE/'inputs/corpus/manifest.json').read_text())
    boundary=json.loads(Path(args.output,'offline_boundary.json').read_text())
    checks={'http_matches_selected_corpus':health.get('corpus_id')==manifest['corpus_id'],
            'canonical_database_matches_selected_corpus':local['corpus_id']==manifest['corpus_id'],
            'canonical_manifest_matches_selected_corpus':mounted['corpus_id']==manifest['corpus_id'],
            'public_network_denied':boundary.get('public_network') is False and boundary.get('no_default_route') is True,
            'only_raw_service':health.get('compressed_content_exposed') is False}
    value={'passed':all(checks.values()),'checks':checks,'data_version':manifest['data_version'],
           'corpus_id':manifest['corpus_id'],'corpus_sha256':manifest['database']['sha256'],
           'material_manifest':args.material_manifest,'canonical_database':str(canonical),'actual_database':manifest['database']['path']}
    Path(args.output,'material_boundary_acceptance.json').write_text(json.dumps(value,indent=2)+'\n')
    if not value['passed']:raise RuntimeError('Selected raw material boundary mismatch')
    os.environ['INSIGHTPRO_MATERIAL_MANIFEST']=args.material_manifest
    os.environ['INSIGHTPRO_MATERIAL_VERSION']=manifest['data_version']
    os.environ['INSIGHTPRO_CORPUS_ID']=manifest['corpus_id']
    os.execv(command[0],command)


if __name__=='__main__':main()
