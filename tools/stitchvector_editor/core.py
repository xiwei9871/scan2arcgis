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

FACE, LINE, STYLES = "colour_faces", "visual_lines", "legend_styles"
ROLES = ("COVER", "SPLIT", "UNKNOWN")


def sha256(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def hex_ok(s):
    if not (isinstance(s, str) and len(s) == 7 and s[0] == "#"): raise ValueError(f"bad colour {s!r}")
    int(s[1:], 16); return s.lower()


def hex_to_rgb(s): return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float)


def lab(rgb):
    from skimage.color import rgb2lab
    return rgb2lab(np.asarray(rgb, float).reshape(-1, 1, 3) / 255.0).reshape(-1, 3)



# ================= Legend: styles stored apart from geometry =================
LINE_TYPES = ("solid", "dash", "teeth")
STYLE_KEYS = {"kind": str, "name": str, "rgb": str, "width": float, "line_type": str, "dash": str,
              "tooth_spacing": float, "tooth_size": float, "tooth_side": str}


def default_styles():
    """a minimal starter library (not a recognised legend): edit or add entries per map."""
    return {
        "L_SOLID_BLACK": {"kind": "line", "name": "solid black 1.5", "rgb": "#202020", "width": 1.5, "line_type": "solid", "dash": "", "tooth_spacing": 0.0, "tooth_size": 0.0, "tooth_side": "left"},
        "L_DASH_RED": {"kind": "line", "name": "dashed red 1.5", "rgb": "#c0392b", "width": 1.5, "line_type": "dash", "dash": "6,4", "tooth_spacing": 0.0, "tooth_size": 0.0, "tooth_side": "left"},
        "L_TEETH_RED": {"kind": "line", "name": "red with teeth (thrust)", "rgb": "#c0392b", "width": 1.5, "line_type": "teeth", "dash": "", "tooth_spacing": 10.0, "tooth_size": 4.0, "tooth_side": "left"},
        "F_PINK": {"kind": "face", "name": "pink fill", "rgb": "#f5c6d0", "width": 0.0, "line_type": "", "dash": "", "tooth_spacing": 0.0, "tooth_size": 0.0, "tooth_side": ""},
        "F_GREEN": {"kind": "face", "name": "green fill", "rgb": "#cfe3a5", "width": 0.0, "line_type": "", "dash": "", "tooth_spacing": 0.0, "tooth_size": 0.0, "tooth_side": ""},
    }


def clean_style(r):
    out = {}
    for k, t in STYLE_KEYS.items():
        v = r.get(k)
        if v is None or (isinstance(v, float) and np.isnan(v)): v = "" if t is str else 0.0
        out[k] = t(v)
    if out["kind"] not in ("line", "face"): raise EditError(f"style kind must be line or face, not {out['kind']!r}")
    out["rgb"] = hex_ok(out["rgb"])
    if out["kind"] == "line":
        if out["line_type"] not in LINE_TYPES: raise EditError(f"line_type must be one of {LINE_TYPES}")
        if out["width"] <= 0 or out["width"] > 50: raise EditError("width must be in (0, 50]")
        if out["line_type"] == "dash":
            try: d = [float(x) for x in out["dash"].split(",")]
            except ValueError: raise EditError("dash must be like '6,4'")
            if len(d) < 2 or min(d) <= 0: raise EditError("dash must be like '6,4' with positive numbers")
        if out["line_type"] == "teeth":
            if not (2 <= out["tooth_spacing"] <= 200) or not (0.5 <= out["tooth_size"] <= 50): raise EditError("tooth spacing 2-200, size 0.5-50")
            if out["tooth_side"] not in ("left", "right"): raise EditError("tooth_side must be left or right")
    return out


