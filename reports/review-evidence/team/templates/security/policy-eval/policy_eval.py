#!/usr/bin/env python3
"""
policy_eval.py — Python policy engine fronted by Kyverno-shaped YAML policies.

Bridge to Kyverno/OPA. Evaluates policies (authored in a deliberately Kyverno-like schema)
against Kubernetes manifests (YAML) or a Terraform plan JSON.

Supported validation primitives (documented subset of Kyverno):
  - validate.pattern         : nested-map match with anchors '?*' (any non-empty) and '*' (any)
  - validate.foreach         : {list: <dotted path to a list>, pattern: {...}}
  - validate.deny.conditions : list of {key, operator, value} (Equals/NotEquals/In/NotIn)
  - validate.attribute       : {path, allowed:[...]} / {path, denied:[...]} [, default]   (tfplan)
  - validate.required_labels : [..]  (convenience; checks metadata.labels)
  - validate.required_tags   : [..]  (tfplan convenience; checks resource values.tags)
  - validate.foreach_any     : {list: <path>, conditions:[...]}  (tfplan) — VIOLATE unless at
                               least one list element satisfies all conditions (e.g. storage
                               blob_properties[*].versioning_enabled == true)

Condition operators (validate.deny.conditions / foreach_any.conditions):
  Equals, NotEquals, In, NotIn, StartsWith, NotStartsWith, Exists, NotExists.
  A condition may set `default:` — the value to assume when the attribute is absent
  (so "missing == insecure default" is explicit, e.g. private_cluster_enabled: false).

Policy mode:
  Enforce -> violations fail the job (exit 1)
  Audit   -> violations reported, job passes (exit 0)   (Dev->Audit->Enforce bridge)

Dependency: PyYAML (single external dep). Everything else is stdlib.

Exit codes:
  0  no Enforce violations (Audit violations may exist)
  1  one or more Enforce violations
  2  setup/execution error
"""
import argparse
import glob
import json
import os
import sys
import xml.etree.ElementTree as ET

try:
    import yaml
except Exception:
    print("[ERROR] PyYAML is required. Install pyyaml in the component image.", file=sys.stderr)
    sys.exit(2)


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_policies(policy_dir):
    policies = []
    for path in sorted(glob.glob(os.path.join(policy_dir, "**", "*.y*ml"), recursive=True)):
        with open(path, "r", encoding="utf-8") as fh:
            for doc in yaml.safe_load_all(fh):
                if isinstance(doc, dict) and doc.get("kind") == "Policy":
                    doc["__file__"] = path
                    policies.append(doc)
    return policies


def load_k8s_resources(manifest_dir):
    resources = []
    for path in sorted(glob.glob(os.path.join(manifest_dir, "**", "*.y*ml"), recursive=True)):
        with open(path, "r", encoding="utf-8") as fh:
            for doc in yaml.safe_load_all(fh):
                if isinstance(doc, dict) and doc.get("kind"):
                    doc["__file__"] = path
                    resources.append(doc)
    return resources


def load_tfplan_resources(plan_path):
    with open(plan_path, "r", encoding="utf-8") as fh:
        plan = json.load(fh)
    out = []

    def walk(module):
        for r in module.get("resources", []) or []:
            out.append(r)
        for child in module.get("child_modules", []) or []:
            walk(child)

    walk((plan.get("planned_values") or {}).get("root_module") or {})
    return out


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def dotted_get(obj, path):
    cur = obj
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


def pattern_match(pattern, value):
    """Kyverno-style pattern match (subset). Returns (ok, failure_detail)."""
    if isinstance(pattern, dict):
        if not isinstance(value, dict):
            return False, f"expected object, got {type(value).__name__}"
        for k, pv in pattern.items():
            if k not in value:
                return False, f"missing key '{k}'"
            ok, detail = pattern_match(pv, value[k])
            if not ok:
                return False, f"{k}: {detail}"
        return True, ""
    # scalar anchors
    if pattern == "?*":
        ok = value is not None and value != "" and value != {}
        return ok, "" if ok else "expected non-empty value"
    if pattern == "*":
        return True, ""
    # literal equality
    ok = pattern == value
    return ok, "" if ok else f"expected {pattern!r}, got {value!r}"


