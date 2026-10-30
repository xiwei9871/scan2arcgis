"""R1 conversion check (recovery P1): native SVG renderer (rsvg-convert, crispEdges = no anti-aliasing) vs our
SVG -> polygon -> rasterize converter, for every saved R1 SVG. Reads only the saved SVGs.

Status rules (fixed here, before this run):
  INVALID_UPSTREAM_SVG  any <path> whose d does not start with M/m (SVG requires it; VTracer 1.0.0a4 polygon mode
                        emits such paths; we do NOT guess a start point)
  VALID                 no such path, and our render agrees with the native crispEdges render (max channel diff <= 2)
                        on >= 0.98 of pixels and our uncovered share <= 0.001
  CHECK                 otherwise (reported, not silently accepted)
"""
import io, json, re, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image
import sv_common as C, sv_svg as S

R1 = C.ROOT / "runs/stitchvector/r1"
D_RE = re.compile(r'<path\s+d="([^"]*)"')


def native(svg):
    crisp = svg.replace("<svg ", '<svg shape-rendering="crispEdges" ', 1)
    png = subprocess.run(["rsvg-convert"], input=crisp.encode(), capture_output=True, check=True).stdout
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


def check(svg_path):
    svg = svg_path.read_text(); ds = D_RE.findall(svg)
    bad = sum(1 for d in ds if not d.lstrip()[:1] in ("M", "m"))
    nat = native(svg); h, w = nat.shape[:2]
    lab = C.render(S.svg_features(svg), h, w); ours = C.key_rgb(lab)
    agree = float((np.abs(ours.astype(int) - nat[..., :3].astype(int)).max(-1) <= 2).mean())
    unc = float((lab < 0).mean()); nat_unc = float((nat[..., 3] == 0).mean())
    st = "INVALID_UPSTREAM_SVG" if bad else ("VALID" if agree >= 0.98 and unc <= 0.001 else "CHECK")
    return {"run": svg_path.stem, "paths": len(ds), "paths_without_moveto": bad, "native_uncovered_share": round(nat_unc, 5),
            "ours_uncovered_share": round(unc, 5), "agree_crisp_le2": round(agree, 5), "status": st}


if __name__ == "__main__":
    rows = [check(p) for p in sorted(R1.glob("*.svg"))]
    out = Path(sys.argv[1]); out.parent.mkdir(parents=True, exist_ok=True)
    from collections import Counter
    json.dump({"renderer": "rsvg-convert, shape-rendering=crispEdges", "counts": Counter(r["status"] for r in rows),
               "runs": rows}, open(out, "w"), indent=1)
    for r in rows:
        if r["status"] != "VALID": print(r)
    print(Counter(r["status"] for r in rows))
