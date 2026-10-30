import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4C0"))
import r4c0_rag as R  # noqa: E402


def _two_units_with_gap(gap=True):
    b = np.zeros((60, 80), np.float32); b[:, 39:41] = 0.9          # strong vertical boundary
    if gap: b[28:32, 39:41] = 0.05                                  # local gap (missed boundary)
    return b


def _pairs(b):
    sr = np.zeros_like(b); sd = np.zeros_like(b)
    sr[:, :-1] = np.maximum(b[:, :-1], b[:, 1:]); sd[:-1] = np.maximum(b[:-1], b[1:])
    return sr, sd


def test_gap_does_not_merge_two_units_with_median_cost():
    b = _two_units_with_gap(True); lab = R.overseg(b); sr, sd = _pairs(b)
    rag = R.build_rag(lab, sr, sd); merges = R.merge(rag)
    root = R.partitions(rag["n"], merges, [0.5])[0.5]
    reg = root[lab]
    assert reg[30, 10] != reg[30, 70]                               # gap is 4/60 of the border -> median stays high


def test_merge_sequence_prefix_equals_stopped_run():
    rng = np.random.default_rng(0); b = rng.random((40, 40)).astype(np.float32) ** 3
    lab = R.overseg(b); sr, sd = _pairs(b); rag = R.build_rag(lab, sr, sd)
    full = R.merge(rag); stopped = R.merge(rag, stop=0.3)
    assert [m[1:] for m in stopped] == [m[1:] for m in full[:len(stopped)]]
    p = R.partitions(rag["n"], full, [0.3])[0.3]; q = R.partitions(rag["n"], stopped, [np.inf])[np.inf]
    assert (p[lab] == q[lab]).all()


def test_colour_cost_blocks_merge_across_weak_boundary():
    b = np.full((40, 60), 0.2, np.float32); b[:, 29:31] = 0.35     # weak boundary
    lab = R.overseg(b + np.linspace(0, 1e-3, 60)[None]); sr, sd = _pairs(b); rag = R.build_rag(lab, sr, sd)
    img = np.zeros((40, 60, 3)); img[:, 30:, 0] = 60.0              # Lab L differs by 60 across the boundary
    cs, cc = R.region_colour(lab, img, np.zeros((40, 60), bool))
    no = R.partitions(rag["n"], R.merge(rag), [0.5])[0.5][lab]
    yes = R.partitions(rag["n"], R.merge(rag, cs, cc, lam=0.5), [0.5])[0.5][lab]
    assert no[20, 5] == no[20, 55] and yes[20, 5] != yes[20, 55]


def test_oracles_A_ge_B_and_pure_case_is_one():
    i1 = np.zeros((40, 40), np.int64); i1[:, :20] = 1; i1[:, 20:] = 2; i1[10:30, 8:12] = 3
    V = np.ones(i1.shape, bool)
    lab = (i1 * 10 + (np.arange(40)[None] // 5)).astype(np.int32)  # pure over-segmentation
    ids = np.array([3])
    assert R.oracle_A(lab, i1, V, ids)[0] == 1.0
    reg, _ = R.oracle_B_regions(lab, i1, V)
    vals = np.unique(reg[i1 == 3]); assert len(vals) == 1 and (reg == vals[0]).sum() == (i1 == 3).sum()
    mixed = lab.copy(); mixed[10:30, 8:14] = 999                    # a region crossing the instance border
    a = R.oracle_A(mixed, i1, V, ids)[0]; asa, ue = R.asa_ue(mixed, i1, V)
    assert a < 1.0 and asa < 1.0 and ue > 0
