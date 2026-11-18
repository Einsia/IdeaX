"""Host dispatch for only explicit matched SciAgents and official Cycle scopes."""
from pathlib import Path
import importlib.util,sys
PHASE=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import material_versions_scoped as M

def build_if_scoring(output,model_socket,command,extra_readonly=(),method=None):
 if str(PHASE/'scoring/runtime.py') not in command or 'preflight' in command:return None
 if '--method' not in command or command[command.index('--method')+1] not in ('sciagents','cycleresearcher'):return None
 selected=M.command_material(command)
 revised=[str(HERE/'versioned_runtime_scoped.py') if str(x)==str(PHASE/'scoring/runtime.py') else x for x in command]
 sys.path.insert(0,str(PHASE/'runtime'))
 if selected['data_version']=='offline-common-corpus-20261117-v1':
  import offline_exec
  return offline_exec.build_command(output,model_socket,revised,extra_readonly,method)
 import offline_exec_material
 return offline_exec_material.build_command(output,model_socket,revised,extra_readonly,method,selected['material_manifest'])
