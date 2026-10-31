---
name: github-delivery
description: Use whenever you are about to git commit, git push, open a PR, or deliver result files (PNG, GPKG, images, data) from this repo. scan2arcgis is a PUBLIC GitHub repo with a pre-push hook that blocks binaries; this skill gives the branch, staging, push-verification and artifact rules.
---
# GitHub delivery

1. Work on a separate branch or worktree; never commit on the user's checkout without asking.
2. Stage explicit paths only (`git add <paths>`), then `git status --short` and read what is staged.
3. Never `--no-verify`, `git add -f` past ignore rules, force-push, or rewrite pushed history.
4. The pre-push hook (`scripts/hooks/pre-push`) blocks images, GPKG/SHP, weights, `data/raw|labels`, legacy history and token-like strings. If it rejects a push: undo the local commit with `git reset --soft HEAD~1`, move the binaries under `runs/` (git-ignored), record `shasum -a 256`, and push again. Do not publish to Releases/gists without explicit approval.
5. After the push: `git ls-remote origin refs/heads/<branch>` must equal `git rev-parse HEAD`; report the full SHA and the repo `xiwei9871/scan2arcgis`.
6. Commit message ends with the agreed `Co-Authored-By` line.
