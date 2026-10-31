"""Score automatic lines against synthetic truth (sv_synth). Pure geometry; no image labels are used by the detector."""
import numpy as np, shapely
from shapely.geometry import LineString
import sv_oracle as O


def _samples(axis, step=1.0):
    g = LineString(axis); n = max(int(g.length / step), 1)
    return g, shapely.line_interpolate_point(g, np.linspace(0, g.length, n + 1))


def score(lines, truth, shape, tol=2.0):
    det = [l["geom"] for l in lines]; U = shapely.union_all(det) if det else None
    tree = shapely.STRtree(np.asarray(det, object)) if det else None
    per = {}
    for t in truth["lines"]:
        g, pts = _samples(t["axis"])
        hit = shapely.distance(pts, U) <= tol if U is not None else np.zeros(len(pts), bool)
        miss = np.r_[0, (~hit).astype(int), 0]; d = np.diff(miss); runs = np.nonzero(d == -1)[0] - np.nonzero(d == 1)[0]
        cover = []
        if tree is not None:
            for j in tree.query(g.buffer(tol)):
                inside = shapely.length(shapely.intersection(det[j], g.buffer(tol)))
                if inside >= 0.5 * det[j].length and inside >= 5: cover.append(int(j))
        w_true = float(np.median(t["width"]))
        wd = [lines[j]["width"] for j in cover]
        per[t["id"]] = {"recall": float(hit.mean()), "gaps_ge3px": int((runs >= 3).sum()), "objects_covering": len(cover),
                        "width_true": w_true, "width_est_median": float(np.median(wd)) if wd else None}
    T = shapely.union_all([LineString(t["axis"]) for t in truth["lines"]])
    det_len = float(sum(g.length for g in det)); near = float(sum(shapely.length(shapely.intersection(g, T.buffer(3.0))) for g in det))
    bands = {}
    for b in truth["bands"]:
        bg = LineString(b["axis"]); m = O.rmask(bg.buffer(max(b["width"] / 2 - 0.5, 0.71)), shape)
        foot = np.zeros(shape, bool)
        for l in lines: foot |= O.rmask(l["geom"].buffer(max(l["width"] / 2, 0.71)), shape)
        _, pts = _samples(b["axis"])
        on = shapely.distance(pts, U) <= 0.5 if U is not None else np.zeros(len(pts), bool)
        bands[b["id"]] = {"width": b["width"], "band_px": int(m.sum()), "band_px_under_line_footprint": float((m & foot).sum() / max(m.sum(), 1)),
                          "axis_share_with_a_line_on_it": float(on.mean())}
    return {"lines": per, "bands": bands, "detected_lines": len(lines), "detected_length": det_len,
            "false_length_share": float(1 - near / det_len) if det_len else None}
