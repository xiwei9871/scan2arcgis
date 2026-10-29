"""R4-A registration v3c = v3 with a different side-offset choice (designed AFTER seeing v3/v3b).

Observation from v3/v3b candidate offsets: every side shows lines at ~0 (outer border), ~10 and
~65 px inward, and the old R2 corners that pass Q3 on 05030/06061 sit ~66 px inside the outer
border. The nominal-size prior (v3) and equal-width prior (v3b) were not reliable. v3c picks the
LARGEST offset that appears on all four sides within +-4 px (innermost consistent border line);
the nominal size is only a sanity bound (0.9-1.1). Falls back to v3 scoring if no such offset.
Disclosure: this rule was chosen after looking at the 13 diagnostic sheets, including validation
candidates 15061/13068 (allowed for registration diagnosis only).

R4-A registration v3: outer border -> inner neatline (image + quadrangle bounds only).

Diagnosis (registration_diagnosis.md): GSJ sheets print a thick OUTER border and a thin INNER
neatline 40-120 px inside it. The geographic quadrangle is the inner line. R2's detector and v2
both lock onto the outer border (size ~1.02-1.04 x nominal); R2 then relied on geo_A colour
refinement to pull the frame inward, which works on some sheets and diverges on others.

Method
  1. outer corners: R2 frame.json if its corners are finite, else v2 frame_v2.json.
  2. for each side, sample the black-hat response along the middle 80% of the side at inward
     offsets 0..160 px (perpendicular to the side) -> 1-D profile; candidate offsets = local maxima
     with response >= 25% of the profile maximum (offset 0 = outer border itself is a candidate).
  3. choose one offset per side minimising
        |log(h/Hn)| + |log(w/Wn)| + 2*|log(h/Hn) - log(w/Wn)|
     where h, w are the resulting inner side lengths and Hn, Wn the nominal 1:50k print size at
     200 dpi (same formula as v2). No official vectors are read.
  4. shift each side line inward by its offset, refine it by a robust fit to black-hat pixels
     within +-3 px, intersect -> corners -> homography (R2 fit_geo).
"""
import json, os, sys, time
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R2_real_map"))
from gsj_frame import fit_side, intersect, fit_geo  # noqa: E402
from gsj_register_v2 import nominal_px  # noqa: E402

MAX_OFF = 160
SIDES = (("top", "tl", "tr"), ("right", "tr", "br"), ("bottom", "br", "bl"), ("left", "bl", "tl"))


def outer_corners(code):
    p = f"runs/r4a/{code}/frame.json"
    if os.path.exists(p):
        c = json.load(open(p))["corners_px"]
        if all(np.isfinite(c[k]).all() for k in ("tl", "tr", "br", "bl")): return c, "R2_frame"
    p = f"runs/r4a/{code}/frame_v2.json"
    if os.path.exists(p):
        r = json.load(open(p))
        if r.get("status") == "OK": return r["corners_px"], "v2_frame"
    return None, None


def profile(bh, a, b, centre):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = (b - a) / np.linalg.norm(b - a); n = np.array([-d[1], d[0]])
    if np.dot(centre - (a + b) / 2, n) < 0: n = -n                 # inward normal
    t = np.linspace(0.1, 0.9, 1500)[:, None]; base = a + t * (b - a)
    h, w = bh.shape; prof = []
    for o in range(MAX_OFF + 1):
        p = np.round(base + o * n).astype(int)
        ok = (p[:, 0] >= 0) & (p[:, 0] < w) & (p[:, 1] >= 0) & (p[:, 1] < h)
        prof.append(float(bh[p[ok, 1], p[ok, 0]].mean()) if ok.any() else 0.0)
    return np.array(prof), n


def candidates(prof):
    mx = prof.max(); out = []
    for o in range(len(prof)):
        lo, hi = max(o - 3, 0), min(o + 4, len(prof))
        if prof[o] == prof[lo:hi].max() and prof[o] >= 0.25 * mx: out.append(o)
    return out


