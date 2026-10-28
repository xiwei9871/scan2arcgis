"""S1 stage 2: assign a stratigraphic code to every candidate region (PREDICTION side, no ground truth).

Inputs: sheet image, R1 run dir (pred_legend_rf_selftrain.npy, map_mask.npy, swatch boxes in
r1_eval.json), legend OCR (s1_legend_ocr.py) and in-map code candidates (s1_map_spot.py).
gt_work.npy in the same directory is NOT read here.

Regions = 4-connected components of the R1 rf_selftrain class map (R1's own candidate polygons).
Methods (each yields a code per region, or None = unassigned):
  A0   R1 class -> R1's own ocr_code on its swatch (plain Tesseract; R2 semantic baseline)
  A1   R1 class -> legend code read by the S1 legend reader (tess_sub_case)
  A2c  region median colour -> nearest swatch -> legend code           (region level, colour only)
  A2t  as A2c + texture terms (L/a/b spread, ink density)              (region level, colour+texture)
  A3   A2t + in-map code anchors: regions containing a lexicon-matched code label take that code;
       per-code reference colours are re-estimated from anchored regions (self-calibration);
       remaining regions are re-classified against those references; regions whose best reference
       belongs to a same-colour swatch group take a group code only from an adjacent anchored region
       with similar colour, otherwise stay unassigned (REVIEW).
Review candidates (A3) carry reasons: MULTI_CODE, ANCHOR_COLOUR_CONFLICT, SAME_COLOUR_NO_ANCHOR,
NO_LEGEND_CODE, METHOD_DISAGREE (A2t vs A3). Scores are UNCALIBRATED.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "R2_real_map"))
from scan2arcgis.recog.legend_classifier import ink_mask  # noqa: E402
from scan2arcgis.recog.legend_swatches import ocr_code  # noqa: E402
from gsj_error_analysis import lab_of  # noqa: E402

W_TEX = 0.5        # texture weight in A2t/A3 (fixed a priori, not tuned)
DE_GROUP = 4.0     # swatches closer than this in Lab form a same-colour group (prediction side)
DE_CONFLICT = 15.0  # anchor code reference vs region colour beyond this -> conflict


def feats(L, ink, m):
    px = L[m & ~ink]
    if len(px) < 5: px = L[m]
    return np.r_[np.median(px, 0), px.std(0), [float(ink[m].mean()) * 100]]


def dist(f, R, w_tex):
    return np.linalg.norm(f[None, :3] - R[:, :3], axis=1) + w_tex * np.linalg.norm(f[None, 3:] - R[:, 3:], axis=1)


def main(img, r1_dir, legend_ocr_json, spot_json, out_dir, reader="rapid"):
    d = Path(r1_dir); out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    ev = json.load(open(d / "r1_eval.json")); s = ev["scale"]
    full = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(full, tuple(ev["work_size"]), interpolation=cv2.INTER_AREA)
    mm = np.load(d / "map_mask.npy"); pred = np.load(d / "pred_legend_rf_selftrain.npy").astype(np.int32)
    ink = ink_mask(rgb, mm); L = lab_of(cv2.medianBlur(rgb, 3))
    sws = ev["swatches"]; nS = len(sws)
    leg = {r["swatch"]: r for r in json.load(open(legend_ocr_json))["swatches"]}
    code_a1 = [leg[sw["id"]]["tess_sub_case"]["code"] for sw in sws]
    code_a0 = []
    for sw in sws:
        x, y, w, h = [int(round(t / s)) for t in sw["box"]]
        c = ocr_code(full, (x, y, w, h)); code_a0.append("".join(ch for ch in c if ch.isalnum()) if c else None)
    # swatch features (interior, work scale)
    SF = []
    for sw in sws:
        x, y, w, h = sw["box"]; m = np.zeros(mm.shape, bool); m[y + 2:y + h - 2, x + 2:x + w - 2] = True
        SF.append(feats(L, ink_mask(rgb, m), m))
    SF = np.array(SF)
    # same-colour swatch groups (prediction side, from swatch colours only)
    group = list(range(nS))
    for i in range(nS):
        for j in range(i):
            if np.linalg.norm(SF[i, :3] - SF[j, :3]) < DE_GROUP: group[i] = group[j]
    grp_codes = {}
    for i, g in enumerate(group): grp_codes.setdefault(g, set()).add(code_a1[i])
    in_group = [len({c for c in grp_codes[group[i]] if c}) > 1 for i in range(nS)]
    # regions
    reg = np.full(mm.shape, -1, np.int32); k0 = 0; reg_cls = []
    for k in np.unique(pred[mm & (pred >= 0)]):
        n, cc = cv2.connectedComponents(((pred == k) & mm).astype(np.uint8), connectivity=4)
        sel = cc > 0; reg[sel] = cc[sel] - 1 + k0; reg_cls += [int(k)] * (n - 1); k0 += n - 1
    nR = k0; reg_cls = np.array(reg_cls)
    area = np.bincount(reg[reg >= 0], minlength=nR)
    order = np.argsort(reg.ravel(), kind="stable"); flat = reg.ravel()[order]
    starts = np.searchsorted(flat, np.arange(nR)); ends = np.searchsorted(flat, np.arange(nR), side="right")
    Lf, inkf = L.reshape(-1, 3), ink.ravel()
    RF = np.zeros((nR, 7))
    for r in range(nR):
        idx = order[starts[r]:ends[r]]; px = Lf[idx]; ik = inkf[idx]; q = px[~ik] if (~ik).sum() >= 5 else px
        RF[r] = np.r_[np.median(q, 0), q.std(0), [ik.mean() * 100]]
    # adjacency between regions
    adj = [set() for _ in range(nR)]
    for a, b in ((reg[:, 1:], reg[:, :-1]), (reg[1:, :], reg[:-1, :])):
        m = (a >= 0) & (b >= 0) & (a != b)
        for x, y in set(zip(a[m].tolist(), b[m].tolist())): adj[x].add(y); adj[y].add(x)
    methods = {}
    methods["A0"] = [code_a0[c] for c in reg_cls]
    methods["A1"] = [code_a1[c] for c in reg_cls]
    best_c = np.array([int(np.argmin(dist(RF[r], SF, 0.0))) for r in range(nR)])
    best_t = np.array([int(np.argmin(dist(RF[r], SF, W_TEX))) for r in range(nR)])
    methods["A2c"] = [code_a1[i] for i in best_c]
    methods["A2t"] = [code_a1[i] for i in best_t]
    # ---- A3: anchors
    spot = [c for c in json.load(open(spot_json))["candidates"] if c["reader"] == reader and c["code"]]
    anchors = [[] for _ in range(nR)]
    for c in spot:
        x, y = int(c["centre_px"][0] * s), int(c["centre_px"][1] * s)
        if 0 <= y < reg.shape[0] and 0 <= x < reg.shape[1] and reg[y, x] >= 0: anchors[reg[y, x]].append(c["code"])
    codes = sorted({c for c in code_a1 if c})
    cref = {}   # code -> reference feature (swatch, then self-calibrated)
    for i, c in enumerate(code_a1):
        if c and c not in cref: cref[c] = SF[i]
    a3 = [None] * nR; reasons = [[] for _ in range(nR)]
    anch = {}
    for r in range(nR):
        u = sorted(set(anchors[r]))
        if len(u) > 1: reasons[r].append("MULTI_CODE")
        if u:
            cnt = {k: anchors[r].count(k) for k in u}; c = max(u, key=lambda k: cnt[k])
            if c in cref and np.linalg.norm(RF[r, :3] - cref[c][:3]) > DE_CONFLICT:
                reasons[r].append("ANCHOR_COLOUR_CONFLICT")
            anch[r] = c; a3[r] = c
    calib = {}
    for c in codes:
        rs = [r for r, cc in anch.items() if cc == c and "ANCHOR_COLOUR_CONFLICT" not in reasons[r]]
        if rs:
            w = area[rs].astype(float); calib[c] = (RF[rs] * w[:, None]).sum(0) / w.sum()
    ref_codes = codes; R = np.array([calib.get(c, cref[c]) for c in ref_codes])
    code_group = {}
    for i, c in enumerate(code_a1):
        if c: code_group.setdefault(c, set()).add(group[i])
    grouped_code = {c for c in codes if any(in_group[i] for i, cc in enumerate(code_a1) if cc == c)}
    pending = []
    for r in range(nR):
        if a3[r] is not None: continue
        c = ref_codes[int(np.argmin(dist(RF[r], R, W_TEX)))]
        if c in grouped_code: pending.append(r); a3[r] = None
        else: a3[r] = c
    # same-colour group regions: inherit from an adjacent assigned region with similar colour, iterate
    changed = True
    while changed:
        changed = False
        for r in pending:
            if a3[r] is not None: continue
            cand = [(np.linalg.norm(RF[r, :3] - RF[q, :3]), a3[q]) for q in adj[r] if a3[q] in grouped_code]
            cand = [x for x in cand if x[0] < DE_GROUP * 1.5]
            if cand: a3[r] = min(cand)[1]; changed = True
    for r in pending:
        if a3[r] is None: reasons[r].append("SAME_COLOUR_NO_ANCHOR")
    for r in range(nR):
        if a3[r] is None and not reasons[r]: reasons[r].append("NO_LEGEND_CODE")
        if a3[r] != methods["A2t"][r] and a3[r] is not None and r not in anch: reasons[r].append("METHOD_DISAGREE")
    methods["A3"] = a3
    # write code maps
    allc = sorted({c for m in methods.values() for c in m if c})
    ci = {c: i for i, c in enumerate(allc)}
    maps = {}
    for k, m in methods.items():
        lut = np.array([ci[c] if c else -1 for c in m] + [-1], np.int32)
        maps[k] = np.where(reg >= 0, lut[reg], -1).astype(np.int16)
    np.savez_compressed(out / "s1_maps.npz", regions=reg, **maps)
    rv = [{"region": int(r), "area_work_px": int(area[r]), "reasons": reasons[r], "code_A3": a3[r],
           "anchors": anchors[r], "centroid_work": [float(v) for v in np.argwhere(reg == r).mean(0)[::-1]]}
          for r in range(nR) if reasons[r] and area[r] >= 20]
    meta = {"codes": allc, "n_regions": int(nR), "reader": reader, "W_TEX": W_TEX, "DE_GROUP": DE_GROUP,
            "DE_CONFLICT": DE_CONFLICT, "n_anchored_regions": len(anch), "n_self_calibrated_codes": len(calib),
            "swatch_codes_A0": code_a0, "swatch_codes_A1": code_a1,
            "same_colour_swatch_groups": [sorted({code_a1[i] or "?" for i in range(nS) if group[i] == g})
                                          for g in sorted(set(group)) if sum(1 for x in group if x == g) > 1],
            "review_candidates": rv, "scores": "UNCALIBRATED"}
    json.dump(meta, open(out / "s1_meta.json", "w"), ensure_ascii=False, indent=1)
    print("regions", nR, "anchored", len(anch), "calibrated codes", len(calib), "groups", meta["same_colour_swatch_groups"])
    from collections import Counter
    print("review reasons", Counter(x for r in rv for x in r["reasons"]))


if __name__ == "__main__":
    main(*sys.argv[1:6], *(sys.argv[6:7] or []))
