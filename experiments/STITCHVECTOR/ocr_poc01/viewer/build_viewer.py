"""Build the local interactive viewer: copies index.html + map image + data.js into runs/ocr_poc01/viewer/ (git-ignored).
data.js holds truth, negatives, per-engine e2e boxes (1x+2x union) with match status, fixed-box readings and B2c lines.
Open runs/ocr_poc01/viewer/index.html in a browser (file://, no server needed)."""
import json, shutil, sys
from pathlib import Path
HERE = Path(__file__).parent; sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent.parent))
import benchmark_runner as B
import gpkg_io as G

OUT = Path.home() / "geomap2arcgis/runs/ocr_poc01/viewer"
IMG = Path.home() / "geomap2arcgis/runs/stitchvector/u2_full/u2_map.png"


def main():
    OUT.mkdir(parents=True, exist_ok=True); T, N = B.load_truth()
    eng = {}
    for e in B.ENGINES:
        P = B.union_scales(B.load_run(f"{e}_e2e_x1"), B.load_run(f"{e}_e2e_x2"))["detections"]; pairs = B.match(P, T); inv = {i: j for j, i in pairs.items()}
        neg = lambda p: any(p["g"].intersection(n["g"]).area / n["g"].area >= 0.3 for n in N)
        boxes = []
        for i, p in enumerate(P):
            j = inv.get(i); ok = j is not None and B.norm(p["raw_text"], "raw") == B.norm(T[j]["raw_text"], "raw")
            boxes.append({"poly": p["polygon"], "text": p["raw_text"], "conf": p["confidence"], "truth": None if j is None else T[j]["sample_id"],
                          "status": "CORRECT" if ok else ("WRONG_TEXT" if j is not None else ("FALSE_POS_NEG" if neg(p) else "UNMATCHED"))})
        missed = [T[j]["sample_id"] for j in range(len(T)) if j not in pairs]
        fixed = {}
        for k in (1, 2):
            for d in json.load(open(B.RAW / f"{e}_fixed_x{k}.json"))["detections"]: fixed.setdefault(d["sample_id"], {})[f"x{k}"] = d["raw_text"]
        eng[e] = {"boxes": boxes, "missed": missed, "fixed": fixed}
    lines = [[[round(x, 1), round(y, 1)] for x, y in l["geometry"].coords] for l in G.layer(
        Path.home() / "geomap2arcgis/runs/stitchvector/u2_full/u2_full_B2c.gpkg", "visual_lines") if l["geometry"].geom_type == "LineString"]
    truth = [{k: t[k] for k in ("sample_id", "polygon", "raw_text", "category", "has_special_symbol", "overlaps_geological_line", "review_status", "note")} for t in T]
    negs = [{"sample_id": n["sample_id"], "polygon": n["polygon"], "kind": n["neg_kind"]} for n in N]
    data = {"image": IMG.name, "w": 805, "h": 780, "truth": truth, "negatives": negs, "engines": eng, "lines": lines,
            "truth_status": "AGENT_DRAFT - not human verified"}
    (OUT / "data.js").write_text("window.OCR_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    shutil.copyfile(HERE / "index.html", OUT / "index.html"); shutil.copyfile(IMG, OUT / IMG.name)
    print(OUT / "index.html", len(truth), {e: len(v["boxes"]) for e, v in eng.items()}, len(lines))


if __name__ == "__main__":
    main()
