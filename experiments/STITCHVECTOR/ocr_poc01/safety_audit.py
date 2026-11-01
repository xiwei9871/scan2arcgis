"""T4 line/face safety audit. Read-only on B2c: GPKG opened with sqlite mode=ro, SHA-256 checked before and after.
Text clearing is *simulated* on in-memory geometry only; nothing is written back.

Per OCR box (e2e 1x+2x union per engine), simulated policy (fixed before running):
  line fully inside box (1 px tolerance)           -> AUTO_ISOLATE (would move to text_residue_lines)
  line crossing box edge                           -> PENDING_HUMAN (never cut)
  face fully inside box                            -> AUTO_MERGE_CANDIDATE only if it touches exactly one outside face
  face crossing box edge / touching >1 outside face-> PENDING_HUMAN
Truth-backed counts only inside the Oracle window (map x711-805, y240-540, 4.5 % of map); elsewhere NOT_EVALUATED.
'True geological line' = B2c line within 2.5 px of an Oracle line over >= 50 % of its length."""
import csv, hashlib, json, sys
from collections import defaultdict
from pathlib import Path
import shapely
from shapely.geometry import LineString, box
from shapely.strtree import STRtree
HERE = Path(__file__).parent; sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import gpkg_io as G
import benchmark_runner as B

RUN = Path.home() / "geomap2arcgis/runs/stitchvector/u2_full"; GP = RUN / "u2_full_B2c.gpkg"
OX, OY = 711, 240; WIN = box(OX, OY, 805, 540)


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def oracle_lines():
    """Oracle traces in map coords, rebuilt exactly as sv_u2_full_audit does (needs .venv-sv for sv_oracle)."""
    import numpy as np
    from PIL import Image
    import sv_common as Cm, sv_oracle as O
    full = np.asarray(Image.open(Path.home() / "geomap2arcgis/runs/real/u2/work.png").convert("RGB"))
    a, off = Cm.centre_crop(full, 300, 300); assert tuple(off) == (OY, OX), off
    ora = json.load(open(HERE.parent / "oracle/u2_300_oracle.json"))
    return [shapely.affinity.translate(LineString(f["raw"]), OX, OY) for f in O.build_lines(a, ora, O.P, 0)[0]]


def main():
    h0 = sha(GP)
    L = G.layer(GP, "visual_lines"); F = G.layer(GP, "colour_faces")
    lg = [l["geometry"] for l in L]; fg = [f["geometry"] for f in F]; LT, FT = STRtree(lg), STRtree(fg)
    OL = oracle_lines(); OU = shapely.union_all(OL).buffer(2.5)
    true_line = [g.intersects(WIN) and g.intersection(OU).length >= 0.5 * g.length for g in lg]
    T, N = B.load_truth()
    rows, summ = [], {}
    for e in B.ENGINES:
        run = B.union_scales(B.load_run(f"{e}_e2e_x1"), B.load_run(f"{e}_e2e_x2")); P = run["detections"]
        pairs = B.match(P, T); matched = set(pairs.values())
        S = defaultdict(int); iso_lines, pend_lines = set(), set()
        for i, p in enumerate(P):
            b = box(*p["g"].bounds); bt = b.buffer(1)
            li = [k for k in LT.query(b) if lg[k].intersects(b)]
            inside = [k for k in li if bt.contains(lg[k])]; cross = [k for k in li if k not in inside]
            fi = [k for k in FT.query(b) if fg[k].intersects(b) and fg[k].intersection(b).area > 0.5]
            f_in = [k for k in fi if bt.contains(fg[k])]; f_cross = [k for k in fi if k not in f_in]
            big_cross = [k for k in f_cross if fg[k].area >= 200]
            classes = {F[k]["colour_class"] for k in big_cross}
            in_win = b.intersects(WIN)
            st = "TEXT_TRUTH_MATCH" if i in matched else ("NEG_SAMPLE_HIT" if any(b.intersection(n["g"]).area / n["g"].area >= 0.3 for n in N) else "NO_TRUTH_MATCH")
            true_iso = [k for k in inside if true_line[k]]; true_cross = [k for k in cross if true_line[k]]
            pending = bool(cross) or len(classes) > 1
            iso_lines.update(inside); pend_lines.update(cross)
            S["boxes"] += 1; S["boxes_" + st] += 1
            S["boxes_touching_any_line"] += bool(li); S["boxes_crossed_by_line"] += bool(cross)
            S["boxes_spanning_2plus_ground_faces"] += len(classes) > 1
            S["boxes_pending_human"] += pending
            S["true_lines_auto_isolated"] += len(true_iso); S["true_lines_crossing_box"] += len(true_cross)
            S["fp_boxes_isolating_lines"] += (st != "TEXT_TRUTH_MATCH") and bool(inside)
            S["faces_fully_inside"] += len(f_in); S["faces_crossing_edge"] += len(f_cross)
            rows.append({"engine": e, "box_id": f"{e}_{i:03d}", "text": p["raw_text"], "bbox": [round(v, 1) for v in b.bounds], "truth_status": st,
                         "lines_inside": len(inside), "lines_crossing": len(cross), "faces_inside": len(f_in), "faces_crossing": len(f_cross),
                         "ground_classes_crossing": len(classes), "in_oracle_window": in_win, "true_lines_auto_isolated": len(true_iso),
                         "true_lines_crossing": len(true_cross),
                         "decision": "PENDING_HUMAN" if pending else ("AUTO_ISOLATE_ALLOWED" if inside else "NO_GEOMETRY_CHANGE"),
                         "line_truth": "EVALUATED" if in_win else "NOT_EVALUATED"})
        S["distinct_lines_auto_isolated"] = len(iso_lines); S["distinct_lines_pending"] = len(pend_lines - iso_lines)
        S["distinct_true_lines_auto_isolated"] = sum(true_line[k] for k in iso_lines)
        summ[e] = dict(S)
    assert sha(GP) == h0, "B2c GPKG changed"
    w = csv.DictWriter(open(B.RES / "safety_audit.csv", "w", newline=""), fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    out = {"b2c_gpkg_sha256_before": h0, "b2c_gpkg_sha256_after": sha(GP), "oracle_lines": len(OL), "b2c_lines": len(lg),
           "b2c_true_lines_in_window": sum(true_line), "oracle_window_share_of_map": round(WIN.area / (805 * 780), 3), "per_engine": summ}
    json.dump(out, open(B.RES / "safety_summary.json", "w"), indent=1)
    keys = ["boxes", "boxes_NO_TRUTH_MATCH", "boxes_NEG_SAMPLE_HIT", "boxes_crossed_by_line", "boxes_spanning_2plus_ground_faces", "boxes_pending_human",
            "distinct_lines_auto_isolated", "distinct_true_lines_auto_isolated", "true_lines_crossing_box", "fp_boxes_isolating_lines"]
    print("oracle-backed true B2c lines in window:", sum(true_line))
    for k in keys: print(f"{k:36s}", *[f"{summ[e].get(k, 0):>9}" for e in B.ENGINES])


if __name__ == "__main__":
    main()