def eval_condition(cond, resource):
    key = cond.get("key")
    op = (cond.get("operator") or "Equals")
    val = cond.get("value")
    # `default` lets a policy state the SECURE default to assume when an attribute is
    # absent from the plan (e.g. private_cluster_enabled defaults to false). This makes
    # "missing == insecure" explicit rather than silently passing.
    actual = dotted_get(resource, key) if key else None
    if actual is None and "default" in cond:
        actual = cond["default"]
    if op == "Equals":
        return actual == val
    if op == "NotEquals":
        return actual != val
    if op == "In":
        return actual in (val or [])
    if op == "NotIn":
        return actual not in (val or [])
    if op == "StartsWith":
        return isinstance(actual, str) and actual.startswith(val)
    if op == "NotStartsWith":
        return not (isinstance(actual, str) and actual.startswith(val))
    if op == "Exists":
        return actual is not None
    if op == "NotExists":
        return actual is None
    raise ValueError(f"unsupported operator {op}")


def k8s_kind_matches(match, resource):
    kinds = match.get("kinds")
    if not kinds:
        return True
    return resource.get("kind") in kinds


def tf_type_matches(match, resource):
    types = match.get("resource_types")
    if not types:
        return True
    return resource.get("type") in types


def resource_id_k8s(r):
    md = r.get("metadata") or {}
    return f"{r.get('kind')}/{md.get('name', '?')}"


def resource_id_tf(r):
    return r.get("address") or f"{r.get('type')}.{r.get('name')}"


# --------------------------------------------------------------------------- #
# Rule evaluation -> list of violation strings for one (policy, resource)
# --------------------------------------------------------------------------- #
def eval_rule_k8s(rule, resource):
    violations = []
    validate = rule.get("validate") or {}
    msg = validate.get("message", rule.get("name", "policy violation"))

    if "required_labels" in validate:
        labels = ((resource.get("metadata") or {}).get("labels") or {})
        missing = [l for l in validate["required_labels"] if l not in labels]
        if missing:
            violations.append(f"{msg} (missing labels {missing})")

    if "pattern" in validate:
        ok, detail = pattern_match(validate["pattern"], resource)
        if not ok:
            violations.append(f"{msg} ({detail})")

    if "foreach" in validate:
        fe = validate["foreach"] or {}
        items = dotted_get(resource, fe.get("list", "")) or []
        if not isinstance(items, list):
            items = []
        for i, item in enumerate(items):
            if "pattern" in fe:
                ok, detail = pattern_match(fe["pattern"], item)
                if not ok:
                    violations.append(f"{msg} ({fe['list']}[{i}]: {detail})")
            if "deny" in fe:
                conds = (fe["deny"] or {}).get("conditions") or []
                if conds and all(eval_condition(c, item) for c in conds):
                    violations.append(f"{msg} ({fe['list']}[{i}]: deny conditions met)")

    if "deny" in validate:
        conds = (validate["deny"] or {}).get("conditions") or []
        # Kyverno deny: if ALL conditions are true, the resource is denied.
        if conds and all(eval_condition(c, resource) for c in conds):
            violations.append(f"{msg} (deny conditions met)")

    return violations


