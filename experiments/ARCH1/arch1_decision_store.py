"""ARCH-1 Gate 4: decision store for candidates (PROTECT / MERGE / UNCERTAIN) that survives merging.

A candidate record keeps its own geometry and evidence independently of the region partition, so a candidate that
is later absorbed by a neighbour can still be exported, re-checked or restored.
Record fields:
  cid            candidate id (stable)
  source         generator id ("C-RAG", "C-PAIR", "ORACLE_NARROW", ...)
  mask_rle       run-length encoding of the candidate mask (row-major over its bbox) + bbox
  width_est_px   predicted width (own-mask inscribed width)
  evidence       {feature: value} with the evidence group of each feature
  state          PROTECT | MERGE | UNCERTAIN
  state_reason   list of (feature, group) that triggered the state
  absorbed_into  final region id it ended up in (None if it survives as its own region)
  overlap_final  share of the candidate covered by its absorbing / own final region
Only PROTECT may later become a hard cut; in ARCH-1 no generator has a validated PROTECT evidence, so states are
recorded but not enforced.
"""
import json
import numpy as np

GROUPS = {"b2_med": "E-LINE", "de": "E-APP", "width": "E-GEO", "ink_share": "E-INK", "m1_mean": "E-REG", "m2_prob_mean": "E-REG"}


def rle(mask):
    flat = mask.ravel().astype(np.int8); d = np.diff(np.concatenate([[0], flat, [0]]))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
    return np.stack([starts, ends - starts], 1).ravel().tolist()


def unrle(r, shape):
    flat = np.zeros(shape[0] * shape[1], bool)
    for s, n in zip(r[::2], r[1::2]): flat[s:s + n] = True
    return flat.reshape(shape)


class DecisionStore:
    def __init__(self):
        self.records = []

    def add(self, source, mask_full, width, evidence, state="UNCERTAIN", reason=()):
        ys, xs = np.nonzero(mask_full)
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        rec = {"cid": len(self.records), "source": source, "bbox": [y0, y1, x0, x1], "mask_rle": rle(mask_full[y0:y1, x0:x1]),
               "area_px": int(mask_full.sum()), "width_est_px": float(width),
               "evidence": {k: {"value": float(v), "group": GROUPS.get(k, "E-GEO")} for k, v in evidence.items()},
               "state": state, "state_reason": list(reason), "absorbed_into": None, "overlap_final": None}
        self.records.append(rec); return rec["cid"]

    def mask(self, cid, shape):
        r = self.records[cid]; y0, y1, x0, x1 = r["bbox"]; m = np.zeros(shape, bool)
        m[y0:y1, x0:x1] = unrle(r["mask_rle"], (y1 - y0, x1 - x0)); return m

    def resolve(self, final_regions):
        """After merging: record which final region holds each candidate and whether it survived as its own region."""
        for r in self.records:
            m = self.mask(r["cid"], final_regions.shape); vals, cnt = np.unique(final_regions[m], return_counts=True)
            k = int(vals[cnt.argmax()]); share = float(cnt.max() / m.sum())
            region_area = int((final_regions == k).sum())
            survived = region_area <= 1.5 * r["area_px"] and share >= 0.8
            r["absorbed_into"] = None if survived else k; r["overlap_final"] = share

    def dump(self, path):
        json.dump({"schema": __doc__, "records": self.records}, open(path, "w"))

    @classmethod
    def load(cls, path):
        s = cls(); s.records = json.load(open(path))["records"]; return s
