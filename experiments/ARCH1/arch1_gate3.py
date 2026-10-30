"""ARCH-1 Gate 3: validation of the cross-section line-width estimator (rules: arch1_criteria.json gate3). One run.
Estimator: experiments/ARCH1/arch1_linewidth.py (image only). Official lines are used ONLY to select evaluation
samples / classify regions, never as estimator input.
Synthetic: widths 1.0-6.0 px, angles 0-90 deg (line), circle (curve), dashed, crossing (junction flags).
GSJ (10 training sheets + 13014 / 15076):
  (a) reliable samples on skeleton pixels within 1 px of official printed_contact lines: per-sheet median in [0.8, 3.5],
      inter-sheet CV <= 0.35
  (b) repeatability: same image twice -> identical arrays
  (c) scale: 15023 rescaled 0.75 / 1.5 (INTER_AREA / INTER_CUBIC), contact-line samples mapped with the image;
      median width ratio within 15% of the factor
  (d) discrimination: RAG regions < 200 px with predicted width < 6 px: ink-band-proxy PSEUDO vs TRUE_SMALL;
      score = region width / local line width, local line width = median width of RELIABLE samples whose skeleton
      pixel lies within the region bbox expanded by 10 px (fixed before the run); AUC >= 0.80 (TRUE_SMALL higher)
Usage: arch1_gate3.py <out_dir>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).parent))
import arch1_linewidth as LW  # noqa: E402
import arch1_feats as F  # noqa: E402
from arch1_gate1 import auc  # noqa: E402

ROOT = F.ROOT
SYN_W = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0]; ANG = [0, 15, 30, 45, 60, 75, 90]


def synthetic():
    per_w = {}
    for w in SYN_W:
        errs = []
        for kind, angs in (("line", ANG), ("curve", [0]), ("dashed", [0, 45])):
            for a in angs:
                img = LW.synthetic(w, a, kind); m = LW.measure(img)
                keep = m["reliable"] & (m["y"] > 20) & (m["y"] < 180) & (m["x"] > 20) & (m["x"] < 180)
                errs += list(m["width"][keep] - w)
        e = np.abs(np.array(errs))
        per_w[str(w)] = {"n_reliable": int(len(e)), "median_abs_err": float(np.median(e)) if len(e) else None,
                         "median_signed_err": float(np.median(errs)) if len(errs) else None,
                         "ok": bool(len(e) and (np.median(e) <= 0.35 if w <= 3 else np.median(e) <= 0.12 * w))}
    jflag = []
    for w in (1.5, 3.0):
        for a in (0, 30):
            img = LW.synthetic(w, a, "cross"); m = LW.measure(img)
            near = np.hypot(m["y"] - 100, m["x"] - 100) <= 3
            jflag += list(~m["reliable"][near])
    return {"per_width": per_w, "junction_samples": len(jflag), "junction_flagged_share": float(np.mean(jflag)) if jflag else None,
            "pass": all(v["ok"] for v in per_w.values()) and bool(jflag) and np.mean(jflag) >= 0.9}


def contact_samples(code, gray=None, scale=1.0):
    d = ROOT / "runs/r4a2" / code
    g = gray if gray is not None else cv2.cvtColor(cv2.imread(str(d / "geotiff_rgb.png")), cv2.COLOR_BGR2GRAY)
    m = LW.measure(g)
    pc = np.load(d / "printed_contact.npy") > 0
    if scale != 1.0: pc = cv2.resize(pc.astype(np.uint8), (g.shape[1], g.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    near = cv2.dilate(pc.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    sel = m["reliable"] & near[m["y"], m["x"]]
    return m, sel


def discrimination(code):
    X = F.load_inputs(code); Rr, V, i1, ia, ids, wid = F.label_ref(code)
    reg = F.compact(F.final_regions(code, X)); maj, _, good, sz = F.label_regions(reg, i1, V, ia)
    ub = (Rr["unit_boundary"] > 0) & V; dub = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)
    m = LW.measure(cv2.cvtColor(X["bgr"], cv2.COLOR_BGR2GRAY))
    rel = m["reliable"]; ry, rx, rw = m["y"][rel], m["x"][rel], m["width"][rel]
    objs = ndi.find_objects(reg); H, W = reg.shape; rows = []
    for k in np.flatnonzero((sz > 0) & (sz < 200)):
        if k == 0: continue
        sl = objs[k - 1]; mk = reg[sl] == k
        w = 2 * (cv2.distanceTransform(np.pad(mk.astype(np.uint8), 1), cv2.DIST_L2, 5).max() - 0.5)
        if w >= 6: continue
        pseudo = maj[k] > 0 and ia[maj[k]] >= 5 * sz[k]
        if pseudo:
            dd = dub[sl][mk]; ik = X["ink1"][sl][mk]
            if not ((dd <= 1.5).mean() >= 0.8 and ik.mean() >= 0.6): continue
            cls = False
        elif good[k]: cls = True
        else: continue
        y0, y1, x0, x1 = sl[0].start - 10, sl[0].stop + 10, sl[1].start - 10, sl[1].stop + 10
        s = (ry >= y0) & (ry < y1) & (rx >= x0) & (rx < x1)
        lw = float(np.median(rw[s])) if s.sum() >= 3 else np.nan
        rows.append({"true": cls, "width": float(w), "local_line_width": lw, "ratio": float(w / lw) if lw == lw and lw > 0 else np.nan})
    return rows


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    res = {"criteria": json.load(open(ROOT / "experiments/ARCH1/arch1_criteria.json"))["gate3"]}
    res["synthetic"] = synthetic(); print("synthetic", json.dumps(res["synthetic"]), flush=True)
    per = {}
    for c in F.TRAIN + F.EXPOSED:
        m, sel = contact_samples(c)
        per[c] = {"reliable_contact_samples": int(sel.sum()), "median_width": float(np.median(m["width"][sel])) if sel.any() else None,
                  "reliable_share_all": float(m["reliable"].mean()),
                  "flag_shares": {f: float(m["flags"][:, i].mean()) for i, f in enumerate(LW.FLAGS)}}
        print(c, per[c]["reliable_contact_samples"], per[c]["median_width"], flush=True)
    meds = np.array([v["median_width"] for v in per.values() if v["median_width"] is not None])
    a_ok = bool(len(meds) == len(per) and ((meds >= 0.8) & (meds <= 3.5)).all() and meds.std() / meds.mean() <= 0.35)
    res["gsj_a_contact_widths"] = {"per_sheet": per, "inter_sheet_cv": float(meds.std() / meds.mean()), "pass": a_ok}
    g = cv2.cvtColor(cv2.imread(str(ROOT / "runs/r4a2/05016/geotiff_rgb.png")), cv2.COLOR_BGR2GRAY)
    m1, m2 = LW.measure(g), LW.measure(g)
    res["gsj_b_repeatability"] = {"pass": bool(all(np.array_equal(m1[k], m2[k]) for k in m1))}
    g15 = cv2.cvtColor(cv2.imread(str(ROOT / "runs/r4a2/15023/geotiff_rgb.png")), cv2.COLOR_BGR2GRAY)
    m0, s0 = contact_samples("15023", g15); w0 = float(np.median(m0["width"][s0])); sc = {}
    for f, it in ((0.75, cv2.INTER_AREA), (1.5, cv2.INTER_CUBIC)):
        gi = cv2.resize(g15, None, fx=f, fy=f, interpolation=it); mi, si = contact_samples("15023", gi, f)
        wf = float(np.median(mi["width"][si])); sc[str(f)] = {"median_width": wf, "ratio": wf / w0, "rel_error": abs(wf / w0 / f - 1), "ok": abs(wf / w0 / f - 1) <= 0.15}
    res["gsj_c_scale"] = {"original_median": w0, "factors": sc, "pass": all(v["ok"] for v in sc.values())}
    rows = []
    for c in F.TRAIN + F.EXPOSED: rows += discrimination(c)
    y = np.array([r["true"] for r in rows]); x = np.array([r["ratio"] for r in rows], float)
    a = auc(x, y); a_w = auc(np.array([r["width"] for r in rows], float), y)
    res["gsj_d_discrimination"] = {"n_true_small_lt6": int(y.sum()), "n_ink_band_proxy_lt6": int((~y).sum()), "n_missing_local_width": int(np.isnan(x).sum()),
                                   "auc_ratio": a, "auc_width_alone_for_reference": a_w,
                                   "median_ratio": {"true_small": float(np.nanmedian(x[y])), "ink_band": float(np.nanmedian(x[~y]))},
                                   "pass": bool(a is not None and a >= 0.80)}
    res["verdict"] = "LINE_WIDTH_ESTIMATOR_QUALIFIED" if all(res[k]["pass"] for k in ("synthetic", "gsj_a_contact_widths", "gsj_b_repeatability", "gsj_c_scale", "gsj_d_discrimination")) else "LINE_WIDTH_ESTIMATOR_NOT_QUALIFIED"
    res["failed"] = [k for k in ("synthetic", "gsj_a_contact_widths", "gsj_b_repeatability", "gsj_c_scale", "gsj_d_discrimination") if not res[k]["pass"]]
    json.dump(res, open(out / "gate3_line_width.json", "w"), indent=1, default=float)
    print(res["verdict"], res["failed"], json.dumps({k: res[k] for k in ("gsj_c_scale", "gsj_d_discrimination")}), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
