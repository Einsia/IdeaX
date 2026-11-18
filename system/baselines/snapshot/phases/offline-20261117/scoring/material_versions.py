"""Material identity resolution shared by the host launcher, evaluator, and summaries."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CATALOG=Path(__file__).resolve().parent/'material_catalog.json'


def read(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return default


def generation_material(slot):
    catalog=read(CATALOG,{})
    recorded=read(Path(slot)/'input_material_version.json',{})
    version=recorded.get('data_version') or 'offline-common-corpus-20261117-v1'
    if version not in catalog:raise ValueError('Unknown generation material version: '+version)
    selected=catalog[version]
    if recorded.get('corpus_id') and recorded['corpus_id']!=selected['corpus_id']:
        raise ValueError('Generation corpus ID does not match material version')
    if recorded.get('corpus_sha256') and recorded['corpus_sha256']!=selected['corpus_sha256']:
        raise ValueError('Generation corpus hash does not match material version')
    return {**selected,'data_version':version,'generation_recorded':bool(recorded)}


def scoring_material(method,domain,index=None):
    slots=[ROOT/'runs'/method/domain/f'slot-{i:02}' for i in ([index] if index is not None else range(1,6))]
    values=[generation_material(slot) for slot in slots]
    identities={(v['data_version'],v['corpus_id'],v['corpus_sha256']) for v in values}
    if len(identities)!=1:raise ValueError('Own-five novelty panel contains different material versions')
    return values[0]


def command_material(command):
    if not any(str(part)==str(ROOT/'scoring/runtime.py') for part in command):return None
    if 'preflight' in command:return None
    def option(name):return command[command.index(name)+1]
    index=int(option('--slot')) if '--slot' in command else None
    return scoring_material(option('--method'),option('--domain'),index)
