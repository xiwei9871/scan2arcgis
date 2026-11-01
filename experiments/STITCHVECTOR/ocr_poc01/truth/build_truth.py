"""Build truth/u2_text_truth.json from the agent-drafted TSV (u2_text_draft.tsv).
Every object is AGENT_DRAFT until a human reviewer flips it to HUMAN_VERIFIED in the JSON (see 02_ground_truth_protocol.md).
overlaps_geological_line is computed from B2c lines that are >= 25 px long and leave the box (a line that only lives
inside the box is treated as the text's own strokes); it is a pre-fill for the reviewer, not truth."""
import csv, json, sys, unicodedata
from pathlib import Path
from shapely.geometry import box
HERE = Path(__file__).parent; sys.path.insert(0, str(HERE.parent))
import gpkg_io as G

GPKG = Path.home() / "geomap2arcgis/runs/stitchvector/u2_full/u2_full_B2c.gpkg"
SPECIAL = set("Є₀₁₂₃₄₅₆₇₈₉′")
CAT = {"PLACE_NAME": "CHINESE_PLACE_NAME", "GEOLOGICAL_CODE": "GEOLOGICAL_CODE", "DIP_NUMBER": "NUMERIC_ATTITUDE",
       "SECTION_LABEL": "LATIN_LABEL", "SAMPLE_LABEL": "LATIN_LABEL", "SCALE_BAR": "NUMERIC_SCALE", "MAP_ANNOTATION": "MIXED_ANNOTATION"}


def main():
    lines = [l["geometry"] for l in G.layer(GPKG, "visual_lines")]
    out = []
    for i, r in enumerate(csv.DictReader(open(HERE / "u2_text_draft.tsv"), delimiter="\t")):
        x0, y0, x1, y1 = (float(r[k]) for k in ("x0", "y0", "x1", "y1")); b = box(x0, y0, x1, y1)
        cross = [l for l in lines if l.length >= 25 and l.intersects(b) and not b.buffer(1).contains(l)]
        out.append({"sample_id": f"u2_text_{i + 1:03d}", "image_id": "u2",
                    "polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                    "raw_text": r["text"], "normalized_text": unicodedata.normalize("NFC", r["text"]),
                    "category": CAT[r["category"]], "draft_category": r["category"],
                    "has_special_symbol": any(c in SPECIAL for c in r["text"]),
                    "orientation": "HORIZONTAL" if r["orient"] == "H" else r["orient"],
                    "overlaps_geological_line": bool(cross), "overlaps_geological_line_source": "auto_B2c_prefill",
                    "note": r["note"], "review_status": "AGENT_DRAFT",
                    "revision": [{"rev": 1, "by": "claude-opus-5-5 (agent)", "date": "2026-11-01", "action": "drafted from 4x map tiles"}]})
    json.dump({"image_id": "u2", "image_sha256": "05cdada47beed21363e7d1bf11bfa308ec3d02d6b270d06b4074906c6dcd64c7",
               "coords": "u2_map.png pixels (= work.png map box [0,0,805,780])", "objects": out}, open(HERE / "u2_text_truth.json", "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(out), Counter(o["category"] for o in out), "special", sum(o["has_special_symbol"] for o in out), "line", sum(o["overlaps_geological_line"] for o in out))


if __name__ == "__main__":
    main()