def teeth_triangles(line, spacing, size, side):
    """triangles along `line`, one every `spacing` px, apex `size` px to the left/right of the travel direction
    (y down, as in the image). Used for display only; the line geometry is not changed."""
    out = []; L = line.length; sgn = 1.0 if side == "left" else -1.0; d = spacing / 2
    while d < L:
        a, b = line.interpolate(max(d - size / 2, 0)), line.interpolate(min(d + size / 2, L)); m = line.interpolate(d)
        tx, ty = b.x - a.x, b.y - a.y; n = np.hypot(tx, ty)
        if n > 1e-9:
            nx, ny = ty / n * sgn, -tx / n * sgn
            out.append([[a.x, a.y], [b.x, b.y], [m.x + nx * size, m.y + ny * size]])
        d += spacing
    return out


class EditError(Exception):
    pass


class Document:
    def __init__(self, gpkg, image_size, image=None):
        self.src = Path(gpkg); self.src_sha = sha256(self.src); self.W, self.H = image_size
        self.img = None if image is None else np.asarray(image)[..., :3]
        layers = [l[0] for l in pyogrio.list_layers(self.src)]
        if FACE not in layers: raise EditError(f"{self.src.name} has no {FACE} layer")
        self.F = pyogrio.read_dataframe(self.src, layer=FACE); self.F["_eid"] = np.arange(len(self.F))
        self.L = pyogrio.read_dataframe(self.src, layer=LINE) if LINE in layers else gpd.GeoDataFrame(
            {"line_id": [], "logical_id": [], "kind": [], "width_px": [], "rgb": [], "source": [], "draw_order": []}, geometry=[])
        self.L["_eid"] = np.arange(len(self.L)); self.other = {l: pyogrio.read_dataframe(self.src, layer=l) for l in layers if l not in (FACE, LINE, STYLES)}
        # line role (COVER / SPLIT / UNKNOWN) and legend binding; existing lines default to UNKNOWN, never inferred
        if "line_role" not in self.L.columns: self.L["line_role"] = "UNKNOWN"
        self.L["line_role"] = self.L["line_role"].fillna("UNKNOWN").astype(object)
        for D in (self.L, self.F):
            if "legend_id" not in D.columns: D["legend_id"] = None
            D["legend_id"] = D["legend_id"].astype(object).where(D["legend_id"].notna(), None)
        self.styles = default_styles()
        if STYLES in layers:
            for r in pyogrio.read_dataframe(self.src, layer=STYLES).to_dict("records"): self.styles[r["legend_id"]] = clean_style(r)
        self.face_cols = [c for c in self.F.columns if c not in ("geometry", "_eid")]; self.line_cols = [c for c in self.L.columns if c not in ("geometry", "_eid")]
        self.F0, self.L0 = self.F.copy(), self.L.copy(); self.next_f, self.next_l = len(self.F), len(self.L)
        self.undo, self.redo, self.log = [], [], []; self.dirty = False
        self.version = 0; self.previews = {}; self._pid = 0

    # ---------- state ----------
    def _bump(self):
        """every change of document content (edit, undo, redo) gets a new version; all stored previews become stale."""
        self.version += 1; self.previews.clear()

    def _snap(self): return (self.F.copy(), self.L.copy(), self.next_f, self.next_l, copy.deepcopy(self.styles))

    def _push(self, desc, counts):
        self.redo.clear(); self.dirty = True; self._bump()
        self.log.append({"t": round(time.time(), 3), "op": desc, **counts})

    def _do(self, desc, fn, **counts):
        snap = self._snap()
        try: fn()
        except Exception:
            self.F, self.L, self.next_f, self.next_l, self.styles = snap; raise
        self.undo.append((snap, desc)); self._push(desc, counts)

    def undo_op(self):
        if not self.undo: raise EditError("nothing to undo")
        snap, desc = self.undo.pop(); self.redo.append((self._snap(), desc)); self.F, self.L, self.next_f, self.next_l, self.styles = snap
        self.dirty = True; self._bump(); self.log.append({"t": round(time.time(), 3), "op": "undo", "of": desc}); return desc

    def redo_op(self):
        if not self.redo: raise EditError("nothing to redo")
        snap, desc = self.redo.pop(); self.undo.append((self._snap(), desc)); self.F, self.L, self.next_f, self.next_l, self.styles = snap
        self.dirty = True; self._bump(); self.log.append({"t": round(time.time(), 3), "op": "redo", "of": desc}); return desc

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
                                                             "rgb": [rgb], "source": ["edited_drawn"], "draw_order": [int(self.L["draw_order"].max()) + 1 if len(self.L) else 0],
                                                             "line_role": ["UNKNOWN"], "legend_id": [""]})
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

    # ---------- line roles and legend (style only, never geometry) ----------
    def set_role(self, ids, role):
        if role not in ROLES: raise EditError(f"role must be one of {ROLES}")
        m = self._rows(LINE, ids)
        def f(): self.L.loc[m, "line_role"] = role
        self._do(f"set line role {role}", f, objects=int(m.sum()), role=1)

    def apply_legend(self, layer, ids, legend_id):
        st = self.styles.get(legend_id)
        if st is None: raise EditError(f"unknown legend {legend_id!r}")
        want = "line" if layer == LINE else "face"
        if st["kind"] != want: raise EditError(f"legend {legend_id} is a {st['kind']} style, not a {want} style")
        m = self._rows(layer, ids)
        def f():
            D = self.L if layer == LINE else self.F
            D.loc[m, "legend_id"] = legend_id; D.loc[m, "rgb"] = st["rgb"]
            if layer == LINE: D.loc[m, "width_px"] = st["width"]
        self._do(f"apply legend {legend_id}", f, objects=int(m.sum()), legend=1)

    def set_style(self, legend_id, style):
        if not isinstance(legend_id, str) or not legend_id or len(legend_id) > 40: raise EditError("bad legend id")
        st = clean_style({**self.styles.get(legend_id, {}), **style})
        def f():
            self.styles[legend_id] = st
            for D in (self.L, self.F):
                m = D["legend_id"] == legend_id
                if m.any():
                    D.loc[m, "rgb"] = st["rgb"]
                    if D is self.L: D.loc[m, "width_px"] = st["width"]
        self._do(f"edit legend {legend_id}", f, legend=1)

    def split_face_preview(self, eid):
        """SPLIT line: cut every face it crosses along the line (snapped to the pixel grid). Returns the pieces that would
        be created. Refused for COVER / UNKNOWN lines. Nothing is modified."""
        m = self._rows(LINE, [eid]); r = self.L.loc[m].iloc[0]
        if r["line_role"] != "SPLIT": raise EditError("only a line marked SPLIT can cut faces; set its role first")
        plan = self._split_plan(r.geometry)
        self._pid += 1; pid = f"split-{self._pid}"; self.previews[pid] = {"kind": "split", "version": self.version, "line": int(eid), "plan": plan}
        return {"preview_id": pid, "faces_cut": len(plan), "pieces": sum(len(v) for v in plan.values()),
                "outline": [[[round(x, 2), round(y, 2)] for x, y in p.exterior.coords] for v in plan.values() for p in v]}

    def _split_plan(self, line):
        cutter = pixel_line_cut(line)
        g = np.asarray(self.F.geometry.values, object); hit = shapely.intersects(g, line); plan = {}
        for e, face in zip(self.F["_eid"][hit], g[hit]):
            parts = [p for p in shapely.get_parts(shapely.difference(face, cutter)) if p.area > 0]
            if len(parts) < 2: continue
            # pixels of the cut strip go to the piece on their left (deterministic, keeps full coverage)
            strip = shapely.intersection(face, cutter)
            big = sorted(parts, key=lambda p: -p.area)
            strip_parts = [q for q in shapely.get_parts(strip) if q.area > 0]
            for q in strip_parts:
                k = int(np.argmax([shapely.length(shapely.intersection(q.boundary, p.boundary)) for p in big])); big[k] = shapely.union_all([big[k], q])
            big = [shapely.normalize(shapely.make_valid(p)) for p in big]
            if all(p.geom_type == "Polygon" for p in big): plan[int(e)] = big
        if not plan: raise EditError("the line does not cut any face into two parts (extend it across the face)")
        return plan

    def split_face_apply(self, preview_id):
        pv = self.previews.get(str(preview_id))
        if pv is None or pv.get("kind") != "split": raise EditError("unknown or expired preview; preview again")
        if pv["version"] != self.version: raise EditError("stale preview: the document changed after the preview")
        plan = pv["plan"]
        def f():
            rows = []
            for e, parts in plan.items():
                k = self.F["_eid"] == e
                if not k.any(): raise EditError(f"face {e} no longer exists")
                base = self.F.loc[k].iloc[0]; self.F.loc[k, "geometry"] = [parts[0]]; self.F.loc[k, "source"] = "edited_split"
                for p in parts[1:]:
                    r = base.copy(); r["geometry"] = p; r["_eid"] = self.next_f; r["source"] = "edited_split"; self.next_f += 1; rows.append(r)
            if rows: self.F = gpd.GeoDataFrame(pd.concat([self.F, gpd.GeoDataFrame(rows, geometry="geometry")], ignore_index=True), geometry="geometry")
            self.F = share_vertices(self.F, shapely.union_all([p for v in plan.values() for p in v]).buffer(1))
            rep = coverage_report(self.F, self.W, self.H)
            if not rep["accepted"]: raise EditError(f"split gives an invalid face layer {rep}")
        self._do("split faces along SPLIT line", f, objects=len(plan), split_face=1)
        return {"faces_cut": len(plan), "pieces": sum(len(v) for v in plan.values())}

    def render_lines(self):
        """display geometry for every line from its legend: dash pattern and tooth triangles. Never stored."""
        out = []
        for e, g, lid in zip(self.L["_eid"], self.L.geometry, self.L["legend_id"]):
            st = self.styles.get(lid) if lid else None
            rec = {"id": int(e), "line_type": "solid", "dash": [], "teeth": []}
            if st and st["kind"] == "line":
                rec["line_type"] = st["line_type"]
                if st["line_type"] == "dash": rec["dash"] = [float(x) for x in st["dash"].split(",")]
                if st["line_type"] == "teeth": rec["teeth"] = [[[round(x, 2), round(y, 2)] for x, y in t] for t in teeth_triangles(g, st["tooth_spacing"], st["tooth_size"], st["tooth_side"])]
            out.append(rec)
        return out

    # ---------- output ----------
    def _out(self, D): return gpd.GeoDataFrame(D.drop(columns=["_eid"]), geometry="geometry")

    def save_as(self, path):
        """atomic save: write a temporary GPKG in the same folder, close it, re-read and validate it; only an accepted file
        is renamed to the requested path. On any failure the temporary file is removed, nothing is left at `path`, and the
        document stays unsaved (dirty)."""
        import os, uuid
        path = Path(path).resolve()
        if path == self.src.resolve(): raise EditError("refusing to overwrite the input GPKG; choose a new file name")
        if path.exists(): raise EditError(f"{path.name} already exists")
        tmp = path.with_name(f".{path.stem}.{uuid.uuid4().hex[:8]}.tmp.gpkg")
        try:
            self._out(self.F).to_file(tmp, layer=FACE, driver="GPKG", engine="pyogrio")
            if len(self.L): self._out(self.L).to_file(tmp, layer=LINE, driver="GPKG", engine="pyogrio")
            pyogrio.write_dataframe(pd.DataFrame([{"legend_id": k, **v} for k, v in self.styles.items()]), tmp, layer=STYLES, driver="GPKG")
            for k, D in self.other.items():
                if isinstance(D, gpd.GeoDataFrame): D.to_file(tmp, layer=k, driver="GPKG", engine="pyogrio")
                else: pyogrio.write_dataframe(D, tmp, layer=k, driver="GPKG")
            rep = self.verify(tmp)
            bad = [k for k in ("accepted", "readback_matches_memory", "input_sha256_unchanged", "face_columns_kept", "line_columns_kept") if not rep.get(k)]
            if bad: raise EditError(f"save rejected, checks failed: {bad}; nothing was written to {path.name}")
            if path.exists(): raise EditError(f"{path.name} appeared during save; not overwritten")
            os.replace(tmp, path)
        except Exception:
            for q in (tmp, Path(str(tmp) + "-wal"), Path(str(tmp) + "-shm")):
                if q.exists(): q.unlink()
            raise
        rep["path_sha256"] = sha256(path); log = path.with_suffix(".edits.json")
        json.dump({"input": str(self.src), "input_sha256": self.src_sha, "output": str(path), "output_sha256": rep["path_sha256"], "edits": self.log,
                   "diff": self.diff(), "verification": rep, "document_version": self.version}, open(log, "w"), indent=1, default=float)
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
        lines = [{"id": int(e), "rgb": r["rgb"], "width": float(r["width_px"]), "logical_id": str(r["logical_id"]), "role": r["line_role"], "legend_id": r["legend_id"],
                  "coords": [[round(x, 3), round(y, 3)] for x, y in g.coords], "attrs": {k: (None if pd.isna(r[k]) else (r[k].item() if hasattr(r[k], "item") else r[k])) for k in self.line_cols}}
                 for e, g, (_, r) in zip(self.L["_eid"], self.L.geometry, self.L.iterrows())]
        return {"width": self.W, "height": self.H, "faces": faces, "lines": lines, "dirty": self.dirty, "undo": len(self.undo), "redo": len(self.redo),
                "log": self.log[-50:], "source": str(self.src), "source_sha256": self.src_sha, "version": self.version,
                "styles": self.styles, "render": self.render_lines()}


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


