import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments/STITCHVECTOR"))
import sv_d71 as D  # noqa: E402

PAL = np.zeros((32, 3), np.uint8)
PAL[0] = (255, 222, 236)   # pink fill
PAL[1] = (210, 40, 40)     # red ink
PAL[2] = (150, 200, 120)   # green fill
PAL[3] = (250, 200, 60)    # yellow fill
PAL[4] = (30, 30, 30)      # black ink


def _scene():
    lab = np.zeros((120, 160), np.int32)
    lab[:, 100:] = 3                                   # yellow right part
    lab[60, 5:95] = 1; lab[61, 5:95] = 1               # 2 px red overlay line inside pink -> cuts pink in two
    lab[10:100, 120:122] = 2                           # 2 px green band inside yellow, other colour on both sides
    lab[20:50, 30:60] = 4; lab[50:58, 44:46] = 4       # black wide block with an attached 2 px tail
    return lab


def test_overlay_line_is_L_and_face_reconnects():
    lab = _scene(); r = D.run_one(lab, PAL, D.P0)
    assert (r["pix"][60:62, 10:90] == 1).all()
    ch = D.face_change(lab, r["F"], r["Lm"])
    assert ch["faces_after"] < ch["faces_before"]
    assert (r["F"][~r["Lm"]] == lab[~r["Lm"]]).all()


def test_attached_tail_is_protected():
    lab = _scene(); r = D.run_one(lab, PAL, D.P0)
    tail = r["pix"][50:58, 44:46]
    assert not np.isin(tail, (1, 4)).any()


def test_band_in_fill_colour_is_P_even_with_same_sides():
    lab = _scene(); lab[100:120, 0:40] = 2               # green also fills a wide region elsewhere
    r = D.run_one(lab, PAL, D.P0)
    assert (r["pix"][15:95, 120:122] == 2).all()


def test_band_in_ink_only_colour_with_same_sides_is_L():
    lab = _scene(); r = D.run_one(lab, PAL, D.P0)    # green appears only as the band
    assert (r["pix"][15:95, 120:122] == 1).all()


def test_composite_restores_original_labels():
    lab = _scene(); r = D.run_one(lab, PAL, D.P0)
    comp = np.where(r["Lm"], lab, r["F"])
    assert (comp == lab).all()


def test_short_blob_is_not_L():
    lab = np.zeros((60, 60), np.int32); lab[30:32, 30:34] = 1
    r = D.run_one(lab, PAL, D.P0)
    assert not r["Lm"].any()


def test_opening_is_subset_of_each_colour():
    lab = _scene(); K, _, _ = D.colour_classes(lab, PAL, 10.0); thin, wide = D.candidates(K, 4)
    assert not (thin & wide).any() and ((thin | wide) == np.ones(K.shape, bool)).all()
    assert not wide[60:62, 10:90].any()


def test_ink_with_some_wide_px_is_not_fill_colour():
    lab = np.zeros((120, 160), np.int32); lab[:, 100:] = 3
    lab[60:62, 5:155] = 4; lab[20:22, 5:155] = 4; lab[56:66, 40:50] = 4     # 2 long black lines + one 10x10 crossing blob
    r = D.run_one(lab, PAL, D.P0)
    assert not r["ft"]["fill_colour"][r["U"][60, 120]]
    assert (r["pix"][20:22, 110:150] == 1).all()
