"""EVALUATION ONLY: S1 v2 metrics. Definitions frozen in experiments/R3/freeze/README_v2.md
before any S1 v2 experiment was run. Reads official xlsx/GT; never imported by prediction code.

Inputs per configuration: a deterministic code map (int index into `codes`, -1 = unassigned) and,
per region, an optional candidate list (codes) for regions left unassigned.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from eval_common import Sheet, semantic_scores, evaluate, adjacency, read_legend  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R2_real_map"))
from gsj_metrics3 import lab1  # noqa: E402

SMALL_UNIT_PX = 10000   # official unit total area < this (work px, 100 dpi) -> "small unit"
SMALL_INST_PX = 5000    # official connected instance < this -> "small instance" (same as region_scores)


class Ctx:
    def __init__(self, sh, xlsx, regions, r1_pred):
        self.sh, self.reg = sh, regions
        v = sh.valid; gt = sh.gt; nU = len(sh.symbols)
        self.area = np.bincount(gt[v], minlength=nU)
        self.adj = adjacency(gt, sh.mm)
        leg = read_legend(xlsx)
        labs = {j: lab1(leg[c]["rgb"])[0] for j, c in enumerate(sh.codes) if leg.get(c, {}).get("rgb")}
        self.same_pair = {(a, b) for a in labs for b in labs if a != b and np.linalg.norm(labs[a] - labs[b]) < 3}
        self.small_units = [j for j in range(nU) if 0 < self.area[j] < SMALL_UNIT_PX]
        self.sc_units = list(sh.same_colour_units)
        self.code2unit = {s: j for j, s in enumerate(sh.symbols) if s}
        # official instances + whether R1 segmentation makes each one recoverable (Hungarian, eval-only)
        e = evaluate(r1_pred, gt, sh.mm, sh.units, 1.5)
        match = {j: int(p["matched_pred"][1:]) for j, p in enumerate(e["per_unit"]) if p["matched_pred"]}
        self.inst = []
        for j in range(nU):
            n, cc = cv2.connectedComponents(((gt == j) & sh.mm).astype(np.uint8), connectivity=4)
            for k in range(1, n):
                m = cc == k; a = int(m.sum())
                if a < 20: continue
                seg_ok = j in match and float((r1_pred[m] == match[j]).mean()) >= 0.5
                self.inst.append((j, np.flatnonzero(m.ravel()), a, seg_ok))
        flat = regions.ravel(); self.order = np.argsort(flat, kind="stable"); fs = flat[self.order]
        nR = int(regions.max()) + 1
        self.starts = np.searchsorted(fs, np.arange(nR)); self.ends = np.searchsorted(fs, np.arange(nR), side="right")


def score(ctx, det, codes, cands=None):
    sh = ctx.sh; v = sh.valid; gt = sh.gt; nU = len(sh.symbols)
    base = semantic_scores(sh, det, codes)
    cu = np.array([ctx.code2unit.get(c, -3) for c in codes] + [-1], np.int64)
    du = cu[np.where(det >= 0, det, len(codes))]
    asg = v & (det >= 0); ok = asg & (du == gt)
    out = {"semantic_miou": base["miou"], "semantic_pixel_acc": base["pixel_acc"],
           "units_iou_ge_0.5": base["units_iou_ge_0.5"], "n_units": base["n_units"],
           "det_coverage": float(asg.sum() / v.sum()), "assigned_precision": float(ok.sum() / max(asg.sum(), 1))}
    # candidate sets (regions without a deterministic code)
    cpx = hit = ksum = 0
    gtf, vf = gt.ravel(), v.ravel()
    for r, cl in (cands or {}).items():
        if not cl: continue
        idx = ctx.order[ctx.starts[r]:ctx.ends[r]]; idx = idx[vf[idx]]
        if not len(idx): continue
        units = {ctx.code2unit[c] for c in cl if c in ctx.code2unit}
        cpx += len(idx); hit += int(np.isin(gtf[idx], list(units)).sum()); ksum += len(cl) * len(idx)
    out.update({"candidate_px_frac": cpx / v.sum(), "candidate_hit_rate": (hit / cpx) if cpx else None,
                "mean_candidates": (ksum / cpx) if cpx else None,
                "det_or_candidate_hit": float((ok.sum() + hit) / v.sum())})
    # wrongful absorption: deterministic code of a LARGER, GT-ADJACENT unit
    wr = asg & (du >= 0) & (du != gt)
    u, w = gt[wr], du[wr]
    pair = np.array([((min(a, b), max(a, b)) in ctx.adj) and ctx.area[b] > ctx.area[a] for a, b in zip(u.tolist(), w.tolist())], bool) \
        if len(u) else np.zeros(0, bool)
    absorbed = np.bincount(u[pair], minlength=nU) if len(u) else np.zeros(nU)
    same_grp = np.array([(a, b) in ctx.same_pair for a, b in zip(u.tolist(), w.tolist())], bool) if len(u) else np.zeros(0, bool)
    absorbed_sg = np.bincount(u[same_grp], minlength=nU) if len(u) else np.zeros(nU)
    def rate(units, arr): a = ctx.area[units].sum(); return float(arr[units].sum() / a) if a else None
    out.update({"absorption_rate_all": float(absorbed.sum() / v.sum()),
                "absorption_rate_small_units": rate(ctx.small_units, absorbed),
                "absorption_rate_same_colour_units": rate(ctx.sc_units, absorbed),
                "same_colour_into_group_partner_rate": rate(ctx.sc_units, absorbed_sg),
                "n_small_units": len(ctx.small_units)})
    # deterministic small-instance recall, split into segmentation vs naming
    okf = ok.ravel()
    small = [(j, idx, a, s) for j, idx, a, s in ctx.inst if a < SMALL_INST_PX]
    hits = [float(okf[idx].mean()) >= 0.5 for j, idx, a, s in small]
    seg = [h for (j, idx, a, s), h in zip(small, hits) if s]
    out.update({"small_instances": len(small), "det_small_instance_recall": float(np.mean(hits)) if hits else None,
                "small_instances_segmentable_by_R1": len(seg),
                "det_small_recall_among_segmentable": float(np.mean(seg)) if seg else None})
    sc = ctx.sc_units; pu = base["per_unit_iou"]
    out.update({"same_colour_unit_iou": {sh.symbols[j]: pu[str(sh.symbols[j])] for j in sc},
                "same_colour_macro_iou": float(np.mean([pu[str(sh.symbols[j])] for j in sc])) if sc else None})
    return out


def main(r1_dir, xlsx, gt_dir, s1v2_dir, r3_s1_dir, out_json):
    sh = Sheet(r1_dir, xlsx, gt_dir)
    r1 = np.load(Path(r1_dir) / "pred_legend_rf_selftrain.npy").astype(np.int32)
    z = np.load(Path(s1v2_dir) / "s1v2_maps.npz"); meta = json.load(open(Path(s1v2_dir) / "s1v2_meta.json"))
    ctx = Ctx(sh, xlsx, z["regions"], r1)
    res = {"definitions": "experiments/R3/freeze/README_v2.md", "configs": {}}
    old = np.load(Path(r3_s1_dir) / "s1_maps.npz"); old_codes = json.load(open(Path(r3_s1_dir) / "s1_meta.json"))["codes"]
    for k in ("A1", "A2t", "A3"):
        res["configs"][f"R3_{k}"] = score(ctx, old[k].astype(np.int32), old_codes)
    for k, cfg in meta["configs"].items():
        cand = {int(r): c for r, c in meta["candidates"].get(k, {}).items()}
        res["configs"][k] = score(ctx, z[k].astype(np.int32), meta["codes"], cand)
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1, default=float)
    hdr = ("semantic_miou", "det_coverage", "assigned_precision", "candidate_hit_rate", "mean_candidates",
           "absorption_rate_small_units", "absorption_rate_same_colour_units", "det_small_instance_recall", "same_colour_macro_iou")
    print("config", *hdr)
    for k, r in res["configs"].items():
        print(k, *[("-" if r[h] is None else f"{r[h]:.3f}") for h in hdr])


if __name__ == "__main__":
    main(*sys.argv[1:7])
