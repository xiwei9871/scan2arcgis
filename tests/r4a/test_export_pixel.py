import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4A"))
from export_pixel_vectors import polygons, regions_from_labels  # noqa: E402


def test_pixel_convention_y_negative_and_scale():
    lab = np.zeros((4, 6), np.int32); lab[:, 3:] = 1
    reg, cls = regions_from_labels(lab, np.ones_like(lab, bool))
    geoms, _ = polygons(reg, 0.5)                      # work scale 0.5 -> original px = 2x
    left = geoms[[r for r in geoms if cls[r] == 0][0]]
    assert left.bounds == (0.0, -8.0, 6.0, 0.0)        # X=col*2, Y=-row*2, origin top-left corner
    assert sum(g.area for g in geoms.values()) == 4 * 6 * 4
