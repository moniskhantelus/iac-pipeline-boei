#!/usr/bin/env python3
"""STR-230 runtime; standard library only. See STR-230.md for provisional schema."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid


def az(*args):
    return subprocess.check_output(['az', *args, '--only-show-errors'], text=True)


def login():
    # Isolate audit MI credentials from the Terraform service principal session.
    os.environ['AZURE_CONFIG_DIR'] = str(Path(os.environ['CI_PROJECT_DIR']) / '.audit-azure')
    az('cloud', 'set', '--name', os.environ.get('AZ_CSP_TYPE', 'AzureUSGovernment'))
    args = ['login', '--identity']
    if os.environ.get('AUDIT_MI_CLIENT_ID'):
        args += ['--client-id', os.environ['AUDIT_MI_CLIENT_ID']]
    az(*args)
    az('account', 'set', '--subscription', os.environ['AUDIT_SUBSCRIPTION_ID'])


def storage():
    return ['--account-name', os.environ['AUDIT_STORAGE_ACCOUNT'], '--container-name',
            os.environ.get('AUDIT_CONTAINER', 'audit'), '--auth-mode', 'login']


def record(code, plan):
    e = os.environ
    return dict(actor=e.get('GITLAB_USER_LOGIN') or e.get('GITLAB_USER_ID'),
                commit_sha=e.get('CI_COMMIT_SHA'), plan_hash=hashlib.sha256(plan.read_bytes()).hexdigest() if plan.exists() else None,
                timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
                environment=e.get('AUDIT_ENVIRONMENT') or e.get('CI_COMMIT_REF_NAME', '').split('_')[0],
                module=e.get('AUDIT_MODULE') or e.get('CI_PROJECT_PATH'),
                outcome='success' if code == 0 else 'failure',
                pipeline_id=e.get('CI_PIPELINE_ID'), job_id=e.get('CI_JOB_ID'),
                pipeline_url=e.get('CI_PIPELINE_URL'), exit_code=code)


def publish(code, plan):
    root = Path(os.environ['CI_PROJECT_DIR'])
    directory = root / 'reports/terraform'
    directory.mkdir(parents=True, exist_ok=True)
    data = record(code, plan)
    path = directory / 'audit.json'
    path.write_text(json.dumps(data, indent=2) + '\n')
    login()
    name = 'records/' + data['timestamp'][:10] + '/' + uuid.uuid4().hex + '.json'
    az('storage', 'blob', 'upload', *storage(), '--name', name, '--file', str(path),
       '--type', 'block', '--overwrite', 'false', '--if-none-match', '*', '--content-type', 'application/json')
    (directory / 'audit-upload.txt').write_text(name + '\n')


def apply():
    root = Path(os.environ['CI_PROJECT_DIR'])
    plan = root / 'reports/terraform/plan.tfplan'
    output = root / 'reports/terraform/terraform-apply-output.txt'
    output.parent.mkdir(parents=True, exist_ok=True)
    code = 1
    try:
        with output.open('w') as log:
            # Never silently regenerate the reviewed plan.
            if not plan.is_file():
                log.write('Saved plan missing; apply refused.\n')
            else:
                process = subprocess.Popen(['terraform', '-chdir=examples/basic', 'apply', '-no-color', str(plan)],
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in process.stdout:
                    log.write(line)
                    print(line, end='', flush=True)
                code = process.wait()
    finally:
        # An upload failure fails a successful apply; it never hides an apply failure.
        try:
            publish(code, plan)
        except Exception as exc:
            print('AUDIT UPLOAD FAILED; retain/reconcile local audit.json:', exc, file=sys.stderr)
            if code == 0:
                code = 1
    return code


def matches(data, args):
    stamp = dt.datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
    return (all(not getattr(args, k) or data.get(k) == getattr(args, k) for k in ('actor', 'environment', 'module'))
            and (not args.start or stamp >= args.start) and (not args.end or stamp <= args.end))


def date(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError('Use timezone-aware ISO-8601 timestamps')
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['apply', 'query', 'finalize'])
    for key in ('actor', 'environment', 'module'):
        parser.add_argument('--' + key)
    parser.add_argument('--start', type=date)
    parser.add_argument('--end', type=date)
    args = parser.parse_args()
    if args.action == 'finalize':
        root = Path(os.environ['CI_PROJECT_DIR'])
        if not (root / 'reports/terraform/audit.json').exists():
            output = root / 'reports/terraform/terraform-apply-output.txt'
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('Apply not reached: job setup failed or was interrupted.\n')
            publish(1, root / 'reports/terraform/plan.tfplan')
        return 0
    if args.action == 'apply':
        return apply()
    if args.start and args.end and args.start > args.end:
        parser.error('--start must precede --end')
    login()
    names = json.loads(az('storage', 'blob', 'list', *storage(), '--prefix', 'records/', '--num-results', '*', '-o', 'json'))
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'record.json'
        for blob in names:
            az('storage', 'blob', 'download', *storage(), '--name', blob['name'], '--file', str(path), '--overwrite', 'true')
            data = json.loads(path.read_text())
            if matches(data, args):
                print(json.dumps(data))
    return 0


if __name__ == '__main__':
    sys.exit(main())
