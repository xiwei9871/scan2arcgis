"""R4-B0 Gate 1: per-instance failure attribution for thin units (rules: preregistration.json gate1).
Writes per-instance CSV (all small instances, all attributed methods), per-bin summaries, the 12 fixed cases
(index committed, images local only) and an evidence re-check of every label from the CSV columns.
Usage: r4b0_gate1.py <out_dir_committed> <local_dir>   (.venv-ml)
"""
import csv, json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import r4b0_common as C  # noqa: E402

G1 = C.G1


def recheck(r):
    """Recompute labels from CSV evidence only; must equal r['labels']."""
    f = []
    if r["boundary_truth_px"] == 0: f.append("NO_BOUNDARY_TRUTH")
    elif r["prob_boundary_cov"] not in (None, "") and float(r["prob_boundary_cov"]) < G1["boundary_cov_min"]: f.append("BOUNDARY_MISS")
    if r.get("pred_max_dist_px") not in (None, "") and r["dist_source"] not in (None, "", "ORACLE_OFFICIAL_DIST"):
        if abs(float(r["pred_max_dist_px"]) - float(r["official_max_dist_px"])) > G1["dist_err_px"]:
            f.append(G1["dist_label_by_source"][r["dist_source"]])
    mp, own, oc, bc = int(r["marker_px_in_instance"]), int(r["own_markers"]), float(r["own_region_cov"]), float(r["best_cov"])
    if mp == 0: f.append("SEED_MISSING")
    elif own == 0: f.append("SEED_FUSED")
    if own >= 2 and bc < 0.5 and oc >= G1["region_cov_min"]: f.append("OVER_SEG")
    if own >= 1 and oc < G1["region_cov_min"]: f.append("WATERSHED_ABSORBED")
    if oc >= G1["region_cov_min"] and float(r["best_iou"]) < 0.5 and int(r["best_region_area_px"]) > G1["overgrow_factor"] * int(r["area_px"]): f.append("REGION_OVERGROWN")
    if r.get("core_iou") not in (None, "") and float(r["core_iou"]) >= G1["eval_limit_core_iou_min"] and float(r["region_within_dilated_share"]) >= G1["eval_limit_within_min"]:
        f.append("EVAL_LIMIT")
    return ";".join(f)


