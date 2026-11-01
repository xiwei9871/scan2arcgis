"""Reproducible text-layer DEMO output for human visual UAT (not a geological result).

Input : runs/stitchvector/editor_v01/inputs/u2_B2c.gpkg (original B2c, never written).
Output: runs/stitchvector/editor_text/demo/u2_text_demo.gpkg
Three user text boxes (Є-O, Ar₂E, 云) with the user-confirmed text. Only residue groups that touch exactly ONE ground
face are merged (the editor's default). Uncertain groups (Ar₂E on the pink/red contact) are NOT assigned: they stay as
they are, pending a human decision. No nearest-colour or other automatic assignment is used.
"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from tools.stitchvector_editor.core import Document, coverage_report  # noqa: E402

INP = Path.home() / "geomap2arcgis/runs/stitchvector/editor_v01/inputs"
OUT = Path.home() / "geomap2arcgis/runs/stitchvector/editor_text/demo"
BOXES = {"Є-O": (3, 25, 35, 42), "Ar₂E": (0, 196, 52, 225), "云": (24, 59, 41, 76)}


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


if __name__ == "__main__":
    src = INP / "u2_B2c.gpkg"; s0 = sha(src); OUT.mkdir(parents=True, exist_ok=True)
    doc = Document(src, (300, 300), np.asarray(Image.open(INP / "u2_original.png").convert("RGB")))
    R = {"input": str(src), "input_sha256": s0, "boxes": {}, "assignment_of_uncertain_groups": "none (left pending)"}
    for t, b in BOXES.items():
        pv = doc.text_preview(b)
        r = doc.text_apply(pv["preview_id"], t)          # no assign: uncertain groups untouched
        R["boxes"][t] = {"box": b, "ocr_candidate": pv["ocr"].get("text"), "ocr_score": pv["ocr"].get("score"), "counts": pv["counts"], "applied": r}
    out = OUT / "u2_text_demo.gpkg"
    if out.exists(): out.unlink()
    sv = doc.save_as(out)
    re = Document(out, (300, 300))
    R.update(output=str(out), output_sha256=sha(out), faces=len(re.F), lines=len(re.L), texts=list(re.T["text"]), residue_lines=len(re.Q),
             pending=re.pending_residue(), coverage=coverage_report(re.F, 300, 300)["accepted"],
             save={k: sv[k] for k in ("accepted", "readback_matches_memory", "text_matches_memory", "input_sha256_unchanged")},
             input_unchanged=sha(src) == s0)
    o = ROOT / "experiments/STITCHVECTOR/text_layer/text_demo.json"; json.dump(R, open(o, "w"), indent=1, default=str, ensure_ascii=False)
    print(json.dumps({k: R[k] for k in ("faces", "lines", "texts", "residue_lines", "coverage", "save", "input_unchanged", "output_sha256")}, ensure_ascii=False))
    for p in R["pending"]: print("pending", p["text"], len(p["faces"]))
    for t, x in R["boxes"].items(): print(t, x["counts"])
