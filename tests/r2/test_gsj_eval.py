import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R2_real_map"))
from gsj_frame import fit_geo  # noqa: E402
from gsj_run_r1 import evaluate  # noqa: E402


def test_fit_geo_maps_bounds_to_corners():
    corners = {"tl": [100.0, 50.0], "tr": [900.0, 52.0], "br": [902.0, 600.0], "bl": [98.0, 598.0]}
    b = (138.0, 36.0, 138.25, 36.1667)
    H = fit_geo(corners, b)
    for (lon, lat), k in [((b[0], b[3]), "tl"), ((b[2], b[3]), "tr"), ((b[2], b[1]), "br"), ((b[0], b[1]), "bl")]:
        p = H @ np.array([lon, lat, 1.0]); p = p[:2] / p[2]
        assert np.allclose(p, corners[k], atol=0.05)  # lon/lat ~138 deg conditions the DLT; 0.05 px is far below 200 dpi resolution


def test_evaluate_is_label_permutation_invariant():
    gt = np.zeros((40, 40), np.int32); gt[:, 20:] = 1; gt[30:, :10] = 2
    pred = np.select([gt == 0, gt == 1, gt == 2], [7, 3, 5]).astype(np.int32)
    units = [{"major_code": str(i), "legend": {"LEGEND01": f"u{i}"}} for i in range(3)]
    ev = evaluate(pred, gt, np.ones_like(gt, bool), units, tol=1.5)
    assert ev["pixel_acc_matched"] == 1.0 and ev["miou_matched_all_units"] == 1.0
    assert ev["components"]["ratio"] == 1.0


def test_evaluate_counts_merged_units_as_errors():
    gt = np.zeros((40, 40), np.int32); gt[:, 20:] = 1
    pred = np.zeros_like(gt)  # two units merged into one class
    units = [{"major_code": str(i), "legend": {"LEGEND01": f"u{i}"}} for i in range(2)]
    ev = evaluate(pred, gt, np.ones_like(gt, bool), units, tol=1.5)
    assert ev["n_units_matched"] == 1 and abs(ev["pixel_acc_matched"] - 0.5) < 1e-9
