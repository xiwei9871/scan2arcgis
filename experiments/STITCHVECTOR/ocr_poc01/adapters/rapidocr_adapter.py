"""RapidOCR baseline adapter (.venv-ocr, rapidocr 3.4.5, default config = PP-OCRv4 mobile ONNX, same as sv_u2_full_ocr.py)."""
import time, numpy as np
import common as C
from rapidocr import RapidOCR

a = C.args(); t0 = time.time(); im = C.load(a); eng = RapidOCR(); out = []
bx = C.boxes(a)
if bx is None:
    r = eng(np.asarray(C.scaled(im, a.scale)))
    for b, s, c in zip(r.boxes if r.boxes is not None else [], r.txts or [], r.scores or []):
        out.append(C.det(np.asarray(b).tolist(), s, c, a.scale))
else:
    for b in bx:
        r = eng(np.asarray(C.crop(im, b["polygon"], a.scale)), use_det=False, use_cls=False)
        t, c = (r.txts[0], r.scores[0]) if r.txts else ("", None)
        out.append({**C.det(b["polygon"], t, c, 1), "sample_id": b["sample_id"]})
C.write(a, "rapidocr", "rapidocr-3.4.5/ch_PP-OCRv4_det+rec_mobile_onnx", out, t0)
