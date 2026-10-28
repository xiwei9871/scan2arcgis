"""R3 shared evaluation (frozen before R3 experiments; see experiments/R3/freeze/README.md).

Region / line / topology metrics reuse the R2 implementations unchanged
(gsj_run_r1.evaluate, line_prf, boundary; gsj_metrics3.adjacency). The topology block reproduces
gsj_metrics3's definitions so predictions other than R1's can be scored the same way.

Semantic metrics score a *symbol map*: every pixel gets a stratigraphic code string chosen by the
system (or None = unassigned). No class remapping of any kind is done at evaluation time.
Ground-truth symbols come from the sheet's xlsx and are used here only.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R2_real_map"))
from gsj_run_r1 import evaluate, line_prf, boundary  # noqa: E402,F401
from gsj_metrics3 import adjacency, read_legend  # noqa: E402,F401


class Sheet:
    """Ground truth at R1 work resolution (outputs of gsj_run_r1.py)."""

    def __init__(self, r1_dir, xlsx, gt_dir):
        d = Path(r1_dir); self.ev = json.load(open(d / "r1_eval.json")); self.scale = self.ev["scale"]
        self.gt = np.load(d / "gt_work.npy").astype(np.int32); self.mm = np.load(d / "map_mask.npy")
        w, h = self.ev["work_size"]
        g = Path(gt_dir)
        self.gt_contacts = cv2.resize(np.load(g / "gt_contacts.npy"), (w, h), interpolation=cv2.INTER_NEAREST) > 0
        self.gt_faults = cv2.resize(np.load(g / "gt_faults.npy"), (w, h), interpolation=cv2.INTER_NEAREST) > 0
        self.per = self.ev["methods"]["legend_rf_selftrain"]["per_unit"]
        self.units = [{"major_code": p["major_code"], "legend": {"LEGEND01": p["name"]}} for p in self.per]
        legend = read_legend(xlsx)
        self.codes = [str(int(float(p["major_code"]))) for p in self.per]
        self.symbols = [legend.get(c, {}).get("symbol") for c in self.codes]
        self.valid = self.mm & (self.gt >= 0)
        # same-colour groups from the official RGB (evaluation-side definition, as in the R2 audit)
        from gsj_metrics3 import lab1
        labs = {c: lab1(legend[c]["rgb"])[0] for c in self.codes if legend.get(c, {}).get("rgb")}
        self.same_colour_units = sorted({j for j, c in enumerate(self.codes) if c in labs and any(
            o != c and np.linalg.norm(labs[o] - labs[c]) < 3 for o in labs if o in self.codes)})


def semantic_scores(sheet, sym_idx, sym_list):
    """sym_idx: HxW int (-1 unassigned) indexing sym_list (system-chosen code strings)."""
    v = sheet.valid
    sym_list = list(sym_list)
    gts = np.array(sheet.symbols, dtype=object)[sheet.gt[v]]
    P = sym_idx[v]
    lut = np.array(sym_list + [None], dtype=object)
    ps = lut[np.where(P >= 0, P, len(sym_list))]
    assigned = P >= 0
    correct = np.array([a is not None and a == b for a, b in zip(ps, gts)])
    ious = []
    for j, s in enumerate(sheet.symbols):
        gm = sheet.gt[v] == j
        if s is None: ious.append(0.0); continue
        pm = ps == s
        u = int((gm | pm).sum()); ious.append(float((gm & pm).sum() / u) if u else 0.0)
    ious = np.array(ious)
    sc = sheet.same_colour_units
    return {"pixel_acc": float(correct.mean()), "miou": float(ious.mean()),
            "units_iou_ge_0.5": int((ious >= 0.5).sum()), "n_units": len(ious),
            "unassigned_frac": float((~assigned).mean()),
            "wrong_assigned_frac": float((assigned & ~correct).mean()),
            "same_colour_units": [sheet.symbols[j] for j in sc],
            "same_colour_mean_iou": float(ious[sc].mean()) if sc else None,
            "same_colour_units_iou_ge_0.5": int((ious[sc] >= 0.5).sum()) if sc else 0,
            "per_unit_iou": {str(sheet.symbols[j]): float(ious[j]) for j in range(len(ious))}}


def region_scores(sheet, pred):
    """Region/line/topology metrics for a class map (Hungarian = EVALUATION-ONLY UPPER BOUND)."""
    gt, mm = sheet.gt, sheet.mm
    e = evaluate(pred, gt, mm, sheet.units, 1.5)
    cb = boundary(np.where(mm, pred, -1)) & mm
    per = e["per_unit"]
    match = {j: int(p["matched_pred"][1:]) for j, p in enumerate(per) if p["matched_pred"]}
    inv = {p: j for j, p in match.items()}
    lut = np.full(int(max(pred.max(), 0)) + 2, -2, np.int32)
    for p, j in inv.items(): lut[p] = j
    pu = np.where(pred >= 0, lut[np.clip(pred, 0, None)], -2)
    small_thr = int(5000 * (sheet.scale / 0.5) ** 2)
    rec, rec_s, frags = [], [], []
    for j in range(len(per)):
        n, cc = cv2.connectedComponents(((gt == j) & mm).astype(np.uint8), connectivity=4)
        for k in range(1, n):
            m = cc == k; a = int(m.sum())
            if a < 20: continue
            hit = float((pu[m] == j).mean()) >= 0.5
            rec.append(hit)
            if a < small_thr: rec_s.append(hit)
            if j in match:
                nf, _ = cv2.connectedComponents((m & (pred == match[j])).astype(np.uint8), connectivity=4)
                frags.append(nf - 1)
    eg = adjacency(gt, mm); ep = adjacency(np.where(pu >= 0, pu, -1), mm)
    return {"region_ub_pixel_acc": e["pixel_acc_matched"], "region_ub_miou": e["miou_matched_all_units"],
            "region_ub_units_iou_ge_0.5": e["units_iou_ge_0.5"],
            "contact": line_prf(cb, sheet.gt_contacts, mm, 1.5),
            "fault_recall_by_area_edges": line_prf(cb, sheet.gt_faults, mm, 1.5)["recall"],
            "instance_recall": float(np.mean(rec)), "small_instance_recall": float(np.mean(rec_s)) if rec_s else None,
            "fragments_per_instance_mean": float(np.mean(frags)) if frags else None,
            "adjacency_precision": len(eg & ep) / max(len(ep), 1), "adjacency_recall": len(eg & ep) / max(len(eg), 1),
            "n_regions": int(sum(cv2.connectedComponents(((pred == k) & mm).astype(np.uint8), connectivity=4)[0] - 1
                                 for k in np.unique(pred[mm & (pred >= 0)]))),
            "note": "region_ub_* and adjacency use Hungarian matching = evaluation-only upper bound"}
