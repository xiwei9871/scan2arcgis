"""Line detection Phase C run. Rules: sv_ld_prereg.json. Usage: sv_ld_run.py <json_dir> <img_dir> <split>   (.venv-sv)"""
import json, sys
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString
from PIL import Image, ImageDraw
import sv_synth as S, sv_ld_fix as F, sv_ld_compare as CMP, sv_ld_stages as L

HERE = Path(__file__).resolve().parent
PRE = json.load(open(HERE / "sv_ld_prereg.json"))


def overlay(img, objs, k, col=(0, 90, 255)):
    im = Image.fromarray(np.kron(img, np.ones((k, k, 1), np.uint8))); d = ImageDraw.Draw(im)
    for o in objs:
        for q in shapely.get_parts(o["geom"]): d.line([(x * k, y * k) for x, y in q.coords], fill=col, width=max(1, k // 2))
    return im


def errors(img, truth, objs, base, k):
    """green = found by both, blue = new vs B0, red = visible truth still missed, magenta = new output far from any truth line."""
    im = Image.fromarray((np.kron(img, np.ones((k, k, 1), np.uint8)) * 0.35 + 255 * 0.65).astype(np.uint8)); d = ImageDraw.Draw(im)
    Ub = shapely.union_all([o["geom"] for o in base]).buffer(1.5) if base else None
    Tu = shapely.union_all([LineString(t["axis"]) for t in truth["lines"]]).buffer(3)
    for o in objs:
        for q in shapely.get_parts(o["geom"]):
            for seg, col in ((shapely.intersection(q, Ub) if Ub is not None else None, (0, 160, 0)),
                             (shapely.difference(shapely.intersection(q, Tu), Ub) if Ub is not None else q, (0, 90, 255)),
                             (shapely.difference(shapely.difference(q, Tu), Ub) if Ub is not None else None, (230, 0, 230))):
                if seg is None or seg.is_empty: continue
                for p in shapely.get_parts(seg):
                    if p.geom_type == "LineString": d.line([(x * k, y * k) for x, y in p.coords], fill=col, width=max(1, k // 2))
    U = shapely.union_all([o["geom"] for o in objs]) if objs else None
    for li, t in enumerate(truth["lines"]):
        g = LineString(t["axis"]); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1)); vis = ~L.occluded(truth, li, pts)
        miss = vis & ((shapely.distance(pts, U) > 2.0) if U is not None else True)
        for p in np.asarray(shapely.get_coordinates(pts))[miss]: d.ellipse([p[0] * k - 1, p[1] * k - 1, p[0] * k + 1, p[1] * k + 1], fill=(230, 0, 0))
    return im


def sheet(ims, names):
    w, h = ims[0].size; out = Image.new("RGB", (len(ims) * (w + 8), h + 20), "white"); dd = ImageDraw.Draw(out)
    for i, (im, n) in enumerate(zip(ims, names)): out.paste(im, (i * (w + 8), 20)); dd.text((i * (w + 8) + 2, 4), n, fill="black")
    return out


def main(json_dir, img_dir, split):
    jd, idr = Path(json_dir), Path(img_dir); jd.mkdir(parents=True, exist_ok=True); idr.mkdir(parents=True, exist_ok=True)
    assert PRE["params"] == F.Q, "params differ from frozen code"
    CMP.METHODS = {k: CMP.ALL[k] for k in PRE["methods"]}
    seeds = PRE["seeds"][split]; CMP.main(str(jd / f"ld_{split}.json"), seeds)
    for s in seeds:
        img, truth, _ = S.generate(s); b0 = F.b0(img); outs = {k: CMP.ALL[k](img)[0] for k in PRE["methods"] if k != "B0"}
        k = 3; ims = [Image.fromarray(np.kron(img, np.ones((k, k, 1), np.uint8))), overlay(img, b0, k)]
        names = ["original", "B0 frozen 2.0"]
        for m, o in outs.items(): ims += [overlay(img, o, k), errors(img, truth, o, b0, k)]; names += [m, f"{m} vs B0: green same, blue new, magenta false, red missed"]
        sheet(ims, names).save(idr / f"ld_{split}_{s}_x3.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
