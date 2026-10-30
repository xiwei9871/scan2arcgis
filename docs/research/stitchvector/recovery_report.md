# StitchVector R2 Recovery — deviation record and amendment

## PREREGISTRATION_REMOTE_FREEZE_DEVIATION

The pre-registration said it would be committed **and pushed** before any experiment. That did not happen.

| Commit | Content | Local commit | On remote |
|---|---|---|---|
| `a9813b4` | pre-registration | before any run | only after the runs |
| `130f54c` | R0 | after R0 run | only after the runs |
| `b6636dc` | R1 grid + summary | after R1 run | only after the runs |
| `722a3ad` | R2 code + synthetic tests | before any real R2 run | only after the runs |
| `e1a0962` | R2 perf change + check wording | after the R2 smoke runs | pushed 2026-10-30 in recovery step 1 |

I reported "pre-registration pushed" from a local `git rev-parse HEAD`, without checking the push. The remote stayed at `d85404d` until recovery step 1. History was not rewritten.

**Evidence level.**
- The order "pre-registration before runs" rests only on local commit history, which I control. Treat every POC-01 result (R0, R1, R2 v1) as **exploratory**, not as a frozen-protocol result.
- R0 (6/6 lossless) is a deterministic check that anyone can re-run; its conclusion does not depend on the freeze.
- R1 numbers must also be read with the conversion verification (`recovery_r1_verification.md`): 12 `polygon` runs are INVALID_UPSTREAM_SVG.
- R2 v1 is recorded as FAILED_V1 (failure scene frozen at `cae2e50`).

From now on each freeze is pushed and the remote ref is read back with `git ls-remote` before the run starts.

## R2 amendment 1

Rules: `experiments/STITCHVECTOR/poc01_r2_amendment1.json`. Summary:
- All repair decisions are made on the integer label image; every pixel keeps exactly one label.
- Boundaries are one shared arc network (each arc stored once, used by both faces), simplified per arc with fixed endpoints. Neighbouring faces can no longer be simplified differently.
- Progressive part: arcs start at 4 px; only arcs near remaining residual pixels drop to 2, 1, 0. Arcs without nearby residual keep their larger tolerance. This is not a full re-polygonization at each step.
- Two separate checks: raster correctness (render == label image) and GIS topology (`shapely.coverage_is_valid`). One does not imply the other.
- Same-input, same-final-accuracy baseline: all arcs at tolerance 0. Progressive is only worth it if it reaches 0 mismatch with fewer vertices than that baseline.
- One sample only (u2 300×300, 32 colours, variant A). If it fails either check within 10 min CPU: report FAIL and propose R1 + local pixel fallback.
