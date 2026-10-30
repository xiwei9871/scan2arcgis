"""ARCH-3 B feasibility diagnostic (ORACLE ONLY: official labels; not an algorithm result).
Rule fixed beforehand in arch3_b_criteria.json (commit 92e4071). Decision uses the 10 training sheets only;
13014 / 15076 are a cross-check that cannot change the rule.

B1: within-instance narrow parts of 6-20 px instances (geometry; does NOT count toward 3-6 px recall).
B2: cross-instance continuity tiers T0 (same code near) / T1 (continuable) / T2 (+ same flanking units)
    for 3-6 px instances, reported for (a) all, (b) the target set = B2 initial Oracle A < 0.5,
    (c) instances missed by the final RAG_BOUNDARY_ONLY (best IoU < 0.5).
Usage: arch3_b_diag.py <out_dir>
"""
import csv, json, sys, time
from pathlib import Path
import cv2, numpy as np
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[2]
for p in ("ARCH3", "ARCH2", "ARCH1", "R4C0", "R4A", "R4B1T"): sys.path.insert(0, str(ROOT / "experiments" / p))
import arch1_feats as F  # noqa: E402
import arch2_metrics as M  # noqa: E402
import r4c0_rag as R  # noqa: E402
import r4b1t_width as W  # noqa: E402

CR = json.load(open(ROOT / "experiments/ARCH3/arch3_b_criteria.json"))
DMAX, GAPMAX, ANG, LOC, JAC = 60, 60, 30.0, 40, 0.5


def axis(ys, xs):
    if len(ys) < 3: return None
    c = np.cov(np.stack([xs, ys]).astype(float)); w, v = np.linalg.eigh(c)
    return np.degrees(np.arctan2(v[1, -1], v[0, -1])) % 180


def adiff(a, b):
    d = abs(a - b) % 180; return min(d, 180 - d)


def best_iou(reg, i1, V, ia):
    C = R.overlaps(reg, i1, V); rsz = np.bincount(reg[V].ravel(), minlength=int(reg.max()) + 1)
    iou = C.data / (rsz[C.row] + ia[C.col] - C.data); out = np.zeros(int(i1.max()) + 1); np.maximum.at(out, C.col, iou)
    return out


def ring_units(mask, unit, own):
    d = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    u = np.unique(unit[d & ~mask]); return set(int(x) for x in u if x >= 0 and x != own)


