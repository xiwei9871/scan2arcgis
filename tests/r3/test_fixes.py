import sys
from pathlib import Path
import numpy as np
from shapely import geometry as sg, polygonize_full, snap, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R3"))
from s1v2_semantic import run_config  # noqa: E402


def _P():
    # 3 regions: r0 anchored 'Ohf' (grouped), r1 same colour next to r0, r2 distinct colour
    RF = np.array([[50, 0, 0, 1, 1, 1, 0], [50.5, 0, 0, 1, 1, 1, 0], [80, 20, 20, 1, 1, 1, 0]], float)
    cref = {"Ohf": RF[0], "Ic": RF[0] + [1, 0, 0, 0, 0, 0, 0], "t": RF[2]}
    return dict(nR=3, RF=RF, area=np.array([9000, 300, 500]), adj=[{1}, {0}, set()], anchors=[["Ohf"], [], []],
                codes=["Ic", "Ohf", "t"], cref=cref, grouped={"Ohf", "Ic"}, group_of_code={"Ohf": ["Ic", "Ohf"], "Ic": ["Ic", "Ohf"]})


def test_inherit_off_leaves_same_colour_region_unassigned_and_candidates_listed():
    a, c = run_config(_P(), "off", "off", True, False)
    assert a[0] == "Ohf" and a[1] is None and a[2] == "t"
    assert c == {1: ["Ic", "Ohf"]}


def test_one_hop_inherits_from_anchored_neighbour_only():
    a, _ = run_config(_P(), "off", "one_hop", False, False)
    assert a[1] == "Ohf"


def test_vector_snap_closes_small_gap_before_polygonize():
    sq = [sg.LineString([(0, 0), (10, 0)]), sg.LineString([(10, 0), (10, 10)]),
          sg.LineString([(10, 10), (0, 10)]), sg.LineString([(0, 10), (0, 0.4)])]   # 0.4 m gap
    raw = unary_union(sq)
    assert len(polygonize_full([raw])[0].geoms) == 0
    fixed = unary_union(snap(raw, raw, 0.5))
    assert len(polygonize_full([fixed])[0].geoms) == 1