def pixel_line_cut(line):
    """the pixels a line passes through (pixel-centre rule after a 0.5 px buffer), as a polygon on the pixel grid."""
    import rasterio.features as RF
    from affine import Affine
    b = shapely.bounds(line); W = int(np.ceil(b[2])) + 2; H = int(np.ceil(b[3])) + 2
    m = RF.rasterize([(line.buffer(0.5), 1)], out_shape=(H, W), fill=0, transform=Affine.identity(), all_touched=False, dtype="uint8")
    if not m.any(): raise EditError("line too short to cut")
    return shapely.union_all([shapely.geometry.shape(g) for g, v in RF.shapes(m, mask=m.astype(bool), connectivity=4, transform=Affine.identity()) if v == 1])


def share_vertices(F, zone):
    """insert into every face near `zone` the vertices of its neighbours that lie on its edges (shape unchanged), so shared
    edges have the same vertices on both sides (required by the strict coverage check)."""
    g = np.asarray(F.geometry.values, object); near = shapely.intersects(g, zone)
    if not near.any(): return F
    pts = shapely.multipoints(np.vstack([shapely.get_coordinates(x) for x in g[near]]))
    out = g.copy()
    for i in np.nonzero(near)[0]: out[i] = shapely.snap(g[i], pts, 1e-6)
    F = F.copy(); F["geometry"] = out; return F


