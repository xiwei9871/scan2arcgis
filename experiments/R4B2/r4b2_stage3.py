"""R4-B2 Stage 3: select 2 new independent test sheets (rules: r4b2_preregistration.json stage3_test_sheets).

Walks experiments/R4B1T/gate5_candidates.json in order, keeps only candidates still eligible by history, and
applies the UNCHANGED Q1/Q2/Q3 procedure experiments/R4A/gtf_dataset.process (download, vector integrity,
standard quadrangle, GeoTIFF frame, independent ink check). Stops at 2 PASS. Every visited sheet is logged.
Labels are NOT built here; no model is run here. Run only after the B2 checkpoint is frozen.
Usage: r4b2_stage3.py <out_json>   (.venv)
"""
import hashlib, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/R4A"))
import gtf_dataset as G  # noqa: E402

TARGET = 2


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def main(out_json):
    cands = json.load(open(ROOT / "experiments/R4B1T/gate5_candidates.json"))
    ck = {p: sha(ROOT / p) for p in ("runs/r4b2/B2_formal/best.pt",)}
    log, accepted = [], []
    for c in cands:
        if len(accepted) >= TARGET: break
        rec = {"code": c["code"], "year": c["year"], "vct": c["vct"]}
        if not c.get("eligible_by_history", False):
            log.append({**rec, "order": c["order"], "status": "SKIP_HISTORY"}); continue
        t0 = time.time(); row = G.process(rec); row["order"] = c["order"]; row["seconds"] = round(time.time() - t0, 1)
        log.append(row)
        if row["status"] == "PASS": accepted.append(c["code"])
        print(c["order"], c["code"], row["status"], {k: round(v, 2) for k, v in row.get("q3", {}).items() if isinstance(v, float)}, flush=True)
    res = {"role": "independent_test", "target": TARGET, "accepted": accepted, "reached_target": len(accepted) >= TARGET,
           "frozen_before_selection": {"b2_checkpoint_sha256": ck, "inference_code": "experiments/R4B2/r4b2_infer.py",
                                       "evaluation_code": "experiments/R4B2/r4b2_eval.py"},
           "rules": "experiments/R4A/gtf_dataset.process (Q1/Q2/Q3 unchanged)", "sealed_not_read": ["08011", "08021"], "log": log}
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1, default=float)
    print("accepted", accepted)


if __name__ == "__main__":
    main(sys.argv[1])
