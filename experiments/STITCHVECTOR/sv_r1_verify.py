"""R1 conversion verification (recovery P1): native SVG render (rsvg-convert) vs our GPKG read-back render.
Also counts SVG paths whose data does not start with M/m (invalid per SVG spec: such paths are not rendered).
Only image-derived R1 artefacts are read; no labels."""
import json, re, subprocess, sys
from pathlib import Path
import numpy as np, geopandas as gpd
from PIL import Image
import sv_common as C

R1 = C.ROOT / "runs/stitchvector/r1"
D = re.compile(r'<path\s+d="([^"]*)"')


def native(svg_path, h, w):
    png = Path("/tmp") / (svg_path.stem + "_rsvg.png")
    subprocess.run(["rsvg-convert", "-b", "none", "-w", str(w), "-h", str(h), "-f", "png", "-o", str(png), str(svg_path)], check=True)
    a = np.asarray(Image.open(png).convert("RGBA")); png.unlink(); return a


def ours(gpkg, h, w):
    g = gpd.read_file(gpkg, engine="pyogrio")
    lab = C.render(zip(g.geometry, g["rgb_key"], g["z"]), h, w)
    return C.key_rgb(np.where(lab < 0, 0, lab)), lab >= 0


def main(out):
    rows = []
    for js in sorted(R1.glob("*.json")):
        r = json.load(open(js))
        if not isinstance(r, dict): continue
        tag = js.stem; svg = R1 / f"{tag}.svg"; gp = R1 / f"{tag}.gpkg"; h, w = r["size"]
        txt = svg.read_text(); ds = D.findall(txt); bad = sum(1 for d in ds if not d.lstrip()[:1] in ("M", "m"))
        n = native(svg, h, w); o, cov = ours(gp, h, w)
        ncov = n[..., 3] == 255                      # fully covered by the native renderer
        both = ncov & cov
        de = np.abs(n[..., :3].astype(int) - o.astype(int)).max(-1)
        rows.append({"run": tag, "config": r["config"], "input": r["input"], "sample": r["sample"],
                     "paths": len(ds), "paths_without_moveto": bad,
                     "native_uncovered_share": round(float((n[..., 3] == 0).mean()), 4),
                     "ours_uncovered_share": round(float((~cov).mean()), 4),
                     "agree_exact_share_on_fully_covered": round(float((de[both] == 0).mean()), 4) if both.any() else None,
                     "agree_le2_share_on_fully_covered": round(float((de[both] <= 2).mean()), 4) if both.any() else None,
                     "partial_alpha_share_native": round(float(((n[..., 3] > 0) & (n[..., 3] < 255)).mean()), 4)})
        print(json.dumps(rows[-1]), flush=True)
    for r in rows:
        r["status"] = ("INVALID_UPSTREAM_SVG" if r["paths_without_moveto"] > 0 else
                       "VALID" if r["ours_uncovered_share"] == 0 and (r["agree_le2_share_on_fully_covered"] or 0) >= 0.99 else
                       "CHECK")
    json.dump(rows, open(out, "w"), indent=1)
    from collections import Counter
    print(Counter(r["status"] for r in rows))


if __name__ == "__main__":
    main(sys.argv[1])
