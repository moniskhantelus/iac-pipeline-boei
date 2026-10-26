#!/usr/bin/env python3
"""STR-222 fail-closed approval gate. Standard library only."""
import json
import os
from pathlib import Path
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request


class Blocked(Exception):
    pass


def environment(branch):
    if branch == 'main':
        return 'production'
    prefix = branch.split('_', 1)[0]
    if prefix in ('sandbox', 'dev', 'uat'):
        return prefix
    raise Blocked('Unsupported target branch; environment cannot be confirmed')


class API:
    def __init__(self, env):
        self.base = env['CI_API_V4_URL'].rstrip('/')
        if urllib.parse.urlsplit(self.base).scheme != 'https':
            raise Blocked('GitLab API must use HTTPS')
        token = env.get('APPROVAL_GATE_TOKEN')
        if not token:
            raise Blocked('APPROVAL_GATE_TOKEN is missing; configure read_api access')
        self.token = token
        self.context = ssl.create_default_context(cafile=env.get('APPROVAL_GATE_CA_FILE') or None)

    def get(self, path):
        request = urllib.request.Request(self.base + path, headers={'PRIVATE-TOKEN': self.token})
        # Refuse redirects so credentials cannot be forwarded to a different host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=self.context))
        with opener.open(request, timeout=20) as response:
            return json.load(response)


def resolve(api, env, branch):
    project = urllib.parse.quote(env['CI_PROJECT_ID'], safe='')
    sha = env['CI_COMMIT_SHA']
    base = '/projects/' + project
    iid = env.get('CI_MERGE_REQUEST_IID')
    if iid:
        if not iid.isdigit():
            raise Blocked('Invalid merge request IID')
        mr = api.get(base + '/merge_requests/' + iid)
        if mr.get('state') != 'opened' or mr.get('sha') != sha or mr.get('target_branch') != branch:
            raise Blocked('Merge request does not match the pipeline commit and target branch')
    else:
        # Branch pipelines must deploy the actual result of a reviewed merge,
        # not any historical MR that merely contains the commit.
        candidates = []
        page = 1
        while True:
            batch = api.get(base + '/repository/commits/' + urllib.parse.quote(sha, safe='') +
                            '/merge_requests?per_page=100&page=' + str(page))
            if not isinstance(batch, list):
                raise Blocked('Invalid merge request lookup response')
            candidates.extend(x for x in batch if x.get('state') == 'merged' and
                              x.get('target_branch') == branch and x.get('target_project_id') == int(env['CI_PROJECT_ID']) and
                              sha in (x.get('merge_commit_sha'), x.get('squash_commit_sha'), x.get('sha')))
            if len(batch) < 100:
                break
            page += 1
            if page > 20:
                raise Blocked('Merge request lookup exceeded safety limit')
        if len(candidates) != 1:
            raise Blocked('Expected one merged MR matching this exact deployment commit; found ' + str(len(candidates)))
        mr = api.get(base + '/merge_requests/' + str(candidates[0]['iid']))
        if (mr.get('state') != 'merged' or mr.get('target_branch') != branch or
                sha not in (mr.get('merge_commit_sha'), mr.get('squash_commit_sha'), mr.get('sha'))):
            raise Blocked('Merge request changed during verification')
    if mr.get('target_project_id') != int(env['CI_PROJECT_ID']):
        raise Blocked('Merge request belongs to another target project')
    return base + '/merge_requests/' + str(mr['iid']), mr


def evaluate(env, get_api=API):
    decision = dict(environment='unknown', approvals_found=None, approvals_required=None,
                    change_record_present=None, outcome='blocked', reason='',
                    commit_sha=env.get('CI_COMMIT_SHA'), pipeline_id=env.get('CI_PIPELINE_ID'), merge_request_iid=None)
    try:
        branch = env.get('CI_MERGE_REQUEST_TARGET_BRANCH_NAME') or env.get('CI_COMMIT_BRANCH', '')
        target = environment(branch)
        decision['environment'] = target
        required = {'sandbox': 0, 'dev': 0, 'uat': 1, 'production': 2}[target]
        decision['approvals_required'] = required
        if required == 0:
            decision.update(approvals_found=0, change_record_present=False, outcome='approved',
                            reason='Auto-approval for ' + target + '; MR checks not required')
            return decision
        api = get_api(env)
        path, mr = resolve(api, env, branch)
        decision['merge_request_iid'] = mr['iid']
        approvals = api.get(path + '/approvals')
        entries = approvals.get('approved_by')
        if not isinstance(entries, list) or not isinstance(mr.get('author', {}).get('id'), int):
            raise Blocked('Malformed approval/author response')
        identities = set()
        for entry in entries:
            user = entry.get('user', {})
            if not isinstance(user.get('id'), int):
                raise Blocked('Malformed approval identity')
            if user['id'] != mr['author']['id']:
                identities.add(user['id'])
        count = len(identities)
        pattern = env.get('SERVICENOW_CHANGE_PATTERN', r'INC[0-9]{7}')
        present = bool(re.search(r'(?<![A-Za-z0-9_])(?:' + pattern + r')(?![A-Za-z0-9_])', mr.get('description') or ''))
        decision.update(approvals_found=count, change_record_present=present)
        errors = []
        if count < required:
            errors.append(f'{count} independent approvals found; {required} required (MR author excluded)')
        if target == 'production' and not present:
            errors.append('Valid ServiceNow change number missing from MR description')
        if errors:
            raise Blocked('; '.join(errors))
        decision.update(outcome='approved', reason='Required approvals and change-control checks passed')
    except Blocked as exc:
        decision['reason'] = str(exc)
    except Exception as exc:
        # Do not log exception text, headers, tokens or MR description.
        decision['reason'] = 'Cannot verify change control via GitLab API/configuration (' + type(exc).__name__ + ')'
    return decision


def main():
    decision = evaluate(os.environ)
    directory = Path(os.environ.get('CI_PROJECT_DIR', '.')) / 'reports/approval'
    directory.mkdir(parents=True, exist_ok=True)
    text = json.dumps(decision, indent=2)
    (directory / 'gate-decision.json').write_text(text + '\n')
    print(text)
    return 0 if decision['outcome'] == 'approved' else 1


if __name__ == '__main__':
    sys.exit(main())
