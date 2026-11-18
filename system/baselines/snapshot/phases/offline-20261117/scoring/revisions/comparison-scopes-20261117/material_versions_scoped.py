"""Preserve generation comparison scope alongside existing material identity."""
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[3]
CATALOG=ROOT/'scoring/material_catalog.json'
spec=importlib.util.spec_from_file_location('frozen_material_versions',ROOT/'scoring/material_versions.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
read=legacy.read
MATCHED='matched-domain-abstract-graph'
TRANSFER='original-graph-transfer'
CYCLE='official-public-workflow-astra-n10-standard4'
DEFAULT='native_pipeline_disclosed_adaptations'
UNASSIGNED='unassigned-native-scope'

def generation_scope(slot):
 slot=Path(slot);material=read(slot/'input_material_version.json',{});result=read(slot/'result.json',{})
 scopes={x['comparison_scope'] for x in (material,result) if x.get('comparison_scope')}
 if len(scopes)>1:raise ValueError('Generation result and input material comparison scopes differ')
 if scopes:return scopes.pop()
 method=slot.parts[-3]
 if method in ('sciagents','cycleresearcher'):return UNASSIGNED
 return DEFAULT

def generation_material(slot):
 legacy.CATALOG=CATALOG
 value=legacy.generation_material(slot)
 return {**value,'comparison_scope':generation_scope(slot)}

def scoring_material(method,domain,index=None):
 slots=[ROOT/'runs'/method/domain/f'slot-{i:02}' for i in ([index] if index is not None else range(1,6))]
 values=[generation_material(slot) for slot in slots]
 identities={(v['data_version'],v['corpus_id'],v['corpus_sha256'],v['comparison_scope']) for v in values}
 if len(identities)!=1:raise ValueError('Own-five novelty panel contains different material versions or comparison scopes')
 scope=values[0]['comparison_scope']
 if method=='sciagents' and scope!=MATCHED:raise ValueError('Canonical SciAgents scoring requires explicit matched graph scope; original graph transfer uses evaluations-transfer')
 if method=='cycleresearcher' and scope!=CYCLE:raise ValueError('Cycle scoring requires explicit official public n10 standard4 scope')
 return values[0]

def command_material(command):
 if str(ROOT/'scoring/runtime.py') not in command or 'preflight' in command:return None
 def option(name):return command[command.index(name)+1]
 index=int(option('--slot')) if '--slot' in command else None
 return scoring_material(option('--method'),option('--domain'),index)
