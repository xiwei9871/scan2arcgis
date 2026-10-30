# StitchVector recovery: R1 SVG/GPKG conversion check, and the remote-freeze deviation

Status: part of `STITCHVECTOR_R2_RECOVERY`. No R1 run was repeated; the 63 saved SVGs were re-checked.

## 1. PREREGISTRATION_REMOTE_FREEZE_DEVIATION

- The POC-01 pre-registration said it would be committed **and pushed** before any run. It was committed locally
  (`a9813b4`) before any run, but **not pushed**. The remote branch stayed at `d85404d` until the recovery push.
- Actual order (local history, not rewritten): `a9813b4` pre-registration -> `130f54c` R0 -> `b6636dc` R1 ->
  `722a3ad` R2 code -> `e1a0962` R2 perf change. All five were pushed together during the recovery
  (remote then read back as `e1a0962`).
- Consequence: the remote cannot prove that the pre-registration preceded the runs. Only local commit order shows it.
  R0, R1 and the first R2 attempt are therefore **exploratory evidence**, not pre-registered results.
  Any R1/R2 conclusion used for a decision must be re-confirmed after a pre-registration that is verified on the remote
  before the run. Git history was not rewritten.
- My earlier report "pre-registration pushed" was wrong: I printed the local `HEAD`, not the remote ref.

## 2. Where the missing `M` comes from (P0-A)

Checked on `13014_rawRGB_polygon.svg`:
- Raw text of the file VTracer returned: `d="L` occurs 108,186 times, `d="M` 35,618 times.
- XML DOM (`xml.etree`) path attributes: 108,186 of 143,804 do not start with `M`/`m`. Example `d="L2,0Z"`.
- So the `M` is missing in VTracer 1.0.0a4's own output (`polygon` mode only). Our parser did not drop it.
- SVG requires every path's data to start with a moveto. The native renderer `rsvg-convert` draws nothing for these
  paths: 93% of 13014 and 84% of u2 stay transparent in the native render.
- The paths were **not** repaired by guessing a start point.
- The same 32x32 synthetic image traced in `polygon` mode had 0 such paths, so the defect depends on the image.

## 3. Check of all 63 R1 runs (native render vs our GPKG render)

`sv_r1_verify_crisp.py`: rsvg-convert with `shape-rendering="crispEdges"` (no anti-aliasing) vs our pixel-centre
rasterization of the flattened GPKG geometry.

| status | runs | meaning |
|---|---|---|
| VALID | 43 | no path without moveto; agreement >= 0.98 within 2 levels per channel; uncovered <= 0.001 |
| INVALID_UPSTREAM_SVG | 12 | all `polygon`-mode runs (3 samples x 4 inputs); upstream SVG invalid |
| CHECK | 8 | all 13014 `spline` runs; agreement 0.940-0.959 |

The 8 CHECK runs (diagnosed on `13014_rawRGB_spline_s1`):
- 99.7% of the disagreeing pixels lie on colour boundaries. 13014 is 88% boundary pixels at this level of detail,
  which is why its agreement is lowest.
- Exact match against the original crop is 0.4087 for **both** renderers.
- Reading: the difference is the edge-pixel rule (rsvg crispEdges vs pixel-centre), not a geometry error. These runs
  are marked `VALID_RENDER_RULE_DIFF`. Their R1 metrics do not change at the reported precision.

Holes, fill rule and paint order: tried holes / even-odd / non-zero on three runs; results identical, so they are not
the cause of any disagreement.

## 4. What the R1 data can be used for

- The 12 `polygon` runs are INVALID and excluded from every R1/R2 comparison. Files are kept.
- The other 51 runs are usable as exploratory R1 evidence (see section 1).
- Strongest R1 points (raw RGB input): 13014 `pixel` dE90 4.2, thin-structure match 0.998, 565k objects;
  `spline` dE90 5.3, thin match 0.980, 552k objects. Fidelity is high, but object counts are about 0.55 per pixel,
  so editability remains the open problem.

Files: `experiments/STITCHVECTOR/r1_verify/` (per-run JSON), scripts `sv_r1_verify.py`, `sv_r1_verify_crisp.py`.
