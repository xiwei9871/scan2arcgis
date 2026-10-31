---
name: github-delivery
description: Use whenever you are about to git commit, git push, open a PR, or deliver result files (PNG, GPKG, images, data) from this repo. scan2arcgis is a PUBLIC GitHub repo with a pre-push hook that blocks binaries; this skill gives the branch, staging, push-verification and artifact rules.
---
# GitHub delivery

1. Work on a separate branch or worktree; never commit on the user's checkout without asking.
2. Stage explicit paths only (`git add <paths>`), then `git status --short` and read what is staged.
3. Never `--no-verify`, `git add -f` past ignore rules, force-push, or rewrite pushed history.
4. The pre-push hook (`scripts/hooks/pre-push`) blocks images, GPKG/SHP, weights, `data/raw|labels`, legacy history and token-like strings. If a push is rejected, do NOT reflexively undo commits. Diagnose first, then pick the smallest fix:
   a. Read the hook output: which rule fired and which files triggered it.
   b. Check state: `git status` (uncommitted/staged changes), `git log origin/<branch>..HEAD` (which commits are unpushed), `git ls-remote` (what is already on the remote — pushed history is never rewritten).
   c. Choose the minimal repair:
      - Blocked file not yet committed → move it under `runs/` (git-ignored), commit clean.
      - Blocked file inside your own tip commit (never pushed) → `git reset --soft HEAD~1` keeps work staged; remove the file and re-commit.
      - Blocked file in an older unpushed commit → do NOT soft-reset across multiple commits blindly; prefer `git commit --fixup` + `git rebase --autosquash` over the unpushed range only, and only after confirming the range with `git log`.
      - Token-like string flagged → remove the string, same procedure.
   d. Record `shasum -a 256` for any relocated binaries. Do not publish to Releases/gists without explicit approval.
5. After the push: `git ls-remote origin refs/heads/<branch>` must equal `git rev-parse HEAD`; report the full SHA and the repo `xiwei9871/scan2arcgis`.
6. Commit message ends with the agreed `Co-Authored-By` line.
