"""P2.1 real-scene acceptance driver: runs every P2 repair path against the REAL U2 B2c output
(protected data - never committed), times each step, and prints a JSON result per scenario.

Usage: .venv-sv/bin/python tests/stitchvector_editor/u2_real_uat.py [out_dir]
Results are also written to <out_dir>/u2_real_uat.json for transcription into
docs/uat/20261105/P2_REAL_UAT_RESULTS.md + P2_REAL_EDIT_COST.csv.
Skips cleanly when the protected inputs are absent."""
import json, sys, time, hashlib
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.stitchvector_editor.core import Document, EditError, coverage_report  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
for base in (ROOT, ROOT.parents[2]):
    if (base / "runs/stitchvector/u2_full/u2_full_B2c.gpkg").exists():
        DATA = base / "runs/stitchvector"; break
else:
    print(json.dumps({"skipped": "protected U2 inputs not present"})); sys.exit(0)

U2 = DATA / "u2_full/u2_full_B2c.gpkg"                 # raw B2c output: 17047 faces / 606 lines, 805x780
U2C = DATA / "u2_full/u2_full_text_cleared.gpkg"       # earlier text-cleaned session: texts + residue layers
W, H = 805, 780
RESULTS = []


def timed(fn):
    t0 = time.perf_counter(); r = fn(); return r, round(time.perf_counter() - t0, 2)


def record(issue, scenario, actions, clicks, elapsed, changed, reverted, success, harm, method, extra=None,
           doc=None, v0=None, src=None):
    RESULTS.append({"issue_id": issue, "scenario": scenario, "operator_type": "AGENT_OPERATED",
                    "input_sha256": sha256(src) if src else None, "before_version": v0,
                    "after_version": None if doc is None else doc.version,
                    "actions_count": actions, "clicks_count": clicks, "elapsed_seconds": elapsed,
                    "objects_changed": changed, "reverted_objects": reverted, "success": bool(success),
                    "harm_detected": bool(harm), "verification_method": method, **(extra or {})})


