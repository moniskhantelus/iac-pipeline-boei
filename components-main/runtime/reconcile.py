#!/usr/bin/env python3
"""Read-only completeness monitor. Unresolved outcome is never invented from a job status."""
import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

def az(args):
    process = subprocess.run(['az'] + args, capture_output=True, text=True)
    if process.returncode:
        raise SystemExit('Audit enumeration failed; cannot report complete evidence: ' + process.stderr)
    return process.stdout

def missing(names, now, age):
    names = set(names)
    issues = []
    for name in sorted(names):
        if not name.endswith('/intent.json'):
            continue
        prefix = name[:-len('intent.json')]
        # Read timestamp from intent, not path; retries can have different dates.
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'intent.json'
            az(['storage', 'blob', 'download', '--account-name', ARGS.account, '--container-name', ARGS.container,
                '--name', name, '--file', str(dest), '--auth-mode', 'login', '--no-progress', '--only-show-errors', '-o', 'none'])
            intent = json.loads(dest.read_text())
        timestamp = dt.datetime.strptime(intent['timestamp'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc)
        if (now - timestamp).total_seconds() < age * 60:
            continue
        absent = [leaf for leaf in ('result.json', 'audit.json') if prefix + leaf not in names]
        if absent:
            issues.append(dict(intent=name, missing=absent, apply_job_id=intent.get('apply_job_id'), outcome='unknown', action='Investigate job and Terraform state; replay saved terminal artifacts when trustworthy. Do not reapply automatically.'))
    return issues

def main():
    global ARGS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True)
    parser.add_argument('--container', default='audit')
    parser.add_argument('--prefix', default='')
    parser.add_argument('--older-than-minutes', type=int, default=30)
    ARGS = parser.parse_args()
    if ARGS.older_than_minutes < 0:
        parser.error('age must be nonnegative')
    names = json.loads(az(['storage', 'blob', 'list', '--account-name', ARGS.account, '--container-name', ARGS.container,
        '--prefix', ARGS.prefix, '--auth-mode', 'login', '--num-results', '*', '--query', '[].name', '-o', 'json', '--only-show-errors']))
    issues = missing(names, dt.datetime.now(dt.timezone.utc), ARGS.older_than_minutes)
    print(json.dumps(dict(outcome='INCOMPLETE' if issues else 'COMPLETE', unresolved=issues), indent=2))
    return 1 if issues else 0

if __name__ == '__main__':
    sys.exit(main())
