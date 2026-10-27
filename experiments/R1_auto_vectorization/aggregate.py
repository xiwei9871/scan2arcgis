"""Aggregate per-case metrics.json into a summary table (by method x variant) with case-level bootstrap CIs."""
import json, sys
from pathlib import Path
import numpy as np
root = Path(sys.argv[1]); out = Path(sys.argv[2])
def _get(d, ks):
    for k in ks:
        if not isinstance(d, dict) or k not in d: return None
        d = d[k]
    return d
rows = []
for f in sorted(root.glob("*/metrics.json")):
    m = json.loads(f.read_text()); case = m["case"]; var = case.rsplit("_s", 1)[0]
    for meth, r in m["methods"].items():
        if "error" in r: rows.append(dict(case=case, variant=var, method=meth, error=r["error"])); continue
        rows.append(dict(case=case, variant=var, method=meth,
            miou=_get(r, ("pixel", "miou")), pix_acc=_get(r, ("pixel", "pixel_accuracy")),
            obj_f1=_get(r, ("object", "f1")), contact_f1=_get(r, ("contact_from_area", "f1")),
            fault_f1=_get(r, ("fault_candidates", "f1")), all_lines_f1=_get(r, ("all_lines", "f1")),
            all_lines_p=_get(r, ("all_lines", "precision")), all_lines_r=_get(r, ("all_lines", "recall")),
            conf_auroc=_get(r, ("confidence", "auroc_correct_vs_signal")),
            cap10=_get(r, ("review_tiles", "top10pct_tiles_error_capture")),
            cap20=_get(r, ("review_tiles", "top20pct_tiles_error_capture")),
            runtime_s=r.get("runtime_s")))
rows = [r for r in rows]
def boot(v, n=2000, seed=0):
    v = np.array([x for x in v if x is not None], float)
    if len(v) == 0: return None
    rng = np.random.default_rng(seed); bs = rng.choice(v, (n, len(v))).mean(1)
    return [float(v.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)), int(len(v))]
methods = sorted({r["method"] for r in rows}); metrics = ["miou", "obj_f1", "contact_f1", "fault_f1", "all_lines_f1", "all_lines_p", "all_lines_r", "conf_auroc", "cap10", "cap20", "runtime_s"]
summary = {m: {k: boot([r.get(k) for r in rows if r["method"] == m]) for k in metrics} for m in methods}
byvar = {}
for v in sorted({r["variant"] for r in rows}):
    byvar[v] = {m: {k: (lambda xs: float(np.mean(xs)) if xs else None)([r[k] for r in rows if r["method"] == m and r["variant"] == v and r.get(k) is not None]) for k in ["miou", "obj_f1", "contact_f1", "all_lines_f1"]} for m in methods}
out.write_text(json.dumps({"n_cases": len({r['case'] for r in rows}), "overall_mean_ci95_n": summary, "by_variant_mean": byvar, "rows": rows}, indent=1))
fmt = lambda x: "—" if x is None else f"{x[0]:.3f} [{x[1]:.3f},{x[2]:.3f}]"
print("method".ljust(28), *[k.ljust(22) for k in ["miou", "obj_f1", "contact_f1", "all_lines_f1", "conf_auroc", "cap20", "runtime_s"]])
for m in methods:
    print(m.ljust(28), *[fmt(summary[m][k]).ljust(22) for k in ["miou", "obj_f1", "contact_f1", "all_lines_f1", "conf_auroc", "cap20", "runtime_s"]])
print()
for v, d in byvar.items():
    print(v.ljust(12), "  ".join(f"{m.replace('legend_','L.')[:18]}:{(d[m]['miou'] or 0):.2f}/{(d[m]['obj_f1'] or 0):.2f}/{(d[m]['all_lines_f1'] or 0):.2f}" for m in methods))
