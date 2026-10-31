"""StitchVector Editor V0.1 - editing core (no UI). Pixel coordinates: x right, y down, same as the scan image; no CRS.

A Document holds the faces layer (colour_faces), the lines layer (visual_lines) and any other layers (kept unchanged).
Every edit is an operation that snapshots both layers first (undo / redo) and appends to an edit log.
The input GPKG is never written; save_as() writes a new file, re-reads it and validates it.
"""
import copy, hashlib, json, time
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, pyogrio, shapely
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.ops import split as shp_split, substring

FACE, LINE = "colour_faces", "visual_lines"


def sha256(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def hex_ok(s):
    if not (isinstance(s, str) and len(s) == 7 and s[0] == "#"): raise ValueError(f"bad colour {s!r}")
    int(s[1:], 16); return s.lower()


def hex_to_rgb(s): return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float)


def lab(rgb):
    from skimage.color import rgb2lab
    return rgb2lab(np.asarray(rgb, float).reshape(-1, 1, 3) / 255.0).reshape(-1, 3)


class EditError(Exception):
    pass


class Document:
    def __init__(self, gpkg, image_size):
        self.src = Path(gpkg); self.src_sha = sha256(self.src); self.W, self.H = image_size
        layers = [l[0] for l in pyogrio.list_layers(self.src)]
        if FACE not in layers: raise EditError(f"{self.src.name} has no {FACE} layer")
        self.F = pyogrio.read_dataframe(self.src, layer=FACE); self.F["_eid"] = np.arange(len(self.F))
        self.L = pyogrio.read_dataframe(self.src, layer=LINE) if LINE in layers else gpd.GeoDataFrame(
            {"line_id": [], "logical_id": [], "kind": [], "width_px": [], "rgb": [], "source": [], "draw_order": []}, geometry=[])
        self.L["_eid"] = np.arange(len(self.L)); self.other = {l: pyogrio.read_dataframe(self.src, layer=l) for l in layers if l not in (FACE, LINE)}
        self.face_cols = [c for c in self.F.columns if c not in ("geometry", "_eid")]; self.line_cols = [c for c in self.L.columns if c not in ("geometry", "_eid")]
        self.F0, self.L0 = self.F.copy(), self.L.copy(); self.next_f, self.next_l = len(self.F), len(self.L)
        self.undo, self.redo, self.log = [], [], []; self.dirty = False

    # ---------- state ----------
    def _snap(self): return (self.F.copy(), self.L.copy(), self.next_f, self.next_l)

    def _push(self, desc, counts):
        self.redo.clear(); self.dirty = True
        self.log.append({"t": round(time.time(), 3), "op": desc, **counts})

    def _do(self, desc, fn, **counts):
        snap = self._snap()
        try: fn()
        except Exception:
            self.F, self.L, self.next_f, self.next_l = snap; raise
        self.undo.append((snap, desc)); self._push(desc, counts)

    def undo_op(self):
        if not self.undo: raise EditError("nothing to undo")
        snap, desc = self.undo.pop(); self.redo.append((self._snap(), desc)); self.F, self.L, self.next_f, self.next_l = snap
        self.dirty = True; self.log.append({"t": round(time.time(), 3), "op": "undo", "of": desc}); return desc

    def redo_op(self):
        if not self.redo: raise EditError("nothing to redo")
        snap, desc = self.redo.pop(); self.undo.append((self._snap(), desc)); self.F, self.L, self.next_f, self.next_l = snap
        self.dirty = True; self.log.append({"t": round(time.time(), 3), "op": "redo", "of": desc}); return desc

    def _rows(self, layer, ids):
        D = self.F if layer == FACE else self.L; m = D["_eid"].isin([int(i) for i in ids])
        if m.sum() != len(set(ids)): raise EditError(f"unknown {layer} ids {sorted(set(ids) - set(D.loc[m, '_eid']))}")
        return m

    # ---------- picking (not edits) ----------
    def pick(self, x, y, layer, tol=3.0):
        p = Point(x, y)
        if layer == LINE:
            if not len(self.L): return []
            d = shapely.distance(np.asarray(self.L.geometry.values, object), p); i = int(np.argmin(d))
            return [int(self.L["_eid"].iloc[i])] if d[i] <= tol else []
        hit = shapely.contains_xy(np.asarray(self.F.geometry.values, object), x, y)
        return [int(e) for e in self.F["_eid"][hit]]

    def box(self, x0, y0, x1, y1, layer):
        b = shapely.box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        if layer == LINE: return [int(e) for e, g in zip(self.L["_eid"], self.L.geometry) if g.intersects(b)]
        rp = shapely.point_on_surface(np.asarray(self.F.geometry.values, object))          # faces whose interior point is inside the box
        return [int(e) for e, inside in zip(self.F["_eid"], shapely.contains(b, rp)) if inside]

    def group(self, eid):
        lid = self.L.loc[self.L["_eid"] == eid, "logical_id"]
        if not len(lid): raise EditError("unknown line")
        return [int(e) for e in self.L.loc[self.L["logical_id"] == lid.iloc[0], "_eid"]]

    def adjacent_similar(self, ids, de=15.0):
        """edge-adjacent faces (shared boundary > 0) whose colour is within de (CIE76) of the first selected face, grown repeatedly."""
        geoms = dict(zip(self.F["_eid"], self.F.geometry)); cols = dict(zip(self.F["_eid"], self.F["rgb"])); tree = shapely.STRtree(np.asarray(self.F.geometry.values, object))
        eids = np.asarray(self.F["_eid"]); ref = lab(hex_to_rgb(cols[int(ids[0])]))[0]; sel = set(int(i) for i in ids); todo = list(sel)
        while todo:
            e = todo.pop()
            for j in tree.query(geoms[e], predicate="touches"):
                f = int(eids[j])
                if f in sel: continue
                if shapely.length(shapely.intersection(geoms[e], geoms[f])) <= 0: continue
                if np.linalg.norm(lab(hex_to_rgb(cols[f]))[0] - ref) <= de: sel.add(f); todo.append(f)
        return sorted(sel)

    # ---------- attribute edits ----------
    def recolour(self, layer, ids, rgb):
        rgb = hex_ok(rgb); m = self._rows(layer, ids)
        def f():
            (self.F if layer == FACE else self.L).loc[m, "rgb"] = rgb
        self._do(f"recolour {layer}", f, objects=int(m.sum()), recolour=1)

    def rewidth(self, ids, w):
        w = float(w)
        if not (0.25 <= w <= 50): raise EditError("width must be 0.25-50 px")
        m = self._rows(LINE, ids)
        def f(): self.L.loc[m, "width_px"] = w
        self._do("rewidth", f, objects=int(m.sum()), rewidth=1)

    def new_group(self, ids):
        m = self._rows(LINE, ids); lid = f"E{self.next_l}"
        def f(): self.L.loc[m, "logical_id"] = lid
        self._do("new logical group", f, objects=int(m.sum()), regroup=1); return lid

    # ---------- line geometry ----------
    def delete_lines(self, ids):
        m = self._rows(LINE, ids)
        def f(): self.L = self.L.loc[~m].copy()
        self._do("delete lines", f, objects=int(m.sum()), delete=1)

    def split_line(self, eid, x, y, tol=3.0):
        m = self._rows(LINE, [eid]); row = self.L.loc[m].iloc[0]; g = row.geometry
        if g.geom_type != "LineString": raise EditError("can only split a LineString")
        if g.distance(Point(x, y)) > tol: raise EditError("click is not on the line")
        s = g.project(Point(x, y))
        if s < 0.5 or s > g.length - 0.5: raise EditError("split point too close to an end")
        a, b = substring(g, 0, s), substring(g, s, g.length)
        def f():
            r2 = self.L.loc[m].copy(); r2["geometry"] = [b]; r2["_eid"] = [self.next_l]; r2["line_id"] = [f"{row.line_id}b"]; r2["source"] = ["edited_split"]
            self.L.loc[m, "geometry"] = [a]; self.L.loc[m, "source"] = "edited_split"; self.next_l += 1
            self.L = gpd.GeoDataFrame(pd.concat([self.L, r2], ignore_index=True), geometry="geometry")
        self._do("split line", f, objects=1, split=1)
        return [int(eid), self.next_l - 1]

    def add_line(self, coords, width, rgb, logical_id=None, snap=3.0):
        """draw a polyline (>= 2 points); first and last points snap to the nearest line end point within `snap` px."""
        c = [list(map(float, p)) for p in coords]
        if len(c) < 2: raise EditError("a line needs at least 2 points")
        ends = [q for g in self.L.geometry for q in (g.coords[0], g.coords[-1])] if len(self.L) else []
        for k in (0, -1):
            if ends:
                d = [np.hypot(q[0] - c[k][0], q[1] - c[k][1]) for q in ends]; j = int(np.argmin(d))
                if d[j] <= snap: c[k] = list(ends[j])
        g = LineString(c)
        if g.length < 0.5: raise EditError("line too short")
        lid = logical_id or f"E{self.next_l}"; rgb = hex_ok(rgb)
        def f():
            r = {k: [None] for k in self.line_cols}; r.update({"line_id": [f"D{self.next_l}"], "logical_id": [lid], "kind": ["manual"], "width_px": [float(width)],
                                                             "rgb": [rgb], "source": ["edited_drawn"], "draw_order": [int(self.L["draw_order"].max()) + 1 if len(self.L) else 0]})
            new = gpd.GeoDataFrame({**r, "_eid": [self.next_l]}, geometry=[g]); self.next_l += 1
            self.L = gpd.GeoDataFrame(pd.concat([self.L, new], ignore_index=True), geometry="geometry")
        self._do("draw line", f, objects=1, redraw_px=round(g.length, 1))
        return self.next_l - 1

    # ---------- face geometry ----------
    def merge_faces(self, ids):
        """dissolve selected faces into one; they must form one edge-connected group (no multipart result)."""
        ids = sorted(set(int(i) for i in ids))
        if len(ids) < 2: raise EditError("select at least 2 faces to merge")
        m = self._rows(FACE, ids); geoms = list(self.F.loc[m, "geometry"])
        u = shapely.union_all(geoms)
        if u.geom_type != "Polygon": raise EditError("selected faces are not one edge-connected group (merge would give a multipart face)")
        sub = self.F.loc[m]; keep = int(sub["_eid"].iloc[int(np.argmax(shapely.area(np.asarray(sub.geometry.values, object))))])
        def f():
            k = self.F["_eid"] == keep; self.F.loc[k, "geometry"] = [u]; self.F.loc[k, "source"] = "edited_merge"
            self.F = self.F.loc[~(m & ~k)].copy()
        self._do("merge faces", f, objects=len(ids), merge=1); return keep

    def line_to_face(self, ids, width=None, rgb=None):
        """EXPERIMENTAL: buffer the selected lines (width/2), cut that area out of every face it overlaps, insert it as a
        new face, remove the lines. Coordinates are snapped to a 1/8 px grid so neighbouring faces share vertices;
        if the face layer is not a valid coverage afterwards the edit is rolled back."""
        m = self._rows(LINE, ids); rows = self.L.loc[m]
        w = float(width) if width is not None else float(np.median(rows["width_px"]))
        buf = shapely.union_all([g.buffer(w / 2, quad_segs=8) for g in rows.geometry])
        poly = pixel_polygon(buf, self.W, self.H)                    # pixels whose centre is inside the buffer, as pixel-edge polygons
        if poly is None or poly.is_empty: raise EditError("buffer covers no pixel centre")
        col = hex_ok(rgb) if rgb else rows["rgb"].iloc[0]
        def f():
            hit = shapely.intersects(np.asarray(self.F.geometry.values, object), poly); keep, new = self.F.loc[~hit], []
            for _, r in self.F.loc[hit].iterrows():
                d = shapely.difference(r.geometry, poly)              # both on pixel edges: the result stays on pixel edges
                parts = [q for q in shapely.get_parts(d) if q.geom_type == "Polygon" and q.area > 1e-9]
                for j, part in enumerate(parts):                      # first piece keeps the face id, extra pieces get new ids
                    rr = r.copy(); rr["geometry"] = part
                    if j: rr["_eid"] = self.next_f; self.next_f += 1
                    new.append(rr)
            add = []
            for p in [q for q in shapely.get_parts(poly) if q.geom_type == "Polygon"]:
                r = {c: None for c in self.face_cols}; r.update({"rgb": col, "source": "edited_line_to_face"})
                if "label" in r: r["label"] = -1
                if "observed_px" in r: r["observed_px"] = 0; r["inferred_px"] = 0
                if "colour_class" in r: r["colour_class"] = -1
                add.append({**r, "geometry": p, "_eid": self.next_f}); self.next_f += 1
            F = gpd.GeoDataFrame(pd.concat([keep, gpd.GeoDataFrame(new, geometry="geometry") if new else keep.iloc[:0], gpd.GeoDataFrame(add, geometry="geometry")], ignore_index=True), geometry="geometry")
            F = share_vertices(F, poly.buffer(1.5))
            rep = coverage_report(F, self.W, self.H)
            if not rep["accepted"]: raise EditError(f"EXPERIMENTAL_NOT_ACCEPTED: line-to-face gives an invalid face layer {rep}")
            self.F = F; self.L = self.L.loc[~m].copy()
        self._do("line to face (experimental)", f, objects=int(m.sum()), line_to_face=1)
        return {"area_px2": float(poly.area), "width": w}

    # ---------- output ----------
    def _out(self, D): return gpd.GeoDataFrame(D.drop(columns=["_eid"]), geometry="geometry")

    def save_as(self, path):
        path = Path(path).resolve()
        if path == self.src.resolve(): raise EditError("refusing to overwrite the input GPKG; choose a new file name")
        if path.exists(): raise EditError(f"{path.name} already exists")
        self._out(self.F).to_file(path, layer=FACE, driver="GPKG", engine="pyogrio")
        if len(self.L): self._out(self.L).to_file(path, layer=LINE, driver="GPKG", engine="pyogrio")
        for k, D in self.other.items(): D.to_file(path, layer=k, driver="GPKG", engine="pyogrio")
        rep = self.verify(path); log = path.with_suffix(".edits.json")
        json.dump({"input": str(self.src), "input_sha256": self.src_sha, "output": str(path), "output_sha256": sha256(path), "edits": self.log,
                   "diff": self.diff(), "verification": rep}, open(log, "w"), indent=1, default=float)
        self.dirty = False; return {"path": str(path), "edit_log": str(log), **rep}

    def verify(self, path):
        layers = [l[0] for l in pyogrio.list_layers(path)]; F = pyogrio.read_dataframe(path, layer=FACE)
        L = pyogrio.read_dataframe(path, layer=LINE) if LINE in layers else None
        rep = coverage_report(F, self.W, self.H)
        mem_f = self.F.sort_values("_eid"); same_faces = len(F) == len(mem_f) and list(F["rgb"]) == list(self.F["rgb"])
        same_lines = (L is None and not len(self.L)) or (L is not None and len(L) == len(self.L) and list(L["rgb"]) == list(self.L["rgb"])
                                                       and np.allclose(L["width_px"].astype(float), self.L["width_px"].astype(float)))
        geom_same = all(a.equals_exact(b, 1e-6) for a, b in zip(F.geometry, self.F.geometry)) and (L is None or all(a.equals_exact(b, 1e-6) for a, b in zip(L.geometry, self.L.geometry)))
        rep.update({"layers": layers, "faces": len(F), "lines": 0 if L is None else len(L), "face_columns_kept": [c for c in self.face_cols if c not in F.columns] == [],
                    "line_columns_kept": L is None or [c for c in self.line_cols if c not in L.columns] == [],
                    "readback_matches_memory": bool(same_faces and same_lines and geom_same), "input_sha256_unchanged": sha256(self.src) == self.src_sha})
        return rep

    def diff(self):
        out = {}
        for name, A, B in ((FACE, self.F0, self.F), (LINE, self.L0, self.L)):
            a, b = A.set_index("_eid"), B.set_index("_eid"); common = a.index.intersection(b.index)
            attr = [c for c in a.columns if c != "geometry"]
            changed_attr = int(sum(1 for i in common if any(str(a.at[i, c]) != str(b.at[i, c]) for c in attr)))
            changed_geom = int(sum(1 for i in common if not a.at[i, "geometry"].equals_exact(b.at[i, "geometry"], 1e-9)))
            out[name] = {"before": len(a), "after": len(b), "deleted": int(len(a.index.difference(b.index))), "added": int(len(b.index.difference(a.index))),
                         "attribute_changed": changed_attr, "geometry_changed": changed_geom,
                         "unchanged": int(len(common) - sum(1 for i in common if any(str(a.at[i, c]) != str(b.at[i, c]) for c in attr) or not a.at[i, "geometry"].equals_exact(b.at[i, "geometry"], 1e-9)))}
        return out

    def state(self):
        def ring(p): return [[round(x, 3), round(y, 3)] for x, y in p.exterior.coords]
        faces = [{"id": int(e), "rgb": c, "rings": [ring(p)] + [[[round(x, 3), round(y, 3)] for x, y in h.coords] for h in p.interiors],
                  "attrs": {k: (None if pd.isna(r[k]) else (r[k].item() if hasattr(r[k], "item") else r[k])) for k in self.face_cols}}
                 for e, c, p, (_, r) in zip(self.F["_eid"], self.F["rgb"], self.F.geometry, self.F.iterrows())]
        lines = [{"id": int(e), "rgb": r["rgb"], "width": float(r["width_px"]), "logical_id": str(r["logical_id"]),
                  "coords": [[round(x, 3), round(y, 3)] for x, y in g.coords], "attrs": {k: (None if pd.isna(r[k]) else (r[k].item() if hasattr(r[k], "item") else r[k])) for k in self.line_cols}}
                 for e, g, (_, r) in zip(self.L["_eid"], self.L.geometry, self.L.iterrows())]
        return {"width": self.W, "height": self.H, "faces": faces, "lines": lines, "dirty": self.dirty, "undo": len(self.undo), "redo": len(self.redo),
                "log": self.log[-50:], "source": str(self.src), "source_sha256": self.src_sha}


