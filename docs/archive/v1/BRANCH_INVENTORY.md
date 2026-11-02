# BRANCH_INVENTORY — StitchVector / scan2arcgis (archive V1, 2026-11-02)

Source: `git for-each-ref` on the Mac mini checkout + `git ls-remote origin`.
Remotes: `origin` = github.com:xiwei9871/scan2arcgis (public); `gitlab` = company GitLab (auth currently denied).
Pre-push hook on this repo blocks: binary/data extensions, `legacy/`, `data/raw|labels/`, `mqkj-` tokens, and any
ref containing the legacy GitLab root `b7248db`.

Legend: SYNCED = local == origin tip; AHEAD = unpushed commits (now resolved); LOCAL_ONLY = no origin ref.

## Public-line branches (safe on GitHub)

| Branch | Tip SHA | Remote | Status | Role |
| --- | --- | --- | --- | --- |
| main | `86e4cc5` | origin/main | SYNCED | clean public mainline root ("start clean scan2arcgis workspace"); NOT the legacy product line |
| feature/stitchvector-studio-v01 | `575a63f` | same | SYNCED | Studio V0.1: recovered Claude work + E2E 30/30; **current development tip** |
| feature/stitchvector-editor-text-layer | `24d2d14` | same | SYNCED | text layer UAT pack (READY_FOR_VISUAL_UAT) |
| feature/stitchvector-editor-line-repair | `bcb4802` | same | SYNCED | line repair + roles + legend + dual view (browser 30/30) |
| feature/stitchvector-editor-poc1 | `79619c5` | same | SYNCED | POC0/POC1 fragment selection, lasso/brush, heal (browser 12/12) |
| feature/stitchvector-editor-v01 | `5019ce4` | same | SYNCED | editor V0.1 Checkpoint C (browser 20/20) |
| research/stitchvector | `de62196` | same | SYNCED | StitchVector 3.0 geometry attribution (Checkpoint A) |
| research/stitchvector-editor-roadmap | `bec2956` | same | SYNCED | editor roadmap doc |
| research/stitchvector-u2-full-validation | `988699e` | same | SYNCED | U2 full-sheet B2c validation (17,047 faces / 606 lines) |
| research/stitchvector-u2-visual-diff | `56146bd` | same | SYNCED | visual diff tool + report |
| research/stitchvector-ocr-poc01 | `cae5a61` | same | SYNCED | OCR POC-01 (PaddleOCR/RapidOCR/surya comparison) |
| research/r4a-boundary-learning | `dee918d` | same | SYNCED (was ahead 2, pushed this session) | ARCH-3 boundary-learning research |
| research/auto-vectorization-r1 | `926be33` | same | SYNCED | R1 route research |
| research/oss-survey-20261028 | `d41ef93` | same | SYNCED | OSS survey |
| research/r1-mac-repro-20261027 | `163d402` | same | SYNCED | R1 macOS arm64 repro |
| research/r2-eval-diagnostics | `440d0ca` | same | SYNCED | R2 eval diagnostics |
| research/r2-external-survey | `cd0faac` | same | SYNCED | R2 external survey |
| research/r2-real-map-recognition | `0ad6d42` | same | SYNCED (gsj audit scripts committed this session) | R2 on GSJ printed sheets + legend audit/split-eval scripts |
| research/r3-fixes | `3dffc33` | same | SYNCED | R3 fixes |
| research/r3-line-polygon-fusion | `5ba09ad` | same | SYNCED | line/polygon fusion |
| research/r3-semantic-ocr | `110895e` | same | SYNCED | semantic OCR |
| wip/stitchvector-editcost-calibration | `bf94978` | same | SYNCED (was LOCAL_ONLY, pushed this session) | WIP edit-cost calibration (paused, not frozen) |
| chore/project-continuity-v101 | `c42f549` | same | SYNCED | governance layer (PR #1 OPEN, awaiting human review) |
| chore/claude-skills-v1 | `479ba64` | same | SYNCED | skills config |
| chore/claude-skills-v101-fix | `a9c5b4b` | same | SYNCED | skills fix |
| chore/stitchvector-archive-v1 | this branch | new | SYNCED | this archive |
| design/d0-e1-e4 | `c2c0788` | same | SYNCED | early design docs |
| worktree-agent-ab091045296713168 | `86e4cc5` | none | pointer at main tip | worktree bookkeeping ref, no unique commits |

## Legacy-line / non-GitHub branches

| Branch | Tip SHA | Remote | Status | Note |
| --- | --- | --- | --- | --- |
| master | `47d6b55` | gitlab/master, origin/master | SYNCED to both | legacy company product line; kept on GitHub as history marker only |
| dev | `7aad0c1` | gitlab/dev | upstream gitlab | contains LEGACY_ROOT → pre-push hook blocks GitHub push by design |
| audit/map-auto-conversion-recovery-20261027 | `9bb7c1c` | none (gitlab upstream gone) | LOCAL_ONLY | contains LEGACY_ROOT → cannot go to GitHub; gitlab auth denied so remote state unverifiable |

## Worktrees (`.claude/worktrees/`)

| Path | Branch | Uncommitted |
| --- | --- | --- |
| (root `~/geomap2arcgis`) | chore/project-continuity-v101 | 2 untracked user files (kept) |
| agent-ab091045296713168 | research/oss-survey-20261028 | clean |
| sv-editor-lr | feature/stitchvector-editor-line-repair | 2 .playwright-cli artifacts |
| sv-editor-poc1 | feature/stitchvector-editor-poc1 | 5 .playwright-cli artifacts |
| sv-editor-text | feature/stitchvector-editor-text-layer | 20 .playwright-cli artifacts |
| sv-editor-v01 | feature/stitchvector-editor-v01 | clean |
| sv-ocr-poc01 | research/stitchvector-ocr-poc01 | clean |
| sv-studio | feature/stitchvector-studio-v01 | .playwright-cli artifacts only |
| sv-u2-diff | research/stitchvector-u2-visual-diff | 6 .playwright-cli artifacts |
| sv-u2-full | research/stitchvector-u2-full-validation | clean |
| devin-archive-v1 | chore/stitchvector-archive-v1 | this archive (docs only) |

## Open PRs

- PR #1 `chore/project-continuity-v101` "Project Continuity V1.0.1 governance layer" — OPEN, awaiting human review.

## Resolved this session

- `research/r4a-boundary-learning` was 2 commits ahead → pushed (`dee918d`).
- `wip/stitchvector-editcost-calibration` had no remote ref → pushed (`bf94978`).
- 2 untracked GSJ scripts in the user checkout → committed on `research/r2-real-map-recognition` (`0ad6d42`).
- `feature/stitchvector-studio-v01` Studio code was untracked-only → committed `24c9ba3`+`7e88243`, later `575a63f`.
