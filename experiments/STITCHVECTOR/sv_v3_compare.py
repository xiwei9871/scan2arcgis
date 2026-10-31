"""2.0 vs 2.0+logical_id vs 3.0 (colour check at crossings + logical_id) on synthetic tiles.
Usage: sv_v3_compare.py <json_out> <seed> [<seed> ...]   (.venv-sv)"""
import json, sys, collections
import numpy as np, shapely
from shapely.geometry import LineString
import sv_synth as S, sv_autoline as AL, sv_v3 as V, sv_v3_eval as E


def methods(img):
    L2, _ = AL.extract(img); g2, _ = V.group(img, L2)
    objs3, g3, r3, info = V.run(img)
    one = lambda L: [{"geom": l["geom"], "parts": 1} for l in L]
    grp = lambda G: [{"geom": g["geom"], "parts": len(g["parts"])} for g in G]
    return {"2.0": one(L2), "2.0+id": grp(g2), "3.0": grp(g3)}, {"joins_refused_by_colour": info["joins_refused_by_colour"],
                                                                 "links": len(r3["links"]), "uncertain": len(r3["uncertain"])}


def main(out, seeds):
    res = {"seeds": seeds, "tiles": {}, "aggregate": {}}; agg = collections.defaultdict(lambda: collections.defaultdict(list))
    for s in seeds:
        img, truth, _ = S.generate(s); M, extra = methods(img); Tu = shapely.union_all([LineString(t["axis"]) for t in truth["lines"]]).buffer(3)
        tile = {"v3": extra}
        for k, objs in M.items():
            sc = E.score(objs, truth); tot = sum(o["geom"].length for o in objs); fal = sum(shapely.difference(o["geom"], Tu).length for o in objs)
            tile[k] = {"objects": sc["objects"], "parts": int(sum(o["parts"] for o in objs)), "mixed": sc["mixed_objects"], "false_share": fal / tot,
                       "lines": {lid: {**v, "verdict": E.verdict(v)} for lid, v in sc["lines"].items()}}
            a = agg[k]; a["objects"].append(sc["objects"]); a["parts"].append(tile[k]["parts"]); a["mixed"].append(sc["mixed_objects"]); a["false"].append(fal / tot)
            for v in sc["lines"].values(): a["recall"].append(v["recall"]); a["select"].append(v["select_count"]); a["v_" + E.verdict(v)].append(1)
        res["tiles"][str(s)] = tile
    for k, a in agg.items():
        res["aggregate"][k] = {"objects": int(sum(a["objects"])), "geometry_parts": int(sum(a["parts"])), "mixed_objects": int(sum(a["mixed"])),
                               "recall_mean": float(np.mean(a["recall"])), "select_mean": float(np.mean(a["select"])), "false_share_mean": float(np.mean(a["false"])),
                               "verdicts": {x[2:]: len(y) for x, y in a.items() if x.startswith("v_")}}
    json.dump(res, open(out, "w"), indent=1, default=float)
    for k, v in res["aggregate"].items(): print(k.ljust(7), json.dumps(v))


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in sys.argv[2:]])
