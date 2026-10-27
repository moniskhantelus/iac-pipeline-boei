#!/usr/bin/env python3
"""
STR-228 unit tests for the seven Terraform governance policies in security/policy-eval.

Runs the engine (templates/security/policy-eval/policy_eval.py) against the shipped tfplan
policy set and the two fixtures, and asserts:
  - the FAIL fixture trips every one of the 7 governance rules (one test per policy);
  - the PASS fixture produces zero Enforce violations (no false positives).

Pure stdlib + PyYAML. Run from the repo root:
    python tests/security/policy_eval_tfplan_test.py
Exit 0 = all tests pass; non-zero = a test failed.
"""
import importlib.util
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGINE = os.path.join(REPO, "templates", "security", "policy-eval", "policy_eval.py")
POLICY_DIR = os.path.join(REPO, "templates", "security", "policy-eval", "policies")
FIX = os.path.join(REPO, "tests", "fixtures", "policy-eval")

# The seven governance policies (metadata.name) that must exist and fire on the fail fixture.
SEVEN = {
    "approved-regions",                 # POLICY-1 tags + POLICY-2 regions
    "naming-convention",                # POLICY-3
    "no-public-aks",                    # POLICY-4
    "storage-soft-delete-versioning",   # POLICY-5
    "keyvault-purge-protection",        # POLICY-6
    "min-tls-12",                       # POLICY-7
}


def load_engine():
    spec = importlib.util.spec_from_file_location("policy_eval", ENGINE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def evaluate(engine, plan_file):
    policies = engine.load_policies(POLICY_DIR)
    resources = engine.load_tfplan_resources(os.path.join(FIX, plan_file))
    return engine.evaluate(policies, resources, "tfplan")


def failing_policies(results):
    return {r["policy"] for r in results if not r["ok"]}


def main():
    engine = load_engine()
    passed, failed = 0, 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            print(f"  [PASS] {name}")
            passed += 1
        else:
            print(f"  [FAIL] {name}")
            failed += 1

    print("== FAIL fixture: each governance policy must fire ==")
    fail_results = evaluate(engine, "tfplan-fail.json")
    fired = failing_policies(fail_results)
    # approved-regions carries both the tags (POLICY-1) and region (POLICY-2) rules.
    for pol in sorted(SEVEN):
        check(f"{pol} fires on fail fixture", pol in fired)
    # Explicitly confirm tags + regions both produce a violation message.
    msgs = [r["message"] for r in fail_results if not r["ok"]]
    check("required-tags violation present", any("tag" in m.lower() for m in msgs))
    check("region violation present", any("region" in m.lower() or "location" in m.lower() for m in msgs))

    print("== PASS fixture: no Enforce violations (no false positives) ==")
    pass_results = evaluate(engine, "tfplan-pass.json")
    enforce_viol = [r for r in pass_results if not r["ok"] and r["mode"] == "Enforce"]
    for r in enforce_viol:
        print(f"     unexpected violation: {r['policy']}/{r['rule']} :: {r['resource']} — {r['message']}")
    check("pass fixture has zero Enforce violations", len(enforce_viol) == 0)

    print(f"\n== Summary: {passed} passed, {failed} failed ==")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
