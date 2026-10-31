"""Linking benchmark (rules: sv_lr_prereg.json).

L1 controlled fragments: render a tile with known lines (sv_synth drawing), then cut every truth line into fragments:
  occluded cuts where a LATER-drawn line crosses it, plus 1-3 visible gaps (2-16 px, ink still in the image), ends
  shortened 0.5 px, interior jitter 0.3 px. True links = consecutive surviving fragments of one truth line.
  Scenes: shaded red 2/3 px, black 1/3 px, pale 1 px, red 2->5 px, a parallel red pair 5 px apart, two collinear black
  lines with a REAL 10 px ink-free gap (must not link), a line ending 4 px from another line's side (must not link),
  a shallow (25 deg) same-colour crossing (ambiguous), two fill-coloured bands also cut into fragments (distractors).
L2 detector + linker: frozen P1 detector (sv_autoline) on sv_synth tiles, then the linker.
"""
import numpy as np, cv2, shapely
from shapely.geometry import LineString, Point
import sv_synth as S, sv_autoline as AL, sv_autoline_eval as EV, sv_linker as LK

H = W = 256


def _draw(big, pts, col, w, shade=None):
    n = len(pts); ws = np.full(n, w) if np.isscalar(w) else np.asarray(w)
    for k in range(n - 1):
        c = col if shade is None else tuple(int(v) for v in np.clip(np.array(col, float) * shade[k], 0, 255))
        S._poly(big, pts[k:k + 2], c, ws[k])


def _seg(p, d, L, n=40): return np.array([p + d * t for t in np.linspace(0, L, n)])


