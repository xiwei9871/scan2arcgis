"""Text-layer acceptance on u2 B2c (copy): three user boxes (Є-O, Ar₂E, 云), OCR candidate, user-confirmed text,
residue cleaned, save + readback. Data level; boxes and texts are the user's decision, not recognised."""
import hashlib, json, shutil, sys
from pathlib import Path
import numpy as np, pyogrio, shapely
from PIL import Image
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from tools.stitchvector_editor.core import Document, coverage_report, TEXT, RESIDUE  # noqa: E402
INP = Path.home() / "geomap2arcgis/runs/stitchvector/editor_v01/inputs"; OUT = Path.home() / "geomap2arcgis/runs/stitchvector/editor_text/uat"
BOXES = {"Є-O": (3, 25, 35, 42), "Ar₂E": (0, 196, 52, 225), "云": (24, 59, 41, 76)}
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def residue(doc, B, max_area=60):
    g = np.asarray(doc.F.geometry.values, object); a = shapely.area(g)
    fm = (a <= max_area) & (shapely.area(shapely.intersection(g, B)) >= 0.5 * a) & (a > 0)
    lm = [ln.length > 0 and ln.intersection(B).length >= 0.9 * ln.length for ln in doc.L.geometry]
    return int(fm.sum()), int(sum(lm))
OUT.mkdir(parents=True, exist_ok=True); src = OUT / "input_copy.gpkg"; shutil.copyfile(INP / "u2_B2c.gpkg", src); s0 = sha(INP / "u2_B2c.gpkg")
doc = Document(src, (300, 300), np.asarray(Image.open(INP / "u2_original.png").convert("RGB")))
F0, L0 = doc.F.set_index("_eid").copy(), doc.L.set_index("_eid").copy(); U = shapely.union_all([shapely.box(*b) for b in BOXES.values()])
R = {"boxes": {}, "verification": "DATA_LEVEL_VERIFIED", "note": "boxes drawn and texts confirmed by the user (simulated); OCR gives candidates only"}
ops = {}
for t, b in BOXES.items():
    B = shapely.box(*b); before = residue(doc, B); pv = doc.text_preview(b)
    # simulated user decision for 'uncertain' groups (box on a contact): assign to the ground face whose stored colour is
    # closest to the residue's own colour. This is the tester's choice, recorded as such, not an automatic rule.
    assign = {}
    for k, g in enumerate(pv["groups"]):
        if g["decision"] != "uncertain" or not g.get("grounds"): continue
        rc = np.mean([[int(c[i:i+2], 16) for i in (1, 3, 5)] for c in doc.F.loc[doc.F["_eid"].isin(g["faces"]), "rgb"]], 0)
        def dist(e): c = doc.F.loc[doc.F["_eid"] == e, "rgb"].iloc[0]; return float(np.linalg.norm(rc - [int(c[i:i+2], 16) for i in (1, 3, 5)]))
        assign[k] = min(g["grounds"], key=dist)
    if assign:
        bad = next(iter(assign)); wrong = next((f for f in doc.F["_eid"] if f not in pv["groups"][bad]["grounds"]), None)
        try: doc.text_apply(pv["preview_id"], t, assign={bad: int(wrong)}); neg = "ACCEPTED (bug)"
        except Exception as e: neg = "rejected: " + str(e)
    else: neg = None
    r = doc.text_apply(pv["preview_id"], t, assign=assign or None)
    ops[t] = {"box": 1, "confirm_text": 1, "apply": 1, "assign_uncertain_groups": len(assign)}
    R["boxes"][t] = {"ocr_candidate": pv["ocr"].get("text"), "ocr_score": pv["ocr"].get("score"), "ocr_correct": pv["ocr"].get("text") == t,
                     "residue_before": {"faces": before[0], "lines": before[1]}, "preview_counts": pv["counts"],
                     "applied": r, "residue_after": dict(zip(("faces", "lines"), residue(doc, B))),
                     "user_assignment": {str(k): v for k, v in assign.items()}, "wrong_assignment_check": neg, "uncertain_groups": [{"faces": len(g["faces"]), "grounds": g.get("grounds"), "reason": g["reason"]} for g in pv["groups"] if g["decision"] == "uncertain"]}
# changed objects whose original geometry does not touch any text box (should be 0)
b = doc.F.set_index("_eid"); bl = doc.L.set_index("_eid")
fo = sum(1 for i in F0.index if not F0.at[i, "geometry"].intersects(U) and (i not in b.index or not F0.at[i, "geometry"].equals_exact(b.at[i, "geometry"], 1e-9) or F0.at[i, "rgb"] != b.at[i, "rgb"]))
lo = sum(1 for i in L0.index if not L0.at[i, "geometry"].intersects(U) and (i not in bl.index or not L0.at[i, "geometry"].equals_exact(bl.at[i, "geometry"], 1e-9)))
R["changed_outside_boxes"] = {"faces": fo, "lines": lo}
R["faces_before_after"] = [len(F0), len(doc.F)]; R["lines_before_after"] = [len(L0), len(doc.L)]; R["coverage"] = coverage_report(doc.F, 300, 300)
out = OUT / "u2_text_layer.gpkg"
if out.exists(): out.unlink()
sv = doc.save_as(out); re = Document(out, (300, 300))
R["save"] = {k: sv[k] for k in ("accepted", "readback_matches_memory", "text_matches_memory", "input_sha256_unchanged", "layers")}
R["reopen"] = {"texts": list(re.T["text"]), "font_px": [float(x) for x in re.T["font_px"]], "residue_lines": len(re.Q),
               "layer_styles_rows": len(pyogrio.read_dataframe(out, layer="layer_styles")) if "layer_styles" in [l[0] for l in pyogrio.list_layers(out)] else 0}
R["ops"] = ops; R["inputs_unchanged"] = sha(INP / "u2_B2c.gpkg") == s0; R["output_sha256"] = sha(out)
o = ROOT / "experiments/STITCHVECTOR/text_layer/text_result.json"; o.parent.mkdir(parents=True, exist_ok=True); json.dump(R, open(o, "w"), indent=1, default=str)
for t, x in R["boxes"].items(): print(t, "ocr", x["ocr_candidate"], x["ocr_score"], "| before", x["residue_before"], "after", x["residue_after"], "| uncertain groups", len(x["uncertain_groups"]))
print("outside", R["changed_outside_boxes"], "faces", R["faces_before_after"], "lines", R["lines_before_after"], "cov", R["coverage"]["accepted"])
print("save", R["save"]); print("reopen", R["reopen"]); print("inputs unchanged", R["inputs_unchanged"])
