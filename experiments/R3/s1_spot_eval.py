"""EVALUATION ONLY: score in-map code candidates (s1_map_spot output) against the official units.

For each candidate whose status is LEXICON_EXACT / LEXICON_EDIT1, look up the official unit under
its centre (gt_work, full-res px -> work px) and compare that unit's official symbol with the code.
Reports, per reader:
  precision_code       : fraction of lexicon-matched candidates whose code == official symbol there
  units_anchored       : official units with >= 1 correct candidate (out of units with a symbol)
  instances_anchored   : official connected instances with >= 1 correct candidate
  area_anchored        : map area covered by anchored instances
  same_colour_anchored : same-colour-group units with >= 1 correct candidate
Also lists the most frequent wrong (code, official) pairs.
"""
import json, sys
from collections import Counter
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from eval_common import Sheet  # noqa: E402


def main(r1_dir, xlsx, gt_dir, spot_json, out_json):
    sh = Sheet(r1_dir, xlsx, gt_dir); s = sh.scale
    sp = json.load(open(spot_json))
    gt, mm = sh.gt, sh.mm
    inst = np.full(gt.shape, -1, np.int32); k0 = 0; inst_unit = []
    for j in range(len(sh.symbols)):
        n, cc = cv2.connectedComponents(((gt == j) & mm).astype(np.uint8), connectivity=4)
        m = cc > 0; inst[m] = cc[m] - 1 + k0; inst_unit += [j] * (n - 1); k0 += n - 1
    inst_unit = np.array(inst_unit)
    inst_area = np.bincount(inst[inst >= 0], minlength=k0)
    res = {"readers": {}}
    for reader in ("rapid", "tess"):
        cs = [c for c in sp["candidates"] if c["reader"] == reader and c["code"]]
        ok, units_ok, inst_ok, wrong = 0, set(), set(), Counter()
        for c in cs:
            x, y = int(c["centre_px"][0] * s), int(c["centre_px"][1] * s)
            if not (0 <= y < gt.shape[0] and 0 <= x < gt.shape[1]) or gt[y, x] < 0:
                wrong[(c["code"], "outside")] += 1; continue
            sym = sh.symbols[gt[y, x]]
            if c["code"] == sym:
                ok += 1; units_ok.add(int(gt[y, x])); inst_ok.add(int(inst[y, x]))
            else:
                wrong[(c["code"], sym)] += 1
        with_sym = [j for j, x in enumerate(sh.symbols) if x]
        sc = sh.same_colour_units
        res["readers"][reader] = {
            "n_text_boxes": sum(1 for c in sp["candidates"] if c["reader"] == reader),
            "n_lexicon_matched": len(cs), "n_correct": ok, "precision_code": ok / max(len(cs), 1),
            "units_anchored": len(units_ok), "units_with_symbol": len(with_sym),
            "instances_anchored": len(inst_ok), "n_instances": int(k0),
            "area_anchored_frac": float(inst_area[list(inst_ok)].sum() / max(inst_area.sum(), 1)) if inst_ok else 0.0,
            "same_colour_anchored": sorted(sh.symbols[j] for j in units_ok if j in sc),
            "same_colour_units": [sh.symbols[j] for j in sc],
            "top_wrong": [[a, b, n] for (a, b), n in wrong.most_common(10)]}
        r = res["readers"][reader]
        print(reader, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k != "top_wrong"})
        print("   wrong", r["top_wrong"][:6])
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:6])
