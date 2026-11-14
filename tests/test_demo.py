"""Offline checks for public evidence and the explicit local-generation handoff."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / '.scratch'
SCRATCH.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('demo_local', ROOT / 'demo/run_local.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


class DemoTests(unittest.TestCase):
    def request(self):
        return {'schema': local.SCHEMA, 'domain': 'agent-memory', 'access': 'api',
                'question': 'How can a memory avoid stale evidence?', 'critique': 'Measure contradictory memories.'}

    def test_invalid_request_cannot_reach_runtime(self):
        for update in ({'domain': '../../outside'}, {'access': 'web'}, {'schema': 'other'},
                       {'question': 'x' * 4001}, {'command': 'untrusted shell'}, {'reference_case': {}}):
            with self.subTest(update=update), patch.object(local.subprocess, 'run') as runtime:
                with self.assertRaises(ValueError):
                    local.validate_request(self.request() | update)
                runtime.assert_not_called()

    def test_prepare_freezes_brief_without_generation_and_rejects_changed_reuse(self):
        request = local.validate_request(self.request())
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            out = Path(directory) / 'run'

            def fake_prepare(command, **kwargs):
                self.assertIn('prepare', command)
                self.assertNotIn('run', command)
                run = out / 'runs/agent-memory'
                (run / 'work').mkdir(parents=True)
                prompt = run / 'initial_prompt.md'
                prompt.write_text('Frozen original prompt.\n')
                local.save(run / 'run.json', {'input_files': {str(prompt): local.digest(prompt)},
                                              'prompt_sha256': local.digest(prompt)})
                local.save(out / 'manifest.json', {'kind': 'single'})

            with patch.object(local.subprocess, 'run', side_effect=fake_prepare) as runtime:
                local.prepare(request, out)
                runtime.assert_called_once()
                run = out / 'runs/agent-memory'
                self.assertEqual((run / 'base_prompt.md').read_text(), 'Frozen original prompt.\n')
                self.assertIn(request['critique'], (run / 'initial_prompt.md').read_text())
                meta = local.read(run / 'run.json')
                for path, expected in meta['input_files'].items():
                    self.assertEqual(local.digest(path), expected)
                self.assertFalse(meta['demo_customization']['paper_benchmark_reproduction'])
                local.prepare(request, out)
                runtime.assert_called_once()
                with self.assertRaises(ValueError):
                    local.prepare(request | {'critique': 'A changed request'}, out)
                local.save(out / 'demo_request.json', request | {'question': 'tampered'})
                with self.assertRaises(ValueError):
                    local.prepare(request, out)

    def test_static_catalog_preserves_complete_original_sources(self):
        subprocess.run([sys.executable, 'demo/build.py'], cwd=ROOT, check=True, capture_output=True)
        catalog = local.read(ROOT / 'demo/site/catalog.json')
        self.assertEqual(len(catalog['cases']), 6)
        self.assertEqual(len(catalog['domains']), 38)
        for case in catalog['cases']:
            for kind in ('PROPOSAL', 'PROCESS'):
                original = ROOT / 'case_studies/model_efficiency' / case['folder'] / (kind + '.md')
                published = ROOT / 'demo/site/sources' / case['id'] / (kind + '.md')
                self.assertEqual(original.read_bytes(), published.read_bytes())
                self.assertEqual(local.digest(original), case['source_sha256'][kind.lower()])
            self.assertEqual(len(case['neighbors']), 3)
        self.assertIn('G01', catalog['api_prompt'])
        self.assertIn('IDEAS.json', catalog['api_prompt'])
        self.assertNotIn('```', catalog['api_prompt'])


if __name__ == '__main__':
    unittest.main()
