"""Editor V0.1 scenario checks (DATA_LEVEL_VERIFIED: drives tools/stitchvector_editor/core.Document, the same code the UI calls).
Truth / Oracle geometry is used only to place user-like clicks and to score afterwards, never inside an editor command.
Usage: sv_editor_uat.py <inputs_dir> <out_dir> <json_out>   (.venv-sv)"""
import json, sys, shutil
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString, Polygon, Point
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2])); sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.stitchvector_editor.core import Document, EditError, FACE, LINE, sha256, coverage_report  # noqa: E402
import sv_synth as S  # noqa: E402

ORA = json.load(open(Path(__file__).with_name("oracle") / "u2_300_oracle.json"))


def eyedrop(img, x, y): r, g, b = img[int(y), int(x)][:3]; return "#%02x%02x%02x" % (r, g, b)


def eyedrop_median(img, geom):
    import sv_oracle as O
    m = O.rmask(geom, img.shape[:2]); return "#%02x%02x%02x" % tuple(int(v) for v in np.median(img[m], 0))


def band_score(doc, q, img):
    g = LineString(q["axis"]); r = q["radius"]; band = g.buffer(r); core = g.buffer(max(r - 1, 0.75))
    pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
    L = shapely.union_all([x.buffer(max(w / 2, 0.71)) for x, w in zip(doc.L.geometry, doc.L["width_px"])]) if len(doc.L) else None
    new = [p for p, s in zip(doc.F.geometry, doc.F["source"]) if s == "edited_line_to_face"]
    N = shapely.union_all(new) if new else None
    cov = lambda G: float(shapely.intersection(G, core).area / core.area) if G is not None else 0.0
    return {"core_by_line_footprint": cov(L), "core_by_new_face": cov(N), "new_face_area_outside_band_px2": float(shapely.difference(N, band).area) if N is not None else 0.0,
            "axis_uncovered_px": int((shapely.distance(pts, shapely.union_all([x for x in [L, N] if x is not None])) > 0.5).sum()) if (L is not None or N is not None) else len(pts)}


def gaps(doc, q, ids):
    g = LineString(q["axis"]); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
    U = shapely.union_all([doc.L.loc[doc.L["_eid"] == i, "geometry"].iloc[0] for i in ids]); miss = shapely.distance(pts, U) > 1.5
    m = np.r_[0, miss.astype(int), 0]; d = np.diff(m); st, en = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    return [(int(s), int(e)) for s, e in zip(st, en) if e - s >= 2], shapely.get_coordinates(pts)


def save(doc, out, name):
    r = doc.save_as(out / name); return {k: r[k] for k in ("path", "accepted", "coverage_is_valid", "readback_matches_memory", "input_sha256_unchanged",
                                                           "face_columns_kept", "line_columns_kept", "faces", "lines")} | {"diff": doc.diff()}


