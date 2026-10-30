import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "ARCH2"))
import arch2_metrics as M  # noqa: E402


def _scene():
    inst = np.ones((40, 40), np.int64); inst[:, 20:] = 2; inst[5:35, 8:12] = 3      # 3 = narrow instance
    cand = np.zeros((40, 40), np.int64)
    cand[5:35, 8:12] = 1        # good candidate
    cand[5:30, 9:12] = 2        # duplicate of the same instance (overwrites part of 1)
    cand[5:35, 19:21] = 3       # band on the 1|2 contact
    return inst, cand


def test_duplicates_are_not_counted_twice():
    inst, cand = _scene()
    mt = M.match_one_to_one(cand, inst, np.array([3]))
    assert sorted(mt.values()) == [3] and len(mt) == 1


def test_classes_and_protection_metrics():
    inst, cand = _scene()
    near = np.zeros(inst.shape, bool); near[:, 18:22] = True
    ink = np.zeros(inst.shape, bool); ink[:, 19:21] = True
    cls, mt = M.classify(cand, inst, np.array([3]), near, ink)
    assert list(cls.values()).count("TRUE_NARROW") == 1 and cls[3] == "INK_BAND" and "INCIDENTAL" in cls.values()
    tn = [c for c, k in cls.items() if k == "TRUE_NARROW"][0]
    m = M.protection_metrics(cls, [tn, 3])
    assert m["precision"]["value"] == 0.5 and m["recall"]["value"] == 1.0 and m["false_protection_ink_band_share"]["value"] == 0.5


def test_wilson_bounds():
    lo, hi = M.wilson(0, 44); assert lo == 0.0 and 0 < hi < 0.1
    assert M.wilson(0, 0) == [None, None]
