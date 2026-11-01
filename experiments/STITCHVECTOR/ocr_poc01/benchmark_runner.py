"""OCR POC-01 scorer. Reads adapter outputs (runs/ocr_poc01/raw/*.json, local) + truth (truth/*.json), writes results/*.
Truth is AGENT_DRAFT: every number here is provisional until a human flips review_status (see 02_ground_truth_protocol.md).

Fixed rules (set before scoring):
- e2e dedup inside one engine run: none (each run scored on its own); multi-scale union = 1x + 2x, IoU>0.3 keeps higher conf.
- detection match: one-to-one greedy by IoU, a pair counts if IoU >= 0.3 OR (pred covers >= 0.6 of truth AND truth covers >= 0.3 of pred).
  A prediction box may contain several truth objects (merged lines) - those extra truths count as missed.
- recognition: exact match on raw string after stripping spaces; CER = Levenshtein / len(truth).
  'raw' compares code points as-is; 'nfkc' compares after NFKC (which folds ₂->2, Є stays Є, ′->'), reported separately.
- false positive on negatives: a prediction whose box covers >= 0.3 of a negative sample box and matches no truth.
"""
import csv, json, sys, unicodedata
from collections import defaultdict
from pathlib import Path
from shapely.geometry import Polygon, box
HERE = Path(__file__).parent; RAW = Path.home() / "geomap2arcgis/runs/ocr_poc01/raw"; RES = HERE / "results"
ENGINES = ["rapidocr", "paddleocr", "surya"]


def lev(a, b):
    d = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        p, d[0] = d[0], i
        for j, cb in enumerate(b, 1): p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (ca != cb))
    return d[-1]


def norm(s, mode):
    s = "".join(s.split())
    return unicodedata.normalize("NFKC", s) if mode == "nfkc" else s


def poly(p):
    g = Polygon(p).buffer(0); return g if g.area > 0 else box(*Polygon(p).bounds)


def match(preds, truth):
    cand = []
    for i, p in enumerate(preds):
        for j, t in enumerate(truth):
            inter = p["g"].intersection(t["g"]).area
            if inter <= 0: continue
            iou = inter / p["g"].union(t["g"]).area
            if iou >= 0.3 or (inter / t["g"].area >= 0.6 and inter / p["g"].area >= 0.3): cand.append((iou, i, j))
    used_p, used_t, pairs = set(), set(), {}
    for iou, i, j in sorted(cand, reverse=True):
        if i in used_p or j in used_t: continue
        used_p.add(i); used_t.add(j); pairs[j] = i
    return pairs


def load_truth():
    T = json.load(open(HERE / "truth/u2_text_truth.json"))["objects"]
    for t in T: t["g"] = box(*Polygon(t["polygon"]).bounds)
    N = json.load(open(HERE / "truth/u2_negatives.json"))
    for n in N: n["g"] = box(*Polygon(n["polygon"]).bounds)
    return T, N


def load_run(name):
    d = json.load(open(RAW / f"{name}.json"))
    for p in d["detections"]: p["g"] = poly(p["polygon"])
    return d


def union_scales(a, b):
    out = list(a["detections"])
    for p in b["detections"]:
        clash = [q for q in out if q["g"].intersection(p["g"]).area / q["g"].union(p["g"]).area > 0.3]
        if not clash: out.append(p)
        elif (p["confidence"] or 0) > max(q["confidence"] or 0 for q in clash):
            for q in clash: out.remove(q)
            out.append(p)
    return {**a, "detections": out, "seconds": a["seconds"] + b["seconds"]}


def rec_score(pairs_text, T):
    """pairs_text: {truth_idx: predicted string or None}. Returns per-category stats."""
    st = defaultdict(lambda: {"n": 0, "exact_raw": 0, "exact_nfkc": 0, "ed_raw": 0, "ed_nfkc": 0, "chars": 0})
    for j, t in enumerate(T):
        s = pairs_text.get(j); s = "" if s is None else s
        for key in ("ALL", t["category"]) + (("SPECIAL_SYMBOL",) if t["has_special_symbol"] else ()) + (("ON_GEOLOGICAL_LINE",) if t["overlaps_geological_line"] else ()):
            r = st[key]; r["n"] += 1; r["chars"] += len(norm(t["raw_text"], "raw"))
            for m in ("raw", "nfkc"):
                a, b = norm(s, m), norm(t["raw_text"], m)
                r[f"exact_{m}"] += a == b; r[f"ed_{m}"] += lev(a, b)
    return {k: {**v, "acc_raw": round(v["exact_raw"] / v["n"], 3), "acc_nfkc": round(v["exact_nfkc"] / v["n"], 3),
                "cer_raw": round(v["ed_raw"] / max(v["chars"], 1), 3), "cer_nfkc": round(v["ed_nfkc"] / max(v["chars"], 1), 3)} for k, v in st.items()}


