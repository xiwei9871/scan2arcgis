"""Render markdown result tables from saved JSON results (so docs quote numbers verbatim)."""
import json, glob, sys
from pathlib import Path
R = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("experiments/R1_auto_vectorization/results")
d = json.loads((R / "synth_summary.json").read_text())
f = lambda x: "—" if x is None else f"{x[0]:.3f} [{x[1]:.2f}, {x[2]:.2f}] (n={x[3]})"
order = ["legacy_stratigraphy", "legacy_boundary", "legend_nearest_color", "legend_rf", "legend_rf_selftrain", "legend_rf_selftrain+sam2"]
out = ["## Synthetic suite: overall (mean, 95% case-bootstrap CI)\n",
       "| method | mIoU | object F1 | contact F1 (from areas) | fault-candidate F1 | all-lines F1 | all-lines P | all-lines R | runtime s |",
       "|---|---|---|---|---|---|---|---|---|"]
for m in order:
    v = d["overall_mean_ci95_n"].get(m, {})
    out.append(f"| {m} | " + " | ".join(f(v.get(k)) for k in ["miou", "obj_f1", "contact_f1", "fault_f1", "all_lines_f1", "all_lines_p", "all_lines_r", "runtime_s"]) + " |")
out += ["", "## Synthetic suite: by variant (mean of 3 seeds) — mIoU / object F1 / all-lines F1\n",
        "| variant | " + " | ".join(order) + " |", "|---|" + "---|" * len(order)]
g = lambda x: "—" if x is None else f"{x:.3f}"
for var, dd in d["by_variant_mean"].items():
    out.append(f"| {var} | " + " | ".join(f"{g(dd.get(m, {}).get('miou'))} / {g(dd.get(m, {}).get('obj_f1'))} / {g(dd.get(m, {}).get('all_lines_f1'))}" for m in order) + " |")
out += ["", "## Confidence signals (UNCALIBRATED) on synthetic suite\n",
        "| method | AUROC(region mean margin → object correct) | error px captured by top-10% tiles | by top-20% tiles |", "|---|---|---|---|"]
for m in ["legend_nearest_color", "legend_rf", "legend_rf_selftrain"]:
    v = d["overall_mean_ci95_n"][m]
    out.append(f"| {m} | {f(v['conf_auroc'])} | {f(v['cap10'])} | {f(v['cap20'])} |")
a = json.loads((R / "auto_retry_selection.json").read_text())
out += ["", "## AUTO_RETRY variant selection (synthetic, mIoU per case)\n",
        "| case | base | shade-invariant | picked by mean margin | oracle |", "|---|---|---|---|---|"]
for c, r in a.items():
    out.append(f"| {c} | {r['legend_rf_selftrain']['miou']:.3f} | {r['legend_rf_selftrain_shadeinv']['miou']:.3f} | {r['_picked'].replace('legend_rf_selftrain','base').replace('base_shadeinv','shadeinv')} | {r['_oracle'].replace('legend_rf_selftrain','base').replace('base_shadeinv','shadeinv')} |")
import numpy as np
mean = lambda k: np.mean([r[r[k]]["miou"] if k.startswith("_") else r[k]["miou"] for r in a.values()])
out.append(f"| **mean** | {mean('legend_rf_selftrain'):.4f} | {mean('legend_rf_selftrain_shadeinv'):.4f} | {mean('_picked'):.4f} | {mean('_oracle'):.4f} |")
out.append(f"\nSelector agreed with oracle in {sum(r['_picked']==r['_oracle'] for r in a.values())}/{len(a)} cases.")
real = R / "real_maps_summary.json"
if real.exists():
    rs = json.loads(real.read_text())
    out += ["", "## Real maps (no full ground truth): observations\n",
            "| map | swatches detected | legacy polygons | legacy unlabeled share | new regions | new classes used | new low-margin share | legacy s | new s |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in rs["maps"].items():
        out.append(f"| {k} | {v['swatches']} | {v['legacy_polygons']} | {v['legacy_unlabeled']:.3f} | {v['new_regions']} | {v['new_classes']} | {v['new_low_margin']:.3f} | {v['legacy_s']:.1f} | {v['new_s']:.1f} |")
(R / "tables.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
