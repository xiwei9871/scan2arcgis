"""OCR helper run in a separate interpreter that has RapidOCR (default ~/geomap2arcgis/.venv-ocr).
stdin: PNG bytes of a crop. stdout: JSON {"text": str, "score": float, "parts": [...]}. Gives a candidate only."""
import io, json, sys
import numpy as np
from PIL import Image
from rapidocr import RapidOCR

im = Image.open(io.BytesIO(sys.stdin.buffer.read())).convert("RGB")
w, h = im.size; im = im.resize((w * 4, h * 4), Image.LANCZOS)
pad = Image.new("RGB", (im.width + 40, im.height + 40), (255, 255, 255)); pad.paste(im, (20, 20))
r = RapidOCR()(np.asarray(pad))
txts = list(r.txts or []); scores = [float(s) for s in (r.scores or [])]
print(json.dumps({"text": " ".join(txts), "score": round(min(scores), 3) if scores else 0.0, "parts": txts}))
