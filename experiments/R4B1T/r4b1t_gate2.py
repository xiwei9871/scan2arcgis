"""R4-B1T Gate 2: candidate B (pixel-adjacency edges) audit (rules: r4b1t_preregistration.json gate2_B).
10 training sheets, official labels only. Reconstruction from official labels is a property of the
representation, NOT a model result. No training.
Usage: r4b1t_gate2.py <out_dir>   (.venv: needs rasterio for the vector check)
"""
import csv, json, sys
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
import r4b1t_width as W  # noqa: E402
import r4b1t_labels as L  # noqa: E402
from r4a2_1_seeds import hybrid_markers, segment  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]
VECTOR_SHEETS = TRAIN[:2]


def pairs(lab, mask):
    """Set of unordered 4-adjacent label pairs (a != b, both > 0, both in mask)."""
    out = set()
    for a, b, m in ((lab[:, :-1], lab[:, 1:], mask[:, :-1] & mask[:, 1:]), (lab[:-1], lab[1:], mask[:-1] & mask[1:])):
        s = m & (a != b) & (a > 0) & (b > 0)
        for x, y in np.unique(np.sort(np.stack([a[s], b[s]], 1), 1), axis=0): out.add((int(x), int(y)))
    return out


def best_iou(i1, reg, valid):
    m = valid & (i1 > 0) & (reg > 0)
    C = coo_matrix((np.ones(int(m.sum())), (i1[m], reg[m])), shape=(int(i1.max()) + 1, int(reg.max()) + 1)).tocsr().tocoo()
    ia = np.bincount(i1[valid].ravel(), minlength=int(i1.max()) + 1); ra = np.bincount(np.where(valid, reg, 0).ravel(), minlength=int(reg.max()) + 1)
    iou = C.data / (ia[C.row] + ra[C.col] - C.data); b = np.zeros(int(i1.max()) + 1); np.maximum.at(b, C.row, iou)
    return b


def vector_check(rec, valid, er, ed):
    import rasterio.features
    from affine import Affine
    seg_regions = {}
    for geom, v in rasterio.features.shapes(rec.astype(np.int32), mask=valid & (rec > 0), connectivity=4, transform=Affine(1, 0, 0, 0, -1, 0)):
        for ring in geom["coordinates"]:
            for (x0, y0), (x1, y1) in zip(ring[:-1], ring[1:]):
                x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
                n = max(abs(x1 - x0), abs(y1 - y0)); sx, sy = np.sign(x1 - x0), np.sign(y1 - y0)
                for k in range(n):
                    a, b = (x0 + sx * k, y0 + sy * k), (x0 + sx * (k + 1), y0 + sy * (k + 1))
                    seg_regions.setdefault(tuple(sorted((a, b))), set()).add(int(v))
    shared = {s for s, r in seg_regions.items() if len(r) >= 2}
    ref = {tuple(sorted(s)) for s in L.segments_B(er, ed)}
    return {"polygon_shared_segments": len(shared), "edge_segments": len(ref), "identical": shared == ref,
            "only_in_polygons": len(shared - ref), "only_in_edges": len(ref - shared)}


