"""R4-C0.1 Gate 1: local GIS QA package for 13014 / 15076 (already exposed sheets; no new evaluation design).

Fixed sampling rules (written before any window is looked at):
  categories, per sheet, 4 windows each (numpy default_rng(20261029) over the list sorted by instance id / window id):
    NARROW_3_6, NARROW_6_10, NARROW_10_20   small instances in that canonical width bin (any outcome)
    NEW_RECOVERED   small instance: RAG_BOUNDARY_ONLY IoU >= 0.5 and M2_hybrid < 0.5
    NEW_OVERSEG     small instance: RAG_BOUNDARY_ONLY has no region covering >= 50% of it, M2_hybrid has one
    FRAGMENTS       256 px grid windows ranked by the number of RAG_BOUNDARY_ONLY regions < 50 px; top 4
    FALSE_BOUNDARY  256 px grid windows ranked by RAG_BOUNDARY_ONLY boundary px farther than 2 px from UNIT_BOUNDARY
                    and within 1 px of image ink (black-hat > 40); top 4
    LARGE_MERGE     instances >= 20000 px whose RAG_BOUNDARY_ONLY best-overlap region holds >= 50% of another instance
    LARGE_SPLIT     instances >= 20000 px covered >= 1% by >= 4 RAG_BOUNDARY_ONLY regions
  window: 256 x 256 px centred on the instance's median pixel (or the grid window), clipped to the image
Panels per window (local only): RGB | official boundary (reference) | M2_hybrid | RAG_BOUNDARY_ONLY | RAG_BOUNDARY_APPEARANCE
Outputs: committed index JSON with sheet, category, window coordinates and per-method IoU of the target (no pixels);
local HTML viewer + JPEG panels under runs/r4c0_1/qa/, plus a QGIS folder with links to the existing GeoPackages.
Usage: r4c0_1_gate1.py <index_json> <local_dir>   (.venv-ml)
"""
import html, json, os, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4c0_gate3 as G3  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
import r4b1t_width as W  # noqa: E402
from r4b1t_labels import ink_masks  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SHEETS, N, S = ("13014", "15076"), 4, 256
METHODS = ("M2_hybrid", "RAG_BOUNDARY_ONLY", "RAG_BOUNDARY_APPEARANCE")


def maps(code):
    return {"M2_hybrid": np.load(ROOT / f"runs/r4c0/pred_test/{code}/M2/regions_M2_hybrid.npy"),
            "RAG_BOUNDARY_ONLY": np.load(ROOT / f"runs/r4c0/gate4/{code}_RAG_BOUNDARY_ONLY.npy"),
            "RAG_BOUNDARY_APPEARANCE": np.load(ROOT / f"runs/r4c0/gate4/{code}_RAG_BOUNDARY_APPEARANCE.npy")}


def bnd(lab):
    b = np.zeros(lab.shape, bool); b[:, 1:] |= lab[:, 1:] != lab[:, :-1]; b[1:] |= lab[1:] != lab[:-1]
    return b


def pick(items, rng):
    items = sorted(items)
    return [items[i] for i in sorted(rng.choice(len(items), min(N, len(items)), replace=False))] if items else []


