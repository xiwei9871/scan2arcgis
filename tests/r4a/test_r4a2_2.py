import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4A"))
import r4a2_2_eval as E  # noqa: E402


def _ref(unit):
    inst = np.full(unit.shape, -1, np.int32); k0 = 0
    for j in np.unique(unit):
        n, cc = cv2.connectedComponents((unit == j).astype(np.uint8), connectivity=4)
        inst[cc > 0] = cc[cc > 0] - 1 + k0; k0 += n - 1
    ub = E.both_side_boundary(unit, np.ones(unit.shape, bool))
    z = np.zeros(unit.shape, np.uint8)
    return {"instance": inst, "unit": unit, "unit_boundary": ub.astype(np.uint8), "printed_contact": z, "low_ink_boundary": z,
            "neg_candidate": z, "ignore": z, "valid": np.ones(unit.shape, bool),
            "dist": cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)}


def _map():
    u = np.zeros((300, 300), np.int32); u[:, 150:] = 1; u[100:130, 40:110] = 2   # small 30x70 = 2100 px unit
    return u


def test_perfect_prediction_scores_one():
    R = _ref(_map()); inst, _ = E.instance_metrics(R["instance"] + 1, R)
    assert inst["small"]["n"] == 1 and inst["small"]["recall_iou50"] == 1.0 and inst["large"]["recall_iou50"] == 1.0
    assert inst["oracle_majority_unit_miou"] == 1.0
    assert E.boundary_metrics(R["instance"] + 1, R)["tol1"]["F1"] == 1.0


def test_absorbed_small_unit_is_flagged():
    R = _ref(_map()); pred = np.where(R["unit"] == 1, 2, 1)       # small unit merged into its large neighbour
    inst, _ = E.instance_metrics(pred, R)
    assert inst["small"]["recall_iou50"] == 0.0 and inst["small"]["absorbed_by_larger_neighbour"] == 1.0
    assert inst["small"]["under_seg"] == 1.0


def test_over_segmentation_is_flagged():
    R = _ref(_map()); pred = R["instance"] + 1
    pred = np.where((R["unit"] == 2) & (np.arange(300)[None, :] >= 64), pred.max() + 1, pred)
    pred = np.where((R["unit"] == 2) & (np.arange(300)[None, :] >= 87), pred.max() + 1, pred)
    inst, _ = E.instance_metrics(pred, R)
    assert inst["small"]["over_seg"] == 1.0 and inst["small"]["recall_iou50"] == 0.0


def test_infer_tile_starts_cover_image():
    import importlib.util
    if importlib.util.find_spec("torch") is None: return              # .venv has no torch; covered in .venv-ml
    import r4a2_2_infer as I
    for n in (512, 700, 2911, 3550):
        s = I._starts(n); assert s[0] == 0 and s[-1] + 512 == n and all(b - a <= 384 for a, b in zip(s, s[1:]))
