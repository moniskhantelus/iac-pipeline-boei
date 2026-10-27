#!/usr/bin/env python3
"""
tf_test.py — Python-driven Terraform exercise + plan-JSON assertions.

Bridge to Terratest. Drives `terraform` via subprocess, then evaluates a declarative
assertion spec (tftest.yaml) against `terraform show -json <plan>`.

Pure standard library (no pip install): YAML spec is parsed with a tiny restricted
parser if PyYAML is unavailable, but PyYAML is used when present.

Exit codes:
  0  all assertions passed
  1  one or more assertions failed
  2  execution/setup error (terraform missing, spec invalid, etc.)
"""
import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

try:
    import yaml  # noqa
    _HAVE_YAML = True
except Exception:  # pragma: no cover - yaml nearly always present in CI image
    _HAVE_YAML = False


def log(msg):
    print(msg, flush=True)


def load_spec(path):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if _HAVE_YAML:
        return yaml.safe_load(text) or {}
    raise SystemExit("[ERROR] PyYAML not available and no fallback parser configured. "
                     "Install pyyaml in the component image.")


def run(cmd, cwd):
    log(f"[tf] $ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.stdout:
        log(proc.stdout.rstrip())
    if proc.returncode != 0:
        log(proc.stderr.rstrip())
    return proc


def terraform_plan(tf_root, spec, binary):
    """fmt -check, init -backend=false, validate, plan -> plan.json path."""
    r = run([binary, "fmt", "-check", "-recursive"], tf_root)
    if r.returncode != 0:
        raise SystemExit("[ERROR] terraform fmt -check failed")
    if run([binary, "init", "-backend=false", "-input=false"], tf_root).returncode != 0:
        raise SystemExit("[ERROR] terraform init failed")
    if run([binary, "validate"], tf_root).returncode != 0:
        raise SystemExit("[ERROR] terraform validate failed")

    plan_cmd = [binary, "plan", "-input=false", "-out=tftest.tfplan"]
    plan_cfg = spec.get("plan", {}) or {}
    if plan_cfg.get("var_file"):
        plan_cmd += ["-var-file", plan_cfg["var_file"]]
    for k, v in (plan_cfg.get("vars") or {}).items():
        plan_cmd += ["-var", f"{k}={v}"]
    if run(plan_cmd, tf_root).returncode != 0:
        raise SystemExit("[ERROR] terraform plan failed")

    show = run([binary, "show", "-json", "tftest.tfplan"], tf_root)
    if show.returncode != 0:
        raise SystemExit("[ERROR] terraform show -json failed")
    plan_json_path = os.path.join(tf_root, "plan.tftest.json")
    with open(plan_json_path, "w", encoding="utf-8") as fh:
        fh.write(show.stdout)
    return json.loads(show.stdout)


def terraform_state(tf_root, binary):
    """Post-apply mode: assert against the APPLIED state, not a fresh plan.

    Assumes the environment is already initialized + applied by the caller
    (the apply-ephemeral path in template.yml). Reads `terraform show -json`
    of current state and reshapes it to the same structure evaluate() expects
    (a `planned_values.root_module`), so the same assertion spec works against
    real applied resources. STR-299 A8: required tests run against applied state.
    """
    show = run([binary, "show", "-json"], tf_root)
    if show.returncode != 0:
        raise SystemExit("[ERROR] terraform show -json (state) failed")
    try:
        state = json.loads(show.stdout or "{}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"[ERROR] could not parse state JSON: {e}")
    # State JSON carries resources under top-level "values.root_module"; plan JSON
    # carries them under "planned_values.root_module". Normalize to the plan shape
    # so planned_resources()/evaluate() need no changes.
    values = state.get("values") or {}
    normalized = {
        "planned_values": {"root_module": values.get("root_module") or {}},
        "output_changes": {},
        "planned_outputs": values.get("outputs") or {},
    }
    normalized["planned_values"]["outputs"] = values.get("outputs") or {}
    return normalized


# --------------------------------------------------------------------------- #
# Plan-JSON helpers
# --------------------------------------------------------------------------- #
def planned_resources(plan):
    """Return list of resource dicts from planned_values root + child modules."""
    out = []

    def walk(module):
        for r in module.get("resources", []) or []:
            out.append(r)
        for child in module.get("child_modules", []) or []:
            walk(child)

    root = (plan.get("planned_values") or {}).get("root_module") or {}
    walk(root)
    return out


def resource_address(r):
    return r.get("address") or f"{r.get('type')}.{r.get('name')}"


def dotted_get(d, path):
    cur = d
    for part in path.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


# --------------------------------------------------------------------------- #
# Assertions -> list of (name, passed, message)
# --------------------------------------------------------------------------- #
def evaluate(plan, assertions):
    results = []
    resources = planned_resources(plan)
    by_addr = {resource_address(r): r for r in resources}
    types = [r.get("type") for r in resources]

    # 1. resources_present
    for addr in assertions.get("resources_present", []) or []:
        ok = addr in by_addr
        results.append((f"resource_present:{addr}", ok,
                        "present" if ok else f"resource {addr} not found in plan"))

    # 2. resource_counts
    for rtype, rule in (assertions.get("resource_counts") or {}).items():
        count = types.count(rtype)
        if "min" in rule:
            ok = count >= rule["min"]
            results.append((f"resource_count_min:{rtype}>={rule['min']}", ok,
                            f"found {count}"))
        if "exact" in rule:
            ok = count == rule["exact"]
            results.append((f"resource_count_exact:{rtype}=={rule['exact']}", ok,
                            f"found {count}"))

    # 3. required_tags (on every resource whose values carry a 'tags' map)
    req_tags = assertions.get("required_tags") or []
    if req_tags:
        for r in resources:
            vals = r.get("values") or {}
            if "tags" in vals and isinstance(vals["tags"], dict):
                missing = [t for t in req_tags if t not in vals["tags"]]
                addr = resource_address(r)
                results.append((f"required_tags:{addr}", not missing,
                                "ok" if not missing else f"missing tags {missing}"))

    # 4. forbidden_types
    for ftype in assertions.get("forbidden_types", []) or []:
        hits = [resource_address(r) for r in resources if r.get("type") == ftype]
        results.append((f"forbidden_type:{ftype}", not hits,
                        "absent" if not hits else f"found forbidden {hits}"))

    # 5. attribute_equals
    for rule in assertions.get("attribute_equals", []) or []:
        addr = rule["resource"]
        r = by_addr.get(addr)
        if not r:
            results.append((f"attribute:{addr}.{rule['path']}", False,
                            f"resource {addr} not in plan"))
            continue
        actual = dotted_get(r.get("values") or {}, rule["path"])
        allowed = rule.get("allowed")
        denied = rule.get("denied")
        ok = True
        detail = f"value={actual}"
        if allowed is not None:
            ok = actual in allowed
            detail = f"value={actual} allowed={allowed}"
        if denied is not None and actual in denied:
            ok = False
            detail = f"value={actual} is denied"
        results.append((f"attribute:{addr}.{rule['path']}", ok, detail))

    # 6. outputs_present
    planned_outputs = (plan.get("planned_values") or {}).get("outputs") or {}
    # Terraform may also report outputs at top-level "output_changes".
    output_changes = plan.get("output_changes") or {}
    known_outputs = set(planned_outputs.keys()) | set(output_changes.keys())
    for out in assertions.get("outputs_present", []) or []:
        ok = out in known_outputs
        results.append((f"output_present:{out}", ok,
                        "present" if ok else f"output {out} not declared in plan"))

    return results


def write_reports(results, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed

    # JSON
    with open(os.path.join(out_dir, "tftest-report.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "total": len(results), "passed": passed, "failed": failed,
            "assertions": [{"name": n, "passed": ok, "message": m} for n, ok, m in results],
        }, fh, indent=2)

    # JUnit
    suite = ET.Element("testsuite", name="terraform-test",
                       tests=str(len(results)), failures=str(failed))
    for name, ok, msg in results:
        case = ET.SubElement(suite, "testcase", classname="tftest", name=name)
        if not ok:
            fail = ET.SubElement(case, "failure", message=msg)
            fail.text = msg
    ET.ElementTree(suite).write(os.path.join(out_dir, "tftest-junit.xml"),
                                encoding="utf-8", xml_declaration=True)
    return passed, failed


def main():
    ap = argparse.ArgumentParser(description="Python Terraform test runner (plan-JSON assertions).")
    ap.add_argument("--tf-root", required=True)
    ap.add_argument("--spec", default="tftest.yaml")
    ap.add_argument("--terraform-bin", default="terraform")
    ap.add_argument("--report-dir", default="reports")
    ap.add_argument("--post-apply", action="store_true",
                    help="Assert against the already-applied state (terraform show -json) "
                         "instead of running a fresh plan. Used by apply-ephemeral mode.")
    args = ap.parse_args()

    spec_path = args.spec if os.path.isabs(args.spec) else os.path.join(args.tf_root, args.spec)
    if not os.path.isfile(spec_path):
        log(f"[ERROR] spec file not found: {spec_path}")
        return 2
    spec = load_spec(spec_path)
    if (spec.get("version") or 1) != 1:
        log(f"[WARN] tftest.yaml version {spec.get('version')} — runner supports version 1")

    try:
        if args.post_apply:
            log("[INFO] post-apply mode: asserting against applied state")
            plan = terraform_state(args.tf_root, args.terraform_bin)
        else:
            plan = terraform_plan(args.tf_root, spec, args.terraform_bin)
    except SystemExit as e:
        log(str(e))
        return 2

    results = evaluate(plan, spec.get("assertions") or {})
    passed, failed = write_reports(results, args.report_dir)

    log("")
    log("=============== terraform/test results ===============")
    for name, ok, msg in results:
        log(f"  [{'PASS' if ok else 'FAIL'}] {name} — {msg}")
    log(f"------------------------------------------------------")
    log(f"  total={len(results)} passed={passed} failed={failed}")
    if failed:
        log("[ERROR] terraform/test assertions failed")
        return 1
    log("[INFO] terraform/test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