def case_panel(S, Ms, P, code, k, out):
    sl = S["objects"][k - 1]; H, W = S["inst1"].shape; half = 64
    cy, cx = (sl[0].start + sl[0].stop) // 2, (sl[1].start + sl[1].stop) // 2
    y0, x0 = int(np.clip(cy - half, 0, H - 2 * half)), int(np.clip(cx - half, 0, W - 2 * half)); s = (slice(y0, y0 + 2 * half), slice(x0, x0 + 2 * half))
    rgb = cv2.cvtColor(cv2.imread(str(C.ROOT / "runs/r4a2" / code / "geotiff_rgb.png")), cv2.COLOR_BGR2RGB)[s]
    tgt = S["inst1"][s] == k
    def outline(p, m, col):
        e = m & ~cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool); p[e] = col; return p
    def up(p): return cv2.resize(p, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    pan = [up(rgb), up(outline((rgb * 0.6 + 100).astype(np.uint8), S["ub"][s], (255, 0, 255)))]
    pr = P["prob2"][s]; pp = cv2.applyColorMap((pr * 255).astype(np.uint8), cv2.COLORMAP_VIRIDIS)[..., ::-1].copy(); pan.append(up(outline(pp, tgt, (0, 255, 255))))
    dd = np.clip(P["dist2"][s] / 16, 0, 1); dp = cv2.applyColorMap((dd * 255).astype(np.uint8), cv2.COLORMAP_MAGMA)[..., ::-1].copy()
    dp[Ms["M2_hybrid"]["markers"][s] > 0] = (0, 255, 0); pan.append(up(outline(dp, tgt, (0, 255, 255))))
    r = Ms["M2_hybrid"]["regions"][s]; b = np.zeros(r.shape, bool); b[:, 1:] |= r[:, 1:] != r[:, :-1]; b[1:] |= r[1:] != r[:-1]
    rp = (rgb * 0.6 + 100).astype(np.uint8); rp[b] = (220, 0, 0); pan.append(up(outline(rp, tgt, (0, 255, 255))))
    cv2.imwrite(str(out), cv2.cvtColor(np.hstack(pan), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])


def main(out_dir, local_dir):
    out, loc = Path(out_dir), Path(local_dir).resolve(); out.mkdir(parents=True, exist_ok=True); (loc / "cases").mkdir(parents=True, exist_ok=True)
    rows, extra, keep = [], {}, {}
    for code in ("15023", "15041"):
        S, P = C.load_sheet(code); Ms = {}
        for m in G1["methods_attributed"]:
            M = C.run_method(m, S, P); r, e = C.analyze(S, M); rows += r; extra[f"{code}_{m}"] = e; Ms[m] = M
            print(code, m, "small recall", round(np.mean([x["success"] for x in r]), 4), e, flush=True)
        keep[code] = (S, P, Ms)
    cols = sorted({k for r in rows for k in r}, key=lambda c: (c not in rows[0], list(rows[0]).index(c) if c in rows[0] else 0, c))
    with open(out / "gate1_instances.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); [w.writerow(r) for r in rows]
    # evidence re-check from the written CSV
    rd = list(csv.DictReader(open(out / "gate1_instances.csv")))
    mism = [(r["sheet"], r["method"], r["instance"], r["labels"], recheck(r)) for r in rd if recheck(r) != r["labels"]]
    summ = {"evidence_recheck": {"rows": len(rd), "mismatches": len(mism), "examples": mism[:5]}, "matching": extra, "by_method": {}}
    for code in ("15023", "15041", "pooled"):
        for m in G1["methods_attributed"]:
            rs = [r for r in rows if r["method"] == m and (code == "pooled" or r["sheet"] == code)]
            summ["by_method"][f"{code}|{m}"] = {"own_width": C.summarize(rs, "width_bin_own"), "old_width": C.summarize(rs, "width_bin_old")}
    two = [r for r in rows if r["method"] == "M2_hybrid" and r.get("two_sided_identifiable") and r["width_bin_own"] in ("3-6", "6-10", "10-20")]
    summ["two_sided_M2_hybrid"] = {b: {"n_identifiable": len([r for r in two if r["width_bin_own"] == b]),
                                      "both_sides_detected": round(float(np.mean([r["both_sides_detected"] for r in two if r["width_bin_own"] == b] or [np.nan])), 4),
                                      "recall": round(float(np.mean([r["success"] for r in two if r["width_bin_own"] == b] or [np.nan])), 4)} for b in ("3-6", "6-10", "10-20")}
    # 12 fixed cases
    rng = np.random.default_rng(20261029); cases = []
    for b in ("3-6", "6-10", "10-20"):
        fails = sorted([r for r in rows if r["method"] == "M2_hybrid" and r["width_bin_own"] == b and not r["success"]], key=lambda r: (r["sheet"], r["instance"]))
        stages = sorted({r["primary_failure_stage"] for r in fails}, key=lambda s: -sum(r["primary_failure_stage"] == s for r in fails))
        need = 4 if b != "10-20" else 4; got = []
        for st in stages:
            grp = [r for r in fails if r["primary_failure_stage"] == st]
            take = min(2, need - len(got), len(grp))
            if take <= 0: break
            got += [grp[i] for i in sorted(rng.choice(len(grp), take, replace=False))]
        for r in got:
            code = r["sheet"]; S, P, Ms = keep[code]; img = loc / "cases" / f"{code}_{b}_{r['primary_failure_stage']}_{r['instance']}.jpg"
            case_panel(S, Ms, P, code, r["instance"] + 1, img)
            cases.append({k: r[k] for k in ("sheet", "instance", "width_bin_own", "width_own_px", "width_old_px", "area_px", "elongation", "best_iou", "labels",
                                              "primary_failure_stage", "prob_boundary_cov", "region_boundary_cov", "official_max_dist_px", "pred_max_dist_px",
                                              "marker_px_in_instance", "own_markers", "own_region_cov", "two_sided_identifiable")} | {"image_local": str(img.relative_to(C.ROOT))})
    summ["cases"] = cases
    json.dump(summ, open(out / "gate1_summary.json", "w"), indent=1, default=str)
    print("evidence recheck mismatches", len(mism), "| cases", len(cases))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
