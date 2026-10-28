"""S1 stage 1: read the stratigraphic code printed in each legend swatch, with several OCR engines.

Prediction side (no ground truth): detected swatch boxes (R1 detect_swatches, stored in r1_eval.json)
-> crop from the full-resolution sheet -> OCR -> normalise.

Engines (all run locally on macOS, licences recorded in the report):
  tess_psm7     Tesseract 5 LSTM, single line, alnum whitelist   (Apache-2.0)
  tess_psm8     Tesseract 5 LSTM, single word, alnum whitelist   (Apache-2.0)
  rapid_rec     RapidOCR PP-OCRv4 recogniser only, on the crop   (Apache-2.0 code + models)
  rapid_detrec  RapidOCR detection + recognition on the crop
  tess_sub      Tesseract, main glyphs (letters) + subscript digit read separately   (s1_ocr_lib)
  tess_sub_case tess_sub + case convention (I->l after the first character)

Each swatch crop is binarised for Tesseract (text is dark on a coloured fill) and passed as colour
to RapidOCR. Output: per swatch, per engine, raw text + score + normalised code.
"""
import json, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
from s1_ocr_lib import read_code  # noqa: E402


def normalise(s):
    """Map OCR text to a code token: strip spaces/punctuation, keep [A-Za-z0-9]."""
    if s is None: return None
    s = re.sub(r"[^A-Za-z0-9]", "", str(s))
    return s or None


def crop_box(full, box_work, scale, inset=3):
    x, y, w, h = [int(round(t / scale)) for t in box_work]
    return full[y + inset:y + h - inset, x + inset:x + w - inset]


def prep_tess(c):
    g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY)
    g = cv2.resize(g, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if (b == 0).mean() > 0.5: b = 255 - b         # make text dark on white
    return cv2.copyMakeBorder(b, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)


def tesseract(img, psm):
    if not shutil.which("tesseract"): return None, None
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, img)
        cmd = ["tesseract", f.name, "stdout", "--psm", str(psm), "-l", "eng",
               "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", "tsv"]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    words, confs = [], []
    for line in out.splitlines()[1:]:
        p = line.split("\t")
        if len(p) == 12 and p[11].strip() and p[10] not in ("-1", ""):
            words.append(p[11].strip()); confs.append(float(p[10]) / 100)
    return (" ".join(words) or None), (float(np.mean(confs)) if confs else None)


class Rapid:
    def __init__(self):
        from rapidocr import RapidOCR
        self.eng = RapidOCR()

    def rec(self, c):
        big = cv2.resize(c, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        r = self.eng(cv2.cvtColor(big, cv2.COLOR_RGB2BGR), use_det=False, use_cls=False, use_rec=True)
        t = getattr(r, "txts", None); s = getattr(r, "scores", None)
        return (t[0] if t else None), (float(s[0]) if s else None)

    def detrec(self, c):
        big = cv2.copyMakeBorder(cv2.resize(c, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC), 16, 16, 16, 16,
                                 cv2.BORDER_REPLICATE)
        r = self.eng(cv2.cvtColor(big, cv2.COLOR_RGB2BGR))
        t = getattr(r, "txts", None) or (); s = getattr(r, "scores", None) or ()
        return (" ".join(t) or None), (float(np.mean(s)) if len(s) else None)


def main(img, r1_eval_json, out_json):
    ev = json.load(open(r1_eval_json)); s = ev["scale"]
    full = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    rapid = Rapid()
    engines = {"tess_psm7": lambda c: tesseract(prep_tess(c), 7), "tess_psm8": lambda c: tesseract(prep_tess(c), 8),
               "rapid_rec": rapid.rec, "rapid_detrec": rapid.detrec,
               "tess_sub": lambda c: read_code(c, convention=False),
               "tess_sub_case": lambda c: read_code(c, convention=True)}
    rows, timing = [], {k: 0.0 for k in engines}
    for sw in ev["swatches"]:
        c = crop_box(full, sw["box"], s)
        r = {"swatch": sw["id"], "box_work": sw["box"]}
        for k, fn in engines.items():
            t0 = time.time(); txt, sc = fn(c); timing[k] += time.time() - t0
            r[k] = {"raw": txt, "score_uncalibrated": sc, "code": normalise(txt)}
        rows.append(r)
    json.dump({"image": Path(img).name, "engines": list(engines), "seconds_total": timing, "swatches": rows},
              open(out_json, "w"), ensure_ascii=False, indent=1)
    for r in rows: print(r["swatch"], {k: r[k]["code"] for k in engines})
    print("seconds", {k: round(v, 1) for k, v in timing.items()})


if __name__ == "__main__":
    main(*sys.argv[1:4])
