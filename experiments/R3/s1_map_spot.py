"""S1 stage 1b: find stratigraphic code labels printed inside the map body (prediction side, no GT).

Pipeline
  1. tile the neatline area of the 200 dpi sheet (1024 px tiles, 160 px overlap)
  2. text LOCALISATION: RapidOCR PP-OCRv4 detector (Apache-2.0) on each tile
  3. character RECOGNITION on each box, two readers kept side by side:
       rapid : RapidOCR recogniser (same pass)
       tess  : s1_ocr_lib.read_code (Tesseract, subscript split + case convention)
  4. NORMALISATION + lexicon match: the lexicon is the set of codes the system itself read from the
     legend (s1_legend_ocr output, engine chosen on the command line). Never the xlsx.
  5. de-duplicate boxes from overlapping tiles (same token, centre within 12 px)

Every candidate keeps raw text, normalised token, lexicon code (or None), box, centre (full-res px),
uncalibrated scores, reader, and a status: LEXICON_EXACT / LEXICON_EDIT1 / NOT_A_CODE.
Non-code text (place names, elevations, grid numbers) is expected to end up NOT_A_CODE.
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from s1_ocr_lib import read_code, normalise, lexicon_match, case_convention  # noqa: E402

TILE, OVL = 1024, 160


def main(img, frame_json, legend_ocr_json, engine, out_json):
    from rapidocr import RapidOCR
    eng = RapidOCR()
    full = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB); H, W = full.shape[:2]
    fr = json.load(open(frame_json))
    c = np.array([fr["corners_px"][k] for k in ("tl", "tr", "br", "bl")])
    x0, y0 = np.floor(c.min(0)).astype(int) + 12; x1, y1 = np.ceil(c.max(0)).astype(int) - 12
    mask = np.zeros((H, W), np.uint8); cv2.fillPoly(mask, [np.round(c).astype(np.int32)], 1)
    mask = cv2.erode(mask, np.ones((25, 25), np.uint8))
    leg = json.load(open(legend_ocr_json))
    lexicon = sorted({r[engine]["code"] for r in leg["swatches"] if r[engine]["code"]})
    cands, t0 = [], time.time()
    for ty in range(y0, y1, TILE - OVL):
        for tx in range(x0, x1, TILE - OVL):
            tile = full[ty:min(ty + TILE, y1), tx:min(tx + TILE, x1)]
            if tile.shape[0] < 64 or tile.shape[1] < 64: continue
            r = eng(cv2.cvtColor(tile, cv2.COLOR_RGB2BGR), use_cls=False)
            boxes = getattr(r, "boxes", None)
            if boxes is None: continue
            for b, txt, sc in zip(boxes, r.txts, r.scores):
                b = np.asarray(b, np.float64) + (tx, ty)
                bx0, by0 = b.min(0); bx1, by1 = b.max(0)
                cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
                if not mask[int(cy), int(cx)]: continue
                h = by1 - by0; w = bx1 - bx0
                if h < 8 or w < 6 or w > 12 * h: continue        # codes are short tokens
                crop = full[int(max(by0 - 3, 0)):int(by1 + 3), int(max(bx0 - 3, 0)):int(bx1 + 3)]
                rt = case_convention(normalise(txt))
                tt, ts = read_code(crop, convention=True)
                for reader, tok, s in (("rapid", rt, float(sc)), ("tess", tt, ts)):
                    code, dist = lexicon_match(tok, lexicon)
                    cands.append({"reader": reader, "raw": txt if reader == "rapid" else tt, "token": tok,
                                  "code": code, "edit_dist": dist,
                                  "status": "NOT_A_CODE" if code is None else ("LEXICON_EXACT" if dist == 0 else "LEXICON_EDIT1"),
                                  "score_uncalibrated": s, "centre_px": [float(cx), float(cy)],
                                  "box_px": [float(bx0), float(by0), float(bx1 - bx0), float(by1 - by0)]})
    # de-duplicate per reader
    out = []
    for reader in ("rapid", "tess"):
        kept = []
        for cnd in sorted([x for x in cands if x["reader"] == reader], key=lambda x: -(x["score_uncalibrated"] or 0)):
            if any(k["token"] == cnd["token"] and np.hypot(k["centre_px"][0] - cnd["centre_px"][0], k["centre_px"][1] - cnd["centre_px"][1]) < 12 for k in kept):
                continue
            kept.append(cnd)
        out += kept
    res = {"image": Path(img).name, "detector": "RapidOCR PP-OCRv4 det (rapidocr 3.4.5)", "lexicon_source": f"legend OCR engine {engine}",
           "lexicon": lexicon, "seconds": time.time() - t0, "n_boxes": sum(1 for x in out if x["reader"] == "rapid"),
           "candidates": out}
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1)
    for reader in ("rapid", "tess"):
        xs = [x for x in out if x["reader"] == reader]
        print(reader, "boxes", len(xs), {s: sum(1 for x in xs if x["status"] == s) for s in ("LEXICON_EXACT", "LEXICON_EDIT1", "NOT_A_CODE")})
    print("seconds", round(res["seconds"], 1), "lexicon", lexicon)


if __name__ == "__main__":
    main(*sys.argv[1:6])