def coverage_report(F, W, H):
    g = np.asarray(F.geometry.values, object); area = float(shapely.area(g).sum()); u = shapely.union_all(g)
    valid = bool(shapely.coverage_is_valid(g)); allpoly = all(x.geom_type == "Polygon" for x in g); geomvalid = bool(shapely.is_valid(g).all())
    ok = valid and allpoly and geomvalid and abs(area - W * H) < 1e-6 and abs(float(u.area) - W * H) < 1e-6
    return {"accepted": bool(ok), "coverage_is_valid": valid, "all_polygon": allpoly, "geometries_valid": geomvalid,
            "area_sum_minus_window": round(area - W * H, 6), "union_area_minus_window": round(float(u.area) - W * H, 6)}


def pixel_polygon(geom, W, H):
    """pixels (pixel-centre rule) covered by geom, as a union of pixel-edge polygons."""
    import rasterio.features as RF
    from affine import Affine
    m = RF.rasterize([(geom, 1)], out_shape=(H, W), fill=0, transform=Affine.identity(), all_touched=False, dtype="uint8")
    if not m.any(): return None
    polys = [shapely.geometry.shape(g) for g, v in RF.shapes(m, mask=m.astype(bool), connectivity=4, transform=Affine.identity()) if v == 1]
    return shapely.union_all(polys)


def share_vertices(F, zone):
    """insert into every face near `zone` the vertices of its neighbours that lie on its edges (shape unchanged), so shared
    edges have the same vertices on both sides (required by the strict coverage check)."""
    g = np.asarray(F.geometry.values, object); near = shapely.intersects(g, zone)
    if not near.any(): return F
    pts = shapely.multipoints(np.vstack([shapely.get_coordinates(x) for x in g[near]]))
    out = g.copy()
    for i in np.nonzero(near)[0]: out[i] = shapely.snap(g[i], pts, 1e-6)
    F = F.copy(); F["geometry"] = out; return F
