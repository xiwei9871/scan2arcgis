"""Protection ablation (rules: sv_pa_prereg.json). Four line methods, all built on the frozen B2c (sv_b2c, 37d81b7).

M0  B2c unchanged.
M1  B2c + grey candidates WITH fill protection: candidate = hysteresis(|L* - L*_median15|, lo, hi) and not protected.
M2  B2c + grey candidates WITHOUT fill protection.
M3  B2c + Lab candidates WITHOUT fill protection: candidate = hysteresis(CIE76 dE to the median15, lo, hi) (the B0 contrast
    with the B2a thresholds 8 / 12, not tuned here).
For M1-M3 the candidate mask goes through the unchanged 2.0 steps (skeleton, spur, join, min_len: sv_ld_fix._pipeline);
only the parts farther than add_r from the B2c drawing and >= min_len are added, and each added segment must pass the
unchanged B2c luminance check (dL <= -3, or unmeasurable sides). B2c lines are never moved, split or removed.
Grey |dL| and Lab dE are different quantities: equal numbers do not mean equal sensitivity.
"""
import numpy as np, cv2, shapely
from skimage.filters import apply_hysteresis_threshold
import sv_autoline as AL, sv_ld_fix as F, sv_b2c as C

Q = {"grey_lo": 5.0, "grey_hi": 8.0, "lab_lo": 8.0, "lab_hi": 12.0, "bg_median": 15, "add_r": 1.5}
METHODS = ["M0", "M1", "M2", "M3"]


def grey_contrast(a, k):
    return np.abs(AL.lab(a)[..., 0] - AL.lab(cv2.medianBlur(a, k))[..., 0])


def protected(a):
    con = AL.contrast(a, AL.P["bg_median"]); return AL.protected(a, AL.fill_colours(a, con, AL.P), AL.P)


def candidates(a, method, q=Q):
    if method in ("M1", "M2"): cand = apply_hysteresis_threshold(grey_contrast(a, q["bg_median"]), q["grey_lo"], q["grey_hi"])
    else: cand = apply_hysteresis_threshold(AL.contrast(a, q["bg_median"]), q["lab_lo"], q["lab_hi"])
    if method == "M1": cand = cand & ~protected(a)
    return cand


def additions(base, new, q=Q):
    if not base: return [o for o in new if o["geom"].length >= AL.P["min_len"]]
    U = shapely.union_all([o["geom"] for o in base]).buffer(q["add_r"]); out = []
    for o in new:
        for p in shapely.get_parts(shapely.difference(o["geom"], U)):
            if p.geom_type == "LineString" and p.length >= AL.P["min_len"]: out.append({**o, "geom": p})
    return out


def run(a, method, q=Q):
    """-> (objects, info). info: added candidates before / after the luminance check, with their dL."""
    base = C.b2c(a)[0]
    if method == "M0": return base, {"candidates": 0, "kept": 0, "segments": []}
    drawn, _ = F._pipeline(a, candidates(a, method, q), AL.P); add = additions(base, drawn, q); L = AL.lab(a); kept, segs = [], []
    for o in add:
        dl, st = C.seg_dL(L, o["geom"], o["width"]); ok = (st < C.Q["min_stable"]) or (dl <= C.Q["dL_max"])
        segs.append({"geom": o["geom"], "dL": dl, "stable": st, "kept": bool(ok)})
        if ok: kept.append(o)
    return base + kept, {"candidates": len(add), "kept": len(kept), "segments": segs}
