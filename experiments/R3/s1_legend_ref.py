"""EVALUATION ONLY: build a reference code for each detected legend swatch, and score legend OCR.

Reference construction (reads ground truth; never imported by prediction code):
each detected swatch is assigned the official unit whose publisher RGB (xlsx) is nearest in Lab,
accepted only if dE < 10 and that unit's colour is not shared (dE < 3) with another unit.
Swatches that fail these tests get reference None and are reported separately as "ambiguous":
they cannot be scored by colour alone, which is itself the same-colour/other-code problem.

OCR scoring separates
  read_any   : engine returned a non-empty token
  exact      : token == reference code (case-sensitive; GSJ codes are case-significant: Ob vs ob)
  exact_ci   : case-insensitive match
  valid      : token is SOME code that exists in the sheet's legend (would be accepted by a lexicon)
"""
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R2_real_map"))
from gsj_metrics3 import read_legend, lab1  # noqa: E402


def swatch_reference(ev, legend, dE_max=10.0, dE_same=3.0):
    units = {c: lab1(v["rgb"])[0] for c, v in legend.items() if v.get("rgb") and v.get("symbol")}
    ref = {}
    for sw in ev["swatches"]:
        L = lab1(sw["fill_rgb"])[0]
        d = sorted((float(np.linalg.norm(L - u)), c) for c, u in units.items())
        if not d or d[0][0] >= dE_max:
            ref[sw["id"]] = {"code": None, "reason": "no_unit_within_dE10", "nearest_dE": d[0][0] if d else None}; continue
        best = d[0][1]
        same = [c for c, u in units.items() if c != best and np.linalg.norm(units[best] - u) < dE_same]
        if same:
            ref[sw["id"]] = {"code": None, "reason": "same_colour_group", "group": sorted([legend[x]["symbol"] for x in [best] + same]),
                             "nearest_dE": d[0][0]}
        else:
            ref[sw["id"]] = {"code": legend[best]["symbol"], "major_code": best, "nearest_dE": d[0][0]}
    return ref


def score(ocr, ref, lexicon):
    out = {}
    for eng in ocr["engines"]:
        n = n_any = ex = exci = val = 0
        for r in ocr["swatches"]:
            rc = ref[r["swatch"]]["code"]
            t = r[eng]["code"]
            if t: n_any += 1
            if t and t in lexicon: val += 1
            if rc is None: continue
            n += 1
            ex += int(t == rc); exci += int(bool(t) and t.lower() == rc.lower())
        out[eng] = {"n_swatches": len(ocr["swatches"]), "n_scorable": n, "read_any": n_any,
                    "exact": ex, "exact_rate": ex / max(n, 1), "exact_ci": exci, "valid_in_lexicon": val}
    return out


def main(r1_eval, xlsx, ocr_json, out_json):
    ev = json.load(open(r1_eval)); legend = read_legend(xlsx); ocr = json.load(open(ocr_json))
    ref = swatch_reference(ev, legend)
    lex = {v["symbol"] for v in legend.values() if v.get("symbol")}
    sc = score(ocr, ref, lex)
    res = {"note": "EVALUATION ONLY reference from xlsx colours", "reference": ref, "scores": sc,
           "ambiguous_swatches": {k: v for k, v in ref.items() if v["code"] is None}}
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1)
    for k, v in sc.items(): print(k, v)
    print("scorable", sum(1 for v in ref.values() if v["code"]), "ambiguous", {k: v.get("reason") for k, v in ref.items() if not v["code"]})


if __name__ == "__main__":
    main(*sys.argv[1:5])
