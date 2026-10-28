# STR-222 / STR-230 pipeline-only fixes

This branch fixes **iac-pipeline-boei only**, based on the supplied team components. No components repository changes or new component release are required.

- `template-workflow/.iac_module_template.yml` consumes the existing team gate and audit components at their original `0.1.2` reference.
- `iac/` and `runtime/` contain this repository's integration fixes and explicit job overrides for the control gaps identified in those components.
- `components-main.zip` is the original supplied archive, unchanged, for reference.
- `reports/` contains the original compliance review and original-source evidence, including findings about the team components.

Read [FIXES-AND-DEPLOYMENT.md](FIXES-AND-DEPLOYMENT.md) for configuration, override behavior and remaining live acceptance requirements. The root CI runs this repository's tests; infrastructure deployment requires a real consumer root and protected environment configuration.
