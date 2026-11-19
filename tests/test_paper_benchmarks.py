"""Offline checks for scientific labels, paired judges, and missing coverage."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks/shared'))
import paper_report as report


class PaperBenchmarkTests(unittest.TestCase):
    def test_contribution_is_not_conceptual_novelty_and_claude_stays_missing(self):
        reviewer = {'cards': [{'group': 's', 'domain': 'd', 'source_idea_id': 'one',
                               'judge': 'astra', 'N': 4, 'I': 3, 'S': 2}]}
        novelty = {'rows': [{'system': 's', 'domain': 'd', 'idea_id': 'one',
                             'judge': 'astra', 'interesting': 20}]}
        gpt, claude = report.generation(reviewer, novelty, expected=2)
        self.assertEqual(gpt['metrics']['C']['successful_mean'], 4)
        self.assertEqual(gpt['metrics']['N']['successful_mean'], 1)
        self.assertIsNone(gpt['metrics']['C']['full_mean'])
        self.assertEqual(claude['metrics']['C']['missing'], 2)
        self.assertIsNone(claude['metrics']['N']['covered_mean'])
        # A certified failed generation slot is a distinct outcome, not a judge response.
        gpt, claude = report.generation(reviewer, novelty, expected=2, zeros=[{'system': 's'}])
        self.assertEqual(gpt['metrics']['C']['full_mean'], 2)
        self.assertEqual(gpt['metrics']['C']['judged'], 1)
        self.assertIsNone(claude['metrics']['C']['full_mean'])
        self.assertEqual(claude['metrics']['C']['confirmed_native_zero'], 1)

    def test_reconstruction_domain_weighting_and_unattempted_judge(self):
        targets = [{'task_id': task, 'founder_paper_id': pid} for task, pid in
                   [('2025-01-01:a', '1'), ('2025-02-01:a', '2'), ('2025-01-01:b', '3')]]
        manifest = {'payloads': [{'labels': {'s': 'A'}}]}
        rows = [{'system': 's', 'judge': 'astra', 'domain': t['task_id'], 'target': t['founder_paper_id'],
                 'best_level': score, 'direction_hit': int(score >= 1), 'mechanism_hit': int(score >= 2)}
                for t, score in zip(targets, [0, 0, 3])]
        gpt, claude = report.reconstruction({'rows': rows}, manifest, targets)
        self.assertEqual(gpt['metrics']['Grade']['domain_mean'], 1.5)
        self.assertEqual(gpt['metrics']['Grade']['historical_target_mean'], 1)
        self.assertIsNone(claude['metrics']['Grade']['domain_mean'])
        partial = report.reconstruction({'rows': rows[:2]}, manifest, targets)[0]
        self.assertIsNone(partial['metrics']['Grade']['domain_mean'])
        self.assertEqual(partial['metrics']['Grade']['expected_targets'], 3)

    def test_is_six_dimension_mean_excludes_novelty_and_transfer(self):
        row = {'system': 's', 'domain': 'd', 'idea_id': 'one', 'judge': 'astra',
               **dict.fromkeys(report.QUALITY, 4), 'novelty': 10, 'transfer': 1}
        gpt, claude = report.is_benchmark({'rows': [row]}, {'jobs': [{'system': 's'}]}, expected=1)
        self.assertEqual(gpt['metrics']['quality_mean']['full_mean'], 4)
        self.assertEqual(gpt['metrics']['novelty']['full_mean'], 10)
        self.assertIsNone(gpt['Overall'])
        self.assertIsNone(claude['metrics']['quality_mean']['full_mean'])

    def command(self, *args, success=True):
        proc = subprocess.run([sys.executable, 'benchmarks/evaluate.py', *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True)
        if success:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        else:
            self.assertNotEqual(proc.returncode, 0)
        return proc

    def test_independent_inputs_prepare_and_report_without_api_calls(self):
        scratch = ROOT / '.scratch'; scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as name:
            p = Path(name)
            rows = [{'system': 'fixture', 'task_id': 'agent-memory', 'domain_ids': ['agent-memory'],
                     'idea_id': str(i), 'idea_text': f'Synthetic fixture {i}\nMechanism: example',
                     'task_context': 'Offline test; not a scientific result'} for i in range(5)]
            source = p / 'cards.json'; source.write_text(json.dumps(rows))
            self.command('generation', 'cis', 'prepare', '--input', source, '--out', p / 'cis')
            self.command('generation', 'novelty', 'prepare', '--input', source, '--out', p / 'novelty')
            manifest = json.loads((p / 'novelty/manifest.json').read_text())
            self.assertEqual(manifest['protocol'], 'interesting-independent-single-card-v1')
            self.assertEqual(len(manifest['jobs']), 5)
            for job in manifest['jobs']:
                payload = json.loads((p / 'novelty/inputs' / (job['id'] + '.json')).read_text())
                self.assertEqual(len(payload['cards']), 1)
                self.assertEqual(len(payload['mapping']), 1)
                self.assertEqual([s['kind'] for s in payload['stages']], ['read', 'score'])
                self.assertTrue(all(s['card_ids'] == ['card_01'] for s in payload['stages']))
            self.command('generation', 'report', '--reviewer', p / 'cis', '--novelty', p / 'novelty',
                         '--generation-model', 'fixture', '--out', p / 'report')
            result = json.loads((p / 'report/scores.json').read_text())
            self.assertEqual([r['judge'] for r in result['rows']], ['GPT', 'Claude'])
            self.assertTrue(all(m['missing'] == 190 for r in result['rows'] for m in r['metrics'].values()))
            rows[0]['idea_text'] = 'A different original proposal'
            changed = p / 'different.json'; changed.write_text(json.dumps(rows))
            self.command('generation', 'novelty', 'prepare', '--input', changed, '--out', p / 'different')
            failed = self.command('generation', 'report', '--reviewer', p / 'cis', '--novelty', p / 'different',
                                  '--generation-model', 'fixture', '--out', p / 'invalid', success=False)
            self.assertIn('proposal inputs differ', failed.stderr)
            four = p / 'four-cards.json'; four.write_text(json.dumps(rows[:4]))
            self.command('generation', 'novelty', 'prepare', '--input', four, '--out', p / 'four')
            self.assertEqual(len(json.loads((p / 'four/manifest.json').read_text())['jobs']), 4)
            # Historical panel results cannot enter a report for the new protocol.
            manifest['protocol'] = 'interesting-read-all-then-score-v2'
            (p / 'novelty/manifest.json').write_text(json.dumps(manifest))
            failed = self.command('generation', 'report', '--reviewer', p / 'cis', '--novelty', p / 'novelty',
                                  '--generation-model', 'fixture', '--out', p / 'mixed', success=False)
            self.assertIn('old panel scores stay separate', failed.stderr)

    def test_worker_limit_rejects_before_starting_any_judge(self):
        proc = self.command('generation', 'cis', 'run', '--out', 'does-not-exist',
                            '--astra-concurrency', '20', '--opus-concurrency', '1', success=False)
        self.assertIn('within 20', proc.stderr)
        proc = self.command('is', 'run', '--out', 'does-not-exist', '--workers', '21', success=False)
        self.assertIn('within 20', proc.stderr)


if __name__ == '__main__':
    unittest.main()