def main(code, year, out_json):
    t0 = time.time()
    img = f"data/raw/gsj_r4a/GSJ_MAP_G050_{code}_{year}_200dpi.jpg"
    b = json.load(open(f"data/raw/gsj_r4a/norm/{code}/sheet_info.json"))["bounds_lonlat"]
    g = cv2.cvtColor(cv2.imread(img), cv2.COLOR_BGR2GRAY)
    bh = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))).astype(np.float32)
    oc, src = outer_corners(code)
    res = {"code": code, "method": "v3c innermost common border line (image + quadrangle bounds only)", "bounds_lonlat": b}
    if oc is None:
        res["status"] = "NO_OUTER_FRAME"; json.dump(res, open(out_json, "w"), indent=1); print(code, res["status"]); return
    Wn, Hn = nominal_px(b)
    centre = np.mean([oc[k] for k in ("tl", "tr", "br", "bl")], 0)
    prof, norm, cand = {}, {}, {}
    for s, a, e in SIDES:
        prof[s], norm[s] = profile(bh, oc[a], oc[e], centre); cand[s] = candidates(prof[s])
    W0 = (np.linalg.norm(np.subtract(oc["tr"], oc["tl"])) + np.linalg.norm(np.subtract(oc["br"], oc["bl"]))) / 2
    H0 = (np.linalg.norm(np.subtract(oc["bl"], oc["tl"])) + np.linalg.norm(np.subtract(oc["br"], oc["tr"]))) / 2
    best = None
    for ot in cand["top"]:
        for ob in cand["bottom"]:
            hh = H0 - ot - ob
            if hh <= 0: continue
            for ol in cand["left"]:
                for orr in cand["right"]:
                    ww = W0 - ol - orr
                    if ww <= 0: continue
                    sh, sw = np.log(hh / Hn), np.log(ww / Wn)
                    sc = abs(sh) + abs(sw) + 2 * abs(sh - sw)
                    if best is None or sc < best[0]: best = (sc, ot, ob, ol, orr, hh / Hn, ww / Wn)
    common = []
    for o in cand["top"]:
        m = [min(cand[k], key=lambda x: abs(x - o)) for k in ("bottom", "left", "right")]
        if all(abs(x - o) <= 4 for x in m):
            hh, ww = H0 - o - m[0], W0 - m[1] - m[2]
            if 0.9 <= hh / Hn <= 1.1 and 0.9 <= ww / Wn <= 1.1: common.append((o, m[0], m[1], m[2], hh / Hn, ww / Wn))
    rule = "v3_fallback"
    if common:
        ot, ob, ol, orr, s_h, s_w = max(common, key=lambda t: t[0]); sc = float("nan"); rule = "innermost_common"
    else:
        sc, ot, ob, ol, orr, s_h, s_w = best
    off = {"top": ot, "bottom": ob, "left": ol, "right": orr}
    lines = {}
    ys, xs = np.nonzero(bh > np.percentile(bh, 90))
    pts_all = np.stack([xs, ys], 1).astype(float)
    for s, a, e in SIDES:
        A = np.asarray(oc[a], float) + off[s] * norm[s]; B = np.asarray(oc[e], float) + off[s] * norm[s]
        d = (B - A) / np.linalg.norm(B - A); n = np.array([-d[1], d[0]])
        rel = pts_all - A; along = rel @ d; perp = rel @ n
        L = np.linalg.norm(B - A)
        sel = (np.abs(perp) <= 3) & (along > 0.05 * L) & (along < 0.95 * L)
        lines[s] = fit_side(pts_all[sel]) if sel.sum() > 200 else np.cross([A[0], A[1], 1.0], [B[0], B[1], 1.0])
    c = {"tl": intersect(lines["top"], lines["left"]), "tr": intersect(lines["top"], lines["right"]),
         "br": intersect(lines["bottom"], lines["right"]), "bl": intersect(lines["bottom"], lines["left"])}
    corners = {k: [float(v[0]), float(v[1])] for k, v in c.items()}
    H = fit_geo(corners, b)
    res.update(status="OK", rule=rule, outer_source=src, offsets_px=off, scale_h=float(s_h), scale_w=float(s_w), score=float(sc),
               candidates=cand, nominal_wh_px=[Wn, Hn], corners_px=corners, H_lonlat_to_px=H.tolist(),
               seconds=round(time.time() - t0, 2))
    json.dump(res, open(out_json, "w"), indent=1)
    print(code, "OK", src, "offsets", off, "scale_h", round(s_h, 4), "scale_w", round(s_w, 4), res["seconds"], "s")


if __name__ == "__main__":
    main(*sys.argv[1:4])
