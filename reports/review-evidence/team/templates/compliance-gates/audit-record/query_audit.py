#!/usr/bin/env python3
"""
query_audit.py — compliance query tool for the KaaS immutable audit store (STR-230).

Searches the WORM audit container for the structured 11-field records written by the
compliance-gates/audit-record component and returns the matching records. A compliance
reviewer can filter by environment, module, date range, and/or actor.

Two sources (the filtering/formatting logic is identical for both):

  --source azure   (default) list + download records from the Azure WORM blob container,
                   using `az storage blob` with Managed Identity (--auth-mode login). No
                   static credentials. Requires the `az` CLI on PATH and an MSI/az login.
  --source local   read records from a local directory tree (the layout the component
                   writes: <env>/<module>/<YYYY/MM/DD>/<record>.json). Used by the self-test
                   and for querying downloaded pipeline artifacts offline.

Examples:
  query_audit.py --source local --path ./audit --environment prod
  query_audit.py --source local --path ./audit --module network --from 2026-10-01 --to 2026-10-31
  query_audit.py --account kaasauditsa --container audit --actor jdoe --format table

Exit codes: 0 = query ran (even if zero matches); 2 = usage/config error; 1 = backend error.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REQUIRED_FIELDS = [
    "actor", "commit_sha", "plan_hash", "timestamp", "environment", "module",
    "outcome", "pipeline_id", "job_id", "project_path", "mr_ref",
]


def _parse_date(s):
    if not s:
        return None
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise SystemExit(f"[ERROR] bad date '{s}', expected YYYY-MM-DD")


def _record_time(rec):
    ts = rec.get("timestamp", "")
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            d = dt.datetime.strptime(ts, fmt)
            return d.replace(tzinfo=dt.timezone.utc) if d.tzinfo is None else d
        except ValueError:
            continue
    return None


def _matches(rec, args, dfrom, dto):
    if args.environment and rec.get("environment") != args.environment:
        return False
    if args.module and rec.get("module") != args.module:
        return False
    if args.actor and rec.get("actor") != args.actor:
        return False
    if args.outcome and rec.get("outcome") != args.outcome:
        return False
    if dfrom or dto:
        rt = _record_time(rec)
        if rt is None:
            return False
        if dfrom and rt < dfrom:
            return False
        if dto and rt > dto + dt.timedelta(days=1):
            return False
    return True


def _load_json(text, origin):
    try:
        rec = json.loads(text)
    except json.JSONDecodeError as e:
        sys.stderr.write(f"[WARN] skipping non-JSON record {origin}: {e}\n")
        return None
    missing = [f for f in REQUIRED_FIELDS if f not in rec]
    if missing:
        sys.stderr.write(f"[WARN] record {origin} missing fields {missing}\n")
    return rec


def _collect_local(path):
    root = Path(path)
    if not root.is_dir():
        raise SystemExit(f"[ERROR] --path '{path}' is not a directory")
    for p in sorted(root.rglob("*.json")):
        rec = _load_json(p.read_text(encoding="utf-8"), str(p))
        if rec is not None:
            yield rec


def _az(args_list):
    try:
        out = subprocess.run(args_list, capture_output=True, text=True, check=True)
        return out.stdout
    except FileNotFoundError:
        raise SystemExit("[ERROR] 'az' CLI not found on PATH (needed for --source azure)")
    except subprocess.CalledProcessError as e:
        sys.stderr.write(e.stderr or "")
        raise SystemExit(1)


def _collect_azure(account, container, prefix):
    names = json.loads(_az([
        "az", "storage", "blob", "list",
        "--account-name", account, "--container-name", container,
        "--prefix", prefix or "", "--auth-mode", "login",
        "--query", "[].name", "-o", "json", "--only-show-errors",
    ]) or "[]")
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            if not name.endswith(".json"):
                continue
            dest = Path(tmp) / "rec.json"
            _az([
                "az", "storage", "blob", "download",
                "--account-name", account, "--container-name", container,
                "--name", name, "--file", str(dest),
                "--auth-mode", "login", "--no-progress", "--only-show-errors",
            ])
            rec = _load_json(dest.read_text(encoding="utf-8"), name)
            if rec is not None:
                yield rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="Query the KaaS immutable audit store (STR-230).")
    ap.add_argument("--source", choices=["azure", "local"], default="azure")
    ap.add_argument("--account", help="WORM storage account (azure source).")
    ap.add_argument("--container", default="audit", help="Audit blob container (azure source).")
    ap.add_argument("--path", help="Local audit directory (local source).")
    ap.add_argument("--environment")
    ap.add_argument("--module")
    ap.add_argument("--actor")
    ap.add_argument("--outcome", choices=["success", "failure", "unknown"])
    ap.add_argument("--from", dest="date_from", help="Start date YYYY-MM-DD (inclusive).")
    ap.add_argument("--to", dest="date_to", help="End date YYYY-MM-DD (inclusive).")
    ap.add_argument("--format", choices=["json", "table"], default="json")
    ap.add_argument("--count", action="store_true",
                    help="Print only the number of matching records (for scripts/self-tests).")
    args = ap.parse_args(argv)

    dfrom, dto = _parse_date(args.date_from), _parse_date(args.date_to)

    if args.source == "local":
        if not args.path:
            ap.error("--path is required with --source local")
        records = _collect_local(args.path)
    else:
        if not args.account:
            ap.error("--account is required with --source azure")
        # Prefix-filter server-side by environment/module when provided (query efficiency).
        prefix = ""
        if args.environment:
            prefix = args.environment + "/"
            if args.module:
                prefix += args.module + "/"
        records = _collect_azure(args.account, args.container, prefix)

    matched = [r for r in records if _matches(r, args, dfrom, dto)]
    matched.sort(key=lambda r: r.get("timestamp", ""))

    if args.count:
        print(len(matched))
        return 0

    if args.format == "table":
        print(f"{'timestamp':20} {'env':8} {'module':16} {'outcome':8} {'actor':16} commit")
        for r in matched:
            print(f"{r.get('timestamp',''):20} {r.get('environment',''):8} "
                  f"{r.get('module',''):16} {r.get('outcome',''):8} "
                  f"{r.get('actor',''):16} {r.get('commit_sha','')[:12]}")
    else:
        print(json.dumps(matched, indent=2))
    sys.stderr.write(f"[INFO] {len(matched)} record(s) matched.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
