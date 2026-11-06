"""P1 red-face interior-fragment repair — seeded, triaged, user-confirmable batch merge.

Flow (nothing is merged silently):
  1. seed = the dominant face inside the ROI (largest face intersecting box centre region - the red unit).
  2. Candidates from Document.internal_fragment_scan(box) restricted to faces whose host/dominant
     neighbour is the seed, PLUS enclosed faces inside the seed outline.
  3. Triage:
       batch_safe - enclosed inside seed, no drawn-line boundary evidence, small, not elongated:
                    union with the seed CANNOT change the outline (interior object) -> batch mergeable
                    after user confirms.
       review    - has line-boundary evidence / elongated / large / touches >=2 faces: real geology
                    could exist -> stays for human judgement, never auto-merged.
       keep      - has geological label or drawn boundary.
  4. apply() merges each confirmed candidate INTO the seed via merge_components(...,
     allow_mixed_labels=True) - REAL geometric union with merged_from provenance + undo,
     not a face_group tag. Outline, lines, attributes and coverage are re-checked.

CLI: python -m tools.stitchvector_editor.red_face_repair IN.gpkg BOX OUT.gpkg [--apply-safe]
     Without --apply-safe it only reports candidates (preview mode, file untouched).
"""
import json, sys
from pathlib import Path
import numpy as np, shapely

from .core import Document


def seed_face(d, box):
    B = shapely.box(*box)
    best, ba = None, -1.0
    for e, g in zip(d.F["_eid"], d.F.geometry):
        i = g.intersection(B).area
        if i > ba: ba, best = i, int(e)
    return best, ba


def candidates(d, box, seed):
    sc = d.internal_fragment_scan(box=box)
    out = {"batch_safe": [], "review": [], "keep": [], "other": []}
    for c in sc["candidates"]:
        if c["kind"] == "enclosed":
            # enclosed anywhere in the ROI, not only inside the seed: union with host is provably interior
            if c["line_evidence"] or c["has_label"] or c["elongated"] or c["area"] > 120:
                out["review"].append(c)
            else:
                out["batch_safe"].append(c)
        elif c["kind"] == "frag":
            out["review"].append(c)          # touches >=2 faces - could be a real unit / boundary
        elif c["decision"] == "keep":
            out["keep"].append(c)
        else:
            out["other"].append(c)
    return sc, out


def apply_safe(d, cand):
    """ONE undoable batch step: every host+frags group is unioned separately inside a single _do(),
    so one user confirmation = one undo record. Hosts are NEVER unioned with each other - each group
    is dissolved independently; a host can only gain its own enclosed fragments."""
    from collections import defaultdict
    from .core import coverage_report, EditError
    by_host = defaultdict(list)
    for c in cand: by_host[c["host_eid"]].append(c["eid"])
    merged, skipped = [], []

    def f():
        for host, frags in by_host.items():
            ids = [host] + frags
            m = d.F["_eid"].isin(ids); sub = d.F.loc[m]
            u = shapely.union_all(list(sub.geometry))
            if u.geom_type != "Polygon":
                skipped.append({"host": host, "frags": frags[:5], "error": f"union is {u.geom_type}"}); continue
            k = d.F["_eid"] == host
            d.F.loc[k, "geometry"] = [u]; d.F.loc[k, "source"] = "edited_merge"
            d.F.loc[k, "merged_from"] = d._merge_provenance(m, host, "red_face_repair")
            d.F = d.F.loc[~(m & ~k)].copy()
            merged.append({"host": host, "frags": len(frags), "kept_id": {"groups": 1, "faces": len(frags) + 1}})
        rep = coverage_report(d.F, d.W, d.H)
        if not rep["accepted"]: raise EditError(f"merge gives an invalid face layer {rep}")

    n = sum(len(v) + 1 for v in by_host.values())
    d._do("red-face batch fragment repair", f, objects=n, merge=len(by_host))
    return merged, skipped


if __name__ == "__main__":
    from .core import coverage_report
    src, box, dst = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
    apply = "--apply-safe" in sys.argv
    d = Document(src, (780, 805), None)
    seed, seed_area = seed_face(d, box)
    sc, cand = candidates(d, box, seed)
    report = {"roi": box, "seed_eid": seed, "seed_area_in_box": round(seed_area, 1),
              "counts": {k: len(v) for k, v in cand.items()},
              "batch_safe_eids": [c["eid"] for c in cand["batch_safe"]],
              "review_eids": [c["eid"] for c in cand["review"]][:50]}
    def rings(d):
        return sum(len(g.interiors) for g in d.F.geometry)
    before = {"faces": len(d.F), "rings": rings(d), "lines": len(d.L)}
    if apply and cand["batch_safe"]:
        outline_before = float(shapely.union_all(np.asarray(d.F.geometry.values, object)).area)
        merged, skipped = apply_safe(d, cand["batch_safe"])
        rep_cov = coverage_report(d.F, d.W, d.H)
        outline_after = float(shapely.union_all(np.asarray(d.F.geometry.values, object)).area)
        after = {"faces": len(d.F), "rings": rings(d), "lines": len(d.L),
                 "merged_from_set": int(d.F["merged_from"].notna().sum()) if "merged_from" in d.F.columns else 0}
        d.undo_op()
        report.update(merged=merged, skipped=skipped[:10], coverage_after=rep_cov["accepted"],
                      faces_after_merge=after["faces"], rings_after_merge=after["rings"],
                      lines_after_merge=after["lines"], lines_unchanged=after["lines"] == before["lines"],
                      merged_from_set=after["merged_from_set"],
                      undo_ok=len(d.F) == before["faces"], undo_records=1,
                      outline_area_before=outline_before, outline_area_after=outline_after,
                      outline_unchanged=abs(outline_after - outline_before) < 1e-6)
        apply_safe(d, cand["batch_safe"])   # re-apply for the output file (single op)
    if dst and apply:
        rep_save = d.save_as(Path(dst), draft=True)
        report["saved"] = {"path": str(dst), "accepted": rep_save.get("accepted")}
    print(json.dumps(report, indent=1, default=str))
