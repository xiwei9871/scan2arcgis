---
name: experiment-governance
description: Use before running any experiment, benchmark or evaluation in this repo (pre-registration, frozen parameters, test seeds, result reports). Checklist for freezing, pushing and verifying before a run, and for reporting after it.
---
# Experiment governance

Before the run:
1. Write the pre-registration (question, data/seeds, method, parameters, metrics, stop rule) as a JSON/MD file next to the code.
2. Disclose everything already seen (dev seeds, images viewed, parameters changed after looking).
3. Commit pre-registration + code + params, push, then `git ls-remote origin refs/heads/<branch>` must equal `git rev-parse HEAD`. If not equal: do not run.
4. Test data must never have been used for tuning (new seeds or a held-out set). No sealed test pool unless the user says so.

During and after:
5. Run once. No code or parameter change after the first number; a crash fix that touches no metric is a new commit, reported.
6. Keep earlier results unchanged; write new results to a new file.
7. Report only what ran; anything else is `NOT_VERIFIED`. Post-hoc analysis is labelled descriptive, not pre-registered.
8. Images/GPKG stay local under `runs/` with SHA-256 + reproduce command (see `github-delivery`).