def scen_pn2(inp, out, img):
    """Scenario 1: PN2 via its logical group: recolour + rewidth (attribute only), then experimental line-to-face."""
    src = inp / "u2_B2c.gpkg"; d = Document(src, (300, 300)); q = [p for p in ORA["protected"] if p["id"] == "PN2"][0]; ops = []
    click = LineString(q["axis"]).interpolate(0.5, normalized=True); e = d.pick(click.x, click.y, LINE, tol=3.0); ops.append("pick line")
    if not e: raise SystemExit("PN2 pick failed")
    grp = d.group(e[0]); ops.append("select logical group")
    col = eyedrop_median(img, LineString(q["axis"]).buffer(max(q["radius"] - 1, 0.75))); ops.append("eyedropper")
    before = band_score(d, q, img); d.recolour(LINE, grp, col); d.rewidth(grp, 2 * q["radius"]); ops += ["recolour", "rewidth"]
    after_attr = band_score(d, q, img); a = save(d, out, "u2_PN2_recolour_rewidth.gpkg")
    lids = sorted(set(d.L.loc[d.L["_eid"].isin(grp), "logical_id"]))
    res = {"logical_ids": lids, "group_features": len(grp), "colour": col, "before": before, "after_recolour_rewidth": after_attr, "save_attr": a}
    try:
        info = d.line_to_face(grp, 2 * q["radius"], col); ops.append("line_to_face"); res["line_to_face"] = {"status": "ACCEPTED_DATA_LEVEL", **info, **band_score(d, q, img)}
        res["save_l2f"] = save(d, out, "u2_PN2_line_to_face.gpkg")
    except EditError as x:
        res["line_to_face"] = {"status": "EXPERIMENTAL_NOT_ACCEPTED", "reason": str(x)[:300]}
    g_, _ = gaps(Document(src, (300, 300)), q, grp); res["remaining_gaps_px"] = [e - s for s, e in g_]
    res["ops"] = {"select": 2, "eyedropper": 1, "recolour": 1, "rewidth": 1, "line_to_face": int("line_to_face" in ops), "split": 0, "merge": 0, "redraw_px": 0}
    res["sequence"] = ops; return res


def scen_pn1(inp, out, img):
    """Scenario 2: PN1: split the group where it leaves the band, regroup in-band parts, redraw the gap, recolour, rewidth."""
    src = inp / "u2_B2c.gpkg"; d = Document(src, (300, 300)); q = [p for p in ORA["protected"] if p["id"] == "PN1"][0]; g = LineString(q["axis"]); zone = g.buffer(q["radius"] + 1.5)
    ops = collections_counter(); seq = []
    on = [int(e) for e, x in zip(d.L["_eid"], d.L.geometry) if x.intersects(zone)]; seq.append(f"pick {len(on)} lines on PN1")
    ops["select"] += len(on); inside = []
    for e in on:
        x = d.L.loc[d.L["_eid"] == e, "geometry"].iloc[0]
        cuts = [p for p in shapely.get_parts(shapely.intersection(x, zone.boundary)) if p.geom_type == "Point"]
        cur = [e]
        for p in sorted(cuts, key=lambda p: -x.project(p)):
            tgt = [i for i in cur if d.L.loc[d.L["_eid"] == i, "geometry"].iloc[0].distance(p) < 0.5]
            if not tgt: continue
            seg = d.L.loc[d.L["_eid"] == tgt[0], "geometry"].iloc[0]; s = seg.project(p)
            if 0.5 < s < seg.length - 0.5: cur = [i for i in cur if i != tgt[0]] + d.split_line(tgt[0], p.x, p.y); ops["split"] += 1; seq.append("split at band outline")
        for i in cur:
            xi = d.L.loc[d.L["_eid"] == i, "geometry"].iloc[0]
            if shapely.intersection(xi, zone).length >= 0.8 * xi.length: inside.append(i)
    lid = d.new_group(inside); seq.append(f"new group {lid} for {len(inside)} in-band parts")
    gp, P = gaps(d, q, inside); drawn = 0.0
    for s, e in gp:
        pts = P[max(s - 1, 0):min(e + 1, len(P))].tolist()
        if len(pts) >= 2: nid = d.add_line(pts, 2 * q["radius"], "#000000", logical_id=lid); inside.append(nid); drawn += LineString(pts).length; ops["redraw_traces"] += 1; seq.append(f"redraw {LineString(pts).length:.1f} px")
    col = eyedrop_median(img, g.buffer(max(q["radius"] - 1, 0.75))); d.recolour(LINE, inside, col); d.rewidth(inside, 2 * q["radius"]); ops["recolour"] += 1; ops["rewidth"] += 1
    res = {"lines_on_band": len(on), "in_band_parts": len(inside), "gaps_px": [e - s for s, e in gp], "redraw_px": round(drawn, 1), "after": band_score(d, q, img),
           "outside_band_length_left_unchanged_px": float(sum(x.length for e, x in zip(d.L["_eid"], d.L.geometry) if e not in inside and x.intersects(zone.buffer(5)))),
           "save": save(d, out, "u2_PN1_split_redraw.gpkg")}
    try:
        info = d.line_to_face(inside, 2 * q["radius"], col); ops["line_to_face"] += 1; res["line_to_face"] = {"status": "ACCEPTED_DATA_LEVEL", **info, **band_score(d, q, img)}
        res["save_l2f"] = save(d, out, "u2_PN1_line_to_face.gpkg")
    except EditError as x:
        res["line_to_face"] = {"status": "EXPERIMENTAL_NOT_ACCEPTED", "reason": str(x)[:300]}
    res["ops"] = dict(ops) | {"redraw_px": round(drawn, 1)}; res["sequence"] = seq; return res