# ================= POC 1: gestures -> feature selection -> previewed commands =================
DE_CONFLICT = 20.0


def _lab_px(img):
    from skimage.color import rgb2lab
    return rgb2lab(img / 255.0)


class SelectionMixin:
    """Gesture -> set of feature ids -> command with preview. Selections never modify data."""

    def gesture(self, kind, pts, radius=0.0):
        pts = [tuple(map(float, p)) for p in pts]
        if kind == "brush":
            if not pts: raise EditError("empty brush stroke")
            r = max(float(radius), 0.5)
            return (LineString(pts) if len(pts) > 1 else Point(pts[0])).buffer(r, quad_segs=8)
        if kind == "lasso":
            if len(pts) < 3: raise EditError("a lasso needs at least 3 points")
            g = shapely.make_valid(Polygon(pts))
            if g.is_empty or g.area <= 0: raise EditError("lasso has no area")
            return g
        raise EditError(f"unknown gesture {kind}")

    def select_region(self, geom, layer=FACE, rule="touch", max_area=None):
        if layer == LINE:
            return [int(e) for e, g in zip(self.L["_eid"], self.L.geometry) if g.intersects(geom)]
        g = np.asarray(self.F.geometry.values, object)
        if rule == "touch": m = shapely.intersects(g, geom)
        elif rule == "centre": m = shapely.contains(geom, shapely.point_on_surface(g))
        elif rule == "cover50": m = shapely.area(shapely.intersection(g, geom)) >= 0.5 * shapely.area(g)
        else: raise EditError(f"unknown rule {rule}")
        if max_area is not None: m &= shapely.area(g) <= float(max_area)
        return [int(e) for e in self.F["_eid"][m]]

    def _edge_neighbours(self, eid):
        geoms = dict(zip(self.F["_eid"], self.F.geometry)); g = geoms[eid]
        tree = shapely.STRtree(np.asarray(self.F.geometry.values, object)); eids = np.asarray(self.F["_eid"]); out = {}
        for j in tree.query(g, predicate="touches"):
            f = int(eids[j])
            if f == eid: continue
            s = shapely.length(shapely.intersection(g, geoms[f]))
            if s > 0: out[f] = s
        return out

    def grow(self, ids, steps=1):
        sel = set(int(i) for i in ids)
        for _ in range(int(steps)):
            add = set()
            for e in sel: add |= set(self._edge_neighbours(e))
            sel |= add
        return sorted(sel)

    def shrink(self, ids, steps=1):
        sel = set(int(i) for i in ids)
        for _ in range(int(steps)):
            sel = {e for e in sel if set(self._edge_neighbours(e)) <= sel}
        return sorted(sel)

    def _components(self, ids):
        ids = sorted(set(int(i) for i in ids)); idset = set(ids); comp, seen = [], set()
        for e in ids:
            if e in seen: continue
            stack, cur = [e], []
            while stack:
                x = stack.pop()
                if x in seen: continue
                seen.add(x); cur.append(x); stack += [n for n in self._edge_neighbours(x) if n in idset and n not in seen]
            comp.append(sorted(cur))
        return comp

    def _face_pixels(self):
        import rasterio.features as RF
        from affine import Affine
        return RF.rasterize([(g, int(e) + 1) for e, g in zip(self.F["_eid"], self.F.geometry)], out_shape=(self.H, self.W), fill=0,
                            transform=Affine.identity(), dtype="int32") - 1

    def _line_mask(self, extra=1.0):
        import rasterio.features as RF
        from affine import Affine
        if not len(self.L): return np.zeros((self.H, self.W), bool)
        U = shapely.union_all([g.buffer(max(w / 2, 0.71) + extra) for g, w in zip(self.L.geometry, self.L["width_px"])])
        return RF.rasterize([(U, 1)], out_shape=(self.H, self.W), fill=0, transform=Affine.identity(), dtype="uint8") > 0

    def merge_preview(self, ids):
        """for each edge-connected group of the selection: merged outline, faces, area, and the pixels inside it whose
        ORIGINAL colour differs from the group's dominant colour by > DE_CONFLICT (ink pixels under lines excluded) - a
        warning that the merge may cross a real boundary. Nothing is modified."""
        comps = self._components(ids); out = []
        lab = _lab_px(self.img) if self.img is not None else None; fid = self._face_pixels() if lab is not None else None
        ink = self._line_mask() if lab is not None else None
        for c in comps:
            u = shapely.union_all([self.F.loc[self.F["_eid"] == e, "geometry"].iloc[0] for e in c]); rec = {"faces": c, "area": float(u.area), "single_polygon": u.geom_type == "Polygon"}
            if lab is not None:
                m = np.isin(fid, c) & ~ink
                if m.any():
                    ref = np.median(lab[m], 0); de = np.linalg.norm(lab[m] - ref, axis=1)
                    rec["colour_conflict_px"] = int((de > DE_CONFLICT).sum()); rec["colour_conflict_share"] = float((de > DE_CONFLICT).mean())
            rec["outline"] = [[[round(x, 2), round(y, 2)] for x, y in p.exterior.coords] for p in shapely.get_parts(u) if p.geom_type == "Polygon"]
            out.append(rec)
        return {"groups": out, "mergeable_groups": sum(1 for r in out if len(r["faces"]) > 1 and r["single_polygon"])}

    def merge_components(self, ids):
        """merge every edge-connected group of the selection (one undoable step); single faces are left alone."""
        comps = [c for c in self._components(ids) if len(c) > 1]
        if not comps: raise EditError("no two selected faces share an edge")
        def f():
            for c in comps:
                m = self.F["_eid"].isin(c); sub = self.F.loc[m]; u = shapely.union_all(list(sub.geometry))
                if u.geom_type != "Polygon": continue
                keep = int(sub["_eid"].iloc[int(np.argmax(shapely.area(np.asarray(sub.geometry.values, object))))])
                k = self.F["_eid"] == keep; self.F.loc[k, "geometry"] = [u]; self.F.loc[k, "source"] = "edited_merge"; self.F = self.F.loc[~(m & ~k)].copy()
            rep = coverage_report(self.F, self.W, self.H)
            if not rep["accepted"]: raise EditError(f"merge gives an invalid face layer {rep}")
        n = sum(len(c) for c in comps); self._do("merge selected groups", f, objects=n, merge=len(comps)); return {"groups": len(comps), "faces": n}

    def _role_mask(self, roles, extra=0.5):
        import rasterio.features as RF
        from affine import Affine
        if not len(self.L): return np.zeros((self.H, self.W), bool)
        r = self.L["line_role"] if "line_role" in self.L.columns else pd.Series(["UNKNOWN"] * len(self.L), index=self.L.index)
        sub = [(g, w) for g, w, k in zip(self.L.geometry, self.L["width_px"], r) if k in roles]
        if not sub: return np.zeros((self.H, self.W), bool)
        U = shapely.union_all([g.buffer(max(float(w) / 2, 0.71) + extra) for g, w in sub])
        return RF.rasterize([(U, 1)], out_shape=(self.H, self.W), fill=0, transform=Affine.identity(), dtype="uint8") > 0

    def heal_preview(self, region, max_area=12.0, de_merge=15.0, de_keep=25.0, min_keep=3.0):
        """small faces touched by the brush get a proposed target: the edge neighbour (not itself a candidate) sharing the
        longest edge. Line roles decide what "under a line" means:
          under a COVER line (>= 50% of the face)   -> merge (the stroke sits on top of one unit)
          under a SPLIT or UNKNOWN line              -> uncertain (it may be a real contact; never merged automatically)
          otherwise: same original colour as target  -> merge; distinct colour and area >= min_keep -> keep; else uncertain.
        The plan is stored on the server under a preview id bound to the current document version. Nothing is modified."""
        if self.img is None: raise EditError("heal needs the scan image")
        cand = self.select_region(region, FACE, "touch", max_area); cs = set(cand)
        lab = _lab_px(self.img); fid = self._face_pixels(); ink = self._line_mask(0.5); local = region.buffer(6)
        cover = self._role_mask({"COVER"}); other = self._role_mask({"SPLIT", "UNKNOWN"})
        import rasterio.features as RF
        from affine import Affine
        near = RF.rasterize([(local, 1)], out_shape=(self.H, self.W), fill=0, transform=Affine.identity(), dtype="uint8") > 0
        out = []
        for e in cand:
            nb = self._edge_neighbours(e); outside = {k: v for k, v in nb.items() if k not in cs}
            pool = outside or nb
            if not pool: out.append({"id": e, "decision": "keep", "reason": "no edge neighbour"}); continue
            t = max(pool, key=pool.get); g = self.F.loc[self.F["_eid"] == e, "geometry"].iloc[0]
            me = fid == e; tm = (fid == t) & near & ~ink
            if not me.any(): me = np.zeros_like(me); c = g.representative_point(); me[int(min(c.y, self.H - 1)), int(min(c.x, self.W - 1))] = True
            n = max(me.sum(), 1); u_cover = float((me & cover).sum() / n); u_other = float((me & other).sum() / n)
            de = float(np.linalg.norm(np.median(lab[me], 0) - np.median(lab[tm], 0))) if tm.any() else None
            if u_other >= 0.5: d, why = "uncertain", "under a SPLIT/UNKNOWN line"
            elif u_cover >= 0.5: d, why = "merge", "under a COVER line"
            elif de is not None and de <= de_merge: d, why = "merge", "same colour as neighbour"
            elif de is not None and de >= de_keep and g.area >= min_keep: d, why = "keep", "distinct colour"
            else: d, why = "uncertain", "check"
            out.append({"id": e, "target": int(t), "target_is_candidate": t in cs, "decision": d, "reason": why, "area": float(g.area),
                        "dE": None if de is None else round(de, 1), "under_cover_share": round(u_cover, 2), "under_split_or_unknown_share": round(u_other, 2)})
        self._pid += 1; pid = f"heal-{self._pid}"
        self.previews[pid] = {"kind": "heal", "version": self.version, "candidates": out}
        return {"preview_id": pid, "version": self.version, "candidates": out,
                "counts": {k: sum(1 for r in out if r["decision"] == k) for k in ("merge", "keep", "uncertain")}}

    def heal_apply(self, preview_id, accept_uncertain=()):
        """apply a stored heal preview. The client sends only the preview id (and, optionally, ids of 'uncertain' faces
        the user explicitly accepts). Rejected if the preview is unknown or stale (document changed since). Every merge
        is re-checked: candidate and target still exist and still share an edge; the result must be one polygon and the
        whole face layer must pass the strict coverage check, otherwise nothing changes."""
        pv = self.previews.get(str(preview_id))
        if pv is None or pv.get("kind") != "heal": raise EditError("unknown or expired preview; preview again")
        if pv["version"] != self.version: raise EditError("stale preview: the document changed after the preview")
        acc = {int(i) for i in accept_uncertain}
        tgt = {r["id"]: r["target"] for r in pv["candidates"] if r.get("target") is not None and (r["decision"] == "merge" or (r["decision"] == "uncertain" and r["id"] in acc))}
        bad = acc - {r["id"] for r in pv["candidates"] if r["decision"] == "uncertain"}
        if bad: raise EditError(f"ids {sorted(bad)} are not uncertain candidates of this preview")
        if not tgt: raise EditError("nothing to merge")
        live = set(int(e) for e in self.F["_eid"])
        for e, t in tgt.items():
            if e not in live or t not in live: raise EditError(f"face {e} or its target {t} no longer exists")
            if t not in self._edge_neighbours(e): raise EditError(f"face {e} does not share an edge with target {t}")
        def final(e, seen=()):
            t = tgt.get(e)
            return e if t is None or t in seen else final(t, seen + (e,))
        groups = {}
        for e in tgt: groups.setdefault(final(e), []).append(e)
        def f():
            done = 0
            for t, members in groups.items():
                if t in tgt: continue
                allm = [t] + members; m = self.F["_eid"].isin(allm); u = shapely.union_all(list(self.F.loc[m, "geometry"]))
                if u.geom_type != "Polygon": continue
                k = self.F["_eid"] == t; self.F.loc[k, "geometry"] = [u]; self.F.loc[k, "source"] = "edited_heal"; self.F = self.F.loc[~(m & ~k)].copy(); done += len(members)
            rep = coverage_report(self.F, self.W, self.H)
            if not rep["accepted"]: raise EditError(f"heal gives an invalid face layer {rep}")
            if not done: raise EditError("no candidate could be merged into one polygon with its target")
        self._do("heal fragments", f, objects=len(tgt), heal=1); return {"merged": len(tgt), "targets": len(groups)}


for _n, _f in list(vars(SelectionMixin).items()):
    if callable(_f) and not _n.startswith("__"): setattr(Document, _n, _f)
