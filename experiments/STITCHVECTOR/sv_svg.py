"""Flatten VTracer SVG paths to polygons (pre-registration: cubics sampled 8 points per segment, transforms applied).
VTracer 1.0.0a4 emits only <path d=... fill=...>; commands M/m L/l C/c Z/z (checked before the runs)."""
import re
import numpy as np
from shapely.geometry import Polygon
from shapely.validation import make_valid

PATH_RE = re.compile(r'<path\s+d="([^"]*)"[^>]*?fill="#([0-9A-Fa-f]{6})"[^>]*?(?:transform="([^"]*)")?[^>]*/>')
TOK = re.compile(r"[MmLlCcZz]|-?\d*\.?\d+(?:[eE][-+]?\d+)?")
NSEG = 8


def _cubic(p0, p1, p2, p3, n=NSEG):
    t = np.linspace(0, 1, n + 1)[1:, None]
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def parse_d(d):
    """Return list of rings (each an (N,2) array) from one path d string."""
    toks = TOK.findall(d); i = 0; cur = np.zeros(2); start = np.zeros(2); rings = []; ring = []; cmd = None
    def num():
        nonlocal i; v = float(toks[i]); i += 1; return v
    while i < len(toks):
        if toks[i].isalpha(): cmd = toks[i]; i += 1
        if cmd in "Zz":
            if ring: rings.append(np.array(ring)); ring = []
            cur = start.copy(); cmd = None; continue
        if cmd in "Mm":
            p = np.array([num(), num()]); cur = cur + p if cmd == "m" else p
            if ring: rings.append(np.array(ring))
            ring = [cur.copy()]; start = cur.copy(); cmd = "l" if cmd == "m" else "L"
        elif cmd in "Ll":
            p = np.array([num(), num()]); cur = cur + p if cmd == "l" else p; ring.append(cur.copy())
        elif cmd in "Cc":
            c = np.array([num(), num(), num(), num(), num(), num()]).reshape(3, 2)
            if cmd == "c": c = c + cur
            pts = _cubic(cur, c[0], c[1], c[2]); ring.extend(list(pts)); cur = c[2].copy()
        else:
            raise ValueError(f"unsupported SVG command {cmd!r}")
    if ring: rings.append(np.array(ring))
    return [r for r in rings if len(r) >= 3]


def _transform(rings, tr):
    if not tr: return rings
    m = re.match(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", tr)
    if not m: raise ValueError(f"unsupported transform {tr!r}")
    off = np.array([float(m.group(1)), float(m.group(2))]); return [r + off for r in rings]


def svg_features(svg):
    """-> list of (geometry, rgb_key, z) in paint order (z = document order)."""
    out = []
    for z, (d, hexc, tr) in enumerate(PATH_RE.findall(svg)):
        rings = _transform(parse_d(d), tr)
        if not rings: continue
        g = Polygon(rings[0], rings[1:])
        if not g.is_valid: g = make_valid(g)
        if g.is_empty: continue
        out.append((g, int(hexc, 16), z))
    return out


def n_svg_paths(svg):
    return len(PATH_RE.findall(svg))
