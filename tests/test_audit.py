import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audit', ROOT / 'scripts/audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

KEEP = ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP', 'HOME', 'USERPROFILE')


def ci_env(temp='', **extra):
    """Hermetic CI environment (host variables such as DEPLOY_ENV never leak in)."""
    env = {k: os.environ[k] for k in KEEP if k in os.environ}
    env.update(CI_PROJECT_DIR=temp, AUDIT_STORAGE_ACCOUNT='testaudit', GITLAB_USER_LOGIN='alice',
               CI_COMMIT_SHA='abc123', CI_PIPELINE_ID='101', CI_JOB_ID='202', CI_PROJECT_NAME='aks',
               CI_PROJECT_PATH='kaas/modules/aks', CI_COMMIT_REF_NAME='dev_feature')
    env.update(extra)
    return patch.dict(os.environ, env, clear=True)


def no_terraform_show():
    return patch.object(audit.subprocess, 'run', side_effect=FileNotFoundError('terraform'))


def http(payload):
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    return response


class AuditTests(unittest.TestCase):
    def test_apply_success_failure_and_missing_plan(self):
        for code in (0, 7, None):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                plan = root / 'reports/terraform/plan.tfplan'
                plan.parent.mkdir(parents=True)
                if code is not None:
                    plan.write_bytes(b'reviewed plan')
                proc = Mock(stdout=iter(['terraform output\n']))
                proc.wait.return_value = code
                with ci_env(temp), patch.object(audit, 'login'), patch.object(audit, 'az') as az, patch.object(audit.subprocess, 'Popen', return_value=proc) as popen, no_terraform_show():
                    result = audit.apply()
                    data = json.loads((plan.parent / 'audit.json').read_text())
                    self.assertEqual(len(data), len(audit.FIELDS))
                    self.assertEqual(len(data), 19)
                    self.assertEqual(result, code if code is not None else 1)
                    self.assertEqual(data['outcome'], 'success' if code == 0 else 'failure')
                    self.assertEqual(data['operation'], 'apply')
                    self.assertEqual(data['plan_hash'], audit.hashlib.sha256(b'reviewed plan').hexdigest() if code is not None else None)
                    self.assertIn('--if-none-match', az.call_args.args)
                    self.assertIn('--overwrite', az.call_args.args)
                    self.assertIn('sha256=' + data['record_sha256'], az.call_args.args)
                    self.assertEqual(popen.call_count, 0 if code is None else 1)
                    if code is not None:
                        self.assertIn('-chdir=examples/basic', popen.call_args.args[0])

    def test_upload_failure_fails_success_preserves_failure(self):
        for code in (0, 9):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                p = root / 'reports/terraform/plan.tfplan'
                p.parent.mkdir(parents=True)
                p.write_bytes(b'plan')
                proc = Mock(stdout=iter([]))
                proc.wait.return_value = code
                with ci_env(temp), patch.object(audit, 'login', side_effect=RuntimeError('offline')), patch.object(audit.subprocess, 'Popen', return_value=proc), no_terraform_show():
                    self.assertEqual(audit.apply(), code or 1)
                    self.assertTrue((p.parent / 'audit.json').exists())

    def test_environment_mapping(self):
        for ref, expected in (('main', 'prod'), ('sandbox', 'sandbox'), ('sandbox_x', 'sandbox'),
                              ('STR_230', 'sandbox'), ('STR_230_components', 'sandbox'),
                              ('dev', 'dev'), ('dev_feature', 'dev'), ('uat_fix', 'uat')):
            with self.subTest(ref=ref), ci_env(CI_COMMIT_REF_NAME=ref):
                self.assertEqual(audit.environment(), expected)
        with ci_env(CI_COMMIT_REF_NAME='main', DEPLOY_ENV='uat'):
            self.assertEqual(audit.environment(), 'uat')
        with ci_env(CI_COMMIT_REF_NAME='main', DEPLOY_ENV='uat', AUDIT_ENVIRONMENT='shared-services'):
            self.assertEqual(audit.environment(), 'shared-services')
        # Unexpanded/empty job variable falls through to DEPLOY_ENV / branch mapping.
        with ci_env(CI_COMMIT_REF_NAME='main', AUDIT_ENVIRONMENT='$DEPLOY_ENV'):
            self.assertEqual(audit.environment(), 'prod')
        for extra in (dict(CI_COMMIT_REF_NAME='feature_x'), dict(DEPLOY_ENV='qa'), dict(CI_COMMIT_REF_NAME='STR_231')):
            with self.subTest(extra=extra), ci_env(**extra), self.assertRaises(ValueError):
                audit.environment()

    def test_invalid_environment_fails_closed_before_terraform(self):
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp) / 'reports/terraform/plan.tfplan'
            plan.parent.mkdir(parents=True)
            plan.write_bytes(b'plan')
            with ci_env(temp, CI_COMMIT_REF_NAME='feature_x'), patch.object(audit, 'az') as az, patch.object(audit.subprocess, 'Popen') as popen, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.apply(), 1)
                self.assertEqual(audit.destroy(), 1)
                popen.assert_not_called()
                az.assert_not_called()

    def test_login_cloud_name_and_prod_identity_guard(self):
        with ci_env('/tmp', AUDIT_USE_MANAGED_IDENTITY='Y', AZ_LOGIN_CSP_TYPE='AzureCloud', AZ_CSP_TYPE='Other', AUDIT_MI_CLIENT_ID='mi-id', DEPLOY_ENV='prod'), patch.object(audit, 'az') as az:
            audit.login()
            self.assertEqual(az.call_args_list[0].args, ('cloud', 'set', '--name', 'AzureCloud'))
            self.assertEqual(az.call_args_list[1].args, ('login', '--identity', '--client-id', 'mi-id'))
        with ci_env('/tmp', AUDIT_USE_MANAGED_IDENTITY='Y'), patch.object(audit, 'az') as az:
            audit.login()
            self.assertEqual(az.call_args_list[0].args, ('cloud', 'set', '--name', 'AzureUSGovernment'))
        # SP mode in prod: warning only (non-breaking), no extra az login.
        with ci_env('/tmp', DEPLOY_ENV='prod'), patch.object(audit, 'az') as az, contextlib.redirect_stderr(io.StringIO()) as err:
            audit.login()
            az.assert_not_called()
            self.assertIn('WARNING', err.getvalue())
        with ci_env('/tmp', DEPLOY_ENV='dev'), contextlib.redirect_stderr(io.StringIO()) as err:
            audit.login()
            self.assertNotIn('WARNING', err.getvalue())
        # Opt-in hard failure, enforced before terraform runs.
        with tempfile.TemporaryDirectory() as temp:
            with ci_env(temp, DEPLOY_ENV='prod', AUDIT_REQUIRE_MI='Y'), patch.object(audit.subprocess, 'Popen') as popen, contextlib.redirect_stderr(io.StringIO()):
                self.assertRaises(RuntimeError, audit.login)
                self.assertEqual(audit.destroy(), 1)
                popen.assert_not_called()

    def test_destroy_action(self):
        for code in (0, 3):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temp:
                proc = Mock(stdout=iter(['Destroy complete!\n']))
                proc.wait.return_value = code
                with ci_env(temp, TF_ROOT='modules/x', AUDIT_REPORT_DIR='out/audit', ARM_SUBSCRIPTION_ID='sub-1'), patch.object(audit, 'login'), patch.object(audit, 'az') as az, patch.object(audit.subprocess, 'Popen', return_value=proc) as popen:
                    self.assertEqual(audit.destroy(), code)
                    command = popen.call_args.args[0]
                    self.assertEqual(command[:3], ['terraform', '-chdir=modules/x', 'destroy'])
                    self.assertIn('-auto-approve', command)
                    report = Path(temp) / 'out/audit'
                    data = json.loads((report / 'audit.json').read_text())
                    self.assertEqual(data['operation'], 'destroy')
                    self.assertEqual(data['outcome'], 'success' if code == 0 else 'failure')
                    self.assertEqual(data['exit_code'], code)
                    self.assertIsNone(data['plan_hash'])
                    self.assertEqual(data['subscription_id'], 'sub-1')
                    self.assertIn('Destroy complete!', (report / 'terraform-destroy-output.txt').read_text())
                    self.assertTrue((report / 'audit-upload.txt').exists())
                    self.assertIn('--if-none-match', az.call_args.args)
        # Upload failure fails a successful destroy.
        with tempfile.TemporaryDirectory() as temp:
            proc = Mock(stdout=iter([]))
            proc.wait.return_value = 0
            with ci_env(temp), patch.object(audit, 'login', side_effect=RuntimeError('offline')), patch.object(audit.subprocess, 'Popen', return_value=proc), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.destroy(), 1)

    def test_finalize_destroy_writes_failure_record(self):
        with tempfile.TemporaryDirectory() as temp:
            with ci_env(temp), patch.object(audit, 'login'), patch.object(audit, 'az') as az:
                self.assertEqual(audit.main(['finalize', '--operation', 'destroy']), 0)
                data = json.loads((Path(temp) / 'reports/terraform/audit.json').read_text())
                self.assertEqual((data['operation'], data['outcome'], data['exit_code']), ('destroy', 'failure', 1))
                self.assertTrue((Path(temp) / 'reports/terraform/terraform-destroy-output.txt').exists())
                az.assert_called_once()

    def test_record_sha256_deterministic(self):
        with ci_env('/tmp'), no_terraform_show():
            data = audit.record(0, None)
        self.assertEqual(data['record_sha256'], audit.digest(data))
        reordered = dict(reversed(list(data.items())))
        self.assertEqual(audit.digest(reordered), data['record_sha256'])
        canonical = json.dumps({k: v for k, v in data.items() if k != 'record_sha256'}, sort_keys=True, separators=(',', ':'))
        self.assertEqual(data['record_sha256'], audit.hashlib.sha256(canonical.encode()).hexdigest())
        audit.validate(data)
        tampered = dict(data, actor='mallory')
        self.assertNotEqual(audit.digest(tampered), data['record_sha256'])
        self.assertRaises(ValueError, audit.validate, tampered)
        self.assertRegex(data['timestamp'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')

    def test_approvers_and_ticket_lookup(self):
        mrs = [{'iid': 4, 'state': 'closed', 'description': 'old'},
               {'iid': 5, 'state': 'merged', 'description': 'Deploy under CHG1234567'}]
        approvals = {'approved_by': [{'user': {'username': 'carol'}}, {'user': {'username': 'bob'}}]}
        api = dict(CI_API_V4_URL='https://gitlab.example/api/v4', CI_PROJECT_ID='42', CI_JOB_TOKEN='job-secret')
        with ci_env(**api), patch.object(audit.urllib.request, 'urlopen', side_effect=[http(mrs), http(approvals)]) as urlopen:
            self.assertEqual(audit.change_context(), (['bob', 'carol'], 'CHG1234567'))
            first, second = (c.args[0] for c in urlopen.call_args_list)
            self.assertEqual(first.full_url, 'https://gitlab.example/api/v4/projects/42/repository/commits/abc123/merge_requests')
            self.assertEqual(second.full_url, 'https://gitlab.example/api/v4/projects/42/merge_requests/5/approvals')
            self.assertEqual(first.get_header('Job-token'), 'job-secret')
            self.assertTrue(all(c.kwargs['timeout'] == 5 for c in urlopen.call_args_list))
        with ci_env(AUDIT_GITLAB_TOKEN='pat-secret', **api), patch.object(audit.urllib.request, 'urlopen', side_effect=[http([])]) as urlopen:
            self.assertEqual(audit.change_context(), ([], 'unavailable'))
            self.assertEqual(urlopen.call_args.args[0].get_header('Private-token'), 'pat-secret')
        # Failure -> "unavailable"; ticket from commit message; tokens never logged.
        with ci_env(CI_COMMIT_MESSAGE='fix for INC8747347', **api), patch.object(audit.urllib.request, 'urlopen', side_effect=urllib.error.URLError('down')), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(audit.change_context(), ('unavailable', 'INC8747347'))
            self.assertNotIn('job-secret', err.getvalue())
        with ci_env(CHANGE_TICKET='CHG7654321', **api), patch.object(audit.urllib.request, 'urlopen', side_effect=TimeoutError()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(audit.change_context(), ('unavailable', 'CHG7654321'))
        # No API configured at all: still never raises.
        with ci_env(), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(audit.change_context(), ('unavailable', 'unavailable'))

    def test_lookup_failure_never_fails_apply(self):
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp) / 'reports/terraform/plan.tfplan'
            plan.parent.mkdir(parents=True)
            plan.write_bytes(b'plan')
            proc = Mock(stdout=iter([]))
            proc.wait.return_value = 0
            with ci_env(temp, CI_API_V4_URL='https://x/api/v4', CI_PROJECT_ID='1', CI_JOB_TOKEN='t'), patch.object(audit.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('u', 403, 'Forbidden', {}, None)), patch.object(audit, 'login'), patch.object(audit, 'az'), patch.object(audit.subprocess, 'Popen', return_value=proc), no_terraform_show(), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.apply(), 0)
                self.assertEqual(json.loads((plan.parent / 'audit.json').read_text())['approvers'], 'unavailable')

    def test_resource_summary_excludes_values(self):
        shown = {'resource_changes': [
            {'address': 'azurerm_key_vault_secret.s', 'change': {'actions': ['create'], 'before': None, 'after': {'value': 'TOPSECRET'}}},
            {'address': 'azurerm_resource_group.rg', 'change': {'actions': ['update'], 'before': {'tags': 'OLDVALUE'}, 'after': {'tags': 'NEWVALUE'}}},
            {'address': 'azurerm_storage_account.sa', 'change': {'actions': ['delete', 'create'], 'before': {'k': 'BEFOREVAL'}, 'after': {'k': 'AFTERVAL'}}},
            {'address': 'azurerm_subnet.old', 'change': {'actions': ['delete'], 'before': {'x': 'GONE'}, 'after': None}},
            {'address': 'data.azurerm_client_config.c', 'change': {'actions': ['read']}},
            {'address': 'azurerm_vnet.same', 'change': {'actions': ['no-op']}}]}
        done = subprocess.CompletedProcess([], 0, stdout=json.dumps(shown), stderr='')
        with ci_env(TF_ROOT='mod'), patch.object(audit.subprocess, 'run', return_value=done) as run:
            summary = audit.resource_summary(Path('plan.tfplan'))
            self.assertEqual(run.call_args.args[0][:4], ['terraform', '-chdir=mod', 'show', '-json'])
        self.assertEqual(summary['counts'], dict(create=1, update=1, delete=1, replace=1))
        self.assertEqual(summary['addresses'], ['azurerm_key_vault_secret.s', 'azurerm_resource_group.rg',
                                                'azurerm_storage_account.sa', 'azurerm_subnet.old'])
        text = json.dumps(summary)
        for value in ('TOPSECRET', 'OLDVALUE', 'NEWVALUE', 'BEFOREVAL', 'AFTERVAL', 'GONE', 'before', 'after'):
            self.assertNotIn(value, text)
        with ci_env(), patch.object(audit.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'terraform')), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(audit.resource_summary(Path('plan.tfplan')), 'unavailable')

    def test_apply_records_resource_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp) / 'reports/terraform/plan.tfplan'
            plan.parent.mkdir(parents=True)
            plan.write_bytes(b'plan')
            proc = Mock(stdout=iter([]))
            proc.wait.return_value = 0
            shown = {'resource_changes': [{'address': 'a.b', 'change': {'actions': ['create'], 'after': {'password': 'P@ss'}}}]}
            done = subprocess.CompletedProcess([], 0, stdout=json.dumps(shown), stderr='')
            with ci_env(temp), patch.object(audit, 'login'), patch.object(audit, 'az'), patch.object(audit.subprocess, 'Popen', return_value=proc), patch.object(audit.subprocess, 'run', return_value=done):
                self.assertEqual(audit.apply(), 0)
                text = (plan.parent / 'audit.json').read_text()
                self.assertEqual(json.loads(text)['resource_changes']['addresses'], ['a.b'])
                self.assertNotIn('P@ss', text)

    def test_blob_naming(self):
        data = dict(environment='dev', module='aks', timestamp='2026-10-20T10:00:00Z', pipeline_id='101', job_id='202')
        name = audit.blob_name(data)
        self.assertRegex(name, r'^dev/aks/2026/10/20/audit-dev-101-202-[0-9a-f]{8}\.json$')
        self.assertNotEqual(name, audit.blob_name(data))
        self.assertTrue(audit.blob_name(dict(data, module='kaas/mod x')).startswith('dev/kaas-mod-x/'))

    def test_filters(self):
        data = dict(timestamp='2026-10-20T10:00:00Z', actor='alice', environment='dev', module='aks', outcome='success', operation='apply')
        args = argparse.Namespace(actor='alice', environment='dev', module='aks', outcome='success', operation='apply', start=audit.date('2026-10-20T00:00:00Z'), end=audit.date('2026-10-21T00:00:00Z'))
        self.assertTrue(audit.matches(data, args))
        for field in ('actor', 'environment', 'module', 'outcome', 'operation'):
            wrong = argparse.Namespace(**vars(args))
            setattr(wrong, field, 'other')
            self.assertFalse(audit.matches(data, wrong))
        # Legacy records (no operation field) were applies; old Namespace without new filters still works.
        legacy = {k: v for k, v in data.items() if k != 'operation'}
        self.assertTrue(audit.matches(legacy, args))
        self.assertTrue(audit.matches(data, argparse.Namespace(actor=None, environment=None, module=None, start=None, end=None)))
        self.assertTrue(audit.matches(dict(data, timestamp='2026-10-20T10:00:00.123456+00:00'), args))
        args.end = audit.date('2026-10-20T09:00:00Z')
        self.assertFalse(audit.matches(data, args))
        with self.assertRaises(argparse.ArgumentTypeError):
            audit.date('2026-10-20')

    def test_query_prefix_and_filters(self):
        records = {'dev/aks/a.json': dict(timestamp='2026-10-20T10:00:00Z', actor='alice', environment='dev', module='aks', outcome='success', operation='apply'),
                   'dev/aks/b.json': dict(timestamp='2026-10-20T11:00:00Z', actor='alice', environment='dev', module='aks', outcome='failure', operation='destroy')}

        def fake_az(*args):
            if args[2] == 'list':
                return json.dumps([{'name': n} for n in records])
            Path(args[args.index('--file') + 1]).write_text(json.dumps(records[args[args.index('--name') + 1]]))
            return ''
        for argv, prefix, expected in ((['query', '--environment', 'dev', '--module', 'aks', '--outcome', 'failure'], 'dev/aks/', ['b.json']),
                                       (['query', '--environment', 'dev', '--operation', 'apply'], 'dev/', ['a.json']),
                                       (['query', '--actor', 'alice', '--start', '2026-10-20T10:30:00Z'], None, ['b.json'])):
            with self.subTest(argv=argv), ci_env(), patch.object(audit, 'login'), patch.object(audit, 'az', side_effect=fake_az) as az, contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(audit.main(argv), 0)
                listing = az.call_args_list[0].args
                self.assertEqual(listing[listing.index('--num-results') + 1], '*')
                if prefix:
                    self.assertEqual(listing[listing.index('--prefix') + 1], prefix)
                else:
                    self.assertNotIn('--prefix', listing)
                printed = [json.loads(line) for line in out.getvalue().splitlines()]
                self.assertEqual([r['timestamp'] for r in printed], [records['dev/aks/' + n]['timestamp'] for n in expected])

    def test_schema_check(self):
        with ci_env('/tmp'), no_terraform_show(), contextlib.redirect_stderr(io.StringIO()):
            data = audit.record(0, None)
        audit.validate(data)
        for key in ('actor', 'environment', 'record_sha256', 'approvers'):
            broken = {k: v for k, v in data.items() if k != key}
            self.assertRaises(ValueError, audit.validate, broken)
        self.assertRaises(ValueError, audit.validate, dict(data, unexpected=1))
        nulled = dict(data, module=None)
        nulled['record_sha256'] = audit.digest(nulled)
        self.assertRaises(ValueError, audit.validate, nulled)
        # Fails closed: a record missing a required value is never uploaded, success becomes failure.
        with tempfile.TemporaryDirectory() as temp:
            plan = Path(temp) / 'reports/terraform/plan.tfplan'
            plan.parent.mkdir(parents=True)
            plan.write_bytes(b'plan')
            proc = Mock(stdout=iter([]))
            proc.wait.return_value = 0
            with ci_env(temp), patch.object(audit, 'az') as az, patch.object(audit.subprocess, 'Popen', return_value=proc), no_terraform_show(), contextlib.redirect_stderr(io.StringIO()):
                del os.environ['GITLAB_USER_LOGIN']
                self.assertEqual(audit.apply(), 1)
                az.assert_not_called()

    def test_immutability_check(self):
        with ci_env(), patch.object(audit, 'az') as az:
            audit.verify_immutability()
            az.assert_not_called()
        with ci_env(AUDIT_VERIFY_IMMUTABILITY='Y', AUDIT_RESOURCE_GROUP='rg'), patch.object(audit, 'az', return_value=json.dumps({'state': 'Unlocked', 'immutabilityPeriodSinceCreationInDays': 730})) as az, contextlib.redirect_stdout(io.StringIO()) as out:
            audit.verify_immutability()
            self.assertIn('state=Unlocked', out.getvalue())
            self.assertIn('immutability-policy', az.call_args.args)
            self.assertIn('rg', az.call_args.args)
        for result in (dict(return_value=''), dict(return_value=json.dumps({'state': None})), dict(side_effect=subprocess.CalledProcessError(3, 'az'))):
            with self.subTest(result=result), ci_env(AUDIT_VERIFY_IMMUTABILITY='Y'), patch.object(audit, 'az', **result), contextlib.redirect_stdout(io.StringIO()):
                self.assertRaises(RuntimeError, audit.verify_immutability)

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
        destroy = (ROOT / 'iac/.iac_tf_destroy.yml').read_text()
        for needle in ('!reference [.str230_runtime, script]', 'audit.py" destroy', 'audit.py" finalize --operation destroy',
                       'reports/terraform/audit.json', 'expire_in: 90 days', 'when: manual', 'allow_failure: true'):
            self.assertIn(needle, destroy)
        self.assertIsNone(re.search(r'^\s*terraform\s.*\sdestroy\s', destroy, re.M))
        for job in ('apply', 'destroy'):
            text = (ROOT / f'iac/.iac_tf_{job}.yml').read_text()
            self.assertIn('AUDIT_ENVIRONMENT: "$DEPLOY_ENV"', text)
            self.assertIn('AUDIT_MODULE: "$CI_PROJECT_NAME"', text)
        policy = (ROOT / 'shared-services/audit/main.tf').read_text()
        self.assertRegex(policy, r'locked\s*= false')
        self.assertRegex(policy, r'immutability_period_in_days\s*= 730')


if __name__ == '__main__':
    unittest.main()
