import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gate', ROOT / 'scripts/approval_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA = 'a' * 40


class FakeAPI:
    def __init__(self, count=2, description='Approved under INC8747347', author=10):
        self.mr = dict(iid=8, state='merged', target_branch='main', target_project_id=1,
                       sha=SHA, merge_commit_sha=SHA, squash_commit_sha=None,
                       description=description, author=dict(id=author))
        self.approvals = {'approved_by': [{'user': {'id': i + 20}} for i in range(count)]}
        self.lookup = [self.mr]

    def get(self, path):
        if '/repository/commits/' in path:
            return self.lookup
        if path.endswith('/approvals'):
            return self.approvals
        return self.mr


class GateTests(unittest.TestCase):
    def evaluate(self, api=None, branch='main', **extra):
        env = dict(CI_COMMIT_BRANCH=branch, CI_COMMIT_SHA=SHA, CI_PROJECT_ID='1', CI_PIPELINE_ID='9')
        env.update(extra)
        return gate.evaluate(env, lambda _: api or FakeAPI())

    def test_auto_approval_no_api(self):
        def forbidden(_):
            raise AssertionError('API must not be required for lower environments')
        for branch in ('dev', 'dev_feature', 'sandbox', 'sandbox_fix'):
            result = gate.evaluate({'CI_COMMIT_BRANCH': branch}, forbidden)
            self.assertEqual(result['outcome'], 'approved')
            self.assertIn('Auto-approval', result['reason'])

    def test_uat_requires_one(self):
        for count in (0, 1):
            api = FakeAPI(count, description='No change number needed')
            api.mr['target_branch'] = 'uat_feature'
            d = self.evaluate(api, branch='uat_feature')
            self.assertEqual(d['outcome'], 'approved' if count else 'blocked')
            self.assertEqual(d['approvals_required'], 1)
            self.assertEqual(d['approvals_found'], count)
            if not count:
                self.assertIn('0 independent approvals found; 1 required', d['reason'])

    def test_production_matrix(self):
        for count in (0, 1, 2, 3):
            for desc in ('INC8747347', '', 'XINC8747347', 'INC87473478', 'CHG0012345'):
                d = self.evaluate(FakeAPI(count, desc))
                self.assertEqual(d['outcome'], 'approved' if count >= 2 and desc == 'INC8747347' else 'blocked')
                self.assertEqual(d['change_record_present'], desc == 'INC8747347')
                if count < 2:
                    self.assertIn(f'{count} independent approvals found; 2 required', d['reason'])
                if desc != 'INC8747347':
                    self.assertIn('ServiceNow', d['reason'])

    def test_independent_reviewers(self):
        api = FakeAPI()
        api.approvals['approved_by'] = [{'user': {'id': n}} for n in (10, 20, 20)]
        d = self.evaluate(api)
        self.assertEqual(d['approvals_found'], 1)
        self.assertEqual(d['outcome'], 'blocked')

    def test_missing_ambiguous_stale_and_foreign_mr(self):
        for kind in ('missing', 'ambiguous', 'stale', 'foreign', 'wrong_branch', 'unmerged'):
            api = FakeAPI()
            if kind == 'missing': api.lookup = []
            if kind == 'ambiguous': api.lookup = [api.mr, copy.deepcopy(api.mr)]
            if kind == 'stale': api.mr.update(sha='b' * 40, merge_commit_sha='b' * 40)
            if kind == 'foreign': api.mr['target_project_id'] = 2
            if kind == 'wrong_branch': api.mr['target_branch'] = 'dev'
            if kind == 'unmerged': api.mr['state'] = 'opened'
            with self.subTest(kind=kind):
                self.assertEqual(self.evaluate(api)['outcome'], 'blocked')

    def test_direct_mr_context_checks(self):
        api = FakeAPI()
        api.mr['state'] = 'opened'
        self.assertEqual(self.evaluate(api, CI_MERGE_REQUEST_IID='8', CI_MERGE_REQUEST_TARGET_BRANCH_NAME='main')['outcome'], 'approved')
        api.mr['sha'] = 'b' * 40
        self.assertEqual(self.evaluate(api, CI_MERGE_REQUEST_IID='8')['outcome'], 'blocked')

    def test_api_failure_and_malformed_payload(self):
        for error in (TimeoutError(), PermissionError(), json.JSONDecodeError('bad', '', 0)):
            with patch.object(FakeAPI, 'get', side_effect=error):
                d = self.evaluate(FakeAPI())
                self.assertEqual(d['outcome'], 'blocked')
                self.assertIn('Cannot verify', d['reason'])
        api = FakeAPI()
        api.approvals = {'approved_by': None}
        self.assertEqual(self.evaluate(api)['outcome'], 'blocked')

    def test_unknown_environment_and_missing_token(self):
        for branch in ('STR_230', 'production', '', 'development', 'sandboxevil'):
            self.assertEqual(self.evaluate(branch=branch)['outcome'], 'blocked')
        d = gate.evaluate(dict(CI_COMMIT_BRANCH='main', CI_API_V4_URL='https://gitlab.test/api/v4'))
        self.assertEqual(d['outcome'], 'blocked')
        self.assertIn('TOKEN', d['reason'])

    def test_real_http_errors_block(self):
        env = dict(CI_COMMIT_BRANCH='main', CI_API_V4_URL='https://gitlab.test/api/v4',
                   CI_PROJECT_ID='1', CI_COMMIT_SHA=SHA, APPROVAL_GATE_TOKEN='secret-test-token')
        for code in (401, 403, 404, 429, 500):
            error = gate.urllib.error.HTTPError('https://gitlab.test', code, 'error', {}, None)
            with patch.object(gate.urllib.request.OpenerDirector, 'open', side_effect=error):
                d = gate.evaluate(env)
                self.assertEqual(d['outcome'], 'blocked')
                self.assertNotIn('secret-test-token', json.dumps(d))

    def test_main_writes_blocked_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run([__import__('sys').executable, str(ROOT / 'scripts/approval_gate.py')],
                                    env={**os.environ, 'CI_PROJECT_DIR': temp, 'CI_COMMIT_BRANCH': 'unknown'}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            d = json.loads((Path(temp) / 'reports/approval/gate-decision.json').read_text())
            self.assertEqual(d['outcome'], 'blocked')
            self.assertIn('approvals_found', d)
            self.assertIn('change_record_present', d)

    def test_runtime_and_pipeline_wiring(self):
        text = (ROOT / 'iac/.iac_gates_job.yml').read_text()
        embedded = text.split("<<'STR222_PY'\n", 1)[1].split('      STR222_PY\n', 1)[0]
        self.assertEqual('\n'.join(line[6:] if line else '' for line in embedded.splitlines()) + '\n',
                         (ROOT / 'scripts/approval_gate.py').read_text())
        self.assertIn('allow_failure: false', text)
        self.assertIn('when: manual', text)
        self.assertIn('when: on_success', text)
        self.assertIn('when: always', text)
        self.assertNotIn('ls -la', text)
        template = (ROOT / 'template-workflow/.iac_module_template.yml').read_text()
        stages = template.split('stages:', 1)[1]
        self.assertLess(stages.index('iac_approval'), stages.index('iac_apply'))
        apply = (ROOT / 'iac/.iac_tf_apply.yml').read_text()
        self.assertNotIn('needs:', apply)


if __name__ == '__main__':
    unittest.main()