def wilson(k, n, z=1.96):
    if n == 0: return [None, None]
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return [round((c - h) / d, 3), round((c + h) / d, 3)]


def main():
    RES.mkdir(exist_ok=True); T, N = load_truth(); summary = {"truth_status": "AGENT_DRAFT (not human verified)", "n_truth": len(T), "n_negatives": len(N), "runs": {}}
    det_rows, rec_rows, fp_rows = [], [], []
    runs = {}
    for e in ENGINES:
        for k in (1, 2): runs[f"{e}_e2e_x{k}"] = load_run(f"{e}_e2e_x{k}")
        runs[f"{e}_e2e_x1+x2"] = union_scales(runs[f"{e}_e2e_x1"], runs[f"{e}_e2e_x2"])
    for name, d in runs.items():
        P = d["detections"]; pairs = match(P, T); tp = len(pairs)
        prec, rec = tp / max(len(P), 1), tp / len(T); f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        matched_p = set(pairs.values())
        fp_neg = [n for n in N if any(i not in matched_p and P[i]["g"].intersection(n["g"]).area / n["g"].area >= 0.3 for i in range(len(P)))]
        unmatched = [P[i] for i in range(len(P)) if i not in matched_p]
        rs = rec_score({j: P[i]["raw_text"] for j, i in pairs.items()}, T)
        summary["runs"][name] = {"mode": "e2e", "n_pred": len(P), "tp": tp, "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
                                 "unmatched_pred": len(unmatched), "neg_hit": len(fp_neg), "neg_fp_rate": round(len(fp_neg) / len(N), 3),
                                 "seconds": d["seconds"], "recognition": rs}
        det_rows.append({"run": name, "n_pred": len(P), "tp": tp, "fp": len(P) - tp, "fn": len(T) - tp, "precision": round(prec, 3), "recall": round(rec, 3),
                         "f1": round(f1, 3), "recall_ci95": wilson(tp, len(T)), "neg_samples_hit": len(fp_neg), "neg_fp_rate": round(len(fp_neg) / len(N), 3), "seconds": d["seconds"]})
        for n in fp_neg: fp_rows.append({"run": name, "sample_id": n["sample_id"], "neg_kind": n["neg_kind"], "bbox": [round(v, 1) for v in n["g"].bounds]})
        for j, t in enumerate(T):
            i = pairs.get(j); rec_rows.append({"run": name, "sample_id": t["sample_id"], "category": t["category"], "truth": t["raw_text"],
                                               "pred": "" if i is None else P[i]["raw_text"], "confidence": "" if i is None else P[i]["confidence"],
                                               "detected": i is not None, "exact_raw": i is not None and norm(P[i]["raw_text"], "raw") == norm(t["raw_text"], "raw")})
    for e in ENGINES:
        for k in (1, 2):
            name = f"{e}_fixed_x{k}"; d = json.load(open(RAW / f"{name}.json")); by = {p["sample_id"]: p["raw_text"] for p in d["detections"]}
            rs = rec_score({j: by.get(t["sample_id"]) for j, t in enumerate(T)}, T)
            summary["runs"][name] = {"mode": "fixed_box", "seconds": d["seconds"], "recognition": rs}
            for t in T: rec_rows.append({"run": name, "sample_id": t["sample_id"], "category": t["category"], "truth": t["raw_text"], "pred": by.get(t["sample_id"], ""),
                                         "confidence": next((p["confidence"] for p in d["detections"] if p["sample_id"] == t["sample_id"]), ""), "detected": True,
                                         "exact_raw": norm(by.get(t["sample_id"], ""), "raw") == norm(t["raw_text"], "raw")})
    w = lambda f, rows: csv.DictWriter(open(RES / f, "w", newline=""), fieldnames=list(rows[0])) if rows else None
    for f, rows in (("detection_comparison.csv", det_rows), ("recognition_comparison.csv", rec_rows), ("negative_hits.csv", fp_rows)):
        if rows:
            wr = w(f, rows); wr.writeheader(); wr.writerows(rows)
    json.dump(summary, open(RES / "benchmark_summary.json", "w"), ensure_ascii=False, indent=1)
    print(f"{'run':24s} {'P':>6} {'R':>6} {'F1':>6} negFP | acc_all  code   place  special  (raw)")
    for name, s in summary["runs"].items():
        r = s["recognition"]; g = lambda c: r.get(c, {}).get("acc_raw", "-")
        print(f"{name:24s} {s.get('precision','-'):>6} {s.get('recall','-'):>6} {s.get('f1','-'):>6} {s.get('neg_hit','-'):>5} | {g('ALL'):>6} {g('GEOLOGICAL_CODE'):>6} {g('CHINESE_PLACE_NAME'):>6} {g('SPECIAL_SYMBOL'):>6}")


if __name__ == "__main__":
    main()