def collections_counter():
    import collections
    return collections.Counter()


def scen_fragments(inp, out):
    """Scenario 3: synthetic 7001 B2c, the fill region with the most faces (test design uses truth to choose the region and to
    place a user-like click; the editor commands never see truth). Three user selection routes are compared:
    colour-grow from one click, a box drawn over the region, and shift-clicking every face. Then recolour + merge."""
    src = inp / "synth_7001_B2c.gpkg"; img = np.asarray(Image.open(inp / "synth_7001.png").convert("RGB")); d = Document(src, (256, 256))
    a, truth, faces = S.generate(7001); order = ["green", "yellow", "redfill"]; regs = {}
    for i, n in enumerate(order):
        r = shapely.make_valid(Polygon(faces[n]))
        for m in order[i + 1:]: r = shapely.difference(r, shapely.make_valid(Polygon(faces[m])))
        regs[n] = r
    inreg = {n: [int(e) for e, g in zip(d.F["_eid"], d.F.geometry) if shapely.intersection(g, r).area >= 0.5 * g.area] for n, r in regs.items()}
    name = max(inreg, key=lambda n: len(inreg[n])); region = regs[name]; truth_ids = inreg[name]
    def score(sel):
        U = shapely.union_all([d.F.loc[d.F["_eid"] == e, "geometry"].iloc[0] for e in sel])
        return {"faces": len(sel), "precision_area": round(float(shapely.intersection(U, region).area / U.area), 4),
                "recall_area": round(float(shapely.intersection(U, region).area / region.area), 4), "truth_faces_selected": len(set(sel) & set(truth_ids))}
    click = region.representative_point(); seed = d.pick(click.x, click.y, FACE)
    routes = {"R1_click_then_grow_de15": d.adjacent_similar(seed, de=15.0)}
    x0, y0, x1, y1 = region.bounds; routes["R2_box_over_region"] = d.box(x0, y0, x1, y1, FACE)
    routes["R3_shift_click_each_face_TRUTH_ASSISTED"] = truth_ids
    res = {"region": name, "region_area": round(region.area, 1), "faces_mostly_in_region": len(truth_ids), "routes": {k: score(v) for k, v in routes.items()}}
    res["routes"]["R1_click_then_grow_de15"]["clicks"] = 2; res["routes"]["R2_box_over_region"]["clicks"] = 1
    res["routes"]["R3_shift_click_each_face_TRUTH_ASSISTED"]["clicks"] = len(truth_ids)
    sel = truth_ids; col = eyedrop(img, click.x, click.y); d.recolour(FACE, sel, col); n0 = len(d.F)
    try: keep = d.merge_faces(sel); merged, err = True, None
    except EditError as x: merged, err = False, str(x)
    if not merged:                                            # merge only the largest edge-connected subset, as a user would after the refusal
        import networkx as nx
        geo = {e: d.F.loc[d.F["_eid"] == e, "geometry"].iloc[0] for e in sel}; Gr = nx.Graph(); Gr.add_nodes_from(sel)
        for p_ in sel:
            for q_ in sel:
                if p_ < q_ and shapely.length(shapely.intersection(geo[p_], geo[q_])) > 0: Gr.add_edge(p_, q_)
        comps = sorted(nx.connected_components(Gr), key=len, reverse=True); res["edge_connected_components"] = [len(c) for c in comps]
        keep = d.merge_faces(sorted(comps[0])) if len(comps[0]) > 1 else None
    after = d.F.loc[d.F["_eid"] == keep, "geometry"].iloc[0] if keep is not None else None
    res.update({"merge_all_selected": merged, "merge_error": err, "faces_before_after": [n0, len(d.F)],
                "merged_face_area": round(after.area, 1) if after is not None else None,
                "merged_face_outside_region_px2": round(float(shapely.difference(after, region).area), 1) if after is not None else None,
                "save": save(d, out, "synth_7001_fragments_merge.gpkg"), "ops": {"select_clicks": len(truth_ids), "eyedropper": 1, "recolour": 1, "merge": 1 + int(not merged)}})
    return res


