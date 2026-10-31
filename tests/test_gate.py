import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gate', ROOT / 'templates/compliance-gates/terraform-gate/gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

KEEP = ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP', 'HOME', 'USERPROFILE')
SHA = 'abc123def456'
API = 'https://gitlab.example/api/v4'
TOKEN = 'glpat-secret-value'
JOB_TOKEN = 'job-secret-value'


def ci_env(temp, **extra):
    """Hermetic CI environment for a prod/uat branch pipeline."""
    env = {k: os.environ[k] for k in KEEP if k in os.environ}
    env.update(CI_PROJECT_DIR=temp, CI_API_V4_URL=API, CI_PROJECT_ID='42', CI_COMMIT_SHA=SHA,
               CI_COMMIT_BRANCH='main_STR301', CI_PIPELINE_ID='101', CI_JOB_ID='202',
               CI_JOB_TOKEN=JOB_TOKEN, GATE_TOKEN=TOKEN, GATE_ENV='prod')
    env.update(extra)
    return patch.dict(os.environ, {k: v for k, v in env.items() if v is not None}, clear=True)


def http(payload, status=200):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value.status = status
    return response


def http_error(code, body=b'{"message":"401 Unauthorized"}'):
    return urllib.error.HTTPError('url', code, 'error', {}, io.BytesIO(body))


def mr(iid=12, sha=SHA, description='Deploy under CHG1234567', author='alice', target='main', **extra):
    data = dict(iid=iid, sha=sha, description=description, state='opened', source_branch='main_STR301',
                target_branch=target, author=dict(id=1, username=author))
    data.update(extra)
    return data


def approvals(*names):
    return {'approved_by': [{'user': {'id': 100 + i, 'username': n}} for i, n in enumerate(names)]}


