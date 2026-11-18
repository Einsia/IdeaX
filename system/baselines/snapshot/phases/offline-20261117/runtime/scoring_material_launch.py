"""Resolve scoring material on the host without changing the durable scheduler."""
import importlib.util
from pathlib import Path

PHASE=Path(__file__).resolve().parents[1]


def build_if_scoring(output,model_socket,command,extra_readonly=(),method=None):
    if str(PHASE/'scoring/runtime.py') not in command or 'preflight' in command:
        return None
    if '--method' in command and command[command.index('--method')+1] in ('insightagents','ai_scientist_v3_native_ideation'):
        new_spec=importlib.util.spec_from_file_location('host_new_method_scoring_scope_launch',PHASE/'scoring/revisions/new-method-scopes-20261117/host_scoring_scope_launch.py')
        new_scoped=importlib.util.module_from_spec(new_spec);new_spec.loader.exec_module(new_scoped)
        return new_scoped.build_if_scoring(output,model_socket,command,extra_readonly,method)
    if '--method' in command and command[command.index('--method')+1] in ('sciagents','cycleresearcher'):
        scoped_spec=importlib.util.spec_from_file_location('host_scoring_scope_launch',PHASE/'scoring/revisions/comparison-scopes-20261117/host_scoring_scope_launch.py')
        scoped=importlib.util.module_from_spec(scoped_spec);scoped_spec.loader.exec_module(scoped)
        return scoped.build_if_scoring(output,model_socket,command,extra_readonly,method)
    spec=importlib.util.spec_from_file_location('host_scoring_material_versions',PHASE/'scoring/material_versions.py')
    material=importlib.util.module_from_spec(spec);spec.loader.exec_module(material)
    selected=material.command_material(command)
    revised=[str(PHASE/'scoring/versioned_runtime.py') if str(x)==str(PHASE/'scoring/runtime.py') else x for x in command]
    if selected['data_version']=='offline-common-corpus-20261117-v1':
        import offline_exec
        return offline_exec.build_command(output,model_socket,revised,extra_readonly,method)
    import offline_exec_material
    return offline_exec_material.build_command(output,model_socket,revised,extra_readonly,method,selected['material_manifest'])