def scen_recolour_line(inp, out, img):
    """Scenario 4: u2 B2c: the red fault line whose stored colour is furthest from the original along it; eyedropper, apply, save, reopen."""
    from skimage.color import rgb2lab
    src = inp / "u2_B2c.gpkg"; d = Document(src, (300, 300)); best = None
    for e, g, c in zip(d.L["_eid"], d.L.geometry, d.L["rgb"]):
        if g.length < 20: continue
        P = shapely.get_coordinates(shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))); xs = np.clip(P[:, 0].astype(int), 0, 299); ys = np.clip(P[:, 1].astype(int), 0, 299)
        o = np.median(img[ys, xs], 0); s = np.array([int(c[i:i + 2], 16) for i in (1, 3, 5)])
        de = float(np.linalg.norm(rgb2lab(o.reshape(1, 1, 3) / 255)[0, 0] - rgb2lab(s.reshape(1, 1, 3) / 255)[0, 0]))
        if best is None or de > best[1]: best = (int(e), de, P[len(P) // 2])
    e, de0, mid = best; ids = d.pick(mid[0], mid[1], LINE); col = eyedrop_median(img, d.L.loc[d.L["_eid"] == e, "geometry"].iloc[0].buffer(0.75))
    g0 = d.L.loc[d.L["_eid"] == e, "geometry"].iloc[0]; d.recolour(LINE, [e], col); r = save(d, out, "u2_line_recolour.gpkg")
    re = Document(Path(r["path"]), (300, 300)); got = re.L["rgb"].iloc[list(d.L["_eid"]).index(e)]
    g1 = re.L.geometry.iloc[list(d.L["_eid"]).index(e)]
    return {"line_eid": e, "picked_by_click": ids == [e], "dE_before": round(de0, 1), "new_colour": col, "reopened_colour": got, "colour_round_trip": got == col,
            "geometry_unchanged": bool(g0.equals_exact(g1, 1e-9)), "save": r, "ops": {"select": 1, "eyedropper": 1, "recolour": 1}}


def main(inp, out, js):
    inp, out = Path(inp), Path(out); out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*"): f.unlink()
    h0 = {f.name: sha256(f) for f in inp.glob("*.gpkg")}; img = np.asarray(Image.open(inp / "u2_original.png").convert("RGB"))
    res = {"mode": "DATA_LEVEL_VERIFIED (editor core, same code the UI calls)", "inputs_sha256": h0}
    res["S1_PN2"] = scen_pn2(inp, out, img); res["S2_PN1"] = scen_pn1(inp, out, img); res["S3_fragments"] = scen_fragments(inp, out); res["S4_line_recolour"] = scen_recolour_line(inp, out, img)
    res["inputs_unchanged"] = all(sha256(inp / k) == v for k, v in h0.items()); res["outputs_sha256"] = {f.name: sha256(f) for f in sorted(out.glob("*.gpkg"))}
    json.dump(res, open(js, "w"), indent=1, default=str); print(json.dumps(res, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