def eval_rule_tfplan(rule, resource):
    violations = []
    validate = rule.get("validate") or {}
    msg = validate.get("message", rule.get("name", "policy violation"))
    values = resource.get("values") or {}

    if "required_tags" in validate:
        tags = values.get("tags") or {}
        if isinstance(tags, dict):
            missing = [t for t in validate["required_tags"] if t not in tags]
            if missing:
                violations.append(f"{msg} (missing tags {missing})")
        else:
            violations.append(f"{msg} (no tags map)")

    if "attribute" in validate:
        att = validate["attribute"]
        actual = dotted_get(values, att["path"])
        # Optional 'default' = the value to assume when the attribute is absent from the
        # plan, so "attribute not set" can be evaluated as the insecure default.
        if actual is None and "default" in att:
            actual = att["default"]
        if "allowed" in att and actual not in att["allowed"]:
            violations.append(f"{msg} ({att['path']}={actual} not in {att['allowed']})")
        if "denied" in att and actual in att.get("denied", []):
            violations.append(f"{msg} ({att['path']}={actual} is denied)")

    if "deny" in validate:
        conds = (validate["deny"] or {}).get("conditions") or []
        if conds and all(eval_condition(c, values) for c in conds):
            violations.append(f"{msg} (deny conditions met)")

    # foreach_any: PASS if at least one element of a nested list satisfies ALL conditions;
    # VIOLATE if the list is empty/absent or no element satisfies them. Used for e.g.
    # storage blob_properties[*].versioning_enabled == true (soft delete + versioning).
    if "foreach_any" in validate:
        fe = validate["foreach_any"] or {}
        items = dotted_get(values, fe.get("list", ""))
        if not isinstance(items, list):
            items = []
        conds = fe.get("conditions") or []
        satisfied = any(conds and all(eval_condition(c, item) for c in conds) for item in items)
        if not satisfied:
            violations.append(f"{msg} (no '{fe.get('list')}' element satisfies the required settings)")

    return violations


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def evaluate(policies, resources, target):
    """Return list of result dicts: {policy, rule, resource, mode, ok, message}."""
    results = []
    for pol in policies:
        spec = pol.get("spec") or {}
        if (spec.get("target") or "kubernetes") != target:
            continue
        mode = spec.get("mode", "Enforce")
        pname = (pol.get("metadata") or {}).get("name", "unnamed")
        for rule in spec.get("rules", []) or []:
            rname = rule.get("name", "rule")
            match = rule.get("match") or {}
            for r in resources:
                if target == "kubernetes":
                    if not k8s_kind_matches(match, r):
                        continue
                    rid = resource_id_k8s(r)
                    violations = eval_rule_k8s(rule, r)
                else:
                    if not tf_type_matches(match, r):
                        continue
                    rid = resource_id_tf(r)
                    violations = eval_rule_tfplan(rule, r)
                if violations:
                    for v in violations:
                        results.append({"policy": pname, "rule": rname, "resource": rid,
                                        "mode": mode, "ok": False, "message": v})
                else:
                    results.append({"policy": pname, "rule": rname, "resource": rid,
                                    "mode": mode, "ok": True, "message": "ok"})
    return results


def write_reports(results, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "policy-eval-report.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)

    failures = [r for r in results if not r["ok"]]
    suite = ET.Element("testsuite", name="policy-eval",
                       tests=str(len(results)), failures=str(len(failures)))
    for r in results:
        case = ET.SubElement(suite, "testcase", classname=f"{r['policy']}",
                             name=f"{r['rule']}::{r['resource']}")
        if not r["ok"]:
            fail = ET.SubElement(case, "failure", message=r["message"])
            fail.text = f"[{r['mode']}] {r['message']}"
    ET.ElementTree(suite).write(os.path.join(out_dir, "policy-eval-junit.xml"),
                                encoding="utf-8", xml_declaration=True)


def main():
    ap = argparse.ArgumentParser(description="Kyverno-shaped Python policy engine (bridge).")
    ap.add_argument("--policy-dir", required=True)
    ap.add_argument("--target", choices=["kubernetes", "tfplan"], default="kubernetes")
    ap.add_argument("--manifest-dir", help="Required when --target kubernetes")
    ap.add_argument("--tfplan-json", help="Required when --target tfplan")
    ap.add_argument("--report-dir", default="reports")
    args = ap.parse_args()

    policies = load_policies(args.policy_dir)
    if not policies:
        print(f"[ERROR] no policies found under {args.policy_dir}", file=sys.stderr)
        return 2

    if args.target == "kubernetes":
        if not args.manifest_dir:
            print("[ERROR] --manifest-dir required for kubernetes target", file=sys.stderr)
            return 2
        resources = load_k8s_resources(args.manifest_dir)
    else:
        if not args.tfplan_json:
            print("[ERROR] --tfplan-json required for tfplan target", file=sys.stderr)
            return 2
        resources = load_tfplan_resources(args.tfplan_json)

    results = evaluate(policies, resources, args.target)
    write_reports(results, args.report_dir)

    enforce_fail = [r for r in results if not r["ok"] and r["mode"] == "Enforce"]
    audit_fail = [r for r in results if not r["ok"] and r["mode"] == "Audit"]

    print("")
    print("=============== policy-eval results ===============")
    for r in results:
        if not r["ok"]:
            print(f"  [{'FAIL' if r['mode'] == 'Enforce' else 'AUDIT'}] "
                  f"{r['policy']}/{r['rule']} :: {r['resource']} — {r['message']}")
    print("---------------------------------------------------")
    print(f"  evaluations={len(results)} enforce_violations={len(enforce_fail)} "
          f"audit_violations={len(audit_fail)}")

    if enforce_fail:
        print("[ERROR] policy-eval found Enforce violations")
        return 1
    if audit_fail:
        print("[WARN] policy-eval found Audit violations (non-blocking)")
    print("[INFO] policy-eval passed (no Enforce violations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
