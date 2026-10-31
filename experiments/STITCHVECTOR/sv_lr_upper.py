"""Phase A part 2: what perfect linking could recover from the frozen P1 fragments (descriptive, test seeds 2001-2005).
Each detected object is assigned to the truth line it mostly follows (>= 60% of its length within 2 px of that line and
nowhere else); impure objects follow 2+ truth lines over >= 10 px each and cannot be linked correctly without splitting."""
import json, sys
import numpy as np, shapely
from shapely.geometry import LineString
import sv_synth as S, sv_autoline as AL

TOL = 2.0


def main(out):
    seeds = json.load(open("autoline/autoline_test.json"))["seeds"]; res = {"tiles": {}, "by_line": {}}
    for s in seeds:
        img, truth, _ = S.generate(s); L, _ = AL.extract(img); det = [l["geom"] for l in L]
        T = [LineString(t["axis"]) for t in truth["lines"]]; Tb = [g.buffer(TOL) for g in T]
        share = np.array([[shapely.length(shapely.intersection(d, b)) / max(d.length, 1e-9) for b in Tb] for d in det])
        alen = np.array([[shapely.length(shapely.intersection(d, b)) for b in Tb] for d in det])
        impure = [j for j in range(len(det)) if (alen[j] >= 10).sum() >= 2]
        owner = np.where(share.max(1) >= 0.6, share.argmax(1), -1); owner[impure] = -2
        tile = {"objects": len(det), "impure_objects": len(impure), "impure_length": float(sum(det[j].length for j in impure)),
                "unassigned_objects": int((owner == -1).sum()), "lines": {}}
        for i, t in enumerate(truth["lines"]):
            g = T[i]; pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
            mine = [det[j] for j in np.nonzero(owner == i)[0]]
            U = shapely.union_all(mine) if mine else None; allU = shapely.union_all(det)
            r_own = float((shapely.distance(pts, U) <= TOL).mean()) if U is not None else 0.0
            r_all = float((shapely.distance(pts, allU) <= TOL).mean())
            tile["lines"][t["id"]] = {"fragments_owned": len(mine), "recall_from_owned_fragments": r_own, "recall_any_object": r_all,
                                      "links_needed_if_perfect": max(len(mine) - 1, 0)}
            b = res["by_line"].setdefault(t["id"], {"fragments": [], "r_own": [], "r_all": []})
            b["fragments"].append(len(mine)); b["r_own"].append(r_own); b["r_all"].append(r_all)
        res["tiles"][str(s)] = tile
    for k, b in res["by_line"].items():
        res["by_line"][k] = {"fragments_mean": float(np.mean(b["fragments"])), "recall_owned_mean": float(np.mean(b["r_own"])),
                             "recall_any_mean": float(np.mean(b["r_all"])), "recall_owned_min": float(np.min(b["r_own"]))}
    json.dump(res, open(out, "w"), indent=1)
    for k, v in sorted(res["by_line"].items()): print(k, {x: round(y, 3) for x, y in v.items()})
    for s, t in res["tiles"].items(): print(s, {k: (round(v, 1) if isinstance(v, float) else v) for k, v in t.items() if k != "lines"})


if __name__ == "__main__":
    main(sys.argv[1])
