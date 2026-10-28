"""Consumer integration contract: unchanged team components, pipeline-owned fixes."""
import hashlib
import re
from pathlib import Path
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = '0ae47a2256c7207b1b54971d19351574314751c5de4f82fae15a2d6293fe5d6e'

class PipelineContract(unittest.TestCase):
    def test_supplied_components_archive_is_unchanged(self):
        self.assertEqual(hashlib.sha256((ROOT/'components-main.zip').read_bytes()).hexdigest(), EXPECTED)
    def test_no_modified_components_library_is_shipped(self):
        self.assertFalse((ROOT/'components-main').exists())
    def test_team_release_is_included_before_consumer_overrides(self):
        workflow=(ROOT/'template-workflow/.iac_module_template.yml').read_text()
        self.assertIn('compliance-gates/terraform-gate@0.1.2',workflow)
        self.assertIn('compliance-gates/audit-record@0.1.2',workflow)
        self.assertLess(workflow.index('compliance-gates/terraform-gate@0.1.2'),workflow.index('/iac/.iac_gates_job.yml'))
        self.assertLess(workflow.index('compliance-gates/audit-record@0.1.2'),workflow.index('/iac/.iac_audit_record.yml'))
    def test_apply_depends_on_gate_and_plan_in_consumer(self):
        source=(ROOT/'iac/.iac_tf_apply.yml').read_text()
        text=re.search(r'(?ms)^  "needs":\n(.*?)(?=^  "[^"]+":|\Z)',source).group(1)
        self.assertIn('"job": "iac_gates_job"',text)
        self.assertIn('"job": "iac_init_job"',text)
        self.assertNotIn('"optional": true',text)
    def test_component_defects_are_patched_in_consumer_not_archive(self):
        with zipfile.ZipFile(ROOT/'components-main.zip') as z:
            original=z.read('components-main/templates/compliance-gates/audit-record/template.yml').decode()
            self.assertIn('grep -q "Apply complete"',original)
        override=(ROOT/'iac/.iac_audit_record.yml').read_text()
        self.assertIn('python3 - deliver',override)
        self.assertNotIn('grep -q "Apply complete"',override)

if __name__ == '__main__':
    unittest.main()
