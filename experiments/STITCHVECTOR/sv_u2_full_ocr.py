import json, sys, time, numpy as np
from PIL import Image
from rapidocr import RapidOCR
im = Image.open(sys.argv[1]).convert("RGB"); t = time.time(); out = []
for k in (1, 2):
    a = np.asarray(im.resize((im.width * k, im.height * k), Image.LANCZOS)); r = RapidOCR()(a)
    for b, s, c in zip(r.boxes if r.boxes is not None else [], r.txts or [], r.scores or []):
        out.append({"scale": k, "quad": (np.asarray(b) / k).round(1).tolist(), "text": s, "score": round(float(c), 3)})
print(json.dumps({"seconds": round(time.time() - t, 1), "items": out}, ensure_ascii=False))
