"""EVALUATION ONLY: legend OCR accuracy on the same-colour-group swatches, against the human-confirmed
transcription in experiments/R3/review/same_colour_review_index.json (status must be CONFIRMED).
Scores every legend OCR run given on the command line (label=path/to/legend_ocr.json[,sheet]).
"""
import json, sys
from pathlib import Path

IDX = Path(__file__).parent / "review" / "same_colour_review_index.json"


def main(out_json, *runs):
    idx = json.load(open(IDX))
    if idx["status"] != "CONFIRMED": raise SystemExit(f"reference status is {idx['status']}, not CONFIRMED")
    res = {"reference": str(IDX.relative_to(Path(__file__).resolve().parents[2])) if IDX.is_absolute() else str(IDX),
           "reference_status": idx["status"], "runs": {}}
    for spec in runs:
        label, rest = spec.split("=", 1); path, sheet = rest.rsplit(",", 1)
        ocr = {r["swatch"]: r for r in json.load(open(path))["swatches"]}
        rows = idx["sheets"][sheet]
        ref = {r["swatch"]: (r["human_code_if_different"] or r["transcription"]) for r in rows if r["human_confirmed"]}
        per = {}
        for eng in json.load(open(path))["engines"]:
            hits = {s: ocr[s][eng]["code"] for s in ref}
            ok = [s for s in ref if hits[s] == ref[s]]
            per[eng] = {"correct": len(ok), "n": len(ref), "accuracy": len(ok) / len(ref),
                        "errors": [[s, ref[s], hits[s]] for s in ref if hits[s] != ref[s]]}
        res["runs"].setdefault(label, {})[sheet] = per
    for label, sheets in res["runs"].items():
        for sheet, per in sheets.items():
            print(label, sheet, {e: f"{v['correct']}/{v['n']}" for e, v in per.items()})
    # pooled over both sheets per run/engine
    res["pooled"] = {}
    for label, sheets in res["runs"].items():
        engs = next(iter(sheets.values())).keys()
        res["pooled"][label] = {e: {"correct": sum(sheets[s][e]["correct"] for s in sheets), "n": sum(sheets[s][e]["n"] for s in sheets)} for e in engs}
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1)
    print("pooled", {l: {e: f"{v['correct']}/{v['n']}" for e, v in p.items()} for l, p in res["pooled"].items()})


if __name__ == "__main__":
    main(*sys.argv[1:])
