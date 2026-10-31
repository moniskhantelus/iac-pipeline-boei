import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LEGACY = (ROOT / 'iac/.iac_tf_apply.yml').exists()
APPLY = ROOT / ('iac/.iac_tf_apply.yml' if LEGACY else 'templates/terraform/apply/template.yml')

class GateDependencyTests(unittest.TestCase):
    def test_heredoc_terminators_have_no_trailing_spaces(self):
        for file in (ROOT / 'iac').glob('.*.yml'):
            self.assertIsNone(re.search(r'(?m)^\s*EOF[ \t]+$', file.read_text()), str(file))

    def test_apply_requires_nonoptional_gate(self):
        text = APPLY.read_text()
        needs = text
        self.assertIn('    - job: iac_gates_job' if LEGACY else '    - job: "$[[ inputs.gate_job ]]"', needs)
        self.assertNotIn('optional: true', needs)
        self.assertNotIn('\n  dependencies:', text)
        gate = ROOT / ('templates/compliance-gates/terraform-gate/template.yml' if LEGACY else 'templates/compliance-gates/terraform-gate/template.yml')
        rules = gate.read_text().split('\n  rules:\n', 1)[1].split('\n  allow_failure:', 1)[0]
        self.assertNotIn('when: never', rules)
        self.assertIn('when: manual', rules)
        self.assertNotIn('\n  needs:', gate.read_text())

    def test_apply_evidence_guard(self):
        text = APPLY.read_text()
        body = text.split("python3 - <<'VERIFY_GATE_PY'\n", 1)[1].split('      VERIFY_GATE_PY', 1)[0]
        program = '\n'.join(line[6:] for line in body.splitlines())
        approved = dict(environment='prod', commit_sha='abc', pipeline_id='123', outcome='APPROVED', approvals_count=2, change_ticket='CHG1234567')
        cases = [('valid', approved, 0), ('missing', None, 1), ('blocked', dict(approved, outcome='BLOCKED'), 1),
                 ('stale commit', dict(approved, commit_sha='old'), 1), ('other pipeline', dict(approved, pipeline_id='122'), 1),
                 ('wrong environment', dict(approved, environment='dev'), 1), ('one approval', dict(approved, approvals_count=1), 1),
                 ('no change', dict(approved, change_ticket=None), 1)]
        for name, record, expected in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                if record is not None:
                    (Path(tmp) / 'gate-decision.json').write_text(json.dumps(record))
                env = dict(os.environ, CI_PROJECT_DIR=tmp, CI_COMMIT_SHA='abc', CI_PIPELINE_ID='123', DEPLOY_ENV='prod', TF_ENV='prod')
                result = subprocess.run([sys.executable, '-c', program], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stderr)

if __name__ == '__main__':
    unittest.main(verbosity=2)
