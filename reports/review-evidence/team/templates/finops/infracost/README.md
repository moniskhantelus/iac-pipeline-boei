# `finops/infracost`

Terraform cost estimation (Infracost) sourced from **Boeing's internal registry at a pinned
version** — no Docker Hub, no `:latest`. Brings the last pipeline image into supply-chain alignment
with the rest of the catalog. (STR-225 / PRD REQ-SVC-13.)

Cost estimation is **advisory** (`allow_failure: true`) and consumes the `plan.tfplan.json`
artifact produced by `terraform/plan`.

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/finops/infracost@<version>
    inputs:
      job_name: infracost
      tf_root: environments/dev
      infracost_skip: "N"   # set to N once the internal mirror is confirmed onboarded
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `job_name` | no | `infracost` | Job name. |
| `stage` | no | `finops` | Stage. |
| `plan_json` | no | `plan.tfplan.json` | Terraform plan JSON from `terraform/plan`. |
| `tf_root` | no | `.` | Root containing the plan JSON. |
| `currency` | no | `USD` | Display currency. |
| `infracost_skip` | no | **`Y`** | `Y` skips the step (default — see fallback below); set `N` to run. |
| `infracost_image` | no | `registry.web.boeing.com/ecs-catalog/infracost/infracost` | Internal mirror. |
| `infracost_image_version` | no | `v0.10.39` | Pinned tag (never `latest`). |

`INFRACOST_API_KEY` must be a masked/protected CI/CD variable in the consumer project (never embedded).

## Default-skip fallback (STR-225 AC 4)

`infracost_skip` defaults to **`Y`**. Per the story's fallback: if the internal Infracost mirror is
not yet established (registry onboarding/approval pending), the cost step is **disabled by default**
so the pipeline keeps working rather than failing on an unreachable external registry. The skip path
logs the reason and the tracking ticket (**STR-225**) and exits 0.

**To enable once the mirror is onboarded:** set `infracost_skip: "N"` in the consumer include.

## Dependency: establish the internal mirror (platform / ECS Catalog team)

The image must be mirrored from Docker Hub into the approved internal registry (one-time, by a
registry admin with perimeter access):

```bash
VER="v0.10.39"
docker pull infracost/infracost:${VER}
docker tag  infracost/infracost:${VER} registry.web.boeing.com/ecs-catalog/infracost/infracost:${VER}
docker push registry.web.boeing.com/ecs-catalog/infracost/infracost:${VER}
```

Until this is confirmed, keep `infracost_skip: "Y"`. Coordinate onboarding with the ECS Catalog team.

Story: STR-225. Traceability: PRD REQ-SVC-13 (public registry pulls blocked; upstream images
mirrored to the approved registry).
