import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4B0"))
import r4b0_common as C  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402


def _sheet(strip_w=8):
    u = np.zeros((200, 260), np.int32); u[:, 130:] = 1; u[:, :60] = 3; u[20:180, 60:60 + strip_w] = 2
    inst = np.full(u.shape, -1, np.int32); k0 = 0
    for j in np.unique(u):
        n, cc = cv2.connectedComponents((u == j).astype(np.uint8), connectivity=4); inst[cc > 0] = cc[cc > 0] - 1 + k0; k0 += n - 1
    b = np.zeros(u.shape, bool)
    h = u[:, 1:] != u[:, :-1]; b[:, 1:] |= h; b[:, :-1] |= h; v = u[1:] != u[:-1]; b[1:] |= v; b[:-1] |= v
    dist = cv2.distanceTransform((~b).astype(np.uint8), cv2.DIST_L2, 3)
    valid = np.ones(u.shape, bool); inst1 = inst + 1; n = int(inst1.max()); area = np.bincount(inst1.ravel(), minlength=n + 1)
    S = {"code": "synth", "R": {"instance": inst}, "valid": valid, "inst1": inst1, "n": n, "area": area, "objects": ndi.find_objects(inst1),
         "ub": b, "dist": dist.astype(np.float32)}
    S["small"] = np.flatnonzero((area >= 200) & (area < 20000)); S["small"] = S["small"][S["small"] > 0]
    md = np.zeros(n + 1, np.float32); np.maximum.at(md, inst1.ravel(), dist.ravel()); S["off_maxdist"] = md; S["w_old"] = 2 * md + 1
    S["w_own"] = np.full(n + 1, np.nan); S["elong"] = np.full(n + 1, np.nan)
    for k in S["small"]:
        m = np.pad((inst1[S["objects"][k - 1]] == k).astype(np.uint8), 1); e = cv2.distanceTransform(m, cv2.DIST_L2, 5).max()
        S["w_own"][k] = 2 * (e - 0.5)
        from skimage.morphology import skeletonize
        S["elong"][k] = skeletonize(m > 0).sum() / S["w_own"][k]
    return S, b


def test_own_width_and_ideal_seed():
    S, b = _sheet(8)
    k = int(S["inst1"][100, 63]); assert k in S["small"] and abs(S["w_own"][k] - 8) <= 1.0
    mk = C.ideal_markers(S); assert all((mk == j).sum() == 1 for j in range(1, S["n"] + 1))


def test_perfect_boundary_ideal_seeds_recovers_strip():
    S, b = _sheet(8)
    prob = b.astype(np.float32)
    M = C.run_method("O_GTD_ideal", S, {"prob1": prob, "prob2": prob, "dist2": S["dist"]})
    rows, extra = C.analyze(S, {**M, "prob": prob})
    r = next(x for x in rows if x["instance"] == int(S["inst1"][100, 63]) - 1)
    assert all(x["success"] for x in rows) and r["primary_failure_stage"] == "SUCCESS"
    assert r["success"] and rows[0]["primary_failure_stage"] == "SUCCESS" and extra["regions_credited_to_more_than_one_instance"] == 0


def test_missing_boundary_is_labelled_boundary_miss():
    S, b = _sheet(8)
    prob = b.astype(np.float32); prob[:, 55:72] = 0                    # strip boundaries erased
    P = {"prob1": prob, "prob2": prob, "dist2": C.derived_distance(prob)}
    M = C.run_method("M1_DD_hybrid", S, P); rows, _ = C.analyze(S, M)
    r = next(x for x in rows if x["instance"] == int(S["inst1"][100, 63]) - 1)
    assert not r["success"] and "BOUNDARY_MISS" in r["labels"] and r["primary_failure_stage"] == "BOUNDARY_MISS"
    assert r["two_sided_identifiable"] and r["both_sides_detected"] is False
