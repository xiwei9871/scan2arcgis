"""Edit-cost calibration run (plan: sv_ec_plan.json). DATA_LEVEL_ONLY. Usage: sv_ec_run.py <json_dir> <copy_dir> [--smoke <gpkg_dir>]"""
import json, sys, hashlib
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString
import sv_g3_run as GR, sv_oracle_v2 as O2, sv_common as Cm, sv_ec as EC

HERE = Path(__file__).resolve().parent; RS = HERE.parents[1] / "runs/stitchvector"


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main(json_dir, copy_dir, smoke_dir=None):
    jd, cd = Path(json_dir), Path(copy_dir); jd.mkdir(parents=True, exist_ok=True); cd.mkdir(parents=True, exist_ok=True)
    sd = Path(smoke_dir) if smoke_dir else RS / "v3_linefaces/gpkg"; seeds = [1201] if smoke_dir else [7001, 7002, 7003, 7004, 7005]
    u2 = None if smoke_dir else RS / "v3_u2_real/gpkg/u2_B2c.gpkg"
    inputs = [sd / f"synth_{s}_{m}.gpkg" for s in seeds for m in ("F0", "B0", "B2c")] + ([u2] if u2 else [])
    before = {str(p): sha(p) for p in inputs}
    if not smoke_dir:
        GR.check_sha([p for p in inputs if "v3_linefaces" in str(p)], HERE / "lf/linefaces_test_artifacts_sha256.txt", RS / "v3_linefaces")
        GR.check_sha([u2], HERE / "u2real/u2_artifacts_sha256.txt", RS / "v3_u2_real")
    res = {"plan": "sv_ec_plan.json", "mode": "DATA_LEVEL_ONLY", "audit": {}, "cases": {}}
    for s in seeds:
        img, inks, fills, bands_, lab = GR.synth_truth(s)
        res["audit"][str(s)] = {m: EC.audit(sd / f"synth_{s}_{m}.gpkg", img, lab, [x["axis"] for x in inks], [x["width"] for x in inks]) for m in ("F0", "B0", "B2c")}
    tot = {}
    for m in ("F0", "B0", "B2c"):
        rows = [res["audit"][str(s)][m] for s in seeds]; tot[m] = {k: int(sum(r[k] for r in rows)) for k in rows[0]}
    res["audit_total"] = tot
    s0 = seeds[0]; img, inks, fills, bands_, lab = GR.synth_truth(s0)
    res["cases"]["A_fragmented_fill"] = EC.case_fragmented(sd / f"synth_{s0}_B2c.gpkg", img, lab, [x["axis"] for x in inks], [x["width"] for x in inks], cd, f"synth_{s0}_B2c")
    lost = {}
    for s in ([7002, 7003] if not smoke_dir else [s0]):
        img, inks, fills, bands_, lab = GR.synth_truth(s)
        b = [x for x in bands_ if x["id"] == "band_yellow"][0]; lost[str(s)] = EC.case_lost_band(sd / f"synth_{s}_B2c.gpkg", img, b["axis"], b["width"], f"synth_{s}_B2c_yellow")
    res["cases"]["D_lost_band"] = lost
    if u2:
        img, _ = Cm.centre_crop(Cm.load("u2"), 300, 300); P = {q["id"]: q for q in O2.ORA["protected"]}
        res["cases"]["B_PN2"] = EC.case_band(u2, img, LineString(P["PN2"]["axis"]), 2 * P["PN2"]["radius"], cd, "u2_B2c_PN2_line_to_face")
        res["cases"]["B_PN2_with_gap_redraw"] = EC.case_band(u2, img, LineString(P["PN2"]["axis"]), 2 * P["PN2"]["radius"], cd, "u2_B2c_PN2_line_to_face_redraw", redraw_gaps=True)
        res["cases"]["C_PN1"] = EC.case_band(u2, img, LineString(P["PN1"]["axis"]), 2 * P["PN1"]["radius"], cd, "u2_B2c_PN1_split_redraw_line_to_face", split_outside=True, redraw_gaps=True)
    after = {p: sha(p) for p in before}; res["originals_unchanged"] = all(before[p] == after[p] for p in before); res["originals_checked"] = len(before)
    res["edited_copies_sha256"] = {p.name: sha(p) for p in sorted(cd.glob("*.gpkg"))}
    json.dump(res, open(jd / ("ec_smoke.json" if smoke_dir else "ec_result.json"), "w"), indent=1, default=float)
    print(json.dumps({"audit_total": tot, "originals_unchanged": res["originals_unchanged"]}, indent=0))
    for k, v in res["cases"].items(): print(k, json.dumps(v, default=float)[:900])


if __name__ == "__main__":
    a = sys.argv[1:]; main(a[0], a[1], a[a.index("--smoke") + 1] if "--smoke" in a else None)
