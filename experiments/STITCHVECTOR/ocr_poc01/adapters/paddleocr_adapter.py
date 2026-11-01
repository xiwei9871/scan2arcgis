"""PaddleOCR adapter (runs/ocr_poc01/venvs/paddle: paddleocr 3.7.0, paddlepaddle 3.3.1 CPU).
Pipeline: PP-OCRv6_medium_det + PP-OCRv6_medium_rec + PP-LCNet_x1_0_textline_ori (library defaults for lang=ch)."""
import os, time, numpy as np
import common as C
from paddleocr import PaddleOCR, TextRecognition

a = C.args(); t0 = time.time(); im = C.load(a); out = []
bx = C.boxes(a)
if bx is None:
    ocr = PaddleOCR(lang="ch", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=True, device="cpu")
    d = ocr.predict(np.asarray(C.scaled(im, a.scale))[:, :, ::-1].copy())[0]
    model = f"paddleocr-3.7.0/{d['model_settings'] if 'model_settings' in d else ''}"
    for p, s, c in zip(d["rec_polys"], d["rec_texts"], d["rec_scores"]):
        out.append(C.det(np.asarray(p).tolist(), s, c, a.scale))
else:
    rec = TextRecognition(model_name="PP-OCRv6_medium_rec", device="cpu")
    crops = [np.asarray(C.crop(im, b["polygon"], a.scale))[:, :, ::-1].copy() for b in bx]
    for b, r in zip(bx, rec.predict(crops, batch_size=8)):
        out.append({**C.det(b["polygon"], r["rec_text"], r["rec_score"], 1), "sample_id": b["sample_id"]})
C.write(a, "paddleocr", "paddleocr-3.7.0/PP-OCRv6_medium_det+PP-OCRv6_medium_rec+PP-LCNet_x1_0_textline_ori", out, t0)
