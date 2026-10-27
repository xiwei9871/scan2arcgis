"""Synthetic geologic map generator with exact ground truth.

Purpose: give every recognizer the same input with a known answer, so that
algorithm comparisons are measurable. It is NOT a substitute for real-map
validation; it isolates specific difficulties (near colours, ink lines, text,
graticule, hillshade, JPEG/scan degradation).

Coordinates: image pixels, origin top-left, x right, y down (D0 convention).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np

# Palette loosely modelled on Chinese geological map conventions; includes
# deliberate near-colour pairs (index pairs (2,3), (6,7), (9,10)).
PALETTE = [
    ("Q",   (250, 246, 220)), ("N",   (255, 230, 150)), ("K1",  (150, 210, 120)),
    ("K2",  (165, 220, 130)), ("J3",  (120, 190, 230)), ("T",   (240, 170, 200)),
    ("P",   (190, 160, 210)), ("C",   (180, 150, 205)), ("D",   (200, 150, 110)),
    ("O",   (100, 170, 140)), ("S",   (110, 180, 150)), ("gamma", (230, 80, 90)),
]


@dataclass
class SynthConfig:
    seed: int = 0
    size: int = 1024
    n_seeds: int = 26
    n_classes: int = 12
    warp_amp: float = 38.0
    n_lenses: int = 6
    n_faults: int = 4
    contact_px: int = 1
    fault_px: int = 3
    text_labels: bool = True
    graticule: bool = True
    hillshade: float = 0.0          # 0..1 multiplicative relief shading
    color_jitter: float = 0.0       # global print/scan colour shift (RGB units)
    noise_sigma: float = 0.0
    blur_sigma: float = 0.0
    jpeg_quality: int = 0           # 0 = no JPEG
    intrusive_pattern: bool = True
    legend_panel: bool = True
    name: str = "synth"


@dataclass
class SynthMap:
    config: SynthConfig
    image: np.ndarray                    # HxWx3 uint8 RGB (map area + optional legend panel)
    map_box: tuple[int, int, int, int]   # x, y, w, h of the map area inside image
    labels: np.ndarray                   # HxW int16 class id (-1 outside map)
    instances: np.ndarray                # HxW int32 instance id
    faults: list[list[tuple[float, float]]]
    legend: list[dict] = field(default_factory=list)


def _smooth_noise(rng, h, w, scale, amp):
    small = rng.standard_normal((max(2, h // scale), max(2, w // scale))).astype(np.float32)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC) * amp


def _label_field(rng, cfg: SynthConfig) -> np.ndarray:
    n = cfg.size
    pts = rng.uniform(0, n, size=(cfg.n_seeds, 2)).astype(np.float32)
    # anisotropy: stretch to mimic elongated, banded outcrop patterns
    angle = rng.uniform(0, np.pi)
    rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]], np.float32)
    stretch = np.array([1.0, rng.uniform(2.0, 3.5)], np.float32)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    wx = xx + _smooth_noise(rng, n, n, 96, cfg.warp_amp) + _smooth_noise(rng, n, n, 24, cfg.warp_amp * 0.25)
    wy = yy + _smooth_noise(rng, n, n, 96, cfg.warp_amp) + _smooth_noise(rng, n, n, 24, cfg.warp_amp * 0.25)
    coords = np.stack([wx, wy], -1) @ rot.T * stretch
    seeds = pts @ rot.T * stretch
    best = np.full((n, n), np.inf, np.float32)
    owner = np.zeros((n, n), np.int32)
    for i, s in enumerate(seeds):
        d = ((coords - s) ** 2).sum(-1)
        m = d < best
        best[m] = d[m]
        owner[m] = i
    return owner


def _assign_classes(rng, owner: np.ndarray, n_seeds: int, n_classes: int) -> np.ndarray:
    # adjacency so that neighbours mostly get different classes (realistic contacts)
    adj = [set() for _ in range(n_seeds)]
    for a, b in ((owner[:, :-1], owner[:, 1:]), (owner[:-1, :], owner[1:, :])):
        diff = a != b
        for u, v in set(zip(a[diff].tolist(), b[diff].tolist())):
            adj[u].add(v)
            adj[v].add(u)
    cls = -np.ones(n_seeds, np.int32)
    usable = n_classes - 1  # last class reserved for intrusive bodies
    for i in rng.permutation(n_seeds):
        taken = {cls[j] for j in adj[i] if cls[j] >= 0}
        options = [c for c in range(usable) if c not in taken] or list(range(usable))
        cls[i] = rng.choice(options)
    return cls


def _add_lenses(rng, cls_map, inst_map, cfg, next_inst, intrusive_cls):
    n = cfg.size
    for k in range(cfg.n_lenses):
        cx, cy = rng.uniform(0.1 * n, 0.9 * n, 2)
        ax, ay = rng.uniform(25, 110), rng.uniform(15, 55)
        mask = np.zeros((n, n), np.uint8)
        cv2.ellipse(mask, (int(cx), int(cy)), (int(ax), int(ay)), float(rng.uniform(0, 180)), 0, 360, 1, -1)
        # irregular outline
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=int(rng.integers(0, 3)))
        c = intrusive_cls if k % 2 == 0 else int(rng.integers(0, cfg.n_classes - 1))
        cls_map[mask > 0] = c
        inst_map[mask > 0] = next_inst
        next_inst += 1
    return next_inst


def _fault_lines(rng, cfg):
    n = cfg.size
    lines = []
    for _ in range(cfg.n_faults):
        x0, y0 = rng.uniform(0, n, 2)
        ang = rng.uniform(0, np.pi)
        length = rng.uniform(0.4 * n, 1.1 * n)
        steps = 40
        pts = []
        for t in np.linspace(-0.5, 0.5, steps):
            bend = 25 * np.sin(t * np.pi * rng.uniform(0.5, 1.5))
            x = x0 + t * length * np.cos(ang) - bend * np.sin(ang)
            y = y0 + t * length * np.sin(ang) + bend * np.cos(ang)
            if 0 <= x < n and 0 <= y < n:
                pts.append((float(x), float(y)))
        if len(pts) >= 5:
            lines.append(pts)
    return lines


def _draw_polyline(img, pts, color, width):
    arr = np.round(np.array(pts)).astype(np.int32).reshape(-1, 1, 2)
    cv2.polylines(img, [arr], False, color, width, lineType=cv2.LINE_AA)


def _legend_panel(cfg: SynthConfig, classes: list[int], height: int) -> tuple[np.ndarray, list[dict]]:
    w = 260
    panel = np.full((height, w, 3), 255, np.uint8)
    entries = []
    y = 20
    for c in classes:
        code, rgb = PALETTE[c]
        x0, y0, x1, y1 = 16, y, 76, y + 30
        cv2.rectangle(panel, (x0, y0), (x1, y1), rgb, -1)
        cv2.rectangle(panel, (x0, y0), (x1, y1), (0, 0, 0), 1)
        cv2.putText(panel, code, (90, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
        entries.append({"legend_entry_id": f"L{c}", "legend_code": code, "class_id": c,
                        "fill_rgb": list(rgb), "swatch_box_panel": [x0 + 3, y0 + 3, x1 - x0 - 6, y1 - y0 - 6]})
        y += 42
        if y + 30 > height:
            break
    return panel, entries


def generate(cfg: SynthConfig) -> SynthMap:
    rng = np.random.default_rng(cfg.seed)
    n = cfg.size
    owner = _label_field(rng, cfg)
    cls_of_seed = _assign_classes(rng, owner, cfg.n_seeds, cfg.n_classes)
    cls_map = cls_of_seed[owner].astype(np.int16)
    inst_map = owner.astype(np.int32)
    intrusive_cls = cfg.n_classes - 1
    _add_lenses(rng, cls_map, inst_map, cfg, cfg.n_seeds, intrusive_cls)
    # instance ids must split same-class disconnected parts too
    final_inst = np.zeros_like(inst_map)
    nxt = 1
    for v in np.unique(inst_map):
        m = (inst_map == v).astype(np.uint8)
        k, cc = cv2.connectedComponents(m, connectivity=4)
        for j in range(1, k):
            final_inst[cc == j] = nxt
            nxt += 1

    img = np.zeros((n, n, 3), np.float32)
    for c in np.unique(cls_map):
        img[cls_map == c] = PALETTE[int(c)][1]
    if cfg.intrusive_pattern:  # '+' pattern inside intrusive bodies, like Chinese map conventions
        pat = np.zeros((n, n), np.uint8)
        for yy in range(6, n, 18):
            for xx in range(6 + (yy // 18 % 2) * 9, n, 18):
                cv2.line(pat, (xx - 3, yy), (xx + 3, yy), 1, 1)
                cv2.line(pat, (xx, yy - 3), (xx, yy + 3), 1, 1)
        sel = (pat > 0) & (cls_map == intrusive_cls)
        img[sel] = (150, 30, 40)
    if cfg.hillshade > 0:
        relief = _smooth_noise(rng, n, n, 40, 1.0) + _smooth_noise(rng, n, n, 10, 0.4)
        gy, gx = np.gradient(relief)
        shade = np.clip(1.0 - cfg.hillshade * (gx - gy) * 6, 1 - cfg.hillshade, 1 + 0.3 * cfg.hillshade)
        img *= shade[..., None]
    if cfg.color_jitter:
        img += rng.uniform(-cfg.color_jitter, cfg.color_jitter, 3)
    img = np.clip(img, 0, 255).astype(np.uint8)

    # contacts: thin dark lines along class boundaries (as printed maps do)
    edge = np.zeros((n, n), np.uint8)
    edge[:, 1:] |= (cls_map[:, 1:] != cls_map[:, :-1]).astype(np.uint8)
    edge[1:, :] |= (cls_map[1:, :] != cls_map[:-1, :]).astype(np.uint8)
    if cfg.contact_px > 1:
        edge = cv2.dilate(edge, np.ones((cfg.contact_px, cfg.contact_px), np.uint8))
    img[edge > 0] = (40, 40, 40)
    if cfg.graticule:
        for g in range(n // 5, n, n // 5):
            cv2.line(img, (g, 0), (g, n - 1), (60, 60, 200), 1)
            cv2.line(img, (0, g), (n - 1, g), (60, 60, 200), 1)
    faults = _fault_lines(rng, cfg)
    for f in faults:
        _draw_polyline(img, f, (10, 10, 10), cfg.fault_px)
    if cfg.text_labels:
        for v in range(1, nxt, 3):
            ys, xs = np.nonzero(final_inst == v)
            if len(xs) < 2500:
                continue
            i = len(xs) // 2
            code = PALETTE[int(cls_map[ys[i], xs[i]])][0]
            cv2.putText(img, code, (int(xs[i]) - 10, int(ys[i])), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)

    legend = []
    full = img
    map_box = (0, 0, n, n)
    labels = cls_map.copy()
    instances = final_inst
    if cfg.legend_panel:
        panel, legend = _legend_panel(cfg, sorted(int(c) for c in np.unique(cls_map)), n)
        full = np.concatenate([img, panel], axis=1)
        for e in legend:
            e["swatch_box"] = [e["swatch_box_panel"][0] + n, *e["swatch_box_panel"][1:]]
        labels = np.concatenate([labels, -np.ones((n, panel.shape[1]), np.int16)], axis=1)
        instances = np.concatenate([instances, np.zeros((n, panel.shape[1]), np.int32)], axis=1)
    if cfg.blur_sigma:
        full = cv2.GaussianBlur(full, (0, 0), cfg.blur_sigma)
    if cfg.noise_sigma:
        full = np.clip(full + rng.normal(0, cfg.noise_sigma, full.shape), 0, 255).astype(np.uint8)
    if cfg.jpeg_quality:
        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(full, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, cfg.jpeg_quality])
        full = cv2.cvtColor(cv2.imdecode(buf, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    return SynthMap(cfg, full, map_box, labels, instances, faults, legend)


def save(sm: SynthMap, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_dir / "image.png"), cv2.cvtColor(sm.image, cv2.COLOR_RGB2BGR))
    np.save(out_dir / "gt_labels.npy", sm.labels)
    np.save(out_dir / "gt_instances.npy", sm.instances)
    meta = {"config": asdict(sm.config), "map_box": sm.map_box, "legend": sm.legend,
            "faults": sm.faults, "palette": {c: list(rgb) for c, rgb in PALETTE}}
    (out_dir / "gt.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


# Benchmark suite: each variant isolates one difficulty seen on real maps.
SUITE = {
    "clean":      dict(),
    "near_color": dict(n_classes=12, warp_amp=45.0),
    "scan_jpeg":  dict(noise_sigma=6.0, blur_sigma=0.8, jpeg_quality=70, color_jitter=8.0),
    "hillshade":  dict(hillshade=0.35, noise_sigma=3.0, jpeg_quality=80),
    "thick_ink":  dict(contact_px=2, fault_px=4, noise_sigma=4.0, jpeg_quality=75),
}


def build_suite(out_root: Path, seeds=(0, 1, 2), size=1024) -> list[Path]:
    paths = []
    for name, kw in SUITE.items():
        for s in seeds:
            cfg = SynthConfig(seed=1000 * (list(SUITE).index(name) + 1) + s, size=size, name=f"{name}_s{s}", **kw)
            p = out_root / cfg.name
            save(generate(cfg), p)
            paths.append(p)
    return paths


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/synth_suite")
    for p in build_suite(root):
        print(p)
