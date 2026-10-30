"""R1 summary: flag invalid VTracer outputs, per-sample table, Pareto front (vs_original exact share / dE90 vs vertices).
polygon mode is flagged INVALID_OUTPUT: 50-75% of its SVG paths have no leading moveto (invalid per SVG spec);
we do not repair VTracer output (pre-registration: measured renderer, no patching)."""
import json, sys
from pathlib import Path

INVALID = {"polygon": "INVALID_OUTPUT: paths without leading moveto (u2 69%, u3 51%, 13014 75%)"}


def load(d):
    rows = []
    for p in sorted(Path(d).glob("*.json")):
        r = json.load(open(p))
        if isinstance(r, dict) and "sample" in r: rows.append(r)
    return rows


def pareto(rows, key):
    """Non-dominated runs: fewer vertices and better fidelity (higher exact / lower dE90)."""
    out = []
    for r in rows:
        dom = False
        for s in rows:
            if s is r: continue
            better = (s["vertices"] <= r["vertices"]) and key(s) >= key(r) and ((s["vertices"] < r["vertices"]) or key(s) > key(r))
            if better: dom = True; break
        if not dom: out.append(r)
    return sorted(out, key=lambda r: r["vertices"])


def main(d, out):
    rows = load(d); res = {"invalid_configs": INVALID, "samples": {}}
    for s in sorted({r["sample"] for r in rows}):
        rs = [r for r in rows if r["sample"] == s]
        valid = [r for r in rs if r["config"] not in INVALID]
        tab = [{k: r[k] for k in ("input", "config", "objects", "vertices", "gpkg_bytes")} |
               {"exact_orig": r["vs_original"]["exact_share"], "dE90_orig": r["vs_original"]["dE90"],
                "thin_orig": r["vs_original"].get("thin_match_dE10"),
                "exact_q": (r.get("vs_quantized") or {}).get("exact_share"),
                "valid": r["config"] not in INVALID} for r in rs]
        pe = pareto(valid, lambda r: r["vs_original"]["exact_share"])
        pd = pareto(valid, lambda r: -r["vs_original"]["dE90"])
        res["samples"][s] = {"runs": tab,
                             "pareto_exact": [(r["input"], r["config"], r["vertices"], r["vs_original"]["exact_share"]) for r in pe],
                             "pareto_dE90": [(r["input"], r["config"], r["vertices"], r["vs_original"]["dE90"]) for r in pd]}
    json.dump(res, open(out, "w"), indent=1)
    for s, v in res["samples"].items():
        print("==", s); print(" pareto dE90:", v["pareto_dE90"]); print(" pareto exact:", v["pareto_exact"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
