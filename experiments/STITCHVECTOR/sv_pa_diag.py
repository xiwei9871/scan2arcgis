"""Protection ablation: pale-line signal diagnosis (descriptive, viewed data only: dev seeds 1201-1203 and u2 centre 300x300).
For each pale truth line (synthetic pale_1, u2 Oracle G1-G3): strongest Lab dE and |dL*| to the 15x15 median within 1 px of
the axis, share of that response coming from luminance, share of axis samples inside the fill-protection mask, noise p95.
Usage: sv_pa_diag.py <json_out>   (.venv-sv)"""
import json, sys
import numpy as np, cv2, shapely
from shapely.geometry import LineString
import sv_synth as S, sv_autoline as AL, sv_common as Cm, sv_oracle as O, sv_oracle_v2 as O2


def maps(a):
    L = AL.lab(a); Lm = AL.lab(cv2.medianBlur(a, 15)); dE = np.sqrt(((L - Lm) ** 2).sum(-1)); dL = L[..., 0] - Lm[..., 0]
    con = AL.contrast(a, 15); prot = AL.protected(a, AL.fill_colours(a, con, AL.P), AL.P); return dE, dL, prot


def best_near(m, g):
    P = shapely.get_coordinates(shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1)))
    x = np.clip(P[:, 0].astype(int), 0, m.shape[1] - 1); y = np.clip(P[:, 1].astype(int), 0, m.shape[0] - 1); pad = np.pad(m, 1, mode="edge")
    return np.stack([pad[y + 1 + dy, x + 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)])


def line_stats(dE, dL, prot, g, flat):
    E = best_near(dE, g); k = np.argmax(E, 0); i = np.arange(E.shape[1]); e = E[k, i]
    d = best_near(dL, g)[k, i]; pr = best_near(prot.astype(float), g)[k, i]
    return {"samples": int(len(e)), "dE_median": float(np.median(e)), "abs_dL_median": float(np.median(np.abs(d))),
            "luminance_share_median": float(np.median(np.abs(d) / np.maximum(e, 1e-6))), "centre_darker_share": float((d < 0).mean()),
            "dE_above_12_share": float((e > AL.P["c_ink"]).mean()), "protected_share": float(pr.mean()),
            "noise_p95_dE": float(np.percentile(dE[flat], 95)), "noise_p95_abs_dL": float(np.percentile(np.abs(dL)[flat], 95))}


def main(out):
    res = {"nature": "descriptive diagnosis on viewed data, run before the protection-ablation freeze", "synthetic_dev": {}, "u2": {}}
    for s in (1201, 1202, 1203):
        a, truth, _ = S.generate(s); dE, dL, prot = maps(a); flat = dE < AL.P["c_ink"]
        t = [x for x in truth["lines"] if x["id"] == "pale_1"][0]; res["synthetic_dev"][str(s)] = line_stats(dE, dL, prot, LineString(t["axis"]), flat)
    a, _ = Cm.centre_crop(Cm.load("u2"), 300, 300); dE, dL, prot = maps(a); flat = (dE < AL.P["c_ink"]) & (np.arange(300)[None, :] < 94)
    P = dict(O.P); P.update(O2.PRE["params"]); ol, _ = O2.build(a, P)
    for f in ol:
        if f["id"] in ("G1", "G2", "G3"): res["u2"][f["id"]] = line_stats(dE, dL, prot, LineString(f["raw"]), flat)
    json.dump(res, open(out, "w"), indent=1)
    for k in ("synthetic_dev", "u2"):
        for i, v in res[k].items(): print(k, i, {a_: round(b, 2) for a_, b in v.items()})


if __name__ == "__main__":
    main(sys.argv[1])
