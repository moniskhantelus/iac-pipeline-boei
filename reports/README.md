# Compliance review and validation evidence

- STR-222-STR-230-compliance-review.md: the original review of the two uploaded ZIPs, before these fixes. Its failures describe the reviewed baseline, not a new assessment of the corrected code.
- review-evidence/: the original reviewed pipeline and team sources, preserving file/line evidence.
- validation-results.json: the original gate-bypass reproductions and query checks.
- compliance-review-evidence.zip: the previously delivered original review/evidence bundle.
- fixed-code-manifest.json: hashes of the two corrected ZIP deliverables supplied in chat. The repository's components-main.zip is repackaged with a components-main/ root, so its ZIP hash differs while its source bytes match the corrected component tree.

See ../FIXES-AND-DEPLOYMENT.md and ../VALIDATION.md for corrected-code setup and acceptance limits. Corrected-code tests are in ../test-results.txt and ../components-main/test-results.txt. No live GitLab/Azure acceptance or legal/S010 approval is claimed.
