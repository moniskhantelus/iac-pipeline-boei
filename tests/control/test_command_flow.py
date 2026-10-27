"""Exercise actual command wrappers against local fake Azure/Terraform executables."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]

FAKE='''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]; name=Path(sys.argv[0]).name
with open(os.environ['FAKE_CALLS'],'a') as out:out.write(json.dumps([name]+args)+'\\n')
def value(key):return args[args.index(key)+1]
if name=='terraform':
 if args[0]=='plan':
  Path(next(v.split('=',1)[1] for v in args if v.startswith('-out='))).write_bytes(b'PLAN_FROM_THIS_PIPELINE')
 elif args[0]=='apply':
  if not Path(args[-1]).is_file() or Path(args[-1]).read_bytes()!=b'PLAN_FROM_THIS_PIPELINE':sys.exit(88)
  print('Apply complete (even a failing provider can print misleading text)')
  sys.exit(int(os.environ.get('FAKE_APPLY_RC','0')))
 elif args[0]=='show': print('Saved plan: add one resource')
else:
 if args[:2]==['account','show']:print(json.dumps({'id':'target-sub'}))
 elif args[:4]==['storage','container','immutability-policy','show']:
  print(json.dumps({'properties':{'state':'Locked','immutabilityPeriodSinceCreationInDays':730}}))
 elif args[:3]==['storage','blob','upload']:
  blob=value('--name'); source=Path(value('--file'))
  if os.environ.get('FAKE_DENY_INTENT')=='1' and blob.endswith('/intent.json'):sys.exit(1)
  destination=Path(os.environ['FAKE_STORE'])/blob
  if destination.exists():sys.exit(1)
  destination.parent.mkdir(parents=True,exist_ok=True);shutil_missing=None
  destination.write_bytes(source.read_bytes())
 elif args[:3]==['storage','blob','download']:
  source=Path(os.environ['FAKE_STORE'])/value('--name')
  if not source.exists():sys.exit(1)
  Path(value('--file')).write_bytes(source.read_bytes())
'''
class CommandFlow(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
  bin=self.base/'bin';bin.mkdir()
  for name in ['az','terraform']:
   f=bin/name;f.write_text(FAKE);f.chmod(0o755)
  config={'project_id':'42','api_url':'https://git.example/api/v4','azure_cloud':'AzureUSGovernment','arm_environment':'usgovernment','schema_contract':'provisional-v1','schema_approved':True,'change_pattern_confirmed':True,
   'audit':{'account':'auditaccount','container':'audit','subscription_id':'audit-sub','resource_group':'audit-rg'},
   'environments':{'dev':{'branches':['dev'],'root':'.','module':'network','subscription_id':'target-sub','identity_client_id':'client','plan_identity_client_id':'read-only-client','backend_resource_group':'state-rg','state_account':'stateaccount','state_container':'tfstate','state_key':'dev/network.tfstate','eligible_approver_ids':[]}}}
  (self.base/'config.json').write_text(json.dumps(config))
  self.env={'PATH':str(bin)+':'+os.environ['PATH'],'CI_COMMIT_REF_PROTECTED':'true','CI_PIPELINE_SOURCE':'push','CI_COMMIT_BRANCH':'dev','CONTROL_ENV':'dev','CONTROL_CONFIG_FILE':str(self.base/'config.json'),'CI_PROJECT_ID':'42','CI_API_V4_URL':config['api_url'],'CI_COMMIT_SHA':'a'*40,'CI_PROJECT_DIR':str(self.base),'CI_PIPELINE_ID':'1','CI_JOB_ID':'10','GITLAB_USER_LOGIN':'actor','CI_PROJECT_PATH':'group/project','CI_JOB_IMAGE':'registry/control@sha256:'+'b'*64,'FAKE_CALLS':str(self.base/'calls.jsonl'),'FAKE_STORE':str(self.base/'store')}
 def invoke(self,command,expected=0):
  result=subprocess.run([sys.executable,str(ROOT/'runtime/control.py'),command],cwd=self.base,env=self.env,capture_output=True,text=True)
  self.assertEqual(result.returncode,expected,result.stdout+result.stderr);return result
 def prepare(self):
  self.invoke('plan');self.env['CI_JOB_ID']='11';self.invoke('gate');self.env['CI_JOB_ID']='12'
 def test_full_success_plan_gate_apply_and_idempotent_delivery(self):
  self.prepare();self.invoke('apply');self.env['CI_JOB_ID']='13';self.invoke('deliver')
  record=json.loads((self.base/'control-evidence/audit.json').read_text())
  self.assertEqual(record['job_id'],'12');self.assertEqual(record['outcome'],'success')
  self.assertEqual(len(list((self.base/'store').rglob('intent.json'))),1)
  self.assertEqual(len(list((self.base/'store').rglob('audit.json'))),1)
  calls=[json.loads(s) for s in (self.base/'calls.jsonl').read_text().splitlines()]
  self.assertFalse(any(arg.startswith('-backend-config=client_id=') for args in calls for arg in args))
  applies=[args for args in calls if args[:2]==['terraform','apply']]
  logins=[args for args in calls if args[:3]==['az','login','--identity']]
  self.assertEqual(logins[0][logins[0].index('--client-id')+1],'read-only-client')
  self.assertEqual(logins[1][logins[1].index('--client-id')+1],'client')
  self.assertEqual(len(applies),1);self.assertEqual(applies[0][-1],str((self.base/'control-evidence/plan.tfplan').resolve()))
 def test_failed_apply_still_persists_failure(self):
  self.prepare();self.env['FAKE_APPLY_RC']='7';self.invoke('apply',7)
  record=json.loads((self.base/'control-evidence/audit.json').read_text())
  self.assertEqual(record['outcome'],'failure');self.assertEqual(len(list((self.base/'store').rglob('audit.json'))),1)
 def test_modified_plan_never_calls_apply(self):
  self.prepare();(self.base/'control-evidence/plan.tfplan').write_bytes(b'OTHER')
  self.invoke('apply',1)
  calls=(self.base/'calls.jsonl').read_text()
  self.assertNotIn('["terraform", "apply"',calls)
 def test_destroy_cannot_run_without_enable(self):
  result=subprocess.run([sys.executable,str(ROOT/'runtime/control.py'),'plan','--operation','destroy'],cwd=self.base,env=self.env,capture_output=True,text=True)
  self.assertEqual(result.returncode,1);self.assertFalse((self.base/'calls.jsonl').exists())
