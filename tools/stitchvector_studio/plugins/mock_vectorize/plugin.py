"""Mock vectoriser for contract / hot-swap tests: a regular grid of faces coloured by the median scan colour of each
cell, and one diagonal line. Proves the Studio runs any plugin that honours vector_layers.v1. NOT a real algorithm."""
import json
from tools.stitchvector_studio.contracts import StageResult, artifact, OK


class Plugin:
    def validate_inputs(self, inputs, params):
        if inputs.get("raster", {}).get("schema") != "raster_document.v1": raise ValueError("mock needs raster_document.v1")

    def run(self, ctx, inputs, params):
        import numpy as np, geopandas as gpd
        from PIL import Image
        from shapely.geometry import box, LineString
        doc = json.load(open(inputs["raster"]["path"], encoding="utf-8")); a = np.asarray(Image.open(doc["raster_artifact"]).convert("RGB"))
        H, W = a.shape[:2]; c = params["cell"]; polys, rgb = [], []
        if params["fail"]: raise RuntimeError("mock vectoriser asked to fail (fail=true)")
        for y in range(0, H, c):
            for x in range(0, W, c):
                polys.append(box(x, y, min(x + c, W), min(y + c, H))); m = np.median(a[y:y + c, x:x + c].reshape(-1, 3), 0).astype(int)
                rgb.append("#%02x%02x%02x" % tuple(m))
        out = ctx.workdir / "vector_layers.gpkg"
        gpd.GeoDataFrame({"label": range(len(polys)), "colour_class": 0, "rgb": rgb, "observed_px": 0, "inferred_px": 0, "source": "mock"},
                         geometry=polys).to_file(out, layer="colour_faces", driver="GPKG", engine="pyogrio")
        gpd.GeoDataFrame({"line_id": ["M0"], "logical_id": ["GM0"], "kind": ["mock"], "width_px": [2.0], "rgb": ["#000000"], "source": ["mock"], "draw_order": [0]},
                         geometry=[LineString([(0, 0), (W, H)])]).to_file(out, layer="visual_lines", driver="GPKG", engine="pyogrio")
        return StageResult(OK, outputs={"vectors": artifact(out, "vector_layers.v1")}, stats={"faces": len(polys), "lines": 1},
                           warnings=["mock vectoriser: test data, not a geological result"], provenance={"algorithm": "mock grid"})
