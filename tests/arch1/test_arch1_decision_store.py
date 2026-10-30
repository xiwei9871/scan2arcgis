import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "ARCH1"))
from arch1_decision_store import DecisionStore  # noqa: E402


def test_geometry_survives_absorption_and_roundtrip(tmp_path):
    m = np.zeros((30, 40), bool); m[5:25, 10:13] = True
    S = DecisionStore(); cid = S.add("C-PAIR", m, 3.0, {"de": 4.0, "b2_med": 0.6}, "UNCERTAIN", [("de", "E-APP")])
    final = np.ones((30, 40), np.int32)                     # candidate absorbed into one big region
    S.resolve(final)
    r = S.records[cid]; assert r["absorbed_into"] == 1 and np.array_equal(S.mask(cid, m.shape), m)
    p = tmp_path / "s.json"; S.dump(p); T = DecisionStore.load(p)
    assert np.array_equal(T.mask(cid, m.shape), m) and T.records[cid]["evidence"]["de"]["group"] == "E-APP"


def test_surviving_candidate_is_not_marked_absorbed():
    m = np.zeros((30, 40), bool); m[5:25, 10:13] = True
    final = np.ones((30, 40), np.int32); final[m] = 2
    S = DecisionStore(); cid = S.add("C-PAIR", m, 3.0, {}); S.resolve(final)
    assert S.records[cid]["absorbed_into"] is None
