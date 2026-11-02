"""GENERIC geological text rules (copied from experiments/STITCHVECTOR/ocr_poc01/geo_postprocess.py @ cae5a61, GENERIC level only).
Standard library only. Produces candidates with reasons; never overwrites the raw OCR string.
  R1 a digit right after an era/period prefix is a subscript (Ar2E -> Ar₂E)
  R2 a range ?-O must go old -> young; E-O / C-O / €-O / 6-O -> Є-O
  R3 '0' at the end of a code range is the letter O
The U2 legend dictionary of the POC is NOT used (it contains unconfirmed entries such as Jxd for J₂d)."""
import re

ERA = ["Ar", "Pt", "Pz", "Mz", "Kz", "Є", "O", "S", "D", "C", "P", "T", "J", "K", "E", "N", "Q"]
SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
CODE_RE = re.compile(r"^[A-Za-zЄ€₀-₉0-9′'\-]{1,7}$")
RULES_VERSION = "generic-1.0 (ocr_poc01 cae5a61)"


def is_code(s):
    s = "".join(str(s).split()); return bool(CODE_RE.match(s)) and any(c.isalpha() for c in s) and not s.isdigit()


def _prefix(s):
    for e in sorted(ERA, key=len, reverse=True):
        if s.startswith(e): return e
    return None


def generic(s):
    t, why = "".join(str(s).split()), []
    if not is_code(t): return str(s), []
    if re.match(r"^([Є€EC6])-([O0o])$", t) and t != "Є-O": t = "Є-O"; why.append("R2 range must be old->young; only Є-O is valid for ?-O")
    p = _prefix(t)
    if p and len(t) > len(p) and t[len(p)].isdigit() and p != "Є":
        t = t[:len(p)] + t[len(p)].translate(SUB) + t[len(p) + 1:]; why.append(f"R1 digit after era prefix '{p}' is a subscript")
    if re.search(r"[A-Za-z]-0$", t): t = t[:-1] + "O"; why.append("R3 0 -> O in code")
    return t, why


def suggest(raw):
    """-> (suggested text, [candidate texts], [reasons]). raw stays the first candidate when a rule changed it."""
    t, why = generic(raw)
    cands = [t] + ([str(raw)] if t != str(raw) else [])
    return t, cands, why
