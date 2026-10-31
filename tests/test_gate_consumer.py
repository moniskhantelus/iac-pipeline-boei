import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'examples/gate-test-consumer.gitlab-ci.yml'

class ConsumerGateTests(unittest.TestCase):
    def test_no_external_includes_and_same_runtime(self):
        text = CONFIG.read_text()
        self.assertNotIn('\ninclude:', text)
        self.assertNotIn('  - component:', text)
        self.assertNotIn('$[[', text)
        self.assertNotIn('unittest discover', text)
        body = text.split("<<'STR222_GATE_PY'\n", 1)[1].split('      STR222_GATE_PY', 1)[0]
        source = ''.join(line[6:] + '\n' for line in body.splitlines())
        self.assertEqual(source, (ROOT / 'scripts/gate.py').read_text())
        self.assertIn("if: '$DEPLOY_ENV =~ /^(uat|prod)$/'", text)

    def test_embedded_dev_gate_then_probe(self):
        text = CONFIG.read_text()
        body = text.split("<<'STR222_GATE_PY'\n", 1)[1].split('      STR222_GATE_PY', 1)[0]
        gate = ''.join(line[6:] + '\n' for line in body.splitlines())
        guard = text.split("python3 - <<'VERIFY_GATE_PY'\n", 1)[1].split('      VERIFY_GATE_PY', 1)[0]
        guard = '\n'.join(line[6:] for line in guard.splitlines())
        with tempfile.TemporaryDirectory() as tmp:
            env = {'PATH': os.environ['PATH'], 'CI_PROJECT_DIR': tmp, 'GATE_ENV': 'dev', 'DEPLOY_ENV': 'dev',
                   'CI_COMMIT_SHA': 'testsha', 'CI_PIPELINE_ID': '101'}
            for program in [gate, guard]:
                result = subprocess.run([sys.executable, '-c', program], env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((Path(tmp) / 'gate-decision.json').read_text())
            self.assertEqual(record['outcome'], 'APPROVED')
            (Path(tmp) / 'gate-decision.json').unlink()
            result = subprocess.run([sys.executable, '-c', guard], env=env, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

if __name__ == '__main__':
    unittest.main()
