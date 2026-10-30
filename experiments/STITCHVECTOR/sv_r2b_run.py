"""R2 amendment 1: one real sample (u2 centre 300x300, 32 colours, same crop as the frozen failure scene).
Progressive 4->2->1->0 on a shared arc network vs single-pass tol0 / tol1 on the same label image.
Reads only image pixels."""
import json, sys, time, resource
from pathlib import Path
import numpy as np
import sv_common as C
import sv_arcs as A


def rss(): return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 3)


def evaluate(name, polys, vals, lines, lab, pal, a, thin, sec, extra=None):
    h, w = lab.shape; R = A.render(polys, vals, h, w); mm = int((R != lab).sum())
    rec = C.key_rgb(0) if False else None
    rgb = pal[np.clip(R, 0, len(pal) - 1)]
    out = {"method": name, "faces": len(polys), "arcs": len(lines), "vertices": int(sum(len(l.coords) for l in lines)),
           "face_vertices": C.n_vertices(polys), "seconds": round(sec, 2), "peak_rss_gb": rss(),
           "final_mismatch_px_vs_labels": mm, "topology": {k: bool(v) for k, v in A.topology(polys, h, w).items()},
           "vs_quantized": C.fidelity(pal[lab], rgb, thin), "vs_original": C.fidelity(a, rgb, thin)}
    if extra: out.update(extra)
    return out


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    a, off = C.centre_crop(C.load("u2"), 300, 300); lab, pal = C.quantize(a, 32); thin = C.thin_mask(a)
    res = {"sample": "u2", "crop_offset_yx": list(off), "size": list(lab.shape), "palette": 32, "runs": []}
    t = time.time(); p, v, l, log = A.progressive(lab); s = time.time() - t
    res["runs"].append(evaluate("R2_progressive_4_2_1_0", p, v, l, lab, pal, a, thin, s, {"stage_log": log}))
    for tol in (0, 1):
        t = time.time(); p, v, l, n0 = A.single_pass(lab, tol); s = time.time() - t
        res["runs"].append(evaluate(f"single_pass_tol{tol}", p, v, l, lab, pal, a, thin, s, {"arcs_forced_to_0": n0}))
    json.dump(res, open(out / "r2b_u2_300.json", "w"), indent=1, default=float)
    for r in res["runs"]:
        print(r["method"], {k: r[k] for k in ("faces", "arcs", "vertices", "seconds", "final_mismatch_px_vs_labels")},
              r["topology"], "orig exact", round(r["vs_original"]["exact_share"], 4), "dE90", round(r["vs_original"]["dE90"], 2),
              "thin", round(r["vs_original"].get("thin_match_dE10", -1), 3))


if __name__ == "__main__":
    main(sys.argv[1])
