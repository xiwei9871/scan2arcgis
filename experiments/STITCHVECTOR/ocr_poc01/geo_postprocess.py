"""Geological text post-processing (T3). Produces *candidates with reasons*; it never overwrites raw OCR text.

Two knowledge levels, reported separately so dictionary hits are not mistaken for OCR accuracy:
  GENERIC  - rules valid for any Chinese geological map (no U2 data):
             R1 a digit right after an era/period prefix is a subscript (Ar2E -> Ar₂E, J3t -> J₃t);
             R2 a range X-Y must go old -> young; E-O / C-O / €-O / 6-O are not valid, Є-O is (Є/E/C/€/6 confusion);
             R3 'O' vs '0' inside a code is the letter O (period Ordovician).
  LEGEND   - U2 map-specific dictionary auto-extracted from the legend OCR of all three engines (legend_dictionary());
             letter/digit confusions (z/s/i/l/u/1 for a lost subscript, missing 't' in Pt) are only *candidates*,
             accepted when exactly one candidate is in the dictionary.
The confusion table was written after looking at errors in this same POC run (exploratory, not pre-registered).
"""
import itertools, json, re
from pathlib import Path

RAW = Path.home() / "geomap2arcgis/runs/ocr_poc01/raw"
ERA = ["Ar", "Pt", "Pz", "Mz", "Kz", "Є", "O", "S", "D", "C", "P", "T", "J", "K", "E", "N", "Q"]
AGE = {"Q": 0, "N": 1, "E": 2, "K": 3, "J": 4, "T": 5, "P": 6, "C": 7, "D": 8, "S": 9, "O": 10, "Є": 11, "Pt": 12, "Ar": 13}  # young -> old
SUB = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
LOST_SUB = {"z": "₂", "s": "₃", "a": "₃", "o": "₃", "i": "₁", "l": "₁", "u": "₁", "1": "₁", "2": "₂", "3": "₃", "e": "₂"}
EPS = "Є€E C6"
CODE_RE = re.compile(r"^[A-Za-zЄ€₀-₉0-9′'\-]{1,7}$")


def is_code(s):
    s = "".join(s.split()); return bool(CODE_RE.match(s)) and any(c.isalpha() for c in s) and not s.isdigit()


def _prefix(s):
    for e in sorted(ERA, key=len, reverse=True):
        if s.startswith(e): return e
    return None


def generic(s):
    """deterministic GENERIC rules; returns (text, [reasons])."""
    t, why = "".join(s.split()), []
    m = re.match(r"^([Є€EC6])-([O0o])$", t)
    if m and t != "Є-O":
        t = "Є-O"; why.append("R2 range must be old->young; only Є-O is valid for ?-O")
    p = _prefix(t)
    if p and len(t) > len(p) and t[len(p)].isdigit() and p not in ("Є",):
        t = t[:len(p)] + t[len(p)].translate(SUB) + t[len(p) + 1:]; why.append(f"R1 digit after era prefix '{p}' is a subscript")
    if "0" in t and any(c.isalpha() for c in t) and re.search(r"-0$", t):
        t = t[:-1] + "O"; why.append("R3 0 -> O in code")
    return t, why


def variants(s):
    """letter/digit confusion candidates (at most one subscript restoration + optional 't' insertion for Pt)."""
    t, _ = generic(s); out = {t: "generic"}
    p = _prefix(t)
    if p and len(t) > len(p) and t[len(p)] in LOST_SUB:
        out[t[:len(p)] + LOST_SUB[t[len(p)]] + t[len(p) + 1:]] = f"'{t[len(p)]}' read for lost subscript {LOST_SUB[t[len(p)]]}"
    if p and len(t) == len(p) + 1:
        for d in "₁₂₃": out.setdefault(t[:len(p)] + d + t[len(p):], f"subscript {d} dropped")
    if p and len(t) >= len(p) + 1 and t[len(p)].isalpha():
        for d in "₁₂₃": out.setdefault(t[:len(p)] + d + t[len(p):], f"subscript {d} dropped")
    if t.startswith("P") and not t.startswith("Pt") and len(t) >= 2 and t[1] in "ui1l":
        out.setdefault("Pt₁" + t[2:], "'Pu/Pi' for Pt₁ (t and subscript merged)")
    if t.startswith("Pt") and len(t) >= 3 and t[2] in "iu1l" and len(t) >= 4:
        out.setdefault("Pt₁" + t[3:], f"'{t[2]}' for subscript ₁")
    return out


def legend_dictionary():
    """codes from legend OCR (3 engines). An entry is accepted when >= 2 engines produce it at the same legend row
    (raw, GENERIC-normalised or one confusion variant). Returns sorted list + provenance."""
    runs = {e: json.load(open(RAW / f"legend_{e}_x2.json"))["detections"] for e in ("paddleocr", "rapidocr", "surya")}
    slots = []  # cluster legend code items by centre
    for e, D in runs.items():
        for d in D:
            for tok in d["raw_text"].split():
                if not is_code(tok) or len(tok) > 5: continue
                xs = [p[0] for p in d["polygon"]]; ys = [p[1] for p in d["polygon"]]
                cx, cy = min(xs) + 15, (min(ys) + max(ys)) / 2
                for s in slots:
                    if abs(s["cx"] - cx) < 25 and abs(s["cy"] - cy) < 10: s["v"].append((e, tok)); break
                else: slots.append({"cx": cx, "cy": cy, "v": [(e, tok)]})
    entries = {}
    for s in slots:
        votes = {}
        for e, tok in s["v"]:
            if re.match(r"^S\d+$", tok): continue          # sample labels (S1) are not stratigraphic codes
            g, _ = generic(tok)
            for cand, why in variants(tok).items():
                w = 2 if cand == g else 1                   # a direct (GENERIC) reading outweighs a speculative variant
                votes.setdefault(cand, {})[e] = max(votes.get(cand, {}).get(e, 0), w)
        scored = sorted(votes.items(), key=lambda kv: (-sum(kv[1].values()), -len(kv[1])))
        if scored and len(scored[0][1]) >= 2 and (len(scored) == 1 or sum(scored[0][1].values()) > sum(scored[1][1].values())):
            entries[scored[0][0]] = {"engines_raw": s["v"], "support": sorted(scored[0][1]), "score": sum(scored[0][1].values())}
        elif s["v"] and not all(re.match(r"^S\d+$", t) for _, t in s["v"]):
            entries.setdefault("_unresolved", []).append(s["v"])
    return dict(sorted(entries.items()))


def suggest(s, dictionary=None):
    """candidate_texts [(text, reason)], suggestion (or None), level used."""
    g, why = generic(s)
    cands = [(g, "; ".join(why) or "raw")] if g != "".join(s.split()) else [("".join(s.split()), "raw")]
    if dictionary is None or not is_code(s):
        return cands, (g if why else None), "GENERIC"
    hits = [(c, r) for c, r in variants(s).items() if c in dictionary]
    for c, r in hits:
        if c not in [x[0] for x in cands]: cands.append((c, f"legend dictionary hit via {r}"))
    if len(hits) == 1: return cands, hits[0][0], "LEGEND"
    return cands, (g if why else None), "LEGEND_AMBIGUOUS" if hits else "GENERIC"


if __name__ == "__main__":
    for k, v in legend_dictionary().items(): print(k, v if k == "_unresolved" else (v["support"], v["engines_raw"]))
