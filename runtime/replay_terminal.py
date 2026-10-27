#!/usr/bin/env python3
"""Replay trusted terminal evidence only; never executes Terraform."""
import argparse
import json
from pathlib import Path
import control

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='Trusted control-config JSON')
    parser.add_argument('--evidence', required=True, help='Downloaded protected apply-job artifact directory')
    parser.add_argument('--expected-job-id', required=True)
    args = parser.parse_args()
    cfg = control.read(args.config)
    base = Path(args.evidence)
    result = control.read(base / 'result.json')
    record = control.read(base / 'audit.json')
    control.validate_record(record)
    control.require(result['record'] == record and record['job_id'] == args.expected_job_id, 'Evidence/job identity mismatch')
    control.require(record['outcome'] == ('success' if result['exit_code'] == 0 else 'failure'), 'Outcome/exit code mismatch')
    control.require(control.sha(base / 'apply.log') == result['apply_log_hash'], 'Apply log hash mismatch')
    target = dict(cfg['environments'][record['environment']], environment=record['environment'])
    control.storage_check(cfg, target)  # Requires existing approved az login in the correct cloud.
    prefix = result['blob_prefix']
    control.require(prefix.startswith(record['environment'] + '/' + record['module'] + '/'), 'Unexpected blob prefix')
    control.upload(cfg, base / 'result.json', prefix + '/result.json')
    control.upload(cfg, base / 'audit.json', prefix + '/audit.json')
    print('Terminal evidence delivered without running infrastructure commands')

if __name__ == '__main__':
    main()
