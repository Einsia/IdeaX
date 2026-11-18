"""Select one immutable shared raw revision for an otherwise unchanged offline worker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import offline_exec

PHASE=Path(__file__).resolve().parents[1]


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda:stream.read(8*1024*1024),b''):digest.update(part)
    return digest.hexdigest()


def build_command(output,model_socket,command,extra_readonly=(),method=None,material_manifest=None):
    path=Path(material_manifest).resolve();manifest=json.loads(path.read_text())
    database=Path(manifest['database']['path']).resolve()
    if not database.is_relative_to(PHASE/'inputs/material_versions'):
        raise ValueError('Versioned corpus must be under shared material_versions')
    if sha(database)!=manifest['database']['sha256']:
        raise ValueError('Versioned raw database SHA mismatch')
    if manifest.get('shared_across_methods') is not True or manifest.get('new_metadata_or_generated_context_added') is not False:
        raise ValueError('Only accepted shared original-paper revisions can launch')
    legacy=PHASE/'inputs/corpus'
    for item in extra_readonly:
        resource=Path(item).resolve()
        if resource==legacy.resolve() or legacy.resolve().is_relative_to(resource):
            raise ValueError('Do not mount an ancestor of the original corpus')
    task=['/usr/bin/python3',str(PHASE/'runtime/material_task.py'),'--material-manifest',str(path),'--output',str(Path(output).resolve()),'--',*command]
    args=offline_exec.build_command(output,model_socket,task,[*extra_readonly,str(path),str(database)],method)
    replacement={str((legacy/'corpus.sqlite').resolve()):str(database),str((legacy/'manifest.json').resolve()):str(path)}
    selected=[];i=0;replaced=[]
    while i<len(args):
        if args[i]=='--ro-bind':
            source,dest=args[i+1:i+3]
            if source in replacement:
                selected.extend(['--ro-bind',replacement[source],dest]);replaced.append(dest);i+=3;continue
            if Path(source).is_relative_to(legacy.resolve()):
                i+=3;continue
        selected.append(args[i]);i+=1
    if str(legacy/'corpus.sqlite') not in replaced or str(legacy/'manifest.json') not in replaced:
        raise ValueError('Canonical corpus mounts not found')
    value={'data_version':manifest['data_version'],'corpus_id':manifest['corpus_id'],
           'corpus_sha256':manifest['database']['sha256'],'material_manifest':str(path),'material_manifest_sha256':sha(path),
           'database':str(database),'canonical_database':str(legacy/'corpus.sqlite'),'old_database_visible':False,
           'read_only':True,'source_command':command}
    Path(output,'offline_material_launch.json').write_text(json.dumps(value,indent=2)+'\n')
    return selected


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--material-manifest',required=True)
    ap.add_argument('--output',required=True);ap.add_argument('--model-socket',required=True)
    ap.add_argument('--read-only',action='append',default=[]);ap.add_argument('--method')
    ap.add_argument('command',nargs=argparse.REMAINDER);args=ap.parse_args()
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    argv=build_command(args.output,args.model_socket,command,args.read_only,args.method,args.material_manifest)
    Path(args.output,'offline_launch.json').write_text(json.dumps({'command':argv},indent=2)+'\n')
    raise SystemExit(subprocess.run(argv).returncode)


if __name__=='__main__':main()
