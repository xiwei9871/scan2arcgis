"""Protection ablation on u2 centre 300x300: descriptive only (already-viewed sample). Rules: sv_pa_prereg.json.
Per method: Oracle line coverage (2 px) by line id, red faults, PN1/PN2 axis share with a line on it, and where added
lines lie (near an Oracle trace / near text-or-symbol ink not traced / elsewhere). Usage: sv_pa_u2.py <json_out> <img_dir>"""
import json, sys
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString, box
from PIL import Image, ImageDraw
import sv_common as Cm, sv_oracle as O, sv_oracle_v2 as O2, sv_pa as PA

MAPC = 94


def cover(objs, g, tol=2.0):
    U = shapely.union_all([o["geom"] for o in objs]) if objs else None
    pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
    return float((shapely.distance(pts, U) <= tol).mean()) if U is not None else 0.0


def main(out, img_dir):
    a, _ = Cm.centre_crop(Cm.load("u2"), 300, 300); P = dict(O.P); P.update(O2.PRE["params"]); ol, _ = O2.build(a, P)
    traces = {f["id"]: LineString(f["raw"]) for f in ol if len(f["raw"]) >= 2}; T = shapely.union_all(list(traces.values())).buffer(3.0)
    bands = {q["id"]: LineString(q["axis"]) for q in O2.ORA["protected"]}; mapbox = box(0, 0, MAPC, 300); res = {"nature": "descriptive, already-viewed sample", "methods": {}}
    base = None; idir = Path(img_dir); idir.mkdir(parents=True, exist_ok=True); ims = [Image.fromarray(np.kron(a[:, :MAPC], np.ones((4, 4, 1), np.uint8)))]
    for m in PA.METHODS:
        objs, info = PA.run(a, m)
        if m == "M0": base = objs
        added = objs[len(base):]
        far = [shapely.difference(o["geom"], T) for o in added]
        res["methods"][m] = {"lines": len(objs), "cover_by_line": {k: cover(objs, g) for k, g in traces.items()},
                             "red_fault_cover_mean": float(np.mean([cover(objs, g) for k, g in traces.items() if k.startswith("F") and "t" not in k])),
                             "band_axis_share_with_line": {k: cover(objs, g, 0.5) for k, g in bands.items()},
                             "added_lines": len(added), "added_length": float(sum(o["geom"].length for o in added)),
                             "added_length_far_from_oracle_traces_in_map": float(sum(shapely.intersection(x, mapbox).length for x in far)),
                             "added_length_outside_map": float(sum(shapely.difference(o["geom"], mapbox).length for o in added)),
                             "candidates": info["candidates"], "kept": info["kept"]}
        im = Image.fromarray(np.kron(a[:, :MAPC], np.ones((4, 4, 1), np.uint8))); d = ImageDraw.Draw(im)
        for o in base:
            for q in shapely.get_parts(o["geom"]): d.line([(x * 4, y * 4) for x, y in q.coords], fill=(0, 90, 255), width=2)
        for o in added:
            for q in shapely.get_parts(o["geom"]): d.line([(x * 4, y * 4) for x, y in q.coords], fill=(230, 0, 230), width=2)
        d.text((2, 2), f"{m}: blue = B2c, magenta = added", fill="black"); ims.append(im); im.save(idir / f"u2_{m}_map_x4.png")
    w, h = ims[0].size; sh = Image.new("RGB", (len(ims) * (w + 8), h), "white")
    for i, im in enumerate(ims): sh.paste(im, (i * (w + 8), 0))
    sh.save(idir / "u2_sheet_map_x4.png"); json.dump(res, open(out, "w"), indent=1)
    for m, x in res["methods"].items():
        print(m, {k: round(x["cover_by_line"][k], 2) for k in ("G1", "G2", "G3")}, "faults", round(x["red_fault_cover_mean"], 2), "bands", {k: round(v, 2) for k, v in x["band_axis_share_with_line"].items()},
              "added", x["added_lines"], round(x["added_length"]), "far in map", round(x["added_length_far_from_oracle_traces_in_map"]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