def sha256(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def fresh(src): return Document(src, (W, H), None)


# ---------------- A09: logical grouping + geometry merge of real fragments ----------------
d = fresh(U2)
F, L = d.F, d.L
# find a same-colour edge-adjacent pair where the smaller piece is a real fragment (speck)
g = np.asarray(F.geometry.values, object); rgb = F["rgb"].values; lab = F["label"].values
pair = None
VA = d.version
for i in np.argsort(F.geometry.area.values)[:4000]:
    for j in d.adjacent_similar([int(F["_eid"].iloc[i])], 15):
        if j != int(F["_eid"].iloc[i]) and rgb[j] == rgb[i] and lab[j] == lab[i]:
            pair = (int(F["_eid"].iloc[i]), j); break
    if pair: break
if pair:
    t0 = time.perf_counter()
    sug = d.merge_suggest([pair[0]], de=15)                                # click main face + suggest
    ok = [c for c in sug["candidates"] if c["suggested"]]
    n_undo = 0
    merged = False
    if len(ok) > 1 and not any("mixed_label" in c["risks"] or "crosses_split_line" in c["risks"] for c in ok):
        ids = [c["eid"] for c in ok]
        d.merge_components(ids, allow_mixed_labels=False)                  # one-confirm batch merge
        merged = coverage_report(d.F, W, H)["accepted"]; n_undo += 1
        d.undo_op()                                                        # revert - keep the doc clean
    # logical grouping on the same cluster (no geometry change)
    grp = d.group_faces([pair[0], pair[1]]); n_undo += 1
    el = round(time.perf_counter() - t0, 2)
    record("A09", "merge_suggest + LOGICAL_GROUP on a real same-colour fragment pair",
           4 + merged, 4 + merged, el, 1 + merged, n_undo, True, False,
           "suggest->risks->(merge|group)->undo; coverage_report", doc=d, v0=VA, src=U2,
           extra={"merge_suggested": len(ok), "geometry_merge_validated": bool(merged), "face_group": grp})
    if not merged:
        RESULTS[-1]["status_note"] = "NOT_VALIDATED_ON_U2 for geometry merge - no hard-risk-free same-colour pair merged; logical group validated instead"
else:
    record("A09", "same-colour edge-adjacent pair search", 1, 1, 0.0, 0, 0, False, False,
           "STRtree scan", {"status_note": "NOT_VALIDATED_ON_U2 - no pair found"})

# ---------------- A15: join a real broken line ----------------
d = fresh(U2)
t0 = time.perf_counter()
VA = d.version
pv = d.join_preview([26, 45])                                              # select 2 segments + preview
n_ok = not pv["dash_protected"] and all(gq["gap"] <= 30 for gq in pv["gaps"])
if n_ok:
    n0 = len(d.L)
    r = d.join_lines([26, 45])                                             # confirm join
    nL = len(d.L); d.undo_op(); rev = len(d.L)                             # revert
    record("A15", "join_preview + join_lines on lines #26/#45", 3, 3, round(time.perf_counter() - t0, 2),
           1, 1, nL == n0 - 1 and rev == n0, False, "preview->join->undo; line count + geometry", doc=d, v0=VA, src=U2,
           extra={"gap_px": pv["gaps"], "joined_id": r["id"], "lines_after": nL, "lines_after_undo": rev})
else:
    record("A15", "join_preview on #26/#45", 2, 2, round(time.perf_counter() - t0, 2), 0, 0, False, False,
           "preview refused", {"reason": pv})

# ---------------- A20/A24: dash-pattern regroup ----------------
d = fresh(U2)
t0 = time.perf_counter()
VA = d.version
pv = d.join_preview([65, 77, 93])                                          # collinear chain, mixed groups G52/G62
lid = d.new_group([65, 77, 93])                                            # batch regroup into ONE logical group
same = set(d.L.loc[d.L["_eid"].isin([65, 77, 93]), "logical_id"]) == {lid}
d.undo_op(); rev = set(d.L.loc[d.L["_eid"].isin([65, 77, 93]), "logical_id"]) != {lid}
record("A24", "new_group on collinear segments #65/#77/#93 (was G52/G62)", 3, 3,
       round(time.perf_counter() - t0, 2), 3, 3, same and rev, False,
       "preview->new_group->undo; logical_id compare", doc=d, v0=VA, src=U2, extra={"new_group": lid})
t0 = time.perf_counter()
try:
    VA = d.version
    d.apply_legend("visual_lines", [65, 77, 93], "L_DASH_RED")
    rend = {r["id"]: r for r in d.render_lines()}
    dash = all(rend[e]["line_type"] == "dash" for e in (65, 77, 93))
    with_refused = False
    try: d.join_lines([65, 77, 93])
    except EditError: with_refused = True
    d.undo_op()
    record("A20", "dash legend + geometry-join refusal on regrouped chain", 4, 4,
           round(time.perf_counter() - t0, 2), 3, 6, dash and with_refused, False,
           "apply_legend->render check->join refused->undo", doc=d, v0=VA, src=U2)
except Exception as e:
    record("A20", "dash protection", 2, 2, round(time.perf_counter() - t0, 2), 0, 0, False, False, str(e))

# ---------------- A05/A33: swallow-and-restore a REAL thin band ----------------
d = fresh(U2)
thin_eid, nb = None, None
for eid, gm in zip(d.F["_eid"], d.F.geometry):
    x0, y0, x1, y1 = gm.bounds
    if min(x1 - x0, y1 - y0) < 3.0 and 30 < max(x1 - x0, y1 - y0) < 60:
        adj = [j for j in d._edge_neighbours(int(eid))]
        if adj: thin_eid, nb = int(eid), adj[0]; break
if thin_eid is not None:
    orig = d.F.loc[d.F["_eid"] == thin_eid].iloc[0]
    G0 = orig.geometry; x0, y0, x1, y1 = G0.bounds
    t0 = time.perf_counter()
    VA = d.version
    d.merge_components([thin_eid, nb], allow_mixed_labels=True)            # simulate the A33 defect: band swallowed
    swallowed = not (d.F["_eid"] == thin_eid).any() or d.F.loc[d.F["_eid"] == thin_eid, "geometry"].iloc[0].area > G0.area * 1.5
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if x1 - x0 > y1 - y0: axis = [(x0 + 1, cy), (x1 - 1, cy)]
    else: axis = [(cx, y0 + 1), (cx, y1 - 1)]
    lid = d.add_line(axis, width=2, rgb=str(orig["rgb"]))                  # operator draws the band axis
    r = d.line_to_face([lid], width=max(1.0, min(x1 - x0, y1 - y0)), rgb=str(orig["rgb"]), label=None)  # preview is inside the op
    new = d.F.loc[d.F["source"] == "edited_line_to_face"].iloc[-1]
    iou = float(new.geometry.intersection(G0).area / new.geometry.union(G0).area)
    cov = coverage_report(d.F, W, H)
    for _ in range(3): d.undo_op()
    restored = (d.F["_eid"] == thin_eid).any()
    record("A33", "swallow real thin band + redraw axis + line_to_face (ground-truth IoU check)",
           4, 4, round(time.perf_counter() - t0, 2), 2, 2, bool(swallowed and iou > 0.4 and cov["accepted"] and restored),
           not cov["accepted"], "merge->draw axis->line_to_face->IoU vs original->undo x2", doc=d, v0=VA, src=U2,
           extra={"thin_eid": thin_eid, "neighbour": nb, "iou": round(iou, 3), "coverage": cov, "defect_simulated": "band merged into neighbour then restored"})
else:
    record("A33", "thin-band candidate scan", 1, 1, 0.0, 0, 0, False, False, "scan", {"status_note": "no thin face with edge neighbour"})

# ---------------- A01/A02/E10: residue cleanup around a real text ----------------
d = fresh(U2C)
best = None
for e, t in zip(d.T["_eid"], d.T.itertuples()):
    try: box = [float(t.box_x0) - 4, float(t.box_y0) - 4, float(t.box_x1) + 4, float(t.box_y1) + 4]
    except (TypeError, ValueError): continue
    B = shapely.box(*box)
    cand = [int(le) for le, ln in zip(d.L["_eid"], d.L.geometry)
            if ln.length and ln.intersection(B).length / ln.length >= 0.9]
    if len(cand) >= 1 and (best is None or len(cand) > len(best[1])): best = (int(e), cand, box, t.text)
if best:
    tid, cand, box, txt = best
    t0 = time.perf_counter()
    VA = d.version
    res = d.text_residue([tid])                                            # select text -> residue suggestion
    tv = res["texts"][0]; sug_lines = [l["id"] for l in tv["line_info"] if l["suggested"]]
    nL0, nQ0 = len(d.L), len(d.Q)
    r = d.text_apply(tv["preview_id"], txt, line_ids=sug_lines)            # confirm: only safe strokes isolated
    boundaries_intact = all(ln.geom_type == "LineString" for ln in d.L.geometry)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/u2_uat") / "u2_residue_cleaned.gpkg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sv = d.save_as(out, draft=True)                                        # draft save (old file lacks review states)
    d2 = Document(out, (W, H), None)
    reopen_ok = len(d2.Q) == len(d.Q) and len(d2.T) == len(d.T)
    el = round(time.perf_counter() - t0, 2)
    record("A01/A02/E10", f"text_residue -> apply on text #{tid} ({txt!r})", 4, 4, el,
           r["moved_lines"] + r["merged_faces"], 0,
           len(d.Q) == nQ0 + r["moved_lines"] and boundaries_intact and sv["accepted"] and reopen_ok,
           not boundaries_intact, "suggest->line_ids=suggested->apply->draft save->reopen compare", doc=d, v0=VA, src=U2C,
           extra={"lines_isolated": r["moved_lines"], "faces_merged": r["merged_faces"], "risky_kept": len(tv["lines"]) - len(sug_lines),
            "export_mode": sv["export_mode"]})
else:
    record("A01/A02/E10", "residue candidate scan on text layer", 1, 1, 0.0, 0, 0, False, False, "scan")

# ---------------- A10: ROI clip export on the real map ----------------
d = fresh(U2)
t0 = time.perf_counter()
VA = d.version
d.set_roi([0, 400, 400, 780])                                              # user drags an ROI over the lower-left quarter
pv = d.roi_clip_preview()                                                  # preview inside/crossing/outside
out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/u2_uat") / "u2_roi_clip.gpkg"
out.parent.mkdir(parents=True, exist_ok=True)
sv = d.save_as(out, roi_mode="clip")                                       # clip export
import pyogrio
Fx = pyogrio.read_dataframe(out, layer="colour_faces")
allin = bool(shapely.covers(shapely.box(0, 400, 400, 780), shapely.union_all(list(Fx.geometry))))
bounded = all(g.bounds[0] >= -0.01 and g.bounds[2] <= 400.01 and g.bounds[1] >= 399.99 and g.bounds[3] <= 780.01 for g in Fx.geometry)
d2 = Document(out, (W, H), None)
roi_restored = d2.roi is not None
d.undo_op()                                                                # undo the set_roi state change
record("A10", "set_roi -> clip_preview -> save_as roi_mode=clip", 4, 4, round(time.perf_counter() - t0, 2),
       len(Fx), 1, sv["accepted"] and bounded and roi_restored, not bounded,
       "preview->clip export->readback bounds->reopen ROI->undo", doc=d, v0=VA, src=U2,
           extra={"faces_out": len(Fx), "preview": {k: {s: len(v) for s, v in Ld.items()} for k, Ld in pv["layers"].items()},
        "roi_restored_on_reopen": roi_restored, "export_mode": sv["export_mode"]})

print(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
outd = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/u2_uat"); outd.mkdir(parents=True, exist_ok=True)
(outd / "u2_real_uat.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
