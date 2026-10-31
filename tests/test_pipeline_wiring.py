from pathlib import Path
import re
import unittest
ROOT = Path(__file__).resolve().parents[1]

class PipelineWiringTests(unittest.TestCase):
    def test_only_owned_local_includes(self):
        for file in [ROOT / '.gitlab-ci.yml', ROOT / 'template-workflow/.iac_module_template.yml']:
            text = file.read_text()
            self.assertIsNone(re.search(r'(?m)^\s*-\s*(component|project|remote):', text))
            for path in re.findall(r"(?m)^\s*- local: ['\"](/[^'\"]+)['\"]", text):
                self.assertTrue((ROOT / path.lstrip('/')).is_file(), path)

    def test_legacy_entrypoint_has_real_jobs_and_gate(self):
        root = (ROOT / '.gitlab-ci.yml').read_text()
        self.assertIn('/template-workflow/.iac_module_template.yml', root)
        workflow = (ROOT / 'template-workflow/.iac_module_template.yml').read_text()
        self.assertIn('/templates/compliance-gates/terraform-gate/template.yml', workflow)
        self.assertIn('job_name: iac_gates_job', workflow)
        self.assertIn('stage: iac_approval', workflow)
        self.assertIn('environment: $DEPLOY_ENV', workflow)
        stages = workflow.split('stages:', 1)[1]
        self.assertLess(stages.index('iac_init'), stages.index('iac_approval'))
        self.assertLess(stages.index('iac_approval'), stages.index('iac_apply'))
        for name in ('apply', 'destroy'):
            text = (ROOT / ('iac/.iac_tf_' + name + '.yml')).read_text()
            self.assertIn('job: iac_gates_job', text)
            self.assertIn('VERIFY_GATE_PY', text)
            self.assertNotIn('optional: true', text)
        self.assertIn('.str230/audit.py', (ROOT / 'iac/.iac_tf_apply.yml').read_text())

if __name__ == '__main__':
    unittest.main()
