import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audit', ROOT / 'scripts/audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def test_apply_success_failure_and_missing_plan(self):
        for code in (0, 7, None):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                plan = root / 'reports/terraform/plan.tfplan'
                plan.parent.mkdir(parents=True)
                if code is not None:
                    plan.write_bytes(b'reviewed plan')
                proc = unittest.mock.Mock(stdout=iter(['terraform output\n']))
                proc.wait.return_value = code
                with patch.dict(os.environ, {'CI_PROJECT_DIR': temp, 'AUDIT_STORAGE_ACCOUNT': 'testaudit'}), patch.object(audit, 'login'), patch.object(audit, 'az') as az, patch.object(audit.subprocess, 'Popen', return_value=proc) as popen:
                    result = audit.apply()
                    data = json.loads((plan.parent / 'audit.json').read_text())
                    self.assertEqual(len(data), 11)
                    self.assertEqual(result, code if code is not None else 1)
                    self.assertEqual(data['outcome'], 'success' if code == 0 else 'failure')
                    self.assertEqual(data['plan_hash'], audit.hashlib.sha256(b'reviewed plan').hexdigest() if code is not None else None)
                    self.assertIn('--if-none-match', az.call_args.args)
                    self.assertIn('--overwrite', az.call_args.args)
                    self.assertEqual(popen.call_count, 0 if code is None else 1)

    def test_upload_failure_fails_success_preserves_failure(self):
        for code in (0, 9):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                p = root / 'reports/terraform/plan.tfplan'
                p.parent.mkdir(parents=True)
                p.write_bytes(b'plan')
                proc = unittest.mock.Mock(stdout=iter([]))
                proc.wait.return_value = code
                with patch.dict(os.environ, {'CI_PROJECT_DIR': temp, 'AUDIT_STORAGE_ACCOUNT': 'testaudit'}), patch.object(audit, 'login', side_effect=RuntimeError('offline')), patch.object(audit.subprocess, 'Popen', return_value=proc):
                    self.assertEqual(audit.apply(), code or 1)
                    self.assertTrue((p.parent / 'audit.json').exists())

    def test_filters(self):
        data = dict(timestamp='2026-10-20T10:00:00Z', actor='alice', environment='dev', module='aks')
        args = argparse.Namespace(actor='alice', environment='dev', module='aks', start=audit.date('2026-10-20T00:00:00Z'), end=audit.date('2026-10-21T00:00:00Z'))
        self.assertTrue(audit.matches(data, args))
        for field in ('actor', 'environment', 'module'):
            wrong = argparse.Namespace(**vars(args))
            setattr(wrong, field, 'other')
            self.assertFalse(audit.matches(data, wrong))
        args.end = audit.date('2026-10-20T09:00:00Z')
        self.assertFalse(audit.matches(data, args))
        with self.assertRaises(argparse.ArgumentTypeError):
            audit.date('2026-10-20')

    def test_embedded_runtime_matches_source(self):
        text = (ROOT / 'iac/.audit_runtime.yml').read_text()
        embedded = text.split("<<'STR230_PY'\n", 1)[1].rsplit('      STR230_PY', 1)[0]
        self.assertEqual(''.join(line[6:] + '\n' for line in embedded.splitlines()), (ROOT / 'scripts/audit.py').read_text())

    def test_pipeline_contract(self):
        for job in ('init', 'apply'):
            text = (ROOT / f'iac/.iac_tf_{job}.yml').read_text()
            self.assertIn('expire_in: 90 days', text)
            self.assertIn('when: always', text)
            self.assertIn('set -eo pipefail', text)
            self.assertNotIn('|| true', text)
        policy = (ROOT / 'shared-services/audit/main.tf').read_text()
        self.assertRegex(policy, r'locked\s*= false')
        self.assertRegex(policy, r'immutability_period_in_days\s*= 730')


if __name__ == '__main__':
    unittest.main()
