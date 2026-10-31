"""StitchVector 7.1 line/face diagnostic run. Frozen rules: sv_d71_prereg.json (pushed before this script runs on u2).
Usage: sv_d71_run.py <out_dir>   (.venv-sv)"""
import csv, json, sys, time, resource
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import sv_common as C
import sv_d71 as D

PRE = json.load(open(Path(__file__).with_name("sv_d71_prereg.json")))
COL = {0: (0, 0, 0, 0), 1: (0, 90, 255, 200), 2: (0, 200, 0, 200), 3: (255, 0, 200, 200), 4: (0, 200, 255, 200)}


def rss(): return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 3)


def up(a, k=3): return np.kron(a, np.ones((k, k, 1), np.uint8)) if a.ndim == 3 else np.kron(a, np.ones((k, k), a.dtype))


def overlay(a, pix, k=3):
    base = Image.fromarray(up(a, k)).convert("RGBA"); o = np.zeros(pix.shape + (4,), np.uint8)
    for c, v in COL.items(): o[pix == c] = v
    return Image.alpha_composite(base, Image.fromarray(up(o, k), "RGBA")).convert("RGB")


def unit_rgb(lab, pal, r):
    """Line layer drawn with one colour per L unit (its most frequent label): cheap stand-in for a single-colour line."""
    X = lab.copy(); U = r["U"]; Lm = r["Lm"]
    if Lm.any():
        u = U[Lm]; l = lab[Lm]; key = u.astype(np.int64) * len(pal) + l; uk, c = np.unique(key, return_counts=True)
        uu, ll = uk // len(pal), uk % len(pal); o = np.lexsort((-c, uu)); f = np.unique(uu[o], return_index=True)[1]
        lut = np.zeros(int(U.max()) + 1, np.int64); lut[uu[o][f]] = ll[o][f]; X[Lm] = lut[U[Lm]]
    return X


