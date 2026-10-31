"""B2b Phase A: can the centre-mixing deviation separate real ink from fill edges among the segments B2a adds?
Descriptive only, on already-viewed seeds. Usage: sv_b2b_phaseA.py <json_out> <img_out>   (.venv-sv)"""
import json, sys, collections
import numpy as np, cv2, shapely
from shapely.geometry import LineString
from PIL import Image, ImageDraw
import sv_synth as S, sv_autoline as AL, sv_b2b as B

SEEDS = [1001, 1002, 1003, 5001, 5002, 5003, 5004, 5005]


def segments():
    rows, crops = [], []
    for s in SEEDS:
        img, truth, faces = S.generate(s); L = AL.lab(img); _, add = B.added(img)
        for o in add:
            lab, parts = B.label(o["geom"], truth, list(faces.values()), truth["bands"]); f = B.features(L, o["geom"], o["width"])
            rows.append({"seed": s, "label": lab, "purity": max(parts.values()), "length": o["geom"].length, "width": o["width"],
                         "dev_median": f["dev_median"], "dev_halves": f["halves"], "stable_share": f["stable_share"],
                         "side_diff_median": f["side_diff_median"], "centre_minus_darker_side_L": f["centre_vs_sides_dL"]})
            crops.append((img, o["geom"], rows[-1]))
    return rows, crops


def scenes():
    """Clean vs noise+JPEG (4:2:0 and 4:4:4 chroma) for four reference cases, 160x120, vertical line at x=80."""
    SS = S.SS; rng = np.random.default_rng(0); out = {}
    def blank(): b = np.zeros((120 * SS, 160 * SS, 3), np.uint8); b[:] = S.FILLS["pink"]; return b
    def make(k):
        b = blank()
        if k == "fill_edge_only": b[:, 80 * SS:] = S.FILLS["redfill"]
        if k == "band_4px_edge": b[:, 78 * SS:82 * SS] = S.FILLS["yellow"]
        if k == "pale_ink_on_pink": S._poly(b, np.array([[80, 5], [80, 115]], float), S.INK["pale"], 1.0)
        if k == "pale_ink_on_yellow_pink_boundary": b[:, 80 * SS:] = S.FILLS["yellow"]; S._poly(b, np.array([[80, 5], [80, 115]], float), S.INK["pale"], 1.0)
        if k == "red_ink_on_green_pink_boundary": b[:, 80 * SS:] = S.FILLS["green"]; S._poly(b, np.array([[80, 5], [80, 115]], float), S.INK["red"], 2.0)
        return cv2.resize(b, (160, 120), interpolation=cv2.INTER_AREA)
    for k in ("fill_edge_only", "band_4px_edge", "pale_ink_on_pink", "pale_ink_on_yellow_pink_boundary", "red_ink_on_green_pink_boundary"):
        g = LineString([(78, 10), (78, 110)]) if k == "band_4px_edge" else LineString([(80, 10), (80, 110)]); w = 2.0 if k.startswith("red") else 1.0
        clean = make(k); r = {"clean": B.features(AL.lab(clean), g, w)["dev_median"]}
        for name, params in (("jpeg75_420", [cv2.IMWRITE_JPEG_QUALITY, 75]),
                             ("jpeg75_444", [cv2.IMWRITE_JPEG_QUALITY, 75, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444])):
            x = np.clip(clean.astype(float) + rng.normal(0, 2.0, clean.shape), 0, 255).astype(np.uint8)
            ok, enc = cv2.imencode(".jpg", cv2.cvtColor(x, cv2.COLOR_RGB2BGR), params); j = cv2.cvtColor(cv2.imdecode(enc, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
            r[name] = B.features(AL.lab(j), g, w)["dev_median"]
        out[k] = r
    return out


def sheet(crops, path, k=6, win=28, per_label=6):
    by = collections.defaultdict(list)
    for c in crops: by[c[2]["label"]].append(c)
    tiles = []
    for lab in ("true_line", "fill_edge", "band_edge", "other"):
        for img, g, r in sorted(by.get(lab, []), key=lambda c: -c[2]["length"])[:per_label]:
            cx, cy = np.asarray(g.interpolate(0.5, normalized=True).coords[0]); x0 = int(np.clip(cx - win / 2, 0, 256 - win)); y0 = int(np.clip(cy - win / 2, 0, 256 - win))
            im = Image.fromarray(np.kron(img[y0:y0 + win, x0:x0 + win], np.ones((k, k, 1), np.uint8))); d = ImageDraw.Draw(im)
            for part in shapely.get_parts(g): d.line([((x - x0) * k, (y - y0) * k) for x, y in part.coords], fill=(0, 90, 255), width=2)
            d.rectangle([0, 0, win * k, 26], fill=(255, 255, 255))
            d.text((2, 1), f"{lab} seed {r['seed']}", fill="black"); d.text((2, 13), f"dev {r['dev_median']:.1f}  dL {r['centre_minus_darker_side_L']:.1f}", fill="black")
            tiles.append(np.asarray(im))
    cols = 6; rows = [np.hstack(tiles[i:i + cols] + [np.full_like(tiles[0], 255)] * (cols - len(tiles[i:i + cols]))) for i in range(0, len(tiles), cols)]
    Image.fromarray(np.vstack(rows)).save(path)


def main(json_out, img_out):
    rows, crops = segments(); by = collections.defaultdict(list)
    for r in rows: by[r["label"]].append(r)
    summ = {}
    for lab, v in sorted(by.items()):
        d = np.array([r["dev_median"] for r in v]); dl = np.array([r["centre_minus_darker_side_L"] for r in v])
        summ[lab] = {"segments": len(v), "length": float(sum(r["length"] for r in v)), "dev_pct_10_25_50_75_90": np.percentile(d, [10, 25, 50, 75, 90]).tolist(),
                     "dL_pct_10_25_50_75_90": np.percentile(dl, [10, 25, 50, 75, 90]).tolist()}
    sweep = {}
    for th in (6, 8, 10, 12, 15):
        sweep[f"dev>={th}"] = {lab: sum(r["length"] for r in v if r["dev_median"] >= th) / sum(r["length"] for r in v) for lab, v in by.items()}
    sweep_dl = {}
    for th in (-1, -2, -3, -4):
        sweep_dl[f"dL<={th}"] = {lab: sum(r["length"] for r in v if r["centre_minus_darker_side_L"] <= th) / sum(r["length"] for r in v) for lab, v in by.items()}
    res = {"seeds_viewed": SEEDS, "segments": rows, "summary_by_label": summ, "kept_length_share_by_dev_threshold": sweep,
           "posthoc_kept_length_share_by_dL_threshold": sweep_dl, "reference_scenes_dev_median": scenes()}
    json.dump(res, open(json_out, "w"), indent=1, default=float); sheet(crops, img_out)
    for lab, x in summ.items(): print(lab.ljust(10), x["segments"], round(x["length"]), "dev", np.round(x["dev_pct_10_25_50_75_90"], 1).tolist(), "dL", np.round(x["dL_pct_10_25_50_75_90"], 1).tolist())
    for k, v in res["reference_scenes_dev_median"].items(): print(k.ljust(34), {a: round(b, 1) for a, b in v.items()})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
