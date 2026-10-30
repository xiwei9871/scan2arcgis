import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "ARCH2"))
import arch2_subdivision as S  # noqa: E402


def _base():
    b = np.zeros((40, 40), np.int32); b[:, 20:] = 1; return b


def test_coincident_candidate_adds_nothing():
    c = np.zeros((40, 40), np.int64); c[:, 20:] = 5
    lab, info, _ = S.graded(_base(), c)
    assert lab.max() == 2 and info["kept_pairs"] == 0


def test_one_px_offset_duplicate_is_dropped():
    c = np.zeros((40, 40), np.int64); c[:, 21:] = 5           # boundary 1 px right of the base boundary
    lab, info, _ = S.graded(_base(), c)
    assert lab.max() == 2 and info["kept_pairs"] == 0 and info["dropped_as_duplicate"] > 0


def test_independent_strip_is_kept_exactly():
    c = np.zeros((40, 40), np.int64); c[5:35, 6:9] = 7         # 3 px strip inside base unit 0
    lab, info, _ = S.graded(_base(), c)
    assert lab.max() == 3
    k = lab[20, 7]; assert ((lab == k) == (c == 7)).all()


def test_no_cut_beyond_declared_pairs_and_regions_4connected():
    rng = np.random.default_rng(0)
    base = np.kron((rng.random((6, 6)) > 0.5).astype(np.int32), np.ones((10, 10), np.int32))
    cand = np.kron(rng.integers(0, 4, (12, 12)), np.ones((5, 5), np.int64))
    lab, info, (kr, kd) = S.graded(base, cand)
    br, bd = S.separations(base); lr, ld = S.separations(lab)
    assert not (br & ~lr).any() and not (bd & ~ld).any()          # every base separation is kept
    assert not (lr & ~(br | kr)).any() and not (ld & ~(bd | kd)).any()   # no cut beyond declared pairs
    assert info["dangling_kept_pairs"] == int((kr & ~lr).sum() + (kd & ~ld).sum())   # open fragments reported, not cut
    from scipy import ndimage as ndi
    for k in np.unique(lab):
        assert ndi.label(lab == k, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])[1] == 1


def test_t_junction_keeps_candidate_closed():
    base = np.zeros((40, 40), np.int32); base[20:, :] = 1          # horizontal base boundary at row 19/20
    c = np.zeros((40, 40), np.int64); c[5:20, 10:13] = 3            # strip touching the base boundary from above
    lab, _, _ = S.graded(base, c)
    k = lab[10, 11]; assert ((lab == k) == (c == 3)).all()


def test_region_dedup_keeps_offset_strip_closed():
    base = np.zeros((40, 40), np.int32); base[:, 20:] = 1
    base[5:35, 9:13] = 2                                         # base already has a region 1 px wider than the strip
    c = np.zeros((40, 40), np.int64); c[5:35, 10:13] = 7          # 3 px candidate, offset by 1 px on one side
    lab, info, _ = S.graded(base, c)                             # pair-level: offset side dropped
    lab2, info2, keep = S.graded_region(base, c)
    assert info2["skipped_already_separated"] == 1 and lab2.max() == 3   # already separated -> nothing added
    c[5:35, 3:6] = 8                                             # second, not separated strip inside unit 0
    lab3, info3, keep3 = S.graded_region(base, c)
    k = lab3[20, 4]; assert list(keep3) == [8] and ((lab3 == k) == (c == 8)).all()
