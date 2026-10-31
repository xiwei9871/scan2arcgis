"""Counterexample scenes for the B2c luminance check (rules: sv_b2c_prereg.json). 256x256, drawn at 4x with
anti-aliasing, reduced with INTER_AREA, Gaussian noise sigma 2, JPEG q75 (4:2:0), same as sv_synth.
Truth: ink lines (with sub-type), fill edges (no ink), fill-coloured bands. Geometry jitter comes from the seed."""
import numpy as np, cv2
import sv_synth as S

H = W = 256
KINDS = ["dark_ink_on_light", "pale_ink_on_light", "pale_ink_on_dark_fill", "ink_on_boundary", "edge_only",
         "bands", "ink_crosses_band", "ink_mix_colour"]


def _line(p, d, L, n=60): return np.array([p + d * t for t in np.linspace(0, L, n)])


def _half_plane(big, c, d, col):
    """fill the side of the line through c with direction d that lies at +normal"""
    nrm = np.array([-d[1], d[0]]); far = 2000
    poly = np.array([c - d * far, c + d * far, c + d * far + nrm * far, c - d * far + nrm * far])
    cv2.fillPoly(big, [np.round(poly * S.SS).astype(np.int32)], col, cv2.LINE_AA)


def _finish(big, rng):
    img = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA).astype(np.float64)
    img = np.clip(img + rng.normal(0, 2.0, img.shape), 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 75])
    return cv2.cvtColor(cv2.imdecode(enc, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)


def scene(kind, seed):
    rng = np.random.default_rng(seed * 100 + KINDS.index(kind)); big = np.zeros((H * S.SS, W * S.SS, 3), np.uint8); big[:] = S.FILLS["pink"]
    t = {"kind": kind, "ink": [], "edges": [], "bands": []}
    tilt = lambda: np.radians(rng.uniform(-12, 12))
    def ink(lid, sub, pts, col, w):
        S._poly(big, pts, col, w); t["ink"].append({"id": lid, "sub": sub, "axis": pts.tolist(), "width": w})
    def vdir(a): return np.array([np.sin(a), np.cos(a)])
    def hdir(a): return np.array([np.cos(a), np.sin(a)])
    if kind == "dark_ink_on_light":
        ink("black_1", "dark", _line(np.array([60, 20.]), vdir(tilt()), 215), S.INK["black"], 1.0)
        ink("red_2", "dark", _line(np.array([180, 20.]), vdir(tilt()), 215), S.INK["red"], 2.0)
    elif kind == "pale_ink_on_light":
        ink("pale_a", "pale_darker", _line(np.array([70, 20.]), vdir(tilt()), 215), S.INK["pale"], 1.0)
        ink("pale_b", "pale_darker", _line(np.array([20, 190.]), hdir(tilt()), 215), S.INK["pale"], 1.0)
    elif kind == "pale_ink_on_dark_fill":
        a = tilt(); d = vdir(a); c = np.array([128, 128.])
        _half_plane(big, c, d, S.FILLS["redfill"])                                    # red fill on one side of the boundary
        t["edges"].append({"id": "red_pink_edge_under_ink", "axis": _line(c - d * 120, d, 240).tolist(), "covered_by_ink": True})
        inside = c + np.array([-d[1], d[0]]) * 45 * (1 if np.array([-d[1], d[0]]) @ np.array([1, 0]) > 0 else 1)
        ink("pale_on_red", "pale_brighter_than_both_sides", _line(inside - d * 100, d, 200), S.INK["pale"], 1.0)
        ink("pale_on_red_pink_edge", "pale_brighter_than_one_side", _line(c - d * 105, d, 210), S.INK["pale"], 1.0)
    elif kind in ("ink_on_boundary", "edge_only"):
        a = tilt(); d = vdir(a); c = np.array([128, 128.])
        _half_plane(big, c, -d, S.FILLS["green"])                                     # green on one side, pink on the other
        t["edges"].append({"id": "green_pink_edge", "axis": _line(c - d * 120, d, 240).tolist(), "covered_by_ink": kind == "ink_on_boundary"})
        b = hdir(tilt()); c2 = np.array([128, 200.]); yel = big.copy(); _half_plane(yel, c2, b, S.FILLS["yellow"])
        m = np.zeros(big.shape[:2], np.uint8); poly = np.array([c - d * 2000, c + d * 2000, c + d * 2000 + np.array([d[1], -d[0]]) * 2000, c - d * 2000 + np.array([d[1], -d[0]]) * 2000])
        cv2.fillPoly(m, [np.round(poly * S.SS).astype(np.int32)], 1); big[m > 0] = yel[m > 0]  # yellow region only on the pink side
        t["edges"].append({"id": "yellow_pink_edge", "axis": _line(c2 - b * 120, b, 240).tolist(), "covered_by_ink": kind == "ink_on_boundary"})
        if kind == "ink_on_boundary":
            ink("red_on_green_pink_edge", "boundary_dark", _line(c - d * 105, d, 210), S.INK["red"], 2.0)
            ink("pale_on_yellow_pink_edge", "boundary_pale", _line(c2 - b * 120, b, 240), S.INK["pale"], 1.0)
    elif kind in ("bands", "ink_crosses_band"):
        for i, (name, w, x) in enumerate((("yellow", 3.0, 60), ("green", 6.0, 120), ("yellow", 6.0, 180), ("green", 3.0, 225))):
            pts = _line(np.array([x, 10.]), vdir(tilt() / 2), 236); S._poly(big, pts, S.FILLS[name], w)
            t["bands"].append({"id": f"band_{name}_{int(w)}", "axis": pts.tolist(), "width": w})
        if kind == "ink_crosses_band":
            ink("red_cross", "dark", _line(np.array([10, 80.]), hdir(tilt()), 236), S.INK["red"], 2.0)
            ink("pale_cross", "pale_darker", _line(np.array([10, 170.]), hdir(tilt()), 236), S.INK["pale"], 1.0)
    elif kind == "ink_mix_colour":
        a = tilt(); d = vdir(a); c = np.array([128, 128.]); _half_plane(big, c, d, S.FILLS["redfill"])
        mix = tuple(int(v) for v in (np.array(S.FILLS["redfill"], float) + np.array(S.FILLS["pink"], float)) / 2)
        t["edges"].append({"id": "red_pink_edge_under_ink", "axis": _line(c - d * 120, d, 240).tolist(), "covered_by_ink": True})
        ink("mix_on_red_pink_edge", "mix_colour_on_boundary", _line(c - d * 105, d, 210), mix, 2.0)
    return _finish(big, rng), t
