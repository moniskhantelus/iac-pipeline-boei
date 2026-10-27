# STR-222 / STR-230 corrected code

Read [FIXES-AND-DEPLOYMENT.md](FIXES-AND-DEPLOYMENT.md) before integration. It describes the fixes, breaking interface changes, protected configuration, identity/storage setup, tests and remaining live acceptance requirements.

The root pipeline runs code tests only. Deployment requires a consumer with a real Terraform root and reviewed configuration. No resources have been deployed and no retention policy has been locked.

## Repository layout

- Root: corrected pipeline library.
- components-main/: corrected team component library as editable source.
- components-main.zip: matching corrected team library distribution.
- reports/: original compliance report, original-source evidence and earlier validation results.

The reports document the pre-fix baseline. Follow FIXES-AND-DEPLOYMENT.md for deployment prerequisites and remaining live acceptance checks.
