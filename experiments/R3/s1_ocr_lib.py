"""Small OCR helpers specialised for stratigraphic codes (prediction side, no ground truth).

Two adaptations, each measured separately against plain Tesseract in the S1 report:
  subscript split : geologic codes often carry a subscript digit (M3, O1, A5). OCR reads the small
                    digit as a letter ('Ms'). We split dark connected components into main glyphs
                    and a trailing subscript (smaller, sitting lower), OCR the main part with a
                    letter whitelist and the subscript with a digit whitelist.
  case convention : codes are written Capital + lowercase (Fl, Jl, Ohf). After the first character an
                    uppercase 'I' is mapped to 'l' (Tesseract confuses the two in this font).
"""
import re, shutil, subprocess, tempfile
import cv2, numpy as np

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"


def tess(img, psm, whitelist):
    if not shutil.which("tesseract"): return None, None
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, img)
        out = subprocess.run(["tesseract", f.name, "stdout", "--psm", str(psm), "-l", "eng",
                              "-c", f"tessedit_char_whitelist={whitelist}", "tsv"],
                             capture_output=True, text=True, timeout=30).stdout
    words, confs = [], []
    for line in out.splitlines()[1:]:
        p = line.split("\t")
        if len(p) == 12 and p[11].strip() and p[10] not in ("-1", ""):
            words.append(p[11].strip()); confs.append(float(p[10]) / 100)
    return ("".join(words) or None), (float(np.mean(confs)) if confs else None)


def binarise(rgb, up=3):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    g = cv2.resize(g, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC)
    _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if (b == 0).mean() > 0.5: b = 255 - b
    return b  # text = 0 (black), background = 255


def split_subscript(b):
    """Return (main_img, sub_img or None) from a binarised code crop."""
    ink = (b == 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    h, w = b.shape
    comps = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 0.0008 * h * w
             and st[i, cv2.CC_STAT_HEIGHT] < 0.95 * h and st[i, cv2.CC_STAT_WIDTH] < 0.9 * w]
    if not comps: return None, None
    H = max(st[i, cv2.CC_STAT_HEIGHT] for i in comps)
    main = [i for i in comps if st[i, cv2.CC_STAT_HEIGHT] >= 0.72 * H]
    if not main: return None, None
    top = min(st[i, cv2.CC_STAT_TOP] for i in main)
    base = max(st[i, cv2.CC_STAT_TOP] + st[i, cv2.CC_STAT_HEIGHT] for i in main)
    right = max(st[i, cv2.CC_STAT_LEFT] + st[i, cv2.CC_STAT_WIDTH] for i in main)
    sub = [i for i in comps if i not in main and st[i, cv2.CC_STAT_LEFT] >= right - 0.15 * H
           and st[i, cv2.CC_STAT_TOP] > top + 0.35 * H and st[i, cv2.CC_STAT_HEIGHT] >= 0.25 * H]

    def render(ids):
        m = np.isin(lab, ids)
        ys, xs = np.nonzero(m)
        c = np.where(m, 0, 255).astype(np.uint8)[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        return cv2.copyMakeBorder(c, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return render(main), (render(sub) if sub else None)


def case_convention(code):
    if not code: return code
    return code[0] + code[1:].replace("I", "l")


def normalise(s):
    if s is None: return None
    s = re.sub(r"[^A-Za-z0-9]", "", str(s))
    return s or None


def read_code(rgb, convention=True):
    """Subscript-aware Tesseract reading of one code crop. Returns (code, score_uncalibrated)."""
    b = binarise(rgb)
    main, sub = split_subscript(b)
    if main is None: return None, None
    t1, c1 = tess(main, 7, LETTERS)
    if not t1: return None, None
    code, sc = t1, [c1]
    if sub is not None:
        t2, c2 = tess(sub, 10, DIGITS)
        if t2: code += t2[:1]; sc.append(c2)
    code = normalise(code)
    if convention: code = case_convention(code)
    return code, float(np.mean([x for x in sc if x is not None])) if any(x is not None for x in sc) else None


def lexicon_match(token, lexicon, max_dist=1):
    """Map a token to the closest legend code (prediction-side lexicon). None if ambiguous/too far."""
    if not token: return None, None
    if token in lexicon: return token, 0
    best, bd, tie = None, 99, False
    for c in lexicon:
        d = levenshtein(token, c)
        if d < bd: best, bd, tie = c, d, False
        elif d == bd: tie = True
    if bd <= max_dist and not tie and len(token) >= 2: return best, bd
    return None, bd


def levenshtein(a, b):
    p = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        q = [i]
        for j, cb in enumerate(b, 1):
            q.append(min(p[j] + 1, q[j - 1] + 1, p[j - 1] + (ca != cb)))
        p = q
    return p[-1]
