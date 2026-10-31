"""Line + face POC run: F0 (faces only) / B0 / B2c on sv_synth tiles and counterexample scenes. Rules: sv_lf_prereg.json.
Usage: sv_lf_run.py <json_dir> <gpkg_img_dir> <dev|test>   (.venv-sv). All images are GPKG readbacks."""
import json, sys, collections
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString
from PIL import Image, ImageDraw
import sv_synth as S, sv_b2c_scenes as SC, sv_lf as LF, sv_lf_eval as EV, sv_oracle_eval as E

HERE = Path(__file__).resolve().parent
PRE = json.load(open(HERE / "sv_lf_prereg.json"))
METHODS = ["F0", "B0", "B2c"]


def up(a, k): return np.kron(a, np.ones((k, k, 1), np.uint8))


def lines_only(img, lines, k):
    im = Image.fromarray((up(img, k) * 0.3 + 255 * 0.7).astype(np.uint8)); d = ImageDraw.Draw(im)
    for f in lines:
        for q in shapely.get_parts(f["geom"]): d.line([(x * k, y * k) for x, y in q.coords], fill=(0, 90, 255), width=max(1, k // 2))
    return im


def err(a, rgb, k): return Image.fromarray(up(np.stack([np.clip(E.de(a, rgb) * 6, 0, 255).astype(np.uint8)] * 3, -1), k))


def sheet(ims, names):
    w, h = ims[0].size; out = Image.new("RGB", (len(ims) * (w + 8), h + 20), "white"); d = ImageDraw.Draw(out)
    for i, (im, n) in enumerate(zip(ims, names)): out.paste(im, (i * (w + 8), 20)); d.text((i * (w + 8) + 2, 4), n, fill="black")
    return out


def one(a, tag, ink_axes, ink_meta, bands, fill_polys, gdir, idir, k):
    res, out = {}, {}
    for m in METHODS:
        gp = gdir / f"{tag}_{m}.gpkg"; r = LF.build(a, m, gp); res[m] = r
        out[m] = EV.evaluate(a, r, gp, ink_axes, ink_meta, bands, fill_polys)
    ims = [Image.fromarray(up(a, k)), lines_only(a, res["B0"]["lines"], k), lines_only(a, res["B2c"]["lines"], k),
           Image.fromarray(up(res["F0"]["rgb"], k)), Image.fromarray(up(res["B0"]["rgb"], k)), Image.fromarray(up(res["B2c"]["rgb"], k)), err(a, res["B2c"]["rgb"], k)]
    names = ["original", "B0 lines", "B2c lines", "F0 faces only (GPKG)", "B0 lines+faces (GPKG)", "B2c lines+faces (GPKG)", "B2c error dE x6"]
    for im, n in zip(ims, names): im.save(idir / f"{tag}__{n.split(' (')[0].replace(' ', '_').replace('+', 'plus')}.png")
    sheet(ims, names).save(idir / f"{tag}__sheet.png")
    for b in bands:                                                       # band zooms
        g = LineString(b["axis"]); c = np.asarray(g.interpolate(0.5, normalized=True).coords[0]); x0, y0 = [int(np.clip(v - 20, 0, 256 - 40)) for v in c]
        crop = lambda im: im.crop((x0 * 8, y0 * 8, (x0 + 40) * 8, (y0 + 40) * 8))
        z = [Image.fromarray(up(a, 8)), Image.fromarray(up(res["B0"]["rgb"], 8)), Image.fromarray(up(res["B2c"]["rgb"], 8))]
        sheet([crop(x) for x in z], [f"{tag} {b['id']} {int(b['width'])}px original", "B0 lines+faces", "B2c lines+faces"]).save(idir / f"{tag}__band_{b['id']}_x8.png")
    return out


def main(json_dir, gi_dir, split):
    jd, base = Path(json_dir), Path(gi_dir); gdir, idir = base / "gpkg", base / "img"
    for d in (jd, gdir, idir): d.mkdir(parents=True, exist_ok=True)
    assert PRE["params"] == LF.Q, "params differ from frozen code"
    res = {"split": split, "synth": {}, "scenes": {}}
    for s in PRE["seeds"][split]["sv_synth"]:
        a, truth, faces = S.generate(s)
        res["synth"][str(s)] = one(a, f"synth_{s}", [t["axis"] for t in truth["lines"]],
                                   [{"id": t["id"], "type": t["id"], "axis": t["axis"]} for t in truth["lines"]], truth["bands"], list(faces.values()), gdir, idir, 3)
    for s in PRE["seeds"][split]["scenes"]:
        for kind in PRE["scene_kinds"]:
            a, t = SC.scene(kind, s)
            res["scenes"][f"{s}_{kind}"] = one(a, f"scene_{s}_{kind}", [x["axis"] for x in t["ink"]],
                                               [{"id": x["id"], "sub": x["sub"], "axis": x["axis"]} for x in t["ink"]], t["bands"], [], gdir, idir, 2)
    res["aggregate"] = aggregate(res)
    json.dump(res, open(jd / f"lf_{split}.json", "w"), indent=1, default=float)
    print(json.dumps(res["aggregate"], indent=0, default=float))


def aggregate(res):
    A = {}
    for m in METHODS:
        x = [t[m] for t in res["synth"].values()]; sc = [t[m] for t in res["scenes"].values()]
        pres = collections.defaultdict(list)
        for t in x:
            for lid, v in t["ink_presence"].items(): pres[lid].append(v["presence"])
        sub = collections.defaultdict(list)
        for t in sc:
            for v in t["ink_presence"].values(): sub[v["sub"]].append(v["presence"])
        bands_s = {f"{s}:{b}": v for s, t in res["synth"].items() for b, v in t[m]["bands"].items()}
        bands_c = {f"{s}:{b}": v for s, t in res["scenes"].items() for b, v in t[m]["bands"].items()}
        fl = collections.Counter()
        for t in x: fl.update(t["false_lines"])
        A[m] = {"faces": sum(t["faces"] for t in x), "lines": sum(t["lines"] for t in x), "logical": sum(t["logical"] for t in x), "vertices": sum(t["vertices"] for t in x),
                "all_topology_valid": all(all(t["topology"].values()) for t in x + sc), "uncovered_px": sum(t["uncovered_px"] for t in x + sc),
                "memory_vs_gpkg_px": sum(t["memory_vs_gpkg_px"] for t in x + sc),
                "dE90_all": float(np.mean([t["fidelity"]["all"]["dE90"] for t in x])), "dE90_line_nbhd": float(np.mean([t["fidelity"]["line_nbhd"]["dE90"] for t in x])),
                "dE90_non_line": float(np.mean([t["fidelity"]["non_line"]["dE90"] for t in x])),
                "share_dE_le_10_all": float(np.mean([t["fidelity"]["all"]["share_dE_le_10"] for t in x])),
                "presence_by_line_type": {k: float(np.mean(v)) for k, v in sorted(pres.items())},
                "scenes_presence_by_sub": {k: float(np.mean(v)) for k, v in sorted(sub.items())},
                "synth_bands_colour_preserved_mean": float(np.mean([v["colour_preserved"] for v in bands_s.values()])) if bands_s else None,
                "synth_bands_colour_preserved_min": float(min(v["colour_preserved"] for v in bands_s.values())) if bands_s else None,
                "scene_bands_colour_preserved_mean": float(np.mean([v["colour_preserved"] for v in bands_c.values()])) if bands_c else None,
                "scene_bands_colour_preserved_min": float(min(v["colour_preserved"] for v in bands_c.values())) if bands_c else None,
                "bands": {**bands_s, **bands_c}, "false_line_length": dict(fl),
                "edit": [t["edit"] for t in x if t["edit"]]}
    return A


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
