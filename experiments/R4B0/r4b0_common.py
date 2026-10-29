"""R4-B0 shared code: post-processing variants and per-instance failure attribution.
Every rule and threshold is read from experiments/R4B0/preregistration.json (committed before any run).

Methods (prediction-side unless marked ORACLE; oracles read official labels and are diagnostics only):
  M1               M1 prob, frozen watershed (markers CC(p<0.3) area>=50, elevation = prob)        [R4-A2.2]
  M2_oldseed       M2 dist head, old markers (dist>=3, area>=50), watershed on -dist                [R4-A2.2]
  M2_hybrid        M2 dist head, hybrid markers                                                     [R4-A2.2]
  M1_DD_oldseed    M1_DERIVED_DISTANCE: dist to (M1 prob > 0.5), clipped 32 px; old markers
  M1_DD_hybrid     M1_DERIVED_DISTANCE + hybrid markers
  M2_PD_hybrid     control: dist to (M2 prob > 0.5), clipped 32; hybrid markers (isolates the dist head)
  O_GTD_old / O_GTD_hybrid / O_GTD_ideal   ORACLE official dist.npy + old / hybrid / ideal seeds
  O_M2D_ideal / O_M1DD_ideal               ORACLE ideal seeds on M2 dist head / M1-derived dist
  O_M1P_ideal                              ORACLE ideal seeds, watershed on M1 prob
Ideal seed: one pixel per official instance at the argmax of official dist inside it (first in raster order).
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from skimage.morphology import skeletonize
from skimage.segmentation import watershed

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/R4A"))
import r4a2_2_eval as E  # noqa: E402
from r4a2_1_seeds import old_markers, hybrid_markers, segment  # noqa: E402

PR = json.load(open(ROOT / "experiments/R4B0/preregistration.json"))
G1 = PR["gate1"]; PRED = ROOT / "runs/r4a2/r4a22"
ORDER = G1["primary_failure_order"]


def derived_distance(prob):
    b = prob > PR["gate2"]["derived_distance"]["prob_threshold"]
    return np.minimum(cv2.distanceTransform((~b).astype(np.uint8), cv2.DIST_L2, 3), PR["gate2"]["derived_distance"]["clip_px"]).astype(np.float32)


def m1_markers(prob):
    n, cc, st, _ = cv2.connectedComponentsWithStats((prob < 0.3).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool); keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 50
    return (np.cumsum(keep) * keep)[cc].astype(np.int32)


def ideal_markers(S):
    """ORACLE: one seed per official instance at its maximum official distance."""
    mk = np.zeros(S["inst1"].shape, np.int32)
    for k, sl in enumerate(S["objects"], start=1):
        if sl is None: continue
        m = S["inst1"][sl] == k
        if not m.any(): continue
        d = np.where(m, S["dist"][sl], -1); y, x = np.unravel_index(int(np.argmax(d)), d.shape)
        mk[sl[0].start + y, sl[1].start + x] = k
    return mk


def load_sheet(code):
    R = E.load_ref(code); valid = R["valid"]
    inst1 = np.where(valid, R["instance"] + 1, 0).astype(np.int32); n = int(inst1.max())
    area = np.bincount(inst1.ravel(), minlength=n + 1)
    S = {"code": code, "R": R, "valid": valid, "inst1": inst1, "n": n, "area": area, "objects": ndi.find_objects(inst1),
         "ub": (R["unit_boundary"] > 0) & valid, "dist": R["dist"].astype(np.float32)}
    S["small"] = np.flatnonzero((area >= 200) & (area < 20000)); S["small"] = S["small"][S["small"] > 0]
    md = np.zeros(n + 1, np.float32); np.maximum.at(md, inst1.ravel(), np.where(valid, S["dist"], 0).ravel()); S["off_maxdist"] = md
    w_old = 2 * md + 1; w_own = np.full(n + 1, np.nan); elong = np.full(n + 1, np.nan)
    for k in S["small"]:
        m = np.pad((inst1[S["objects"][k - 1]] == k).astype(np.uint8), 1)
        e = cv2.distanceTransform(m, cv2.DIST_L2, 5).max()
        w_own[k] = 2 * (e - 0.5)                                          # edge-to-edge inscribed diameter
        elong[k] = skeletonize(m > 0).sum() / max(w_own[k], 1)
    S["w_old"], S["w_own"], S["elong"] = w_old, w_own, elong
    P = {"prob1": np.load(PRED / code / "M1/prob.npy").astype(np.float32), "prob2": np.load(PRED / code / "M2/prob.npy").astype(np.float32),
         "dist2": np.load(PRED / code / "M2/dist_px.npy").astype(np.float32)}
    return S, P


def run_method(name, S, P):
    """Return dict(regions, markers, dist, dist_source, prob, oracle, seconds)."""
    t0 = time.time(); prob, dist, src, oracle = None, None, None, name.startswith("O_")
    if name == "M1":
        prob = P["prob1"]; mk = m1_markers(prob); reg = watershed(prob, mk)
    elif name in ("M2_oldseed", "M2_hybrid"):
        prob, dist, src = P["prob2"], P["dist2"], "M2_PRED_DIST"
        mk = (old_markers if name == "M2_oldseed" else hybrid_markers)(dist); reg = segment(dist, mk)
    elif name in ("M1_DD_oldseed", "M1_DD_hybrid"):
        prob = P["prob1"]; dist, src = derived_distance(prob), "M1_DERIVED_DISTANCE"
        mk = (old_markers if name == "M1_DD_oldseed" else hybrid_markers)(dist); reg = segment(dist, mk)
    elif name == "M2_PD_hybrid":
        prob = P["prob2"]; dist, src = derived_distance(prob), "M2_PROB_DERIVED_DISTANCE"
        mk = hybrid_markers(dist); reg = segment(dist, mk)
    elif name.startswith("O_GTD_"):
        dist, src = S["dist"], "ORACLE_OFFICIAL_DIST"
        mk = {"O_GTD_old": old_markers, "O_GTD_hybrid": hybrid_markers}.get(name, lambda d: ideal_markers(S))(dist); reg = segment(dist, mk)
    elif name == "O_M2D_ideal":
        prob, dist, src = P["prob2"], P["dist2"], "M2_PRED_DIST"; mk = ideal_markers(S); reg = segment(dist, mk)
    elif name == "O_M1DD_ideal":
        prob = P["prob1"]; dist, src = derived_distance(prob), "M1_DERIVED_DISTANCE"; mk = ideal_markers(S); reg = segment(dist, mk)
    elif name == "O_M1P_ideal":
        prob = P["prob1"]; mk = ideal_markers(S); reg = watershed(prob, mk)
    else:
        raise KeyError(name)
    return {"name": name, "regions": reg.astype(np.int32), "markers": mk.astype(np.int32), "dist": dist, "dist_source": src,
            "prob": prob, "oracle": oracle, "seconds": round(time.time() - t0, 2)}


def _overlap(a, b, valid):
    m = valid & (a > 0) & (b > 0)
    C = coo_matrix((np.ones(int(m.sum()), np.int64), (a[m], b[m])), shape=(int(a.max()) + 1, int(b.max()) + 1)).tocsr()
    C.sum_duplicates(); return C.tocoo()


def width_bin(w):
    for lo, hi in G1["width_bins_px"]:
        if lo <= w < hi: return f"{lo}-{hi}"
    return "lt3" if w < G1["width_bins_px"][0][0] else "ge20"


def analyze(S, M):
    """Per small instance: evidence values, all applicable failure labels, primary_failure_stage."""
    inst1, valid, area, n = S["inst1"], S["valid"], S["area"], S["n"]
    reg, mk = M["regions"], M["markers"]
    ra = np.bincount(np.where(valid, reg, 0).ravel(), minlength=int(reg.max()) + 1)
    C = _overlap(inst1, np.where(valid, reg, 0), valid); i, r, c = C.row, C.col, C.data
    iou = c / (area[i] + ra[r] - c)
    best_iou = np.zeros(n + 1); np.maximum.at(best_iou, i, iou)
    best_cov = np.zeros(n + 1); np.maximum.at(best_cov, i, c / area[i])
    o = np.lexsort((-c, i)); f = np.unique(i[o], return_index=True)[1]; best_r = np.zeros(n + 1, np.int64); best_r[i[o][f]] = r[o][f]
    o2 = np.lexsort((-c, r)); f2 = np.unique(r[o2], return_index=True)[1]; maj = np.zeros(int(reg.max()) + 1, np.int64); maj[r[o2][f2]] = i[o2][f2]
    credited = np.bincount(r[iou >= 0.5], minlength=int(reg.max()) + 1)          # one-to-one check
    # markers: owner = instance holding >= own_share of the marker's pixels
    ms = np.bincount(mk.ravel(), minlength=int(mk.max()) + 1)
    CM = _overlap(inst1, mk, valid); mi, mm_, mc = CM.row, CM.col, CM.data
    owner = np.zeros(len(ms), np.int64); share = mc / np.maximum(ms[mm_], 1)
    sel = share >= G1["own_marker_share_min"]; owner[mm_[sel]] = mi[sel]
    n_mk_px = np.bincount(mi, weights=mc, minlength=n + 1)
    n_own = np.bincount(owner[owner > 0], minlength=n + 1)
    own_cov = np.zeros(n + 1); hit_own = owner[r] == i; np.add.at(own_cov, i[hit_own], c[hit_own] / area[i[hit_own]])
    # distance evidence
    pmax = None
    if M["dist"] is not None:
        pmax = np.zeros(n + 1, np.float32); np.maximum.at(pmax, inst1.ravel(), np.where(valid, M["dist"], 0).ravel())
    # boundary evidence
    tol = G1["boundary_tol_px"]
    dB = cv2.distanceTransform((~(M["prob"] > G1["prob_threshold"])).astype(np.uint8), cv2.DIST_L2, 3) if M["prob"] is not None else None
    rb = E.both_side_boundary(np.where(valid, reg, -1), valid)
    dR = cv2.distanceTransform((~rb).astype(np.uint8), cv2.DIST_L2, 3)
    rows, H, W = [], *inst1.shape
    adj = E.adjacency(inst1, valid)
    pad = G1["eval_limit_dilate_px"] + 1
    for k in S["small"]:
        sl = S["objects"][k - 1]
        y0, y1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, H); x0, x1 = max(sl[1].start - pad, 0), min(sl[1].stop + pad, W)
        L = inst1[y0:y1, x0:x1]; m = L == k; ubk = S["ub"][y0:y1, x0:x1] & m
        row = {"sheet": S["code"], "method": M["name"], "oracle": M["oracle"], "instance": int(k - 1), "area_px": int(area[k]),
               "width_own_px": round(float(S["w_own"][k]), 2), "width_old_px": round(float(S["w_old"][k]), 2),
               "width_bin_own": width_bin(S["w_own"][k]), "width_bin_old": width_bin(S["w_old"][k]), "elongation": round(float(S["elong"][k]), 2),
               "best_iou": round(float(best_iou[k]), 4), "best_cov": round(float(best_cov[k]), 4), "success": bool(best_iou[k] >= 0.5),
               "best_region_area_px": int(ra[best_r[k]]) if best_r[k] else 0, "dist_source": M["dist_source"]}
        flags = []
        # boundary coverage (prediction-level and final-region-level)
        if ubk.sum() == 0:
            row.update(boundary_truth_px=0, prob_boundary_cov=None, region_boundary_cov=None); flags.append("NO_BOUNDARY_TRUTH")
        else:
            row["boundary_truth_px"] = int(ubk.sum())
            row["region_boundary_cov"] = round(float((dR[y0:y1, x0:x1][ubk] <= tol).mean()), 4)
            if dB is not None:
                pc = float((dB[y0:y1, x0:x1][ubk] <= tol).mean()); row["prob_boundary_cov"] = round(pc, 4)
                if pc < G1["boundary_cov_min"]: flags.append("BOUNDARY_MISS")
            else:
                row["prob_boundary_cov"] = None
            # sides: neighbour instance across each boundary pixel (4-neighbourhood, first non-self label)
            nb = np.zeros(L.shape, np.int64)
            for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                sh = np.zeros_like(L); ys, xs = slice(max(dy, 0), L.shape[0] + min(dy, 0)), slice(max(dx, 0), L.shape[1] + min(dx, 0))
                yd, xd = slice(max(-dy, 0), L.shape[0] + min(-dy, 0)), slice(max(-dx, 0), L.shape[1] + min(-dx, 0))
                sh[yd, xd] = L[ys, xs]; take = (nb == 0) & (sh > 0) & (sh != k); nb[take] = sh[take]
            ids, cnt = np.unique(nb[ubk & (nb > 0)], return_counts=True)
            sh_ = cnt / max(cnt.sum(), 1); top = np.argsort(-cnt)[:2]
            two = bool(S["elong"][k] >= G1["elongated_min"] and S["w_own"][k] < 20 and len(ids) >= 2 and (sh_[top] >= G1["side_share_min"]).all())
            row["two_sided_identifiable"] = two
            if two and dB is not None:
                for j, t in enumerate(top):
                    sp = ubk & (nb == ids[t]); row[f"side{j + 1}_cov"] = round(float((dB[y0:y1, x0:x1][sp] <= tol).mean()), 4)
                row["both_sides_detected"] = bool(min(row["side1_cov"], row["side2_cov"]) >= G1["boundary_cov_min"])
        # distance
        row["official_max_dist_px"] = round(float(S["off_maxdist"][k]), 6)
        if pmax is not None:
            row["pred_max_dist_px"] = round(float(pmax[k]), 6)
            if M["dist_source"] != "ORACLE_OFFICIAL_DIST" and abs(pmax[k] - S["off_maxdist"][k]) > G1["dist_err_px"]:
                flags.append({"M2_PRED_DIST": "DIST_ERROR_M2_PRED", "M1_DERIVED_DISTANCE": "DIST_ERROR_M1_DERIVED",
                              "M2_PROB_DERIVED_DISTANCE": "DIST_ERROR_M2_PROB_DERIVED"}[M["dist_source"]])
        # seeds
        row.update(marker_px_in_instance=int(n_mk_px[k]), own_markers=int(n_own[k]), own_region_cov=round(float(own_cov[k]), 4))
        if n_mk_px[k] == 0: flags.append("SEED_MISSING")
        elif n_own[k] == 0: flags.append("SEED_FUSED")
        if n_own[k] >= 2 and best_cov[k] < 0.5 and own_cov[k] >= G1["region_cov_min"]: flags.append("OVER_SEG")
        if n_own[k] >= 1 and own_cov[k] < G1["region_cov_min"]: flags.append("WATERSHED_ABSORBED")
        if own_cov[k] >= G1["region_cov_min"] and best_iou[k] < 0.5 and ra[best_r[k]] > G1["overgrow_factor"] * area[k]: flags.append("REGION_OVERGROWN")
        if best_r[k]:
            a = maj[best_r[k]]; row["absorber_is_larger_adjacent"] = bool(a != k and area[a] > area[k] and (int(k), int(a)) in adj)
            row["best_region_credited_to_n_instances"] = int(credited[best_r[k]])
        # evaluation-criterion limit: geometry recovered except the boundary ring
        if not row["success"] and best_r[k]:
            R_ = reg[y0:y1, x0:x1] == best_r[k]; core = m & ~ubk
            inter = int((R_ & core).sum()); core_iou = inter / max(ra[best_r[k]] + int(core.sum()) - inter, 1)
            dil = cv2.dilate(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * G1["eval_limit_dilate_px"] + 1,) * 2)) > 0
            within = float((R_ & dil).sum() / max(ra[best_r[k]], 1))
            row.update(core_iou=round(core_iou, 4), region_within_dilated_share=round(within, 4))
            if core_iou >= G1["eval_limit_core_iou_min"] and within >= G1["eval_limit_within_min"]: flags.append("EVAL_LIMIT")
        row["labels"] = ";".join(flags)
        if row["success"]: row["primary_failure_stage"] = "SUCCESS"
        elif "EVAL_LIMIT" in flags: row["primary_failure_stage"] = "EVAL_LIMIT"
        else: row["primary_failure_stage"] = next((fl for s in ORDER for fl in flags if fl.startswith(s)), "UNEXPLAINED")
        rows.append(row)
    return rows, {"regions_credited_to_more_than_one_instance": int((credited > 1).sum())}


def summarize(rows, key="width_bin_own"):
    out = {}
    for b in sorted({r[key] for r in rows}):
        rs = [r for r in rows if r[key] == b]; fail = [r for r in rs if not r["success"]]
        labs = {}
        for r in fail:
            for l in filter(None, r["labels"].split(";")): labs[l] = labs.get(l, 0) + 1
        prim = {}
        for r in fail: prim[r["primary_failure_stage"]] = prim.get(r["primary_failure_stage"], 0) + 1
        out[b] = {"n": len(rs), "recall": round(sum(r["success"] for r in rs) / max(len(rs), 1), 4), "failures": len(fail),
                  "label_share_of_failures": {l: round(v / max(len(fail), 1), 4) for l, v in sorted(labs.items())},
                  "primary_share_of_failures": {l: round(v / max(len(fail), 1), 4) for l, v in sorted(prim.items())}}
    return out
