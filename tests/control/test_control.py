import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
c = load('control', ROOT / 'runtime/control.py')
query_path = ROOT / 'runtime/query_audit.py'
if not query_path.exists():
    query_path = ROOT / 'templates/compliance-gates/audit-record/query_audit.py'
q = load('query', query_path)

class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.original = Path.cwd(); os.chdir(self.temp.name); self.addCleanup(os.chdir, self.original)
        self.policy = dict(project_id='42', api_url='https://git.example/api/v4', azure_cloud='AzureUSGovernment', arm_environment='usgovernment', schema_contract='provisional-v1', schema_approved=True, change_pattern_confirmed=True,
            audit=dict(account='auditaccount', container='audit', subscription_id='audit-sub', resource_group='audit-rg', allow_draft_lower_env=False),
            environments={})
        for env, branch in [('dev','dev'),('sandbox','sandbox'),('uat','uat'),('prod','main')]:
            self.policy['environments'][env] = dict(branches=[branch], root='.', module='network', subscription_id='target-sub', identity_client_id='client', plan_identity_client_id='read-only-client', backend_resource_group='state-rg', state_account='stateaccount', state_container='tfstate', state_key=env+'/network.tfstate', eligible_approver_ids=[10,20,30])
        self.save_policy()
        self.env = dict(CI_COMMIT_REF_PROTECTED='true', CI_PIPELINE_SOURCE='push', CI_COMMIT_BRANCH='main', CONTROL_ENV='prod', CONTROL_CONFIG_FILE=str(Path('policy.json').resolve()), CI_PROJECT_ID='42', CI_API_V4_URL='https://git.example/api/v4', CI_COMMIT_SHA='a'*40, CI_PROJECT_DIR=self.temp.name, CI_PIPELINE_ID='100', CI_JOB_ID='200', GITLAB_USER_LOGIN='trigger', CI_PROJECT_PATH='group/project', CI_JOB_IMAGE='registry/control@sha256:'+'b'*64, GITLAB_APPROVAL_TOKEN='not-a-real-token')
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, self.env, clear=True).start()
        patch('sys.stdout', new=io.StringIO()).start()
        self.mr = dict(iid=7, state='merged', target_project_id=42, target_branch='main', merge_commit_sha='a'*40, squash_commit_sha=None, author={'id':1}, description='Approved CHG1234567')
        self.approvers = [{'user':dict(id=i,state='active',bot=False)} for i in [10,20]]
        self.settings = dict(reset_approvals_on_push=True,merge_requests_author_approval=False,merge_requests_disable_committers_approval=True,disable_overriding_approvers_per_merge_request=True)
        self.api_calls=[]
    def save_policy(self):
        Path('policy.json').write_text(json.dumps(self.policy))
    def mock_api(self, cfg, endpoint):
        self.api_calls.append(endpoint)
        if endpoint == '/approvals': return self.settings
        if endpoint.startswith('/repository/commits/'): return [self.mr]
        if endpoint.endswith('/approvals'): return {'approved_by':self.approvers}
        return self.mr
    def approve(self):
        cfg,target=c.config()
        with patch.object(c,'api',side_effect=self.mock_api):return c.approval(cfg,target)
    def seed_apply(self):
        cfg,target=c.config(); base=c.paths(); (base/'plan.tfplan').write_bytes(b'reviewed plan')
        manifest=c.metadata(cfg,target,base/'plan.tfplan','apply');c.write(base/'plan-manifest.json',manifest)
        c.write(base/'gate-decision.json',dict(outcome='APPROVED',plan_hash=manifest['plan_hash'],pipeline_id='100',operation='apply',commit_sha='a'*40))
        return cfg,target
    def test_dev_prod_mismatch_blocks(self):
        os.environ['CI_COMMIT_BRANCH']='dev'
        with self.assertRaises(c.Blocked):c.config()
    def test_empty_env_blocks(self):
        os.environ['CONTROL_ENV']=''
        with self.assertRaises(c.Blocked):c.config()
    def test_ambiguous_mapping_blocks(self):
        self.policy['environments']['dev']['branches']=['main'];self.save_policy()
        with self.assertRaises(c.Blocked):c.config()
    def test_unprotected_ref_blocks(self):
        os.environ['CI_COMMIT_REF_PROTECTED']='false'
        with self.assertRaises(c.Blocked):c.config()
    def test_unpinned_image_blocks(self):
        os.environ['CI_JOB_IMAGE']='registry/control:latest'
        with self.assertRaises(c.Blocked):c.config()
    def test_wrong_project_blocks(self):
        os.environ['CI_PROJECT_ID']='99'
        with self.assertRaises(c.Blocked):c.config()
    def test_state_account_reuse_blocks(self):
        self.policy['audit']['account']='stateaccount';self.save_policy()
        with self.assertRaises(c.Blocked):c.config()
    def test_schema_unapproved_blocks(self):
        self.policy['schema_approved']=False;self.save_policy()
        with self.assertRaises(c.Blocked):c.config()
    def test_path_escape_blocks(self):
        self.policy['environments']['prod']['root']='..';self.save_policy()
        with self.assertRaises(c.Blocked):c.config()
    def test_lower_auto_without_api(self):
        for env in ('dev','sandbox'):
            os.environ.update(CI_COMMIT_BRANCH=env,CONTROL_ENV=env)
            cfg,target=c.config()
            with patch.object(c,'api',side_effect=AssertionError('unexpected API')):
                self.assertEqual(c.approval(cfg,target)['outcome'],'APPROVED')
    def test_prod_accepts_two_independent_reviewers(self):
        self.assertEqual(self.approve()['approvals_found'],2)
    def test_uat_accepts_one(self):
        os.environ.update(CI_COMMIT_BRANCH='uat',CONTROL_ENV='uat');self.mr['target_branch']='uat';self.approvers=self.approvers[:1];self.mr['description']=''
        self.assertEqual(self.approve()['outcome'],'APPROVED')
    def test_uat_zero_blocks(self):
        os.environ.update(CI_COMMIT_BRANCH='uat',CONTROL_ENV='uat');self.mr['target_branch']='uat';self.approvers=[]
        with self.assertRaisesRegex(c.Blocked,'require 1'):self.approve()
    def test_prod_one_blocks(self):
        self.approvers=self.approvers[:1]
        with self.assertRaisesRegex(c.Blocked,'require 2'):self.approve()
    def test_duplicate_reviewer_does_not_count_twice(self):
        self.approvers=[self.approvers[0],self.approvers[0]]
        with self.assertRaises(c.Blocked):self.approve()
    def test_author_inactive_bot_and_unlisted_do_not_count(self):
        self.approvers=[{'user':dict(id=1,state='active')},{'user':dict(id=10,state='blocked')},{'user':dict(id=20,state='active',bot=True)},{'user':dict(id=99,state='active')}]
        with self.assertRaises(c.Blocked):self.approve()
    def test_no_chg_or_oversized_tokens_block(self):
        for desc in ['', 'CHG123456789', 'XCHG1234567', 'CHG1234567_']:
            self.mr['description']=desc
            with self.assertRaisesRegex(c.Blocked,'ServiceNow'):self.approve()
    def test_wrong_commit_blocks(self):
        self.mr['merge_commit_sha']='c'*40
        with self.assertRaises(c.Blocked):self.approve()
    def test_wrong_target_blocks(self):
        self.mr['target_branch']='other'
        with self.assertRaises(c.Blocked):self.approve()
    def test_open_mr_does_not_authorize_deployed_commit(self):
        self.mr['state']='opened'
        with self.assertRaises(c.Blocked):self.approve()
    def test_approval_reset_must_be_enabled(self):
        self.settings['reset_approvals_on_push']=False
        with self.assertRaises(c.Blocked):self.approve()
    def test_api_failure_logs_block(self):
        cfg,target=c.config()
        with patch.object(c,'api',side_effect=c.Blocked('HTTP 403')):
            with self.assertRaises(c.Blocked):c.approval(cfg,target)
        self.assertEqual(c.read('control-evidence/gate-decision.json')['outcome'],'BLOCKED')
    def test_malformed_approval_schema_blocks(self):
        self.approvers=[None]
        with self.assertRaises(c.Blocked):self.approve()
    def test_plan_tampering_blocks(self):
        cfg,target=self.seed_apply();Path('control-evidence/plan.tfplan').write_bytes(b'changed')
        with self.assertRaisesRegex(c.Blocked,'plan_hash'):c.bound_plan(cfg,target,'apply')
    def test_cross_pipeline_plan_blocks(self):
        cfg,target=self.seed_apply();os.environ['CI_PIPELINE_ID']='other'
        with self.assertRaisesRegex(c.Blocked,'pipeline_id'):c.bound_plan(cfg,target,'apply')
    def test_missing_gate_blocks(self):
        cfg,target=self.seed_apply();Path('control-evidence/gate-decision.json').unlink()
        with self.assertRaises(FileNotFoundError):c.apply_command(cfg,target,'apply')
    def test_audit_intent_failure_prevents_mutation(self):
        cfg,target=self.seed_apply()
        with patch.object(c,'approval',return_value={'mr_ref':'7'}),patch.object(c,'login'),patch.object(c,'storage_check'),patch.object(c,'upload',side_effect=c.Blocked('offline')),patch.object(c,'init') as init:
            with self.assertRaises(c.Blocked):c.apply_command(cfg,target,'apply')
            init.assert_not_called()
    def test_success_failure_and_misleading_output_use_real_exit_code(self):
        for rc in (0,1,42):
            cfg,target=self.seed_apply()
            def execute(*args,**kwargs):
                Path('control-evidence/apply.log').write_text('Apply complete (misleading arbitrary text)\n')
                return rc
            with patch.object(c,'approval',return_value={'mr_ref':'7'}),patch.object(c,'login'),patch.object(c,'storage_check'),patch.object(c,'upload') as upload,patch.object(c,'init'),patch.object(c,'run',side_effect=execute):
                self.assertEqual(c.apply_command(cfg,target,'apply'),rc)
                self.assertEqual(c.read('control-evidence/audit.json')['outcome'],'success' if rc==0 else 'failure')
                self.assertEqual(c.read('control-evidence/result.json')['exit_code'],rc)
                self.assertEqual(c.read('control-evidence/audit.json')['job_id'],'200')
                self.assertEqual(upload.call_count,3)
    def test_setup_failure_has_terminal_failure(self):
        cfg,target=self.seed_apply()
        with patch.object(c,'approval',return_value={'mr_ref':'7'}),patch.object(c,'login'),patch.object(c,'storage_check'),patch.object(c,'upload'),patch.object(c,'init',side_effect=c.Blocked('backend failed')):
            self.assertEqual(c.apply_command(cfg,target,'apply'),1)
        self.assertEqual(c.read('control-evidence/audit.json')['outcome'],'failure')
    def test_production_unlocked_policy_blocks(self):
        cfg,target=c.config()
        with patch.object(c,'run',return_value=subprocess.CompletedProcess([],0,json.dumps({'properties':{'state':'Unlocked','immutabilityPeriodSinceCreationInDays':730}}),'')):
            with self.assertRaises(c.Blocked):c.storage_check(cfg,target)
    def test_lower_draft_requires_explicit_opt_in(self):
        cfg,target=c.config();target['environment']='dev'
        with patch.object(c,'run',return_value=subprocess.CompletedProcess([],0,json.dumps({'state':'Unlocked','immutabilityPeriodSinceCreationInDays':730}),'')):
            with self.assertRaises(c.Blocked):c.storage_check(cfg,target)
            cfg['audit']['allow_draft_lower_env']=True;c.storage_check(cfg,target)
    def test_schema_names_and_values_are_validated(self):
        record=dict(actor='actor',commit_sha='a'*40,plan_hash='b'*64,timestamp='2026-10-27T01:02:03Z',environment='prod',module='network',outcome='success',pipeline_id='1',job_id='2',project_path='group/project',mr_ref='7')
        c.validate_record(record)
        for bad in [dict(record,plan_hash='unavailable'),dict(record,actor=''),dict(record,extra='x')]:
            with self.assertRaises(c.Blocked):c.validate_record(bad)
    def test_date_end_excludes_next_midnight(self):
        args=type('Args',(),dict(environment=None,module=None,actor=None,outcome=None))()
        self.assertFalse(q._matches({'timestamp':'2026-10-28T00:00:00Z'},args,None,q._parse_date('2026-10-27')))
        self.assertTrue(q._matches({'timestamp':'2026-10-27T23:59:59Z'},args,None,q._parse_date('2026-10-27')))
    def test_query_rejects_nonobject_and_missing_fields(self):
        for raw in ['[]','null','{"actor":"x"}','{invalid']:
            with self.assertRaises(SystemExit):q._load_json(raw,'fixture')
    def test_query_requests_all_azure_pages(self):
        calls=[]
        with patch.object(q,'_az',side_effect=lambda args: calls.append(args) or '[]'):
            self.assertEqual(list(q._collect_azure('auditaccount','audit','')),[])
        self.assertIn('*',calls[0]);self.assertIn('--num-results',calls[0])
    def test_pagination_reads_all_gitlab_pages(self):
        with patch.object(c,'api',side_effect=[[{}]*100,[{}]*2]) as api:
            self.assertEqual(len(c.pages(self.policy,'/test')),102)
            self.assertIn('page=2',api.call_args[0][1])
    def test_http_403_fails_without_retry_or_leaking_token(self):
        import urllib.error
        exc=urllib.error.HTTPError('https://git.example',403,'Forbidden',{},None)
        self.addCleanup(exc.close)
        with patch.object(c.urllib.request.OpenerDirector,'open',side_effect=exc) as request:
            with self.assertRaisesRegex(c.Blocked,'HTTP 403'):c.api(self.policy,'/approvals')
            self.assertEqual(request.call_count,1)
    def test_terminal_upload_failure_retains_replay_artifact(self):
        cfg,target=self.seed_apply()
        with patch.object(c,'approval',return_value={'mr_ref':'7'}),patch.object(c,'login'),patch.object(c,'storage_check'),patch.object(c,'upload',side_effect=[None,c.Blocked('outage')]),patch.object(c,'init'),patch.object(c,'run',return_value=0):
            with self.assertRaises(c.Blocked):c.apply_command(cfg,target,'apply')
        self.assertEqual(c.read('control-evidence/result.json')['exit_code'],0)
    def test_redirect_cannot_forward_api_token(self):
        with self.assertRaisesRegex(c.Blocked,'redirects'):
            c.NoRedirect().redirect_request(None,None,302,'Moved',{},'https://other.example')
    def test_plan_and_apply_identity_cannot_match(self):
        self.policy['environments']['prod']['plan_identity_client_id']='client';self.save_policy()
        with self.assertRaisesRegex(c.Blocked,'different identities'):c.config()
    def test_plan_refuses_approval_token(self):
        cfg,target=c.config()
        with self.assertRaisesRegex(c.Blocked,'approval API credential'):c.plan_command(cfg,target,'apply')
    def terminal_fixture(self, rc=0):
        base=c.paths(); log=base/'apply.log';log.write_text('actual apply transcript')
        record=dict(actor='actor',commit_sha='a'*40,plan_hash='b'*64,timestamp='2026-10-28T01:02:03Z',environment='prod',module='network',outcome='success' if rc==0 else 'failure',pipeline_id='100',job_id='200',project_path='group/project',mr_ref='7')
        attempt='200-'+'c'*32
        result=dict(kind='result',record=record,exit_code=rc,operation='apply',apply_log_hash=c.sha(log),attempt=attempt,blob_prefix='prod/network/2026/10/28/42/100/'+attempt)
        return result,record,log
    def test_terminal_record_validates_success_and_failure(self):
        for rc in (0,1,42):
            result,record,log=self.terminal_fixture(rc)
            c.validate_terminal(result,record,log,'42')
    def test_terminal_rejects_outcome_exit_code_mismatch(self):
        result,record,log=self.terminal_fixture(42);record['outcome']='success'
        with self.assertRaisesRegex(c.Blocked,'exit code'):c.validate_terminal(result,record,log,'42')
    def test_terminal_rejects_boolean_and_string_exit_codes(self):
        for rc in (True,'0',None):
            result,record,log=self.terminal_fixture();result['exit_code']=rc
            with self.assertRaises(c.Blocked):c.validate_terminal(result,record,log,'42')
    def test_terminal_rejects_changed_apply_log(self):
        result,record,log=self.terminal_fixture();log.write_text('modified transcript')
        with self.assertRaisesRegex(c.Blocked,'hash mismatch'):c.validate_terminal(result,record,log,'42')
    def test_terminal_rejects_wrong_project_pipeline_and_attempt_paths(self):
        for source,replacement in [('/42/','/99/'),('/100/','/101/'),('200-','201-')]:
            result,record,log=self.terminal_fixture();result['blob_prefix']=result['blob_prefix'].replace(source,replacement)
            with self.assertRaises(c.Blocked):c.validate_terminal(result,record,log,'42')
    def test_terminal_rejects_invalid_date(self):
        result,record,log=self.terminal_fixture();result['blob_prefix']=result['blob_prefix'].replace('/10/','/99/')
        with self.assertRaisesRegex(c.Blocked,'path date'):c.validate_terminal(result,record,log,'42')
    def test_query_environment_module_actor_and_date_filters(self):
        record={'environment':'prod','module':'network','actor':'reviewer','timestamp':'2026-10-28T12:00:00Z'}
        filters=dict(environment='prod',module='network',actor='reviewer',outcome=None)
        args=type('Args',(),filters)()
        self.assertTrue(q._matches(record,args,q._parse_date('2026-10-28'),q._parse_date('2026-10-28')))
        for field in ('environment','module','actor'):
            mismatch=type('Args',(),filters|{field:'other'})()
            self.assertFalse(q._matches(record,mismatch,None,None))
    def test_api_null_approvals_blocks(self):
        self.approvers=None
        with self.assertRaisesRegex(c.Blocked,'approved_by'):self.approve()
    def test_static_credential_blocks_login(self):
        cfg,target=c.config();os.environ['ARM_CLIENT_SECRET']='not-real'
        with self.assertRaises(c.Blocked):c.login(cfg,target)

if __name__=='__main__':unittest.main()
