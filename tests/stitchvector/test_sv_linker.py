import sys
from pathlib import Path
import numpy as np, cv2
from shapely.geometry import LineString
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments/STITCHVECTOR"))
import sv_linker as LK  # noqa: E402

RED = (170, 74, 80)


def _img(draw):
    a = np.full((80, 160, 3), (255, 222, 236), np.uint8); draw(a); return a


def _f(c): return {"geom": LineString(c), "rgb": np.array(RED, np.uint8), "width": 2.0}


def test_gap_with_ink_is_linked():
    a = _img(lambda a: cv2.line(a, (5, 40), (155, 40), RED, 2))
    r = LK.link([_f([(5.5, 40.5), (70.5, 40.5)]), _f([(78.5, 40.5), (150.5, 40.5)])], a)
    assert len(r["links"]) == 1 and len(r["logical"]) == 1


def test_real_gap_without_ink_is_not_linked():
    def d(a): cv2.line(a, (5, 40), (70, 40), RED, 2); cv2.line(a, (82, 40), (155, 40), RED, 2)
    r = LK.link([_f([(5.5, 40.5), (70.5, 40.5)]), _f([(82.5, 40.5), (150.5, 40.5)])], _img(d))
    assert len(r["links"]) == 0 and len(r["logical"]) == 2


def test_t_junction_is_not_linked():
    def d(a): cv2.line(a, (5, 20), (155, 20), RED, 2); cv2.line(a, (80, 24), (80, 75), RED, 2)
    r = LK.link([_f([(5.5, 20.5), (78.5, 20.5)]), _f([(82.5, 20.5), (150.5, 20.5)]), _f([(80.5, 24.5), (80.5, 75.5)])], _img(d))
    pairs = {tuple(sorted((x["a"][0], x["b"][0]))) for x in r["links"]}
    assert (0, 2) not in pairs and (1, 2) not in pairs
