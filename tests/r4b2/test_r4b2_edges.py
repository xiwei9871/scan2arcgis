import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4B2"))
import r4b2_edges as E  # noqa: E402


def _cc_ref(unit, valid):
    ref = np.zeros(unit.shape, np.int64); k0 = 0
    for u in np.unique(unit[valid]):
        n, cc = cv2.connectedComponents(((unit == u) & valid).astype(np.uint8), connectivity=4)
        ref[cc > 0] = cc[cc > 0] + k0; k0 += n - 1
    return ref, k0


def _same_partition(a, b, m):
    p = np.unique(np.stack([a[m], b[m]], 1), axis=0)
    return len(p) == len(np.unique(a[m])) == len(np.unique(b[m]))


def _check(unit, valid=None):
    valid = np.ones(unit.shape, bool) if valid is None else valid
    er, ed, mr, md = E.edges_from_labels(unit, valid)
    lab = E.components(er, ed, valid); ref, k = _cc_ref(unit, valid)
    assert _same_partition(lab, ref, valid) and len(np.unique(lab[valid])) == k


def test_thin_strip_pinch_bend_checkerboard_and_invalid():
    u = np.zeros((60, 80), np.int32); u[:, 40:] = 1; u[:, 20:23] = 2          # 3 px strip
    _check(u)
    u = np.zeros((60, 80), np.int32); u[10:50, 30] = 2; u[30:50, 31] = 2     # 1-2 px tapering (pinch-out)
    _check(u)
    u = np.zeros((60, 60), np.int32); cv2.ellipse(u, (30, 30), (20, 20), 0, 0, 270, 3, 2)   # bent thin unit
    _check(u)
    u = np.zeros((8, 8), np.int32); u[3, 3] = u[4, 4] = 1                    # checkerboard: diagonal only -> 2 regions
    _check(u)
    er, ed, _, _ = E.edges_from_labels(u, np.ones(u.shape, bool))
    lab = E.components(er, ed); assert lab[3, 3] != lab[4, 4]
    u = np.zeros((40, 40), np.int32); u[:, 20:] = 1; u[:, 10:12] = -1      # unlabelled band splits unit 0
    _check(u, u >= 0)


def test_single_pixel_connection_is_one_region():
    u = np.zeros((30, 30), np.int32); u[:, 14:16] = 1; u[10, 14:16] = 0     # unit 0 left/right joined through 1 row
    _check(u)


def test_missing_edge_merges_and_cleanup_merges_small():
    u = np.zeros((40, 40), np.int32); u[:, 20:] = 1
    er, ed, _, _ = E.edges_from_labels(u, np.ones(u.shape, bool))
    pr, pd = er.astype(np.float32), ed.astype(np.float32); pr[5, 19] = 0      # one missing pair
    lab, _ = E.regions_from_probs(pr, pd); assert lab.max() == 1           # whole map merges: sensitivity
    u2 = np.zeros((40, 40), np.int32); u2[5:9, 5:9] = 1                     # 16 px region < 50
    er, ed, _, _ = E.edges_from_labels(u2, np.ones(u2.shape, bool))
    lab, merged = E.regions_from_probs(er.astype(np.float32), ed.astype(np.float32)); assert lab.max() == 1 and merged == 1


def test_edge_metrics_strict_and_tolerance():
    u = np.zeros((20, 20), np.int32); u[:, 10:] = 1
    er, ed, mr, md = E.edges_from_labels(u, np.ones(u.shape, bool))
    m = E.edge_metrics(er.astype(np.float32), ed.astype(np.float32), er, ed, mr, md); assert m["strict"]["F1"] == 1.0
    sh = np.roll(er, 1, 1).astype(np.float32)                               # shifted by one pair
    m = E.edge_metrics(sh, ed.astype(np.float32), er, ed, mr, md); assert m["strict"]["F1"] == 0.0 and m["tol1"]["F1"] == 1.0