def sheet(code):
    X = F.load_inputs(code); Rr, V, i1, ia, ids, wid = F.label_ref(code)
    unit = np.load(ROOT / "runs/r4a2" / code / "unit.npy")
    n = int(i1.max()); objs = W.instances(Rr["instance"], V)[2]
    allids = np.flatnonzero(ia > 0); allids = allids[allids > 0]
    wall = np.zeros(n + 1, np.float32); wall[allids] = 2 * (W.max_edt(i1, objs, allids) - 0.5)
    # official unit per instance (majority)
    m = V & (i1 > 0) & (unit >= 0); key = i1[m].astype(np.int64) * 10000 + unit[m]
    uk, cnt = np.unique(key, return_counts=True); o = np.lexsort((-cnt, uk // 10000)); f = np.unique((uk // 10000)[o], return_index=True)[1]
    ucode = np.full(n + 1, -1, np.int64); ucode[(uk // 10000)[o][f]] = (uk % 10000)[o][f]
    oa = dict(zip(ids.tolist(), R.oracle_A(F.initial_regions(code, X).astype(np.int32), i1, V, ids).tolist()))
    fi = best_iou(F.final_regions(code, X).astype(np.int32), i1, V, ia)
    H, Wd = i1.shape; rows = []
    # ---- B2 tiers for 3-6 px instances
    for k in ids[(wid >= 3) & (wid < 6)]:
        sl = objs[k - 1]; pad = DMAX + LOC
        y0, y1 = max(0, sl[0].start - pad), min(H, sl[0].stop + pad); x0, x1 = max(0, sl[1].start - pad), min(Wd, sl[1].stop + pad)
        I = i1[y0:y1, x0:x1]; U = unit[y0:y1, x0:x1]; mk = I == k
        dist, lab = cv2.distanceTransformWithLabels((~mk).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        ny, nx = np.nonzero(mk); src = np.zeros(int(lab.max()) + 1, np.int64); src[lab[ny, nx]] = np.arange(len(ny))
        ax_n = axis(ny, nx); own_nb = ring_units(mk, U, int(ucode[k]))
        r = {"sheet": code, "instance": int(k), "width": round(float(wid[ids == k][0]), 2), "area": int(ia[k]),
             "unit": int(ucode[k]), "initial_oracleA": round(oa[int(k)], 4), "final_rag_iou": round(float(fi[k]), 4),
             "T0": False, "T1": False, "T2": False, "best_gap_px": None}
        cand = np.unique(I[(dist <= DMAX) & (I > 0) & (I != k)])
        for j in cand:
            if ucode[j] != ucode[k] or ucode[k] < 0 or wall[j] < 6: continue
            mj = I == j; dj = np.where(mj, dist, np.inf); g = float(dj.min()); r["T0"] = True
            if r["best_gap_px"] is None or g < r["best_gap_px"]: r["best_gap_px"] = round(g, 2)
            if g > GAPMAX or ax_n is None: continue
            gy, gx = np.unravel_index(np.argmin(dj), dj.shape); p = src[lab[gy, gx]]; sy, sx = ny[p], nx[p]
            yy, xx = np.ogrid[:I.shape[0], :I.shape[1]]; disk = (yy - gy) ** 2 + (xx - gx) ** 2 <= LOC ** 2
            wy, wx = np.nonzero(mj & disk); ax_w = axis(wy, wx)
            if ax_w is None or adiff(ax_n, ax_w) > ANG: continue
            if g >= 2 and adiff(ax_n, np.degrees(np.arctan2(gy - sy, gx - sx)) % 180) > ANG: continue
            r["T1"] = True
            wn = ring_units(mj & disk, U, int(ucode[j]))
            if own_nb and wn and len(own_nb & wn) / len(own_nb | wn) >= JAC: r["T2"] = True; break
        rows.append(r)
    # ---- B1 within-instance narrow parts of 6-20 px instances
    b1 = {"n": 0, "with_narrow_part": 0, "narrow_skeleton_share_median": None, "with_narrow_part_and_initialOA_fail": 0}
    shares = []
    for k in ids[(wid >= 6) & (wid < 20)]:
        sl = objs[k - 1]; mk = np.pad(i1[sl] == k, 1)
        e = cv2.distanceTransform(mk.astype(np.uint8), cv2.DIST_L2, 5); sk = skeletonize(mk)
        if sk.sum() == 0: continue
        lw = 2 * e[sk] - 0.5; sh = float((lw < 6).mean()); b1["n"] += 1; shares.append(sh)
        if sh > 0:
            b1["with_narrow_part"] += 1
            if oa[int(k)] < 0.5: b1["with_narrow_part_and_initialOA_fail"] += 1
    b1["narrow_skeleton_share_median"] = float(np.median(shares)) if shares else None
    return rows, b1


def tally(rows):
    out = {}
    for name, sel in (("all_3_6", lambda r: True), ("target_initial_oracleA_fail", lambda r: r["initial_oracleA"] < 0.5),
                      ("final_rag_missed", lambda r: r["final_rag_iou"] < 0.5)):
        s = [r for r in rows if sel(r)]; n = len(s)
        out[name] = {"n": n, **{t: {"k": sum(r[t] for r in s), "ci95": M.wilson(sum(r[t] for r in s), n) if n else None}
                               for t in ("T0", "T1", "T2")}}
    return out


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); t0 = time.time()
    groups = {"train": F.TRAIN, "exposed": F.EXPOSED}; res = {"criteria_commit": "92e4071", "status": CR["status"], "groups": {}}
    allrows = []
    for gname, codes in groups.items():
        rows, b1s, per = [], [], {}
        for c in codes:
            r, b1 = sheet(c); rows += r; b1s.append(b1); per[c] = tally(r); print(c, per[c]["target_initial_oracleA_fail"], b1, flush=True)
        B1 = {k: sum(b[k] for b in b1s) for k in ("n", "with_narrow_part", "with_narrow_part_and_initialOA_fail")}
        res["groups"][gname] = {"B2_tiers": tally(rows), "per_sheet": per, "B1": B1}
        allrows += [dict(r, group=gname) for r in rows]
    tgt = res["groups"]["train"]["B2_tiers"]["target_initial_oracleA_fail"]
    share = tgt["T2"]["k"] / tgt["n"] if tgt["n"] else 0.0
    res["decision"] = {"rule": CR["decision_rule"]["B_main_route_for_3_6_if"], "train_target_n": tgt["n"],
                       "train_T2_k": tgt["T2"]["k"], "train_T2_share": round(share, 4),
                       "B_role": "MAIN_ROUTE_FOR_3_6" if share >= 0.30 else "AUXILIARY_PINCHOUT_GEOMETRY",
                       "exposed_cross_check_only": res["groups"]["exposed"]["B2_tiers"]["target_initial_oracleA_fail"]}
    res["minutes"] = round((time.time() - t0) / 60, 1)
    json.dump(res, open(out / "b_feasibility.json", "w"), indent=1, default=float)
    with open(out / "b_instances.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(allrows[0])); w.writeheader(); w.writerows(allrows)
    print(json.dumps(res["decision"], default=float))


if __name__ == "__main__":
    main(sys.argv[1])
