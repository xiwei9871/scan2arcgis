"""Unit tests for the scorer and post-processor (no OCR engines, no local data needed)."""
import sys, types
from pathlib import Path
from shapely.geometry import box
HERE = Path(__file__).parent.parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "adapters"))
import benchmark_runner as B
import geo_postprocess as GP


def test_lev():
    assert B.lev("Ar₂E", "Ar2E") == 1 and B.lev("", "abc") == 3 and B.lev("abc", "abc") == 0


def test_norm_keeps_subscript_in_raw_only():
    assert B.norm("Ar₂ E", "raw") == "Ar₂E" and B.norm("Ar₂E", "nfkc") == "Ar2E" and B.norm("Є-O", "nfkc") == "Є-O"


def test_match_one_to_one():
    T = [{"g": box(0, 0, 10, 10)}, {"g": box(20, 0, 30, 10)}]
    P = [{"g": box(0, 0, 10, 10)}, {"g": box(1, 1, 10, 10)}, {"g": box(0, 0, 30, 10)}]
    pairs = B.match(P, T)
    assert pairs[0] == 0 and len(set(pairs.values())) == len(pairs)


def test_wilson():
    lo, hi = B.wilson(5, 10); assert 0.2 < lo < 0.5 < hi < 0.8


def test_generic_rules():
    assert GP.generic("Ar2E")[0] == "Ar₂E"
    assert GP.generic("J3t")[0] == "J₃t"
    assert GP.generic("€-o")[0] == "Є-O" and GP.generic("C-O")[0] == "Є-O" and GP.generic("E-0")[0] == "Є-O"
    assert GP.generic("C-P")[0] == "C-P" and GP.generic("N-Q")[0] == "N-Q"   # valid ranges untouched
    assert GP.generic("宁武县")[0] == "宁武县"


def test_suggest_never_changes_raw_and_needs_unique_hit():
    raw = "PuD"; cands, sug, lvl = GP.suggest(raw, {"Pt₁D"})
    assert raw == "PuD" and sug == "Pt₁D" and lvl == "LEGEND"
    _, sug2, lvl2 = GP.suggest("Jy", {"J₁y", "J₂y"})
    assert sug2 is None and lvl2 == "LEGEND_AMBIGUOUS"


def test_surya_html_and_latex():
    for m in ["surya", "surya.detection", "surya.recognition", "surya.layout", "surya.layout.schema"]:
        sys.modules.setdefault(m, types.SimpleNamespace(DetectionPredictor=0, RecognitionPredictor=0, LayoutBox=0, LayoutResult=0))
    src = open(HERE / "adapters/surya_adapter.py").read().split("a = C.args()")[0]; ns = {}; exec(src, ns)
    f = ns["to_text"]
    assert f("<p>Ar<sub>2</sub>E</p>") == "Ar₂E" and f(r"\text{Ar}_2E") == "Ar₂E" and f("J_2y") == "J₂y" and f("<p>云</p>") == "云"