def samples(a, r, cls_id, n, seed, k=4, win=24):
    rng = np.random.default_rng(seed); ids = np.nonzero(r["cls"] == cls_id)[0]; ids = ids[ids > 0]
    pick = rng.choice(ids, size=min(n, len(ids)), replace=False) if len(ids) else []
    tiles = []
    for u in sorted(pick):
        ys, xs = np.nonzero(r["U"] == u); cy, cx = int(ys.mean()), int(xs.mean())
        y0, x0 = max(0, min(cy - win // 2, a.shape[0] - win)), max(0, min(cx - win // 2, a.shape[1] - win))
        t = up(a[y0:y0 + win, x0:x0 + win], k).copy(); m = up((r["U"][y0:y0 + win, x0:x0 + win] == u).astype(np.uint8), k) > 0
        edge = m & ~np.pad(m, 1)[2:, 1:-1] | m & ~np.pad(m, 1)[:-2, 1:-1] | m & ~np.pad(m, 1)[1:-1, 2:] | m & ~np.pad(m, 1)[1:-1, :-2]
        t[edge] = (0, 90, 255); tiles.append((int(u), (y0, x0), t))
    cols = 6; rows = (len(tiles) + cols - 1) // cols; S = win * k + 4
    sheet = Image.new("RGB", (cols * S, max(rows, 1) * (S + 12)), "white"); d = ImageDraw.Draw(sheet)
    for i, (u, (y0, x0), t) in enumerate(tiles):
        X, Y = (i % cols) * S, (i // cols) * (S + 12); sheet.paste(Image.fromarray(t), (X, Y + 12)); d.text((X + 2, Y), f"u{u} @{y0},{x0}", fill="black")
    return sheet, [t[0] for t in tiles]


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); t0 = time.time()
    a, off = C.centre_crop(C.load("u2"), 300, 300); lab, pal = C.quantize(a, 32)
    r = D.run_one(lab, pal, D.P0); ft = r["ft"]
    res = {"prereg": "sv_d71_prereg.json", "sample": "u2", "crop_offset_yx": list(off), "size": list(lab.shape), "palette": 32,
           "params": D.P0, "colour_classes": int(len(r["cent"])), "candidate_px": int(r["thin"].sum()),
           "thin_mask_px_reference": int(C.thin_mask(a).sum()), "units": int(r["n_units"]), "classes": D.counts(r)}
    Lm = r["Lm"]; F = r["F"]; comp = np.where(Lm, lab, F); comp_u = np.where(Lm, unit_rgb(lab, pal, r), F)
    res["checks"] = {"composite_equals_labels": bool((comp == lab).all()),
                     "non_L_labels_unchanged": int((F[~Lm] != lab[~Lm]).sum()),
                     "P_pixels_unchanged_in_face_layer": float((F[r["pix"] == 2] == lab[r["pix"] == 2]).mean()) if (r["pix"] == 2).any() else None}
    res["face_change"] = D.face_change(lab, F, Lm)
    vb, _ = D.face_vector(lab); vf, Rf = D.face_vector(F)
    res["face_vectors_exact"] = {"baseline_labels": vb, "face_layer": vf}
    res["line_layer_cost_estimate"] = D.line_cost(r, lab)
    lc = res["line_layer_cost_estimate"]
    res["totals"] = {"baseline": {"objects": vb["faces"], "vertices": vb["vertices"]},
                     "layered_pixel_faithful_lines": {"objects": vf["faces"] + lc["pixel_faithful_polygons"]["objects"],
                                                      "vertices": vf["vertices"] + lc["pixel_faithful_polygons"]["vertices_exact"]},
                     "layered_single_colour_units": {"objects": vf["faces"] + lc["single_colour_unit_polygons"]["objects"],
                                                     "vertices": vf["vertices"] + lc["single_colour_unit_polygons"]["vertices_exact"]},
                     "layered_centreline_estimate": {"objects": vf["faces"] + lc["centreline_estimate"]["chains"],
                                                     "vertices": vf["vertices"] + lc["centreline_estimate"]["vertices_simplify1"]}}
    q = pal[lab]; thin = C.thin_mask(a)
    res["fidelity"] = {name: {"all": C.fidelity(a, pal[X], thin),
                              **{f"{D.CLS[c]}_px": D.region_stats(a, pal[X], lab, X, r["pix"] == c) for c in (1, 2, 3, 4)}}
                       for name, X in (("baseline_labels", lab), ("composite_exact_L", comp), ("composite_single_colour_L", comp_u),
                                       ("face_layer_only", F))}
    sens = []
    for k, vals in PRE["sensitivity"].items():
        for v in vals:
            p = dict(D.P0); p[k] = v; rr = D.run_one(lab, pal, p); ch = D.face_change(lab, rr["F"], rr["Lm"])
            sens.append({"param": k, "value": v, "classes": D.counts(rr), "faces_after": ch["faces_after"],
                         "after_faces_merging_2plus_baseline_faces": ch["after_faces_merging_2plus_baseline_faces"]})
    res["sensitivity"] = sens
    with open(out / "units.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["unit", "class", "colour_class", "px", "skeleton_px", "width", "elong", "branch", "attach_px", "side_same", "contrast_dE", "bg_class", "fill_colour"])
        for u in range(1, r["n_units"] + 1):
            w.writerow([u, D.CLS[int(r["cls"][u])], int(ft["ucls"][u]), int(ft["npx"][u]), int(ft["skel"][u]), round(float(ft["width"][u]), 3),
                        round(float(ft["elong"][u]), 3), round(float(ft["branch"][u]), 4), int(ft["attach_px"][u]), round(float(ft["side_same"][u]), 3),
                        round(float(ft["contrast"][u]), 2), int(ft["bg_cls"][u]), int(ft["fill_colour"][u])])
    Image.fromarray(up(a)).save(out / "original_x3.png"); Image.fromarray(up(q)).save(out / "labels_x3.png")
    overlay(a, r["pix"]).save(out / "lpu_overlay_x3.png")
    Image.fromarray(up(pal[F])).save(out / "face_layer_x3.png")
    Lrgb = np.full(a.shape, 255, np.uint8); Lrgb[Lm] = pal[lab][Lm]; Image.fromarray(up(Lrgb)).save(out / "line_layer_x3.png")
    Image.fromarray(up(pal[comp])).save(out / "composite_exact_x3.png"); Image.fromarray(up(pal[comp_u])).save(out / "composite_single_colour_x3.png")
    Image.fromarray(np.hstack([up(a), up(pal[F]), up(pal[comp_u])])).save(out / "compare_original_face_composite_x3.png")
    np.save(out / "lpu_pixel_class.npy", r["pix"].astype(np.uint8))
    res["visual_samples"] = {}
    for cid, name in ((1, "L_core"), (2, "P"), (3, "U")):
        sheet, ids = samples(a, r, cid, PRE["visual_review"]["per_class"], PRE["visual_review"]["seed"]); sheet.save(out / f"samples_{name}.png")
        res["visual_samples"][name] = ids
    res["seconds"] = round(time.time() - t0, 1); res["peak_rss_gb"] = rss()
    json.dump(res, open(out / "d71_result.json", "w"), indent=1, default=float)
    print(json.dumps({k: res[k] for k in ("classes", "checks", "face_change", "totals", "seconds")}, indent=1, default=float))


if __name__ == "__main__":
    main(sys.argv[1])
