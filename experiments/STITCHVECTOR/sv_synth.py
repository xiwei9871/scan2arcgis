"""Synthetic map tiles with exact geometric truth for the automatic line test (rules: sv_autoline_prereg.json).

Each tile: flat colour faces (pink background, green, yellow, red fill), then narrow colour bands (fill colours, 3-6 px,
must be protected), then lines: anti-aliased red ink with colour shading along the line, black 1/3/5 px, one line whose
width grows 2->5 px, one pale line, one red line that starts inside the red fill. Drawn at 4x and reduced (INTER_AREA,
anti-aliasing), small noise, JPEG quality 75. Colours are read from u2 (fills) and the u2 red faults."""
import numpy as np, cv2

SS = 4
FILLS = {"pink": (255, 222, 236), "green": (211, 229, 161), "yellow": (250, 214, 120), "redfill": (216, 82, 65)}
INK = {"red": (170, 74, 80), "black": (45, 40, 45), "pale": (232, 180, 165)}


def curve(rng, n, H, W, margin=12):
    P = rng.uniform([margin, margin], [W - margin, H - margin], (4, 2)); t = np.linspace(0, 1, n)[:, None]
    return ((1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t ** 2 * P[2] + t ** 3 * P[3])


def _poly(img, pts, col, w):
    cv2.polylines(img, [np.round(pts * SS * 16).astype(np.int32)], False, col, max(1, int(round(w * SS))), cv2.LINE_AA, shift=4)


def generate(seed, H=256, W=256, jpeg=75, noise=2.0):
    rng = np.random.default_rng(seed); big = np.zeros((H * SS, W * SS, 3), np.uint8); big[:] = FILLS["pink"]
    faces = {}
    for name in ("green", "yellow", "redfill"):
        c = rng.uniform([40, 40], [W - 40, H - 40]); r = rng.uniform(28, 48)
        ang = np.sort(rng.uniform(0, 2 * np.pi, 9)); rad = r * rng.uniform(0.6, 1.2, 9)
        poly = np.stack([c[0] + rad * np.cos(ang), c[1] + rad * np.sin(ang)], 1); faces[name] = poly
        cv2.fillPoly(big, [np.round(poly * SS).astype(np.int32)], FILLS[name], cv2.LINE_AA)
    truth = {"lines": [], "bands": [], "faces": {k: v.tolist() for k, v in faces.items()}}
    for i, (name, w) in enumerate((("green", float(rng.integers(3, 7))), ("yellow", float(rng.integers(3, 7))))):
        pts = curve(rng, 60, H, W); _poly(big, pts, FILLS[name], w)
        truth["bands"].append({"id": f"band_{name}", "colour": FILLS[name], "width": w, "axis": pts.tolist()})
    specs = [("red_aa_2", "red", 2.0), ("red_aa_3", "red", 3.0), ("black_1", "black", 1.0), ("black_3", "black", 3.0),
             ("black_5", "black", 5.0), ("pale_1", "pale", 1.0), ("red_var_2to5", "red", None)]
    for lid, ink, w in specs:
        pts = curve(rng, 120, H, W); base = np.array(INK[ink], float); n = len(pts)
        shade = 1 + 0.12 * np.sin(np.linspace(0, rng.uniform(2, 6) * np.pi, n)) if ink == "red" else np.ones(n)
        widths = np.linspace(2.0, 5.0, n) if w is None else np.full(n, w)
        for k in range(n - 1):
            col = tuple(int(v) for v in np.clip(base * shade[k], 0, 255)); _poly(big, pts[k:k + 2], col, widths[k])
        truth["lines"].append({"id": lid, "ink": ink, "colour": INK[ink], "width": widths.tolist(), "axis": pts.tolist()})
    fc = faces["redfill"].mean(0); ang = rng.uniform(0, 2 * np.pi); d = np.array([np.cos(ang), np.sin(ang)])
    pts = np.array([fc + d * s for s in np.linspace(0, 90, 60)]); pts = np.clip(pts, 6, [W - 6, H - 6])
    _poly(big, pts, INK["red"], 2.0)
    truth["lines"].append({"id": "red_touch_fill", "ink": "red", "colour": INK["red"], "width": [2.0] * len(pts), "axis": pts.tolist(),
                           "note": "starts inside the red fill and is drawn on top of it (visible everywhere; inside the fill only by its darker colour)"})
    img = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA).astype(np.float64)
    img = np.clip(img + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, jpeg])
    img = cv2.cvtColor(cv2.imdecode(enc, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    return img, truth, faces