class GateTests(unittest.TestCase):
    def run_gate(self, responses, **env):
        """Run main() with mocked urlopen; return (exit code, record, log, urlopen mock)."""
        with tempfile.TemporaryDirectory() as temp, ci_env(temp, **env), \
                patch.object(gate.urllib.request, 'urlopen', side_effect=responses) as urlopen, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            code = gate.main()
            text = (Path(temp) / 'gate-decision.json').read_text()
        self.assertNotIn(TOKEN, text + out.getvalue())
        self.assertNotIn(JOB_TOKEN, text + out.getvalue())
        return code, json.loads(text), out.getvalue(), urlopen

    def test_sandbox_and_dev_auto_approve_without_api(self):
        for env in ('sandbox', 'dev'):
            with self.subTest(env=env):
                code, record, log, urlopen = self.run_gate([], GATE_ENV=env)
                self.assertEqual((code, record['outcome'], record['required']), (0, 'APPROVED', 0))
                urlopen.assert_not_called()

    def test_invalid_environment_fails_closed(self):
        for env in ('qa', 'Prod', '', '$DEPLOY_ENV', None):
            with self.subTest(env=env):
                code, record, log, urlopen = self.run_gate([], GATE_ENV=env)
                self.assertEqual((code, record['outcome']), (1, 'BLOCKED'))
                self.assertIn('is not one of sandbox|dev|uat|prod', record['reason'])
                urlopen.assert_not_called()

    def test_uat_needs_one_approval(self):
        code, record, _, _ = self.run_gate([http([mr(description='no ticket')]), http(approvals())], GATE_ENV='uat')
        self.assertEqual((code, record['outcome'], record['required']), (1, 'BLOCKED', 1))
        self.assertIn('0 of 1 required approvals', record['reason'])
        code, record, _, _ = self.run_gate([http([mr(description='no ticket')]), http(approvals('bob'))], GATE_ENV='uat')
        self.assertEqual((code, record['outcome'], record['approvers'], record['change_ticket']), (0, 'APPROVED', ['bob'], None))
        code, record, _, _ = self.run_gate([http([mr()]), http(approvals('bob'))], GATE_ENV='uat', GATE_MIN_APPROVALS_UAT='2')
        self.assertEqual((code, record['required']), (1, 2))

    def test_prod_needs_two_approvals_and_ticket(self):
        code, record, _, _ = self.run_gate([http([mr()]), http(approvals('bob'))])
        self.assertEqual((code, record['outcome']), (1, 'BLOCKED'))
        self.assertIn('1 of 2 required approvals', record['reason'])
        code, record, _, _ = self.run_gate([http([mr(description='no ticket here')]), http(approvals('bob', 'carol'))])
        self.assertEqual((code, record['outcome']), (1, 'BLOCKED'))
        self.assertIn('no change ticket matching', record['reason'])
        code, record, _, _ = self.run_gate([http([mr()]), http(approvals('carol', 'bob'))])
        self.assertEqual((code, record['outcome'], record['approvers'], record['approvals_count']), (0, 'APPROVED', ['bob', 'carol'], 2))

    def test_default_ticket_requires_bounded_change_number(self):
        for ticket, expected in [('CHG1234567', 0), ('INC8747347', 1),
                                 ('CHG12345678', 1), ('XCHG1234567', 1)]:
            with self.subTest(ticket=ticket):
                code, _, _, _ = self.run_gate([http([mr(description='Change: ' + ticket)]), http(approvals('bob', 'carol'))])
                self.assertEqual(code, expected)

    def test_story_minima_cannot_be_lowered(self):
        for env, setting in [('prod', 'GATE_MIN_APPROVALS_PROD'), ('uat', 'GATE_MIN_APPROVALS_UAT')]:
            code, _, _, api = self.run_gate([], GATE_ENV=env, **{setting: '0'})
            self.assertEqual(code, 1)
            api.assert_not_called()

    def test_author_approval_excluded(self):
        code, record, log, _ = self.run_gate([http([mr()]), http(approvals('alice', 'bob'))])
        self.assertEqual((code, record['approvers'], record['approvals_count']), (1, ['bob'], 1))
        self.assertIn('ignoring approval by MR author alice', log)

    def test_stale_sha_blocked(self):
        code, record, _, _ = self.run_gate([http([mr(sha='0ld5ha')]), http(approvals('bob', 'carol'))])
        self.assertEqual((code, record['outcome']), (1, 'BLOCKED'))
        self.assertIn('approvals are for a different commit', record['reason'])
        self.assertIn('re-run pipeline on MR head', record['reason'])

    def test_multiple_or_no_open_mrs_fail_closed(self):
        code, record, _, _ = self.run_gate([http([mr(iid=12), mr(iid=13, target='dev')])])
        self.assertEqual((code, record['outcome']), (1, 'BLOCKED'))
        self.assertIn('multiple open merge requests', record['reason'])
        self.assertIn('!12 -> main', record['reason'])
        self.assertIn('!13 -> dev', record['reason'])
        # Same source and target is not an MR for this branch; nothing left -> blocked.
        code, record, _, _ = self.run_gate([http([mr(target='main_STR301')])])
        self.assertEqual(code, 1)
        self.assertIn('no open merge request from main_STR301', record['reason'])

    def test_mr_pipeline_uses_iid_directly(self):
        code, record, _, urlopen = self.run_gate([http(mr(iid=7)), http(approvals('bob', 'carol'))], CI_MERGE_REQUEST_IID='7', CI_COMMIT_BRANCH=None)
        self.assertEqual((code, record['mr_iid']), (0, 7))
        urls = [c.args[0].full_url for c in urlopen.call_args_list]
        self.assertEqual(urls, [API + '/projects/42/merge_requests/7', API + '/projects/42/merge_requests/7/approvals'])
        # Merged-results pipeline: compare with the MR source sha, not the merge commit.
        code, _, _, _ = self.run_gate([http(mr(iid=7)), http(approvals('bob', 'carol'))], CI_MERGE_REQUEST_IID='7',
                                      CI_COMMIT_SHA='mergecommit', CI_MERGE_REQUEST_SOURCE_BRANCH_SHA=SHA)
        self.assertEqual(code, 0)
        code, record, _, _ = self.run_gate([http(mr(iid=7, state='merged'))], CI_MERGE_REQUEST_IID='7')
        self.assertEqual(code, 1)

    def test_branch_lookup_query_and_status_logging(self):
        code, _, log, urlopen = self.run_gate([http([mr()]), http(approvals('bob', 'carol'))])
        self.assertEqual(code, 0)
        first = urlopen.call_args_list[0].args[0].full_url
        self.assertEqual(first, API + '/projects/42/merge_requests?state=opened&source_branch=main_STR301&per_page=100')
        self.assertIn('GET /projects/42/merge_requests?state=opened&source_branch=main_STR301&per_page=100 -> HTTP 200', log)
        self.assertIn('GET /projects/42/merge_requests/12/approvals -> HTTP 200', log)
        self.assertTrue(all(c.kwargs['timeout'] == 10 for c in urlopen.call_args_list))

    def test_private_token_vs_job_token_header(self):
        _, _, _, urlopen = self.run_gate([http([mr()]), http(approvals('bob', 'carol'))])
        request = urlopen.call_args_list[0].args[0]
        self.assertEqual(request.get_header('Private-token'), TOKEN)
        self.assertIsNone(request.get_header('Job-token'))
        for empty in ('', '$GATE_API_TOKEN', None):
            with self.subTest(token=empty):
                _, _, log, urlopen = self.run_gate([http([mr()]), http(approvals('bob', 'carol'))], GATE_TOKEN=empty)
                request = urlopen.call_args_list[0].args[0]
                self.assertEqual(request.get_header('Job-token'), JOB_TOKEN)
                self.assertIsNone(request.get_header('Private-token'))
                self.assertIn('falling back to CI_JOB_TOKEN', log)

    def test_401_gives_actionable_error(self):
        for token, who in ((None, 'CI_JOB_TOKEN'), (TOKEN, 'GATE_API_TOKEN')):
            for status in (401, 403):
                with self.subTest(token=token, status=status):
                    code, record, log, urlopen = self.run_gate([http_error(status)], GATE_TOKEN=token)
                    self.assertEqual((code, record['outcome']), (1, 'BLOCKED'))
                    self.assertIn(who, record['reason'])
                    self.assertIn('HTTP {}'.format(status), record['reason'])
                    self.assertIn('set masked CI variable GATE_API_TOKEN = project/group access token with read_api', record['reason'])
                    self.assertIn('-> HTTP {}'.format(status), log)
                    self.assertNotIn('unreachable', log)
                    self.assertEqual(urlopen.call_count, 1)

    def test_retry_once_then_fail_closed(self):
        code, _, log, urlopen = self.run_gate([http_error(502), http([mr()]), http(approvals('bob', 'carol'))])
        self.assertEqual((code, urlopen.call_count), (0, 3))
        self.assertIn('-> HTTP 502', log)
        code, record, _, urlopen = self.run_gate([http_error(503), http_error(503)])
        self.assertEqual((code, urlopen.call_count), (1, 2))
        self.assertIn('HTTP 503', record['reason'])
        code, record, log, urlopen = self.run_gate([TimeoutError('timed out'), urllib.error.URLError('dns')])
        self.assertEqual((code, urlopen.call_count), (1, 2))
        self.assertIn('did not respond', record['reason'])
        code, record, _, urlopen = self.run_gate([http_error(404)])
        self.assertEqual((code, urlopen.call_count), (1, 1))
        self.assertIn('HTTP 404', record['reason'])

    def test_bad_inputs_fail_closed(self):
        for env, needle in ((dict(GATE_MIN_APPROVALS_PROD='two'), 'non-negative integer'),
                            (dict(GATE_CHG_PATTERN='(CHG'), 'not a valid regex'),
                            (dict(CI_API_V4_URL=None), 'CI_API_V4_URL'),
                            (dict(GATE_TOKEN=None, CI_JOB_TOKEN=None), 'no GitLab API token')):
            with self.subTest(env=env):
                code, record, _, _ = self.run_gate([], **env)
                self.assertEqual(code, 1)
                self.assertIn(needle, record['reason'])

    def test_decision_file_contents(self):
        code, record, log, _ = self.run_gate([http([mr(description='CHG8747347')]), http(approvals('bob', 'carol'))])
        self.assertEqual(code, 0)
        self.assertEqual(set(record), {'environment', 'branch', 'commit_sha', 'pipeline_id', 'job_id', 'mr_iid', 'approvers',
                                       'approvals_count', 'required', 'change_ticket', 'outcome', 'reason', 'timestamp'})
        self.assertEqual(record['environment'], 'prod')
        self.assertEqual(record['branch'], 'main_STR301')
        self.assertEqual((record['commit_sha'], record['pipeline_id'], record['job_id'], record['mr_iid']), (SHA, '101', '202', 12))
        self.assertEqual((record['required'], record['change_ticket'], record['outcome']), (2, 'CHG8747347', 'APPROVED'))
        self.assertRegex(record['timestamp'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
        self.assertIn('[AUDIT] gate_decision environment=prod branch=main_STR301', log)
        self.assertIn('approvers=bob,carol change_ticket=CHG8747347 outcome=APPROVED', log)

    def test_token_never_leaks_even_in_error_text(self):
        # An error message that happens to contain the token is redacted everywhere.
        code, record, log, _ = self.run_gate([urllib.error.URLError('bad ' + TOKEN), urllib.error.URLError('bad ' + TOKEN)])
        self.assertEqual(code, 1)
        self.assertIn('[MASKED]', record['reason'])

    def test_embedded_template_matches_source(self):
        text = (ROOT / 'templates/compliance-gates/terraform-gate/template.yml').read_text()
        embedded = text.split("<<'STR222_GATE_PY'\n", 1)[1].rsplit('      STR222_GATE_PY', 1)[0]
        self.assertEqual(''.join(line[6:] + '\n' for line in embedded.splitlines()), (ROOT / 'templates/compliance-gates/terraform-gate/gate.py').read_text())

    def test_template_contract(self):
        text = (ROOT / 'templates/compliance-gates/terraform-gate/template.yml').read_text()
        header, job = text.split('\n---\n', 1)
        for name in ('job_name', 'stage', 'environment', 'min_approvals_uat', 'min_approvals_prod', 'chg_pattern', 'gate_image', 'gitlab_token'):
            self.assertIn('    {}:\n'.format(name), header)
        for needle in ("default: '(?<![A-Za-z0-9])CHG[0-9]{7}(?![A-Za-z0-9])'", "default: '$GATE_API_TOKEN'",
                       'ubi8minimal-azterraform/v1.9.2:26.04.15', "default: '1'", "default: '2'"):
            self.assertIn(needle, header)
        for needle in ("GATE_ENV: '$[[ inputs.environment ]]'", "if: '$GATE_ENV =~ /^(sandbox|dev)$/ || $DEPLOY_ENV =~ /^(sandbox|dev)$/'",
                       "if: '$GATE_ENV =~ /^(uat|prod)$/ || $DEPLOY_ENV =~ /^(uat|prod)$/'", 'when: manual', 'when: on_success', 'allow_failure: false',
                       'expire_in: 90 days', 'when: always', '- gate-decision.json'):
            self.assertIn(needle, job)


if __name__ == '__main__':
    unittest.main()
