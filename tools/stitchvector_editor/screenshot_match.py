"""Task 1: locate user-provided UAT screenshots inside candidate source maps.

Pipeline per (screenshot, candidate-map) pair:
  1. ORB feature match (multi-scale: screenshot is tried at 0.5x/0.75x/1x/1.25x/1.5x/2x in case it was
     taken at a different zoom) -> homography -> projected crop box in map coordinates.
  2. Multi-scale template match (cv2.matchTemplate on grayscale + edges) as a second opinion.
  3. Confidence = inlier ratio x template NCC, recorded with crop box + scale + sha256 of both files.

Reliability rule: confidence < MIN_CONF or homography fails => SOURCE_NOT_MATCHED - never substitute a
provisional region for the user's exact defect location.

Usage:
    python -m tools.stitchvector_editor.screenshot_match SHOT.png MAP.png [MAP2.png ...] [--out report.json]
"""
import hashlib, json, sys
from pathlib import Path
import cv2, numpy as np

MIN_CONF = 0.35          # below this -> SOURCE_NOT_MATCHED
MIN_INLIERS = 12


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def orb_match(shot_bgr, map_bgr):
    orb = cv2.ORB_create(nfeatures=4000)
    k1, d1 = orb.detectAndCompute(cv2.cvtColor(shot_bgr, cv2.COLOR_BGR2GRAY), None)
    k2, d2 = orb.detectAndCompute(cv2.cvtColor(map_bgr, cv2.COLOR_BGR2GRAY), None)
    if d1 is None or d2 is None or len(k1) < MIN_INLIERS or len(k2) < MIN_INLIERS:
        return None
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    good = [m for m, n in bf.knnMatch(d1, d2, k=2) if m.distance < 0.75 * n.distance]
    if len(good) < MIN_INLIERS: return None
    src = np.float32([k1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([k2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    H, msk = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if H is None: return None
    inl = int(msk.sum()); h, w = shot_bgr.shape[:2]
    corners = cv2.perspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2), H).reshape(-1, 2)
    x0, y0 = corners.min(0); x1, y1 = corners.max(0)
    return {"box": [float(x0), float(y0), float(x1), float(y1)], "inliers": inl, "inlier_ratio": inl / len(good), "H": H}


def template_ncc(shot_bgr, map_bgr, box):
    """NCC of the screenshot against the projected map crop (colour tolerant: compare on gradients)."""
    x0, y0, x1, y1 = [int(v) for v in box]
    if x1 - x0 < 10 or y1 - y0 < 10: return 0.0
    crop = map_bgr[max(0, y0):y1, max(0, x0):x1]
    if crop.size == 0: return 0.0
    s = cv2.resize(shot_bgr, (crop.shape[1], crop.shape[0]))
    e1 = cv2.Canny(cv2.cvtColor(s, cv2.COLOR_BGR2GRAY), 50, 150)
    e2 = cv2.Canny(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 50, 150)
    r = cv2.matchTemplate(e1.astype(np.float32), e2.astype(np.float32), cv2.TM_CCOEFF_NORMED)
    return float(r[0, 0])


def locate(shot_path, map_paths):
    shot = cv2.imread(str(shot_path))
    if shot is None: return {"status": "SOURCE_NOT_MATCHED", "reason": f"screenshot unreadable: {shot_path}"}
    results = []
    for mp in map_paths:
        m = cv2.imread(str(mp))
        if m is None: continue
        best = None
        for scale in (1.0, 0.75, 0.5, 1.25, 1.5, 2.0):
            s = shot if scale == 1.0 else cv2.resize(shot, None, fx=scale, fy=scale)
            r = orb_match(s, m)
            if not r: continue
            box = r["box"]
            ncc = template_ncc(s, m, box)
            conf = round(r["inlier_ratio"] * 0.6 + max(ncc, 0) * 0.4, 3)
            if best is None or conf > best["confidence"]:
                best = {"map": str(mp), "map_sha256": sha(mp), "box": [round(v, 1) for v in box], "shot_scale": scale,
                        "inliers": r["inliers"], "inlier_ratio": round(r["inlier_ratio"], 3), "ncc": round(ncc, 3), "confidence": conf}
        if best: results.append(best)
    results.sort(key=lambda r: -r["confidence"])
    top = results[0] if results else None
    return {"shot": str(shot_path), "shot_sha256": sha(shot_path), "status": "MATCHED" if top and top["confidence"] >= MIN_CONF else "SOURCE_NOT_MATCHED",
            "best": top, "candidates": results[:4]}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = None
    if "--out" in sys.argv: out = sys.argv[sys.argv.index("--out") + 1]
    rep = locate(args[0], args[1:])
    if out: Path(out).parent.mkdir(parents=True, exist_ok=True); Path(out).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1)[:1200])
