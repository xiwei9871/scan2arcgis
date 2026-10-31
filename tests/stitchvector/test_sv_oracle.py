import sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments/STITCHVECTOR"))
import sv_oracle as O  # noqa: E402
import sv_d71 as D  # noqa: E402

P = dict(O.P)


def _img():
    a = np.full((120, 160, 3), (255, 222, 236), np.uint8); a[:, 110:] = (211, 229, 161)
    cv2.line(a, (5, 100), (150, 20), (200, 60, 60), 2, cv2.LINE_AA)                  # anti-aliased red line across both
    cv2.line(a, (20, 10), (60, 60), (150, 200, 120), 3)                             # green narrow strip (to protect)
    return a


def test_trace_follows_line_and_faces_reconnect():
    a = _img(); ora = {"lines": [{"id": "R", "kind": "red", "waypoints": [[5, 100], [80, 59], [150, 20]]}],
                       "protected": [{"id": "N", "axis": [[20, 10], [60, 60]], "radius": 2.5}]}
    lines, con = O.build_lines(a, ora, P, 1.0)
    from PIL import Image
    q = Image.fromarray(a).quantize(colors=8, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    lab = np.asarray(q).astype(np.int32)
    g = lines[0]["geom"]; assert len(g.coords) <= 8 and 1.0 <= lines[0]["width"] <= 4.0
    prot = O.protect_mask(ora, lab.shape); core, rem = O.footprints(lines, lab.shape, P, prot)
    F = D.fill(lab, rem); fb, fo = O.faces(lab, 0), O.faces(F, 0)
    assert len(fo["polys"]) < len(fb["polys"]) and all(fo["topology"].values())
    assert (F[prot] == lab[prot]).all() and not (rem & prot).any()
    assert lines[0]["rgb"][0] > lines[0]["rgb"][1] + 60                              # red measured from the original


def test_fixed_trace_is_used_verbatim():
    a = _img(); ora = {"lines": [{"id": "S", "kind": "x", "traced": [[0.5, 5.5], [100.5, 5.5]]}]}
    lines, _ = O.build_lines(a, ora, P, 1.0)
    assert list(lines[0]["geom"].coords) == [(0.5, 5.5), (100.5, 5.5)]


def test_width_estimate_tracks_drawn_width():
    est = []
    for w in (1, 2, 3, 5):
        a = np.full((120, 200, 3), (255, 222, 236), np.uint8); cv2.line(a, (10, 60), (190, 40), (200, 60, 60), w)
        L, _ = O.build_lines(a, {"lines": [{"id": "x", "kind": "k", "waypoints": [[10, 60], [100, 50], [190, 40]]}]}, P, 1.0)
        est.append(L[0]["width"])
    assert all(b > a for a, b in zip(est, est[1:])) and est[-1] >= 4.0
