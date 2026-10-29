"""R4-B0.1 Gate C1: validate the pre-registered ink-mass line-width estimator on 15023 at 0.5 / 0.75 / 1.0 / 1.5.
Rules: r4b0_1_preregistration.json c1. One run; on failure -> SCALE_ESTIMATOR_FAILED, no second estimator.
Usage: r4b0_1_c1.py <out_dir>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import r4b0_1_common as C1  # noqa: E402

V = C1.PR1["c1"]["validation"]


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    rgb = cv2.cvtColor(cv2.imread(str(C1.ROOT / "runs/r4a2/15023/geotiff_rgb.png")), cv2.COLOR_BGR2RGB)
    res = {"image": "runs/r4a2/15023/geotiff_rgb.png", "scales": {}}
    for s in V["scales"]:
        im = rgb if s == 1.0 else cv2.resize(rgb, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        r = C1.line_width(im); r["image_hw"] = list(im.shape[:2]); res["scales"][str(s)] = r
        print(s, {k: r[k] for k in ("median_width_px", "accepted_components", "accepted_length_px", "direction_ratio_diag_over_axial", "long_only_rel_change", "enough_samples")}, flush=True)
    w1 = res["scales"]["1.0"]["median_width_px"]
    chk = {"enough_samples": {s: v["enough_samples"] for s, v in res["scales"].items()}, "scale_error": {}, "direction_bias": {}, "text_contamination": {}}
    for s, v in res["scales"].items():
        dr, tc = v["direction_ratio_diag_over_axial"], v["long_only_rel_change"]
        chk["direction_bias"][s] = {"ratio": dr, "ok": dr is not None and 0.85 <= dr <= 1.18}
        chk["text_contamination"][s] = {"rel_change": tc, "ok": tc is not None and tc <= 0.15}
        if s != "1.0":
            rec = v["median_width_px"] / w1 if v["median_width_px"] and w1 else None
            err = abs(rec / float(s) - 1) if rec is not None else None
            chk["scale_error"][s] = {"recovered_factor": None if rec is None else round(rec, 4), "rel_error": None if err is None else round(err, 4),
                                     "ok": err is not None and err <= 0.15}
    rep = C1.line_width(rgb); first = {k: v for k, v in res["scales"]["1.0"].items() if k != "image_hw"}   # image_hw is added by this script, not by line_width
    chk["repeatability"] = {"identical": rep == first}
    ok = (all(chk["enough_samples"].values()) and all(v["ok"] for v in chk["scale_error"].values())
          and all(v["ok"] for v in chk["direction_bias"].values()) and all(v["ok"] for v in chk["text_contamination"].values())
          and chk["repeatability"]["identical"])
    res["checks"] = chk; res["verdict"] = "PASS" if ok else "SCALE_ESTIMATOR_FAILED"
    res["failed_checks"] = [f"{k}:{s}" for k in ("scale_error", "direction_bias", "text_contamination") for s, v in chk[k].items() if not v["ok"]] \
                           + [f"enough_samples:{s}" for s, v in chk["enough_samples"].items() if not v] + ([] if chk["repeatability"]["identical"] else ["repeatability"])
    json.dump(res, open(out / "c1_validation.json", "w"), indent=1, default=float)
    print("C1", res["verdict"], res["failed_checks"], json.dumps(chk["scale_error"]))


if __name__ == "__main__":
    main(sys.argv[1])
