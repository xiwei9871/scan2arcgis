"""StitchVector 3.0 minimal line recovery run. Rules: sv_v3_prereg.json.
Usage: sv_v3_run.py <json_dir> <img_dir> <split>   (.venv-sv). split = test (new seeds) or viewed (P1 test seeds 2001-2005)."""
import json, sys
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString
from PIL import Image, ImageDraw
import sv_synth as S, sv_autoline as AL, sv_v3 as V, sv_v3_compare as CMP

HERE = Path(__file__).resolve().parent
PRE = json.load(open(HERE / "sv_v3_prereg.json"))
PAL = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (0, 200, 200), (240, 50, 230), (150, 190, 0),
       (0, 128, 128), (170, 110, 40), (128, 0, 0), (0, 0, 160), (128, 128, 0), (255, 180, 0), (0, 150, 255), (199, 21, 133)]


def draw(img, objs, k, mode):
    base = np.kron(img, np.ones((k, k, 1), np.uint8)).astype(float)
    im = Image.fromarray((base * 0.3 + 255 * 0.7).astype(np.uint8)) if mode != "on_image" else Image.fromarray(base.astype(np.uint8))
    d = ImageDraw.Draw(im)
    for n, o in enumerate(objs):
        c = (0, 90, 255) if mode == "on_image" else PAL[n % len(PAL)]
        for part in shapely.get_parts(o["geom"]):
            d.line([(x * k, y * k) for x, y in part.coords], fill=c, width=max(1, k // 2))
    return im


def sheet(panels, names):
    w, h = panels[0].size; out = Image.new("RGB", (len(panels) * (w + 8), h + 20), "white"); d = ImageDraw.Draw(out)
    for i, (p, n) in enumerate(zip(panels, names)): out.paste(p, (i * (w + 8), 20)); d.text((i * (w + 8) + 2, 4), n, fill="black")
    return out


def main(json_dir, img_dir, split):
    jd, idr = Path(json_dir), Path(img_dir); jd.mkdir(parents=True, exist_ok=True); idr.mkdir(parents=True, exist_ok=True)
    assert PRE["params"] == V.Q, "params differ from frozen code"
    seeds = PRE["seeds"][split]; CMP.main(str(jd / f"v3_{split}.json"), seeds); res = json.load(open(jd / f"v3_{split}.json"))
    names = ["original", "2.0 objects (one colour each)", "3.0 logical objects (one colour per logical_id)", "3.0 lines on original"]
    examples = []
    for s in seeds:
        img, truth, _ = S.generate(s); L2, _ = AL.extract(img); objs, lg, r, info = V.run(img)
        k = 3; sheet([Image.fromarray(np.kron(img, np.ones((k, k, 1), np.uint8))), draw(img, L2, k, "c"), draw(img, lg, k, "c"), draw(img, lg, k, "on_image")],
                     names).save(idr / f"v3_{split}_{s}_x3.png")
        for lid, m in res["tiles"][str(s)]["3.0"]["lines"].items():
            m2 = res["tiles"][str(s)]["2.0"]["lines"][lid]
            if m["verdict"] == "acceptable" and m2["select_count"] > m["select_count"]: examples.append((s, lid, m2["select_count"], m["select_count"]))
    for s, lid, n2, n3 in examples[:5]:
        img, truth, _ = S.generate(s); L2, _ = AL.extract(img); _, lg, _, _ = V.run(img)
        g = LineString([t for t in truth["lines"] if t["id"] == lid][0]["axis"]); x0, y0, x1, y1 = [int(v) for v in g.buffer(6).bounds]
        x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(256, x1), min(256, y1); k = 4
        near = lambda O: [o for o in O if shapely.length(shapely.intersection(o["geom"], g.buffer(2))) >= 0.6 * o["geom"].length]
        crop = lambda im: im.crop((x0 * k, y0 * k, x1 * k, y1 * k))
        sheet([crop(Image.fromarray(np.kron(img, np.ones((k, k, 1), np.uint8)))), crop(draw(img, near(L2), k, "c")), crop(draw(img, near(lg), k, "c"))],
              [f"{s} {lid} original", f"2.0: {n2} objects", f"3.0: {n3} logical object(s)"]).save(idr / f"v3_{split}_example_{s}_{lid}.png")
    res["grouping_examples"] = [{"seed": s, "line": lid, "objects_2_0": n2, "logical_3_0": n3} for s, lid, n2, n3 in examples]
    json.dump(res, open(jd / f"v3_{split}.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
