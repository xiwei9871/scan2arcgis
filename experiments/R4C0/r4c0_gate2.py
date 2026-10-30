"""R4-C0 Gate 2: select tau (BOUNDARY_ONLY) and (tau, lambda) (BOUNDARY_APPEARANCE) on the 10 training sheets only.
Rules: r4c0_preregistration.json gate2. Candidate fixed by Gate 1 (B2). Uses the Gate 1 initial regions
(runs/r4c0/gate1/<sheet>_B2.npz) and the in-sample B2 predictions (runs/r4c0/pred). Labels are read only to score.
Objective: pooled small recall (r4a2_2_eval.instance_metrics, pooled by counts) s.t. pooled small over-seg <= 0.10;
ties (< 0.002) -> lower tau, then lower lambda.
Usage: r4c0_gate2.py <out_dir>   (.venv-ml)
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4c0_rag as R  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
from r4b1t_labels import ink_masks, lab_image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PR = json.load(open(ROOT / "experiments/R4C0/r4c0_preregistration.json"))["gate2"]
G1 = json.load(open(ROOT / "experiments/R4C0/gate1/gate1_summary.json"))
TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]
TAUS, LAMS = PR["tau_grid"], PR["lambda_grid"]


def candidate():
    q = G1["qualified"]; p = G1["pooled"]
    best = max(q, key=lambda m: (p[m]["oracle_B_6_20"], -p[m]["regions_median_of_sheets"]))
    ties = [m for m in q if p[best]["oracle_B_6_20"] - p[m]["oracle_B_6_20"] < 0.005]
    return min(ties, key=lambda m: p[m]["regions_median_of_sheets"]) if len(ties) > 1 else best


def sheet_inputs(code, cand):
    z = np.load(ROOT / f"runs/r4c0/gate1/{code}_{cand}.npz"); lab = z["lab"]
    d = ROOT / "runs/r4c0/pred" / code
    P = {"pr": np.load(d / "B2/prob_right.npy"), "pd": np.load(d / "B2/prob_down.npy")} if cand == "B2" else {"prob": np.load(d / f"{cand}/prob.npy")}
    _, sr, sd = R.strengths(cand, P); rag = R.build_rag(lab, sr, sd)
    bgr = cv2.imread(str(ROOT / "runs/r4a2" / code / "geotiff_rgb.png")); _, ink1, _ = ink_masks(bgr)
    cs, cc = R.region_colour(lab, lab_image(bgr), ink1)
    return lab, rag, cs, cc


def score(lab, rag, merges, Rref):
    out = {}
    for t, root in R.partitions(rag["n"], merges, TAUS).items():
        s = EV.instance_metrics(root[lab].astype(np.int64), Rref)[0]["small"]
        out[t] = (s["n"], s["recall_iou50"] * s["n"], s["over_seg"] * s["n"])
    return out


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); cand = candidate(); t0 = time.time()
    acc = {"BOUNDARY_ONLY": {t: [0, 0.0, 0.0] for t in TAUS}, **{f"APPEARANCE_{l}": {t: [0, 0.0, 0.0] for t in TAUS} for l in LAMS}}
    for code in TRAIN:
        lab, rag, cs, cc = sheet_inputs(code, cand); Rref = EV.load_ref(code)
        runs = {"BOUNDARY_ONLY": R.merge(rag)} | {f"APPEARANCE_{l}": R.merge(rag, cs, cc, lam=l) for l in LAMS}
        for k, mg in runs.items():
            for t, (n, r, o) in score(lab, rag, mg, Rref).items():
                a = acc[k][t]; a[0] += n; a[1] += r; a[2] += o
        print(code, "done", round((time.time() - t0) / 60, 1), "min", flush=True)
    table = {k: {str(t): {"n": v[0], "small_recall": v[1] / v[0], "small_over_seg": v[2] / v[0]} for t, v in d.items()} for k, d in acc.items()}

    def pick(keys):
        rows = [(k, t, table[k][str(t)]) for k in keys for t in TAUS if table[k][str(t)]["small_over_seg"] <= PR_OVERSEG]
        if not rows: return None
        top = max(r[2]["small_recall"] for r in rows)
        near = [r for r in rows if top - r[2]["small_recall"] < 0.002]
        lam = lambda k: 0.0 if k == "BOUNDARY_ONLY" else float(k.split("_")[1])
        k, t, v = min(near, key=lambda r: (r[1], lam(r[0])))
        return {"key": k, "tau": t, "lambda": lam(k), **v}
    sel = {"RAG_BOUNDARY_ONLY": pick(["BOUNDARY_ONLY"]), "RAG_BOUNDARY_APPEARANCE": pick([f"APPEARANCE_{l}" for l in LAMS])}
    res = {"candidate": cand, "selection_on": "10 training sheets, in-sample predictions", "objective": PR["objective"],
           "grid_table": table, "selected": sel, "minutes": round((time.time() - t0) / 60, 1)}
    json.dump(res, open(out / "gate2_selection.json", "w"), indent=1)
    print(json.dumps(sel, indent=1))


PR_OVERSEG = 0.10

if __name__ == "__main__":
    main(sys.argv[1])
