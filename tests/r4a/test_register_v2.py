import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4A"))
from gsj_register_v2 import nominal_px, peaks  # noqa: E402


def test_nominal_size_of_standard_sheet_at_200dpi():
    # 1/6 deg latitude at 1:50,000 is ~370 mm -> ~2917 px at 200 dpi, independent of latitude
    w, h = nominal_px([138.75, 36.3333, 139.0, 36.5])
    assert abs(h - 2916.7) < 1.0
    assert 3300 < w < 3360          # 0.25 deg longitude at ~36.4 N


def test_peaks_groups_adjacent_indices():
    p = np.zeros(100); p[10:13] = [5, 9, 6]; p[50] = 8
    assert peaks(p, 4) == [11, 50]
