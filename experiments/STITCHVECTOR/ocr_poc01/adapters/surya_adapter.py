"""Surya adapter (runs/ocr_poc01/venvs/surya: surya-ocr 0.23.0; detector s3://text_detection/2025_05_07;
recogniser surya-ocr-2.5 GGUF Q8_0 via llama.cpp llama-server 0.8.0, Metal). Recognition uses Surya's block mode
(one crop per line box), because full-page mode returns layout blocks, not text lines.
HTML from the model is kept in `raw_html`; `raw_text` converts <sub>/<sup> to Unicode sub/superscripts where one exists."""
import html, re, time
import common as C
from surya.detection import DetectionPredictor
from surya.recognition import RecognitionPredictor
from surya.layout.schema import LayoutBox, LayoutResult

SUB = str.maketrans("0123456789+-=()aeoxhklmnpst", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜ")
SUP = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")


def _latex(h):
    """inline LaTeX the model sometimes emits (\\text{Ar}_2E, J_{3t}): drop \\text{}, turn _x / _{x} into Unicode subscripts
    where every character has one, otherwise keep the characters as plain text. Format conversion only, no correction."""
    h = re.sub(r"\\(?:text|mathrm|mathit)\{([^{}]*)\}", r"\1", h)
    def sub(m):
        t = m.group(1) or m.group(2); u = t.translate(SUB)
        return u if all(c != o for c, o in zip(u, t)) else t
    h = re.sub(r"_\{([^{}]*)\}|_(\w)", sub, h)
    return h.replace("$", "")


def to_text(h):
    h = _latex(h)
    h = re.sub(r"<sub>(.*?)</sub>", lambda m: m.group(1).translate(SUB), h, flags=re.S)
    h = re.sub(r"<sup>(.*?)</sup>", lambda m: m.group(1).translate(SUP), h, flags=re.S)
    h = re.sub(r"<br\s*/?>", " ", h)
    return html.unescape(re.sub(r"<[^>]+>", "", h)).strip()


a = C.args(); t0 = time.time(); im = C.load(a); out = []
bx = C.boxes(a); rec = RecognitionPredictor()
if bx is None:
    img = C.scaled(im, a.scale); d = DetectionPredictor()([img])[0]
    polys = [b.polygon for b in d.bboxes]; dconf = [b.confidence for b in d.bboxes]
else:
    img = C.scaled(im, a.scale); polys = [[[x * a.scale, y * a.scale] for x, y in b["polygon"]] for b in bx]; dconf = [None] * len(bx)
lb = [LayoutBox(polygon=p, label="Text", raw_label="Text", position=i, count=50) for i, p in enumerate(polys)]
r = rec([img], [LayoutResult(bboxes=lb, image_bbox=[0, 0, img.width, img.height])], full_page=False)[0] if lb else None
for i, p in enumerate(polys):
    blk = r.blocks[i]
    extra = {"raw_html": blk.html, "det_confidence": dconf[i]}
    if bx is not None: extra["sample_id"] = bx[i]["sample_id"]
    out.append(C.det(p, to_text(blk.html), blk.confidence, a.scale, **extra))
C.write(a, "surya", "surya-ocr-0.23.0/det-2025_05_07+surya-ocr-2.5-Q8_0.gguf(llama.cpp-0.8.0)", out, t0)
