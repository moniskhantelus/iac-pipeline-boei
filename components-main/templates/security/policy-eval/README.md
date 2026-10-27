# `security/policy-eval`

Python policy engine fronted by **Kyverno-shaped** YAML policies. A **bridge to Kyverno/OPA**
(AD-1): enforce the platform policy baseline in CI today, with policy files that carry forward to the
real admission engine. Drop-in sibling of `compliance-gates/policy-gate` — same stage/shape, swap the include
once Kyverno is live.

```yaml
# Kubernetes manifests
- component: $CI_SERVER_FQDN/kaas/pipelines/components/security/policy-eval@0.1.0
  inputs:
    job_name: policy-eval
    stage: develop
    target: kubernetes
    manifest_dir: k8s/base
    use_builtin_policies: "true"      # or policy_dir / policy_repo

# Terraform plan JSON
- component: $CI_SERVER_FQDN/kaas/pipelines/components/security/policy-eval@0.1.0
  inputs:
    job_name: policy-eval-iac
    stage: policy
    target: tfplan
    tfplan_json: examples/basic/plan.tfplan.json
    use_builtin_policies: "true"
```

| Input | Required | Default | Description |
|---|---|---|---|
| `target` | no | `kubernetes` | `kubernetes` or `tfplan`. |
| `manifest_dir` | no | `k8s` | Manifests (kubernetes target). |
| `tfplan_json` | no | `plan.tfplan.json` | Plan JSON (tfplan target). |
| `policy_dir` | no | `policies` | Local policy directory. |
| `policy_repo` / `policy_ref` | no | `` / `v1.0.0` | Clone policies from a repo instead. |
| `use_builtin_policies` | no | `false` | Use the seeded set shipped with this component. |

## Policy schema (Kyverno subset)

```yaml
apiVersion: kaas.boeing/policy-eval/v1   # -> kyverno.io/v1 later
kind: Policy
metadata: { name: require-resources }
spec:
  mode: Enforce                           # Audit | Enforce  (-> validationFailureAction)
  target: kubernetes                      # kubernetes | tfplan
  rules:
    - name: <rule>
      match:
        kinds: [Deployment, ...]          # kubernetes
        resource_types: [azurerm_...]     # tfplan
      validate:
        message: "..."
        # one or more of:
        pattern: { ... }                  # anchors: '?*' any non-empty, '*' any; nested maps
        foreach: { list: <dotted.path>, pattern: { ... } }
        deny: { conditions: [ {key, operator: ..., value [, default]} ] }
        attribute: { path: <dotted>, allowed: [...] [, default] }   # tfplan
        foreach_any: { list: <dotted>, conditions: [...] }          # tfplan (STR-228)
        required_labels: [...]            # kubernetes
        required_tags: [...]              # tfplan
```

### Supported vs not (be explicit)
- **Supported:** nested `pattern` with `?*`/`*`, `foreach.list` + `pattern`, `deny.conditions`
  (Equals/NotEquals/In/NotIn/**StartsWith/NotStartsWith/Exists/NotExists**), `attribute`
  allowed/denied, **`foreach_any`** (tfplan: violate unless ≥1 list element satisfies all
  conditions), a condition/attribute **`default`** (value assumed when the attribute is absent, so
  "missing == insecure default" is explicit), `required_labels`, `required_tags`.
- **Not yet (lands with real Kyverno):** regex anchors, `anyPattern`, JMESPath expressions,
  `preconditions`, `verifyImages`, mutate/generate. For image-provenance hard gates, rely on
  `supply-chain/sign-image` + `gitops/manifest-update` digest enforcement, not this bridge.

## Modes and lifecycle

`mode: Audit` reports violations and **passes** (exit 0); `mode: Enforce` **fails** (exit 1). This is
the Dev→Audit→Enforce bridge: seed a new policy as `Audit`, soak, then flip to `Enforce`. The seeded
`approved-registry` and `no-mutable-tag` policies ship as `Audit` deliberately.

## Reports

`reports/policy-eval-junit.xml` (one testcase per rule×resource) + `reports/policy-eval-report.json`.

## Seeded policies

**Kubernetes:** `require-nonroot`, `require-resources`, `require-labels`, `approved-registry`
(Audit), `no-mutable-tag` (Audit), `cluster-secret-store-only`.

**Terraform plan (STR-228 — the seven governance policies, all `Enforce`, `target: tfplan`):**

| # | Policy file | Rule |
|---|---|---|
| 1 | `approved-regions.yaml` | required cost/ownership tags |
| 2 | `approved-regions.yaml` | approved US Gov regions only |
| 3 | `naming-convention.yaml` | names start with `kaas` |
| 4 | `no-public-aks.yaml` | AKS `private_cluster_enabled = true` |
| 5 | `storage-soft-delete-versioning.yaml` | blob versioning + soft delete |
| 6 | `keyvault-purge-protection.yaml` | Key Vault `purge_protection_enabled = true` |
| 7 | `min-tls-12.yaml` | `min_tls_version = TLS1_2` |

The seven are unit-tested by `tests/security/policy_eval_tfplan_test.py` against
`tests/fixtures/policy-eval/tfplan-fail.json` (every rule fires) and `tfplan-pass.json` (zero
Enforce violations — no false positives). This set brings vnext to full STR-228 parity with the
legacy OPA gate.

## Migration to Kyverno (AD-1)

| policy-eval | Kyverno |
|---|---|
| `apiVersion: kaas.boeing/policy-eval/v1`, `kind: Policy` | `kyverno.io/v1`, `ClusterPolicy` |
| `spec.mode` | `spec.validationFailureAction` |
| `match.kinds` | `match.any[].resources.kinds` |
| `validate.message` + `validate.pattern` + `foreach` | identical shapes in Kyverno |
| `validate.deny.conditions` | `validate.deny.conditions.all` |
| `target: tfplan` policies | retire (conftest/checkov own the IaC layer) |

Story: `epic-07-policy-as-code/E07-S04`.
