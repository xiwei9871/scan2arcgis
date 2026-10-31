import sys
from pathlib import Path
import numpy as np, cv2, shapely
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments/STITCHVECTOR"))
import sv_synth as S, sv_autoline as AL, sv_v3 as V  # noqa: E402


def test_inf_colour_threshold_reproduces_2_0():
    img, _, _ = S.generate(1001); L2, _ = AL.extract(img); L3, _ = V.extract_v3(img, AL.P, float("inf"))
    assert len(L2) == len(L3) and all(shapely.equals_exact(a["geom"], b["geom"], 1e-9) for a, b in zip(L2, L3))


def test_red_and_black_crossing_not_chained():
    a = np.full((120, 200, 3), (255, 222, 236), np.uint8)
    cv2.line(a, (5, 30), (195, 90), (45, 40, 45), 2, cv2.LINE_AA); cv2.line(a, (5, 90), (195, 30), (170, 74, 80), 2, cv2.LINE_AA)
    L3, _ = V.extract_v3(a)
    red, black = shapely.LineString([(5, 90), (195, 30)]).buffer(2), shapely.LineString([(5, 30), (195, 90)]).buffer(2)
    assert not any(shapely.length(shapely.intersection(o["geom"], red.difference(black))) >= 10 and
                   shapely.length(shapely.intersection(o["geom"], black.difference(red))) >= 10 for o in L3)


def test_same_ink_as_2_0():
    for s in (1001, 1003):
        img, _, _ = S.generate(s); L2, _ = AL.extract(img); L3, _ = V.extract_v3(img)
        u2, u3 = shapely.union_all([o["geom"] for o in L2]), shapely.union_all([o["geom"] for o in L3])
        assert shapely.hausdorff_distance(u2, u3) <= 1.5


def test_grouping_keeps_geometry():
    img, _, _ = S.generate(1002); objs, lg, r, _ = V.run(img)
    parts = sorted(i for g in lg for i in g["parts"]); assert parts == list(range(len(objs)))
    assert abs(sum(g["geom"].length for g in lg) - sum(o["geom"].length for o in objs)) < 1e-6