def window(cy, cx, H, Wd):
    y0, x0 = int(np.clip(cy - S // 2, 0, H - S)), int(np.clip(cx - S // 2, 0, Wd - S)); return y0, x0


def main(index_json, local_dir):
    loc = Path(local_dir).resolve(); (loc / "img").mkdir(parents=True, exist_ok=True); (loc / "qgis").mkdir(exist_ok=True)
    rng = np.random.default_rng(20261029); index = []
    for code in SHEETS:
        R = EV.load_ref(code); unit = np.load(ROOT / "runs/r4a2" / code / "unit.npy")
        V = (R["ignore"] == 0) & (unit >= 0); i1, area, ids, wid = W.canonical_widths(R["instance"], V)
        M = maps(code); H, Wd = V.shape
        per = {m: G3.per_instance(M[m], i1, V, ids, area) for m in METHODS}       # best IoU, best region, holders, held
        hit = {m: per[m][0] >= 0.5 for m in METHODS}; held = {m: per[m][3] for m in METHODS}
        cats = {}
        for name, lo, hi in (("NARROW_3_6", 3, 6), ("NARROW_6_10", 6, 10), ("NARROW_10_20", 10, 20)):
            cats[name] = [int(k) for k, w in zip(ids, wid) if lo <= w < hi]
        cats["NEW_RECOVERED"] = [int(k) for k, a, b in zip(ids, hit["RAG_BOUNDARY_ONLY"], hit["M2_hybrid"]) if a and not b]
        cats["NEW_OVERSEG"] = [int(k) for k, a, b in zip(ids, held["RAG_BOUNDARY_ONLY"], held["M2_hybrid"]) if not a and b]
        big = np.flatnonzero(area >= 20000); big = big[big > 0]
        rb = M["RAG_BOUNDARY_ONLY"]; best_b, br_b, hold_b, _ = G3.per_instance(rb, i1, V, big, area)
        cats["LARGE_MERGE"] = [int(k) for k, r in zip(big, br_b) if hold_b[r] >= 2]
        C = G3.R.overlaps(rb, i1, V).tocsc()
        cats["LARGE_SPLIT"] = [int(g) for g in big if (C.getcol(g).data >= 0.01 * area[g]).sum() >= 4]
        # grid-window categories
        sz = np.bincount(rb.ravel()); tiny = (sz > 0) & (sz < 50)
        tiny_px = tiny[rb]
        ub = (R["unit_boundary"] > 0) & V
        dub = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)
        _, ink1, _ = ink_masks(cv2.imread(str(ROOT / "runs/r4a2" / code / "geotiff_rgb.png")))
        fb = bnd(rb) & V & (dub > 2) & ink1
        grid = [(y, x) for y in range(0, H - S + 1, S) for x in range(0, Wd - S + 1, S)]
        def top(mask_count):
            sc = sorted(((mask_count(y, x), (y, x)) for y, x in grid), reverse=True)[:N]
            return [g for c, g in sc if c > 0]
        lab_t = np.zeros(rb.shape, bool); lab_t[np.isin(rb, np.flatnonzero(tiny))] = True
        frag_windows = top(lambda y, x: len(np.unique(rb[y:y + S, x:x + S][lab_t[y:y + S, x:x + S]])))
        fb_windows = top(lambda y, x: int(fb[y:y + S, x:x + S].sum()))
        rgb = cv2.imread(str(ROOT / "runs/r4a2" / code / "geotiff_rgb.png"))
        def render(y0, x0, tgt, tag):
            s = (slice(y0, y0 + S), slice(x0, x0 + S)); base = rgb[s]
            def pan(b, title):
                p = (base * 0.6 + 100).astype(np.uint8); p[b] = (0, 0, 220)
                if tgt is not None:
                    t = i1[s] == tgt; e = t & ~cv2.erode(t.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool); p[e] = (255, 255, 0)
                p = cv2.resize(p, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
                cv2.putText(p, title, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2); return p
            row = [cv2.resize(base, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST), pan(ub[s], "official (reference)")]
            row += [pan(bnd(M[m][s]), m.replace("RAG_BOUNDARY_", "RAG_")) for m in METHODS]
            f = loc / "img" / f"{tag}.jpg"; cv2.imwrite(str(f), np.hstack(row), [cv2.IMWRITE_JPEG_QUALITY, 85]); return f
        for cat, items in cats.items():
            for k in pick(items, rng):
                ys, xs = np.nonzero(i1 == k); y0, x0 = window(int(np.median(ys)), int(np.median(xs)), H, Wd)
                tag = f"{code}_{cat}_{k - 1}"; render(y0, x0, k, tag)
                j = list(ids).index(k) if k in ids else None
                e = {"sheet": code, "category": cat, "instance": int(k - 1), "area_px": int(area[k]), "window_yx": [y0, x0], "size": S, "image_local": f"img/{tag}.jpg"}
                if j is not None: e |= {"width_px": round(float(wid[j]), 2), **{f"iou_{m}": round(float(per[m][0][j]), 3) for m in METHODS}}
                index.append(e)
        for cat, wins in (("FRAGMENTS", frag_windows), ("FALSE_BOUNDARY", fb_windows)):
            for y0, x0 in wins:
                tag = f"{code}_{cat}_{y0}_{x0}"; render(y0, x0, None, tag)
                index.append({"sheet": code, "category": cat, "window_yx": [y0, x0], "size": S, "image_local": f"img/{tag}.jpg",
                              "tiny_regions_in_window": int(len(np.unique(rb[y0:y0 + S, x0:x0 + S][lab_t[y0:y0 + S, x0:x0 + S]]))),
                              "false_boundary_px_in_window": int(fb[y0:y0 + S, x0:x0 + S].sum())})
        for m in ("RAG_BOUNDARY_ONLY", "RAG_BOUNDARY_APPEARANCE"):
            src = ROOT / f"runs/r4c0/gate4/export/{code}/{m}"; dst = loc / "qgis" / f"{code}_{m}"
            if not dst.exists(): os.symlink(src, dst)
        m2 = ROOT / f"runs/r4c0/pred_test/{code}/M2"; (loc / "qgis" / f"{code}_README.txt").write_text(
            "Open the *.gpkg in QGIS (no CRS on purpose: pixel coordinates, X = col, Y = -row).\n"
            f"Raster: {ROOT / 'runs/r4a2' / code / 'geotiff_rgb.png'} with a world file 1,0,0,-1,0.5,-0.5.\n"
            f"M2_hybrid region map (npy): {m2 / 'regions_M2_hybrid.npy'}\n")
        img = ROOT / "runs/r4a2" / code / "geotiff_rgb.png"; wld = loc / "qgis" / f"{code}_geotiff_rgb.pgw"
        wld.write_text("1.0\n0.0\n0.0\n-1.0\n0.5\n-0.5\n")
        if not (loc / "qgis" / f"{code}_geotiff_rgb.png").exists(): os.symlink(img, loc / "qgis" / f"{code}_geotiff_rgb.png")
        print(code, {c: len(v) for c, v in cats.items()}, "frag windows", len(frag_windows), "fb windows", len(fb_windows), flush=True)
    rows = "".join(f"<tr><td>{html.escape(e['sheet'])}</td><td>{e['category']}</td><td>{e.get('instance', '')}</td><td>{e.get('width_px', '')}</td>"
                   f"<td>{e.get('iou_M2_hybrid', '')}</td><td>{e.get('iou_RAG_BOUNDARY_ONLY', '')}</td><td>{e.get('iou_RAG_BOUNDARY_APPEARANCE', '')}</td>"
                   f"<td>{e['window_yx']}</td><td><img src='{e['image_local']}' width='1280'></td></tr>" for e in index)
    (loc / "index.html").write_text("<html><meta charset='utf-8'><body><h3>R4-C0.1 QA package (LOCAL ONLY, restricted GSJ pixels)</h3>"
                                    "<p>Panels: RGB | official boundary (reference) | M2_hybrid | RAG_B | RAG_A. Yellow outline = target instance.</p>"
                                    "<table border=1><tr><th>sheet</th><th>category</th><th>instance</th><th>width</th><th>IoU M2h</th><th>IoU RAG_B</th>"
                                    "<th>IoU RAG_A</th><th>window y,x</th><th>panels</th></tr>" + rows + "</table></body></html>")
    json.dump({"rules": __doc__, "windows": index}, open(index_json, "w"), indent=1)
    print("windows", len(index), "->", loc / "index.html")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
