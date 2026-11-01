"""U2 full-sheet visual residual (task B + D). Read-only on every input.

Renders u2_full_B2c.gpkg and u2_full_text_cleared.gpkg at the scan's exact size and pixel grid (tools/stitchvector_editor/
render.py: pixel-centre rasterisation, faces then lines by draw_order, no anti-aliasing, no registration or warping) and
subtracts per RGB channel. Raw residuals are kept as uint8 .npy (max |dR|,|dG|,|dB| per pixel); heat-map PNGs are views.
Text / legend / symbol differences are NOT geological errors: the text-box mask is reported separately.
"""
import hashlib, json, sys, time
from pathlib import Path
import numpy as np, pyogrio
from PIL import Image
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from tools.stitchvector_editor import render as R  # noqa: E402

RUN = Path.home() / "geomap2arcgis/runs/stitchvector/u2_full"
MAP, B2C, CLR, OCR = RUN / "u2_map.png", RUN / "u2_full_B2c.gpkg", RUN / "u2_full_text_cleared.gpkg", RUN / "u2_ocr_full.json"
OUT = RUN / "visual_diff"


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    t0 = time.time(); OUT.mkdir(parents=True, exist_ok=True); before = {p.name: sha(p) for p in (MAP, B2C, CLR)}
    scan = np.asarray(Image.open(MAP).convert("RGB")); H, W = scan.shape[:2]
    rb, fid_b, lid_b = R.render(B2C, (H, W)); rc, fid_c, lid_c = R.render(CLR, (H, W))
    rb2, _, _ = R.render(B2C, (H, W))
    tmask = R.text_mask(CLR, (H, W), pad=1)                       # boxes of the 126 cleared text objects (+1 px)
    c_full, d_full = R.residual(scan, rb)                              # scan vs B2c
    c_clr, d_clr = R.residual(scan, rc)                               # scan vs cleared
    c_ba, d_ba = R.residual(rb, rc)                                  # B2c vs cleared
    imgs = {"u2_render_B2c.png": rb, "u2_render_cleared.png": rc,
            "u2_residual_full.png": R.heatmap(d_full), "u2_residual_no_text.png": R.heatmap(d_full, tmask),
            "u2_residual_before_after.png": R.heatmap(d_ba)}
    for k, a in imgs.items(): Image.fromarray(a).save(OUT / k)
    for k, d in (("residual_scan_vs_B2c", c_full), ("residual_scan_vs_cleared", c_clr), ("residual_B2c_vs_cleared", c_ba)): np.save(OUT / f"{k}_rgb.npy", d)
    ba = d_ba > 0
    M = {"inputs": {**before, "shape_hw": [H, W]}, "settings": {"rasterisation": "pixel centre, all_touched=False", "order": "faces, then lines by draw_order",
         "anti_alias": False, "registration": "none", "residual": "max over R,G,B of |a-b| (uint8); raw .npy kept"},
         "checks": {"scan_vs_itself_max": int(R.residual(scan, scan)[0].max()), "repeat_render_identical": bool((rb == rb2).all()),
                    "uncovered_px_B2c": int((fid_b < 0).sum()), "uncovered_px_cleared": int((fid_c < 0).sum())},
         "scan_vs_B2c": R.stats(d_full), "scan_vs_B2c_outside_text": R.stats(d_full, tmask), "scan_vs_B2c_inside_text": R.stats(d_full, ~tmask),
         "scan_vs_cleared": R.stats(d_clr), "scan_vs_cleared_outside_text": R.stats(d_clr, tmask), "scan_vs_cleared_inside_text": R.stats(d_clr, ~tmask),
         "B2c_vs_cleared": {**R.stats(d_ba), "changed_px": int(ba.sum()), "changed_px_inside_text_boxes": int((ba & tmask).sum()),
                            "changed_px_outside_text_boxes": int((ba & ~tmask).sum())},
         "text_mask_px": int(tmask.sum()),
         "interpretation": "Residual is appearance, not geology: text, legend symbols, fault teeth, hatching and scan noise all show up. "
                           "Inside text boxes a larger scan residual after clearing is expected (glyph ink no longer copied)."}
    M["inputs_unchanged"] = all(sha(RUN / k) == v for k, v in before.items())
    M["outputs_local"] = {p.name: sha(p) for p in sorted(OUT.iterdir()) if p.suffix in (".png", ".npy")}
    M["seconds"] = round(time.time() - t0, 1)
    o = ROOT / "experiments/STITCHVECTOR/u2_visual_diff/u2_visual_diff_metrics.json"; o.parent.mkdir(parents=True, exist_ok=True)
    json.dump(M, open(o, "w"), indent=1); print(json.dumps({k: M[k] for k in ("checks", "B2c_vs_cleared", "inputs_unchanged", "seconds")}))
    for k in ("scan_vs_B2c", "scan_vs_B2c_outside_text", "scan_vs_cleared_outside_text", "scan_vs_cleared_inside_text", "scan_vs_B2c_inside_text"):
        print(k, {x: M[k][x] for x in ("mean_max_abs", "p90", "share_ge_30")})


if __name__ == "__main__":
    main()
