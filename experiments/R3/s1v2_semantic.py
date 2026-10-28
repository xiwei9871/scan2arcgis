"""S1 v2: ablations of the two A3 mechanisms that absorb small / same-colour units, plus
multi-candidate output (PREDICTION side; reads no ground truth, no xlsx).

Same inputs and features as s1_semantic.py (R1 regions, legend OCR tess_sub_case, in-map anchors).
Configurations are declared up front (no selection on results):

  V0_A3            calib=on          inherit=iterative   (must reproduce R3 A3)
  V1_calib_off     calib=off         inherit=iterative
  V2_calib_constr  calib=constrained inherit=iterative   (no re-estimation for same-colour-group codes)
  V3_inherit_off   calib=on          inherit=off
  V4_inherit_1hop  calib=on          inherit=one_hop     (only from directly anchored regions, one pass)
  V5_both_constr   calib=constrained inherit=one_hop
  V6_both_off      calib=off         inherit=off
  V7 = V5 + candidates, V8 = V6 + candidates : unassigned same-colour regions get the group's codes
                                              as a candidate set instead of nothing
  V9 = V7 + margin rule : small regions (< 5000 work px) whose best and second-best reference
                          distances differ by < 3 are left unassigned with their top-2 codes
Candidates never change the deterministic map. Scores are UNCALIBRATED.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from s1_semantic import feats, dist, W_TEX, DE_GROUP, DE_CONFLICT  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "R2_real_map"))
from scan2arcgis.recog.legend_classifier import ink_mask  # noqa: E402
from gsj_error_analysis import lab_of  # noqa: E402

MARGIN_SMALL_PX, MARGIN_DE = 5000, 3.0
CONFIGS = {
    "V0_A3": ("on", "iterative", False, False), "V1_calib_off": ("off", "iterative", False, False),
    "V2_calib_constr": ("constrained", "iterative", False, False), "V3_inherit_off": ("on", "off", False, False),
    "V4_inherit_1hop": ("on", "one_hop", False, False), "V5_both_constr": ("constrained", "one_hop", False, False),
    "V6_both_off": ("off", "off", False, False), "V7_constr_cands": ("constrained", "one_hop", True, False),
    "V8_off_cands": ("off", "off", True, False), "V9_constr_cands_margin": ("constrained", "one_hop", True, True)}


def prepare(img, r1_dir, legend_ocr_json, spot_json, reader):
    d = Path(r1_dir); ev = json.load(open(d / "r1_eval.json")); s = ev["scale"]
    rgb = cv2.resize(cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB), tuple(ev["work_size"]), interpolation=cv2.INTER_AREA)
    mm = np.load(d / "map_mask.npy"); pred = np.load(d / "pred_legend_rf_selftrain.npy").astype(np.int32)
    ink = ink_mask(rgb, mm); L = lab_of(cv2.medianBlur(rgb, 3))
    sws = ev["swatches"]; nS = len(sws)
    leg = {r["swatch"]: r for r in json.load(open(legend_ocr_json))["swatches"]}
    code = [leg[sw["id"]]["tess_sub_case"]["code"] for sw in sws]
    SF = []
    for sw in sws:
        x, y, w, h = sw["box"]; m = np.zeros(mm.shape, bool); m[y + 2:y + h - 2, x + 2:x + w - 2] = True
        SF.append(feats(L, ink_mask(rgb, m), m))
    SF = np.array(SF)
    group = list(range(nS))
    for i in range(nS):
        for j in range(i):
            if np.linalg.norm(SF[i, :3] - SF[j, :3]) < DE_GROUP: group[i] = group[j]
    grp_codes = {}
    for i, g in enumerate(group): grp_codes.setdefault(g, set()).add(code[i])
    in_group = [len({c for c in grp_codes[group[i]] if c}) > 1 for i in range(nS)]
    reg = np.full(mm.shape, -1, np.int32); k0 = 0
    for k in np.unique(pred[mm & (pred >= 0)]):
        n, cc = cv2.connectedComponents(((pred == k) & mm).astype(np.uint8), connectivity=4)
        sel = cc > 0; reg[sel] = cc[sel] - 1 + k0; k0 += n - 1
    nR = k0; area = np.bincount(reg[reg >= 0], minlength=nR)
    order = np.argsort(reg.ravel(), kind="stable"); flat = reg.ravel()[order]
    st = np.searchsorted(flat, np.arange(nR)); en = np.searchsorted(flat, np.arange(nR), side="right")
    Lf, inkf = L.reshape(-1, 3), ink.ravel(); RF = np.zeros((nR, 7))
    for r in range(nR):
        idx = order[st[r]:en[r]]; px = Lf[idx]; ik = inkf[idx]; q = px[~ik] if (~ik).sum() >= 5 else px
        RF[r] = np.r_[np.median(q, 0), q.std(0), [ik.mean() * 100]]
    adj = [set() for _ in range(nR)]
    for a, b in ((reg[:, 1:], reg[:, :-1]), (reg[1:, :], reg[:-1, :])):
        m = (a >= 0) & (b >= 0) & (a != b)
        for x, y in set(zip(a[m].tolist(), b[m].tolist())): adj[x].add(y); adj[y].add(x)
    anchors = [[] for _ in range(nR)]
    for c in json.load(open(spot_json))["candidates"]:
        if c["reader"] != reader or not c["code"]: continue
        x, y = int(c["centre_px"][0] * s), int(c["centre_px"][1] * s)
        if 0 <= y < reg.shape[0] and 0 <= x < reg.shape[1] and reg[y, x] >= 0: anchors[reg[y, x]].append(c["code"])
    codes = sorted({c for c in code if c})
    cref = {}
    for i, c in enumerate(code):
        if c and c not in cref: cref[c] = SF[i]
    grouped = {c for c in codes if any(in_group[i] for i, cc in enumerate(code) if cc == c)}
    group_of_code = {}
    for c in grouped:
        gs = {group[i] for i, cc in enumerate(code) if cc == c}
        group_of_code[c] = sorted({x for g in gs for x in grp_codes[g] if x})
    return dict(reg=reg, nR=nR, area=area, RF=RF, adj=adj, anchors=anchors, codes=codes, cref=cref,
                grouped=grouped, group_of_code=group_of_code)


def run_config(P, calib, inherit, cands, margin):
    nR, RF, area, codes, cref, grouped = P["nR"], P["RF"], P["area"], P["codes"], P["cref"], P["grouped"]
    a3 = [None] * nR; anch = {}; conflict = set()
    for r in range(nR):
        u = sorted(set(P["anchors"][r]))
        if u:
            cnt = {k: P["anchors"][r].count(k) for k in u}; c = max(u, key=lambda k: cnt[k])
            if c in cref and np.linalg.norm(RF[r, :3] - cref[c][:3]) > DE_CONFLICT: conflict.add(r)
            anch[r] = c; a3[r] = c
    calib_ref = {}
    if calib != "off":
        for c in codes:
            if calib == "constrained" and c in grouped: continue
            rs = [r for r, cc in anch.items() if cc == c and r not in conflict]
            if rs:
                w = area[rs].astype(float); calib_ref[c] = (RF[rs] * w[:, None]).sum(0) / w.sum()
    R = np.array([calib_ref.get(c, cref[c]) for c in codes])
    pending, best_code, cand = [], {}, {}
    for r in range(nR):
        if a3[r] is not None: continue
        dd = dist(RF[r], R, W_TEX); o = np.argsort(dd); c = codes[int(o[0])]; best_code[r] = c
        if c in grouped: pending.append(r); continue
        if margin and area[r] < MARGIN_SMALL_PX and len(o) > 1 and dd[o[1]] - dd[o[0]] < MARGIN_DE:
            cand[r] = [codes[int(o[0])], codes[int(o[1])]]; continue
        a3[r] = c
    if inherit == "iterative":
        changed = True
        while changed:
            changed = False
            for r in pending:
                if a3[r] is not None: continue
                cs = [(np.linalg.norm(RF[r, :3] - RF[q, :3]), a3[q]) for q in P["adj"][r] if a3[q] in grouped]
                cs = [x for x in cs if x[0] < DE_GROUP * 1.5]
                if cs: a3[r] = min(cs)[1]; changed = True
    elif inherit == "one_hop":
        for r in pending:
            cs = [(np.linalg.norm(RF[r, :3] - RF[q, :3]), anch[q]) for q in P["adj"][r] if q in anch and anch[q] in grouped]
            cs = [x for x in cs if x[0] < DE_GROUP * 1.5]
            if cs: a3[r] = min(cs)[1]
    if cands:
        for r in pending:
            if a3[r] is None: cand[r] = P["group_of_code"][best_code[r]]
    elif margin is False:
        cand = {}
    return a3, cand


def main(img, r1_dir, legend_ocr_json, spot_json, out_dir, reader="rapid", only=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    P = prepare(img, r1_dir, legend_ocr_json, spot_json, reader)
    ci = {c: i for i, c in enumerate(P["codes"])}
    maps, cands, summ = {}, {}, {}
    for k, (cal, inh, ca, mg) in CONFIGS.items():
        if only and k not in only.split(","): continue
        a3, cand = run_config(P, cal, inh, ca, mg)
        lut = np.array([ci[c] if c else -1 for c in a3] + [-1], np.int32)
        maps[k] = np.where(P["reg"] >= 0, lut[P["reg"]], -1).astype(np.int16)
        cands[k] = {str(r): c for r, c in cand.items()}
        summ[k] = {"calib": cal, "inherit": inh, "candidates": ca, "margin_rule": mg,
                   "assigned_regions": int(sum(1 for x in a3 if x)), "candidate_regions": len(cand)}
        print(k, summ[k])
    np.savez_compressed(out / "s1v2_maps.npz", regions=P["reg"], **maps)
    json.dump({"codes": P["codes"], "configs": summ, "candidates": cands, "reader": reader,
               "params": {"W_TEX": W_TEX, "DE_GROUP": DE_GROUP, "DE_CONFLICT": DE_CONFLICT,
                          "MARGIN_SMALL_PX": MARGIN_SMALL_PX, "MARGIN_DE": MARGIN_DE},
               "same_colour_code_groups": sorted({tuple(v) for v in P["group_of_code"].values()}),
               "scores": "UNCALIBRATED"}, open(out / "s1v2_meta.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:6], *(sys.argv[6:8] or []))
