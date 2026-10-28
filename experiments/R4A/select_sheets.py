"""Draw R4-A training/validation sheets from the GSJ 1:50k catalogue snapshot (fixed seed, no peeking).

Rules (fixed before any download):
  * candidates: sheets offering BOTH the 200 dpi JPEG and a vector package, same year in both names
  * exclude region 08 entirely: dev sheets 08004/08001 and sealed holdout 08011/08021 are there,
    so no train/val sheet can touch them
  * train pool: regions 05, 06, 07; validation pool: regions 13, 14, 15 (far apart -> no shared edges)
  * ordered random draw with seed 20261028; sheets are taken in this order and a sheet that fails
    the pre-defined QC (download, vector integrity, registration check) is replaced by the next one
    in the same order. Targets: 10 train, 2 validation.
"""
import json, random, sys
from pathlib import Path

SEED, N_TRAIN, N_VAL = 20261028, 10, 2
TRAIN_REGIONS, VAL_REGIONS = {"05", "06", "07"}, {"13", "14", "15"}


def main(catalog, out):
    cat = json.load(open(catalog))
    ok = {k: v for k, v in cat.items() if v.get("year") == v.get("vct_year")}
    rng = random.Random(SEED)
    tr = sorted(k for k in ok if k[:2] in TRAIN_REGIONS); va = sorted(k for k in ok if k[:2] in VAL_REGIONS)
    rng.shuffle(tr); rng.shuffle(va)
    res = {"seed": SEED, "targets": {"train": N_TRAIN, "validation": N_VAL},
           "train_regions": sorted(TRAIN_REGIONS), "validation_regions": sorted(VAL_REGIONS),
           "excluded": {"region_08": "dev 08004/08001 and sealed holdout 08011/08021",
                        "year_mismatch": sorted(k for k in cat if k not in ok)},
           "train_order": [{"code": k, "year": ok[k]["year"], "jpg": ok[k]["jpg"], "vct": ok[k]["vct"]} for k in tr],
           "validation_order": [{"code": k, "year": ok[k]["year"], "jpg": ok[k]["jpg"], "vct": ok[k]["vct"]} for k in va]}
    json.dump(res, open(out, "w"), indent=1)
    print("train pool", len(tr), "first 14:", tr[:14]); print("val pool", len(va), "first 5:", va[:5])


if __name__ == "__main__":
    main(*sys.argv[1:3])