def scene(seed):
    rng = np.random.default_rng(seed); big = np.zeros((H * S.SS, W * S.SS, 3), np.uint8); big[:] = S.FILLS["pink"]
    for name in ("green", "yellow", "redfill"):
        c = rng.uniform([40, 40], [W - 40, H - 40]); r = rng.uniform(25, 40); ang = np.sort(rng.uniform(0, 2 * np.pi, 9))
        poly = np.stack([c[0] + r * rng.uniform(.6, 1.2, 9) * np.cos(ang), c[1] + r * rng.uniform(.6, 1.2, 9) * np.sin(ang)], 1)
        cv2.fillPoly(big, [np.round(poly * S.SS).astype(np.int32)], S.FILLS[name], cv2.LINE_AA)
    lines, bands = [], []
    for name in ("green", "yellow"):
        w = float(rng.integers(3, 7)); pts = S.curve(rng, 60, H, W); _draw(big, pts, S.FILLS[name], w)
        bands.append({"id": f"band_{name}", "kind": "band", "colour": S.FILLS[name], "width": w, "axis": pts})
    def add(lid, kind, ink, w, pts, shade=None):
        col = S.INK[ink]; _draw(big, pts, col, w, shade); lines.append({"id": lid, "kind": kind, "colour": col, "width": float(np.median(w)), "axis": pts})
    for lid, ink, w in (("red_aa_2", "red", 2.0), ("red_aa_3", "red", 3.0), ("black_1", "black", 1.0), ("black_3", "black", 3.0), ("pale_1", "pale", 1.0)):
        pts = S.curve(rng, 120, H, W); sh = 1 + 0.12 * np.sin(np.linspace(0, rng.uniform(2, 6) * np.pi, 120)) if ink == "red" else None
        add(lid, "line", ink, w, pts, sh)
    pts = S.curve(rng, 120, H, W); add("red_var_2to5", "line", "red", np.linspace(2, 5, 120), pts)
    base = S.curve(rng, 120, H, W, margin=24); off = shapely.offset_curve(LineString(base), 5.0)
    if off.geom_type != "LineString" or off.length < 50: off = LineString(base + [5.0, 0])
    add("par_a", "parallel", "red", 2.0, base); add("par_b", "parallel", "red", 2.0, np.asarray(off.coords))
    p = rng.uniform([50, 50], [W - 50, H - 50]); a = rng.uniform(0, np.pi); d = np.array([np.cos(a), np.sin(a)])
    add("term_a", "true_termination", "black", 2.0, _seg(p - d * 50, d, 45)); add("term_b", "true_termination", "black", 2.0, _seg(p + d * 5, d, 45))
    q = rng.uniform([50, 50], [W - 50, H - 50]); b = rng.uniform(0, np.pi); e = np.array([np.cos(b), np.sin(b)]); nrm = np.array([-e[1], e[0]])
    add("tbar_top", "true_termination", "red", 2.0, _seg(q - e * 40, e, 80)); add("tbar_stem", "true_termination", "red", 2.0, _seg(q + nrm * 46, -nrm, 42))
    c0 = rng.uniform([70, 70], [W - 70, H - 70]); g0 = rng.uniform(0, np.pi)
    for k, s in enumerate((-1, 1)):
        u = np.array([np.cos(g0 + s * np.radians(12.5)), np.sin(g0 + s * np.radians(12.5))])
        add(f"shallow_{k}", "ambiguous_crossing", "black", 2.0, _seg(c0 - u * 60, u, 120))
    img = cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA).astype(np.float64)
    img = np.clip(img + rng.normal(0, 2.0, img.shape), 0, 255).astype(np.uint8)
    ok, enc = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 75])
    img = cv2.cvtColor(cv2.imdecode(enc, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    return img, lines, bands, rng


def cut(img, lines, bands, rng):
    """-> fragments (dicts: geom, rgb, width, line, order) and true link pairs with kind."""
    allx = lines + bands; frags = []; truth_pairs = []
    order = {x["id"]: i for i, x in enumerate(bands + lines)}           # draw order: bands first, then lines in list order
    for x in allx:
        g = LineString(x["axis"]); L = g.length; occ = []
        for y in allx:
            if order[y["id"]] <= order[x["id"]]: continue
            it = shapely.intersection(g, LineString(y["axis"]))
            for pt in shapely.get_parts(it):
                if pt.geom_type != "Point": continue
                s = g.project(pt); h = y["width"] / 2 + 1.5; occ.append((max(0, s - h), min(L, s + h)))
        vis = []
        for _ in range(int(rng.integers(1, 4))):
            ln = float(rng.choice([2, 4, 6, 8, 12, 16])); s = float(rng.uniform(8, max(L - 8 - ln, 9))); vis.append((s, s + ln))
        cuts = sorted([(a, b, "occluded") for a, b in occ] + [(a, b, "visible") for a, b in vis])
        merged = []
        for a, b, k in cuts:
            if merged and a <= merged[-1][1]: merged[-1] = (merged[-1][0], max(b, merged[-1][1]), "occluded" if "occluded" in (k, merged[-1][2]) else "visible")
            else: merged.append((a, b, k))
        keep, s0 = [], 0.0
        for a, b, k in merged: keep.append((s0, a, k)); s0 = b
        keep.append((s0, L, None)); prev = None; ordn = 0
        for (a, b, kind_after), idx in zip(keep, range(len(keep))):
            a2, b2 = a + (0.5 if a > 0 else 0), b - (0.5 if b < L else 0)
            if b2 - a2 < 4.0:
                continue
            seg = shapely.ops.substring(g, a2, b2) if hasattr(shapely, "ops") else None
            from shapely.ops import substring
            seg = substring(g, a2, b2); c = np.asarray(seg.coords, float)
            if len(c) > 2: c[1:-1] += rng.normal(0, 0.3, c[1:-1].shape)
            seg = LineString(c); px = shapely.get_coordinates(shapely.line_interpolate_point(seg, np.linspace(0, seg.length, int(seg.length) + 1)))
            ys = np.clip(px[:, 1].astype(int), 0, H - 1); xs = np.clip(px[:, 0].astype(int), 0, W - 1)
            f = {"geom": seg, "rgb": np.median(img[ys, xs], 0).astype(np.uint8), "width": max(1.0, x["width"] + rng.normal(0, 0.3)),
                 "line": x["id"], "kind": x["kind"], "order": ordn, "s": (a2, b2)}
            if prev is not None:
                gapk = "occluded" if any(o[0] < a2 and o[1] > prev["s"][1] for o in occ) else "visible"
                truth_pairs.append({"a": (prev["idx"], 1), "b": (len(frags), 0), "line": x["id"], "kind": x["kind"], "gap_kind": gapk,
                                    "gap_px": float(a2 - prev["s"][1])})
            f["idx"] = len(frags); frags.append(f); prev = f; ordn += 1
    return frags, truth_pairs


def score_l1(frags, truth_pairs, res):
    T = {(min(p["a"], p["b"]), max(p["a"], p["b"])): p for p in truth_pairs}
    def key(r): return (min(r["a"], r["b"]), max(r["a"], r["b"]))
    out = {"true_pairs": len(T), "predicted": 0, "correct": 0, "wrong": 0, "band_band_links": 0, "uncertain": len(res["uncertain"]),
           "uncertain_on_true_pair": 0, "wrong_by_kind": {}, "correct_by_gap": {}, "true_by_gap": {}, "wrong_links": []}
    for p in T.values():
        k = f"{p['gap_kind']}_{'le8' if p['gap_px'] <= 8.5 else 'gt8'}" if p["kind"] != "band" else "band"; out["true_by_gap"][k] = out["true_by_gap"].get(k, 0) + 1
    for r in res["links"]:
        fa, fb = frags[r["a"][0]], frags[r["b"][0]]
        if fa["kind"] == "band" and fb["kind"] == "band": out["band_band_links"] += 1; continue
        out["predicted"] += 1
        if key(r) in T:
            p = T[key(r)]; out["correct"] += 1; k = f"{p['gap_kind']}_{'le8' if p['gap_px'] <= 8.5 else 'gt8'}"
            out["correct_by_gap"][k] = out["correct_by_gap"].get(k, 0) + 1
        else:
            k = "band_to_line" if "band" in (fa["kind"], fb["kind"]) else ("same_line_nonadjacent" if fa["line"] == fb["line"] else f"{fa['kind']}->{fb['kind']}")
            out["wrong"] += 1; out["wrong_by_kind"][k] = out["wrong_by_kind"].get(k, 0) + 1
            out["wrong_links"].append({"a": fa["line"], "b": fb["line"], "d": round(r["d"], 1), "theta": [round(t) for t in r["theta"]], "status": r["status"]})
    for r in res["uncertain"]:
        if key(r) in T: out["uncertain_on_true_pair"] += 1
    comp = {}
    for li, lg in enumerate(res["logical"]):
        for i in lg["fragments"]: comp[i] = li
    per = {}
    for f in frags:
        if f["kind"] == "band": continue
        per.setdefault(f["line"], set()).add(comp[f["idx"]])
    lines_in = {}
    for f in frags:
        if f["kind"] != "band": lines_in.setdefault(comp[f["idx"]], set()).add(f["line"])
    out["fragments"] = sum(1 for f in frags if f["kind"] != "band"); out["components_per_line"] = {k: len(v) for k, v in per.items()}
    out["impure_components"] = sum(1 for v in lines_in.values() if len(v) >= 2)
    return out


def owners(det, truth, tol=2.0):
    Tb = [LineString(t["axis"]).buffer(tol) for t in truth["lines"]]
    al = np.array([[shapely.length(shapely.intersection(d, b)) for b in Tb] for d in det]); sh = al / np.maximum([[d.length] for d in det], 1e-9)
    own = np.where(sh.max(1) >= 0.6, sh.argmax(1), -1); own[(al >= 10).sum(1) >= 2] = -2
    return own


def run_l2(seed, p=LK.P):
    img, truth, faces = S.generate(seed); L, info = AL.extract(img); frags = [{"geom": l["geom"], "rgb": l["rgb"], "width": l["width"]} for l in L]
    res = LK.link(frags, img, p); own = owners([f["geom"] for f in frags], truth)
    ok = wrong = unk = 0; wrong_l = []
    for r in res["links"]:
        a, b = own[r["a"][0]], own[r["b"][0]]
        if a >= 0 and b >= 0: ok += a == b; wrong += a != b
        else: unk += 1
        if a >= 0 and b >= 0 and a != b: wrong_l.append([truth["lines"][a]["id"], truth["lines"][b]["id"], round(r["d"], 1)])
    before = EV.score(L, truth, img.shape[:2]); after_lines = [{"geom": lg["geom"], "width": lg["width"]} for lg in res["logical"]]
    after = EV.score(after_lines, truth, img.shape[:2])
    return {"fragments": len(frags), "logical": len(res["logical"]), "links": len(res["links"]), "uncertain": len(res["uncertain"]),
            "links_same_owner": int(ok), "links_different_owner": int(wrong), "links_unassignable": int(unk), "wrong_links": wrong_l,
            "before": before, "after": after}
