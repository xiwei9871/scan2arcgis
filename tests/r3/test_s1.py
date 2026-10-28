import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R3"))
from s1_ocr_lib import case_convention, lexicon_match, levenshtein, normalise, split_subscript  # noqa: E402


def test_normalise_and_case_convention():
    assert normalise(" F-l ") == "Fl" and normalise("") is None and normalise(None) is None
    assert case_convention("FI") == "Fl" and case_convention("Ic") == "Ic"   # only after the first char


def test_lexicon_match_exact_edit1_and_ambiguous():
    lex = ["Ohf", "Ohl", "Mz", "t1"]
    assert lexicon_match("Mz", lex) == ("Mz", 0)
    assert lexicon_match("Mx", lex)[0] == "Mz"
    assert lexicon_match("Oh", lex)[0] is None          # tie Ohf/Ohl -> refuse
    assert lexicon_match("t", lex)[0] is None           # single char never fuzzy-matched
    assert levenshtein("kitten", "sitting") == 3


def test_split_subscript_finds_low_small_digit():
    b = np.full((60, 120), 255, np.uint8)
    b[10:50, 10:40] = 0                    # main glyph, full height
    b[35:55, 60:72] = 0                    # smaller, lower, to the right -> subscript
    main, sub = split_subscript(b)
    assert main is not None and sub is not None
    assert sub.shape[0] < main.shape[0]
