#!/usr/bin/env python3
"""Acceptance test only. Never locks a policy; creates a test blob retained for 730 days."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

def command(args, must_pass=True):
    result = subprocess.run(['az'] + args, capture_output=True, text=True)
    if must_pass and result.returncode:
        raise SystemExit('Azure operation failed: ' + result.stderr)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', required=True)
    parser.add_argument('--container', default='audit')
    parser.add_argument('--resource-group', required=True)
    parser.add_argument('--subscription', required=True)
    parser.add_argument('--evidence', default='worm-acceptance.json')
    args = parser.parse_args()
    policy = json.loads(command(['storage', 'container', 'immutability-policy', 'show', '--account-name', args.account,
        '--container-name', args.container, '--resource-group', args.resource_group, '--subscription', args.subscription, '-o', 'json']).stdout)
    properties = policy.get('properties', policy)
    if properties.get('state') != 'Locked' or properties.get('immutabilityPeriodSinceCreationInDays') != 730:
        raise SystemExit('Refusing test: requires already locked 730-day policy and prior legal authorization')
    blob = 'acceptance/' + uuid.uuid4().hex + '.json'
    common = ['--account-name', args.account, '--container-name', args.container, '--name', blob, '--auth-mode', 'login', '--only-show-errors']
    with tempfile.TemporaryDirectory() as tmp:
        original = Path(tmp) / 'original.json'; original.write_text('{"acceptance":"original"}\n')
        changed = Path(tmp) / 'changed.json'; changed.write_text('{"acceptance":"modified"}\n')
        command(['storage', 'blob', 'upload'] + common + ['--file', str(original), '--overwrite', 'false', '--if-none-match', '*', '-o', 'none'])
        results = {}
        for operation, extra in [('overwrite', ['upload', '--file', str(changed), '--overwrite', 'true']), ('delete', ['delete'])]:
            result = command(['storage', 'blob', extra[0]] + common + extra[1:], must_pass=False)
            code = re.search(r'\b(BlobImmutableDueToPolicy)\b', result.stderr + result.stdout)
            if result.returncode == 0 or not code:
                raise SystemExit(operation + ' did not return BlobImmutableDueToPolicy; acceptance FAILED: ' + result.stderr)
            results[operation] = code.group(1)
        downloaded = Path(tmp) / 'download.json'
        command(['storage', 'blob', 'download'] + common + ['--file', str(downloaded), '--no-progress', '-o', 'none'])
        if downloaded.read_bytes() != original.read_bytes():
            raise SystemExit('Acceptance FAILED: original record bytes changed')
        evidence = dict(account=args.account, container=args.container, blob=blob, policy=policy, tests=results,
                        sha256=hashlib.sha256(original.read_bytes()).hexdigest(), outcome='PASS')
        Path(args.evidence).write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence, indent=2))

if __name__ == '__main__':
    main()