def per_sheet(code):
    d0 = ROOT / "runs/r4a2" / code
    inst = np.load(d0 / "instance.npy"); unit = np.load(d0 / "unit.npy").astype(np.int32); ign = np.load(d0 / "ignore.npy")
    ub = np.load(d0 / "unit_boundary.npy") > 0
    V = (ign == 0) & (unit >= 0)
    er, ed = L.edges_B(unit, V)
    i1, area, ids, wid = W.canonical_widths(inst, V)
    # 1 no duplicate: edge count == number of differing valid 4-adjacent pairs (by construction) and UB/edge ratio
    n_pairs = int((V[:, :-1] & V[:, 1:] & (unit[:, :-1] != unit[:, 1:])).sum() + (V[:-1] & V[1:] & (unit[:-1] != unit[1:])).sum())
    r = {"edges": int(er.sum() + ed.sum()), "differing_valid_pairs": n_pairs, "ub_px_valid": int((ub & V).sum())}
    r["ub_px_per_edge"] = round(r["ub_px_valid"] / max(r["edges"], 1), 4)
    # 3 adjacency
    adj_inst = pairs(i1, V)
    rec, n_rec = L.reconstruct_B(er, ed, V)
    sep = set()
    for a, b, e in ((i1[:, :-1], i1[:, 1:], er[:, :-1]), (i1[:-1], i1[1:], ed[:-1])):
        s = e & (a > 0) & (b > 0)
        for x, y in np.unique(np.sort(np.stack([a[s], b[s]], 1), 1), axis=0): sep.add((int(x), int(y)))
    r["adjacency"] = {"instance_pairs": len(adj_inst), "edge_separated_pairs": len(sep), "identical": adj_inst == sep}
    # 4 reconstruction vs instances (restricted to V)
    m = V & (i1 > 0)
    P = np.unique(np.stack([i1[m], rec[m]], 1), axis=0)
    inst_ids = np.unique(i1[m]); split = inst_ids[np.bincount(P[:, 0], minlength=int(i1.max()) + 1)[inst_ids] > 1]
    rec_ids = np.unique(rec[m]); merged = rec_ids[np.bincount(P[:, 1], minlength=int(rec.max()) + 1)[rec_ids] > 1]
    causes = []
    for k in split:                                                     # instance cut into pieces by the valid mask?
        n_cc = ndi.label((i1 == k) & V, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])[1]
        causes.append({"instance": int(k - 1), "pieces_in_valid": int(n_cc), "cause": "valid mask splits the instance" if n_cc > 1 else "UNEXPLAINED"})
    r["reconstruction"] = {"instances_in_valid": int(len(inst_ids)), "regions": n_rec, "instances_split": int(len(split)),
                           "regions_merging_instances": int(len(merged)),
                           "partition_equal_share": round(1 - (len(split) + len(merged)) / max(len(inst_ids), 1), 6), "split_causes": causes}
    # 5 topology
    a, b, c, d = unit[:-1, :-1], unit[:-1, 1:], unit[1:, :-1], unit[1:, 1:]
    vv = V[:-1, :-1] & V[:-1, 1:] & V[1:, :-1] & V[1:, 1:]
    checker = vv & (((a == d) & (b == c) & (a != b)))
    r["topology"] = {"checkerboard_vertices": int(checker.sum()), "diagonal_same_unit_contacts": int((vv & (((a == d) & (a != b) & (a != c)) | ((b == c) & (b != a) & (b != d)))).sum()),
                     "small_lt3": int(sum(W.width_bin(w) == "lt3" for w in wid))}
    # recovery per width bin (direct reconstruction) and distance target
    bi = best_iou(i1, rec, V)
    D = L.dist_to_edge(er, ed)
    regd = segment(D, hybrid_markers(D)); bd = best_iou(i1, regd, V)
    md = np.zeros(int(i1.max()) + 1, np.float32); np.maximum.at(md, i1.ravel(), np.where(V, D, 0).ravel())
    rows = [{"sheet": code, "instance": int(k - 1), "area_px": int(area[k]), "width_px": round(float(w), 2), "width_bin": W.width_bin(w),
             "ub_share_of_area": round(float((ub & (i1 == k)).sum() / area[k]), 4) if False else None,
             "rec_B_direct": bool(bi[k] >= 0.5), "iou_B_direct": round(float(bi[k]), 4),
             "max_dist_to_edge": round(float(md[k]), 3), "rec_B_dist_hybrid": bool(bd[k] >= 0.5)} for k, w in zip(ids, wid)]
    if code in VECTOR_SHEETS: r["vector_mapping"] = vector_check(rec, V, er, ed)
    return r, rows


def summarize(rows):
    out = {}
    for b, _, _ in W.BINS:
        rs = [x for x in rows if x["width_bin"] == b]
        if rs: out[b] = {"n": len(rs), "rec_B_direct": round(float(np.mean([x["rec_B_direct"] for x in rs])), 4),
                         "pixels_kept_share": 1.0, "max_dist_to_edge_median": float(np.median([x["max_dist_to_edge"] for x in rs])),
                         "rec_B_dist_hybrid_markers": round(float(np.mean([x["rec_B_dist_hybrid"] for x in rs])), 4)}
    return out


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); sheets, rows = {}, []
    for c in TRAIN:
        s, r = per_sheet(c); sheets[c] = s; rows += r
        print(c, {k: s[k] for k in ("edges", "differing_valid_pairs", "ub_px_per_edge")}, s["adjacency"]["identical"],
              {k: v for k, v in s["reconstruction"].items() if k != "split_causes"}, s.get("vector_mapping"), flush=True)
    for x in rows: x.pop("ub_share_of_area")
    with open(out / "gate2_instances.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    inst_total = sum(s["reconstruction"]["instances_in_valid"] for s in sheets.values())
    bad = sum(s["reconstruction"]["instances_split"] + s["reconstruction"]["regions_merging_instances"] for s in sheets.values())
    unexplained = sum(1 for s in sheets.values() for c_ in s["reconstruction"]["split_causes"] if c_["cause"] == "UNEXPLAINED")
    res = {"label": "reconstruction from official labels: property of the representation, NOT a model result",
           "per_sheet": sheets, "by_width_bin": summarize(rows),
           "totals": {"instances_in_valid": inst_total, "partition_mismatches": bad, "partition_equal_share": round(1 - bad / max(inst_total, 1), 6),
                      "unexplained_mismatches": unexplained, "adjacency_identical_all": all(s["adjacency"]["identical"] for s in sheets.values()),
                      "edges_equal_pairs_all": all(s["edges"] == s["differing_valid_pairs"] for s in sheets.values()),
                      "ub_px_per_edge_pooled": round(sum(s["ub_px_valid"] for s in sheets.values()) / sum(s["edges"] for s in sheets.values()), 4),
                      "vector_mapping_identical": {c: sheets[c]["vector_mapping"]["identical"] for c in VECTOR_SHEETS}}}
    json.dump(res, open(out / "gate2_candidate_B.json", "w"), indent=1)
    print(json.dumps(res["totals"], indent=1)); print(json.dumps(res["by_width_bin"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
