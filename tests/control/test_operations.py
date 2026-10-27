import argparse
import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
def load(name):
 spec=importlib.util.spec_from_file_location(name,ROOT/'runtime'/f'{name}.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
r=load('reconcile');v=load('verify_worm')
class Operations(unittest.TestCase):
 def test_unresolved_intent_is_reported_unknown(self):
  r.ARGS=argparse.Namespace(account='auditaccount',container='audit')
  def az(args):
   Path(args[args.index('--file')+1]).write_text(json.dumps({'timestamp':'2026-10-27T00:00:00Z','apply_job_id':'12'}));return ''
  with patch.object(r,'az',side_effect=az):
   result=r.missing(['dev/module/path/intent.json'],dt.datetime(2026,10,27,1,tzinfo=dt.timezone.utc),30)
  self.assertEqual(result[0]['outcome'],'unknown');self.assertIn('result.json',result[0]['missing'])
 def test_complete_attempt_has_no_reconciliation_alert(self):
  r.ARGS=argparse.Namespace(account='auditaccount',container='audit')
  def az(args):
   Path(args[args.index('--file')+1]).write_text('{"timestamp":"2026-10-27T00:00:00Z"}');return ''
  with patch.object(r,'az',side_effect=az):
   self.assertEqual(r.missing(['dev/x/intent.json','dev/x/result.json','dev/x/audit.json'],dt.datetime(2026,10,27,1,tzinfo=dt.timezone.utc),30),[])
 def test_worm_verifier_rejects_unlocked_container_without_writing(self):
  with patch('sys.argv',['verify_worm.py','--account','auditaccount','--resource-group','rg','--subscription','sub']),patch.object(v,'command',return_value=subprocess.CompletedProcess([],0,'{"state":"Unlocked","immutabilityPeriodSinceCreationInDays":730}','')) as cmd:
   with self.assertRaisesRegex(SystemExit,'already locked'):v.main()
   self.assertEqual(cmd.call_count,1)
 def test_worm_verifier_does_not_accept_authorization_error(self):
  calls=[]
  def command(args,must_pass=True):
   calls.append(args)
   if 'immutability-policy' in args:return subprocess.CompletedProcess([],0,'{"state":"Locked","immutabilityPeriodSinceCreationInDays":730}','')
   if len(calls)==2:return subprocess.CompletedProcess([],0,'','')
   return subprocess.CompletedProcess([],1,'','AuthorizationPermissionMismatch')
  with patch('sys.argv',['verify_worm.py','--account','auditaccount','--resource-group','rg','--subscription','sub']),patch.object(v,'command',side_effect=command):
   with self.assertRaisesRegex(SystemExit,'acceptance FAILED'):v.main()
