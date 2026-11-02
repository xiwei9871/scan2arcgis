"""legacy-b2c-v01 vectoriser: wraps the frozen B2c line/face build used for the U2 full-sheet validation
(experiments/STITCHVECTOR/sv_u2_full_build.py). The algorithm modules are imported unchanged; the only adapter step is the
one already recorded there (multi-part B2c lines split into parts before grouping)."""
import json, sys
from pathlib import Path
from tools.stitchvector_studio.contracts import StageResult, artifact, OK

ROOT = Path(__file__).resolve().parents[4]
EXP = ROOT / "experiments/STITCHVECTOR"


class Plugin:
    def validate_inputs(self, inputs, params):
        if inputs.get("raster", {}).get("schema") != "raster_document.v1": raise ValueError("b2c needs a raster_document.v1 input")

    def run(self, ctx, inputs, params):
        import numpy as np
        from PIL import Image
        sys.path.insert(0, str(EXP))
        import sv_lf as LF, sv_d71 as D, sv_oracle as O, sv_oracle_v2 as O2, sv_u2_full_build as BLD
        doc = json.load(open(inputs["raster"]["path"], encoding="utf-8"))
        img = np.asarray(Image.open(doc["raster_artifact"]).convert("RGB")); shape = img.shape[:2]
        ctx.log(f"b2c on {doc['raster_artifact']} {shape}")
        X, kpal = LF.labels(img); log = {"multipart_split": []}
        raw, lines = BLD.line_objects(img, log)
        rem = LF.footprint(lines, shape, LF.Q["halo"]); Fimg = D.fill(X, rem); fc = O.faces(Fimg, LF.Q["tol"]); obs, inf = O.provenance(Fimg, rem, fc)
        out = ctx.workdir / "vector_layers.gpkg"
        O2.write(out, fc, kpal, np.arange(len(kpal)), obs, inf, lines, [])
        return StageResult(OK, outputs={"vectors": artifact(out, "vector_layers.v1")},
                           stats={"faces": int(len(fc["polys"])), "lines": len(lines), "b2c_objects": len(raw), "colour_classes": int(len(kpal)),
                                  "multipart_split": len(log["multipart_split"])},
                           provenance={"algorithm": "B2c (frozen)", "modules": ["sv_lf", "sv_b2c", "sv_v3", "sv_d71", "sv_oracle", "sv_oracle_v2"]})
