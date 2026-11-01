"""T3.3 / T3.4: post-processing and multi-engine fusion, scored with the same rules as benchmark_runner.
Configs (all use the same truth and the same one-to-one matcher):
  1-3  single engine e2e (1x+2x union)
  4a   PaddleOCR e2e + GENERIC rules (no U2 knowledge)      4b  + U2 legend dictionary
  5    PaddleOCR boxes + Surya re-reads code-like boxes (no dictionary)
  6a   PaddleOCR boxes + vote of Paddle/Rapid/Surya readings + GENERIC   6b  + U2 legend dictionary
Fusion rule fixed here, written after seeing per-engine errors in this run (exploratory, not pre-registered):
  Chinese (any CJK char in Paddle reading) -> Paddle text. Code-like -> Surya text if it holds a subscript or Є, else Paddle.
  Votes (6): a candidate supported by >=2 engines after GENERIC wins, ties -> the code rule above.
Suggestions never overwrite raw text in the exported object; here we score `suggestion or raw` to measure what review would see."""
import csv, json, re
from collections import Counter
import benchmark_runner as B
import geo_postprocess as GP

CJK = re.compile(r"[一-鿿]")


def pick_code(p, s):
    if s and any(c in s for c in "₀₁₂₃₄₅₆₇₈₉Є") and not CJK.search(s): return s
    return p


def main():
    T, _ = B.load_truth(); D = GP.legend_dictionary(); D.pop("_unresolved", None); dic = set(D)
    paddle = B.union_scales(B.load_run("paddleocr_e2e_x1"), B.load_run("paddleocr_e2e_x2"))
    on = {e: {d["sample_id"]: d["raw_text"] for d in json.load(open(B.RAW / f"{e}_on_paddle_x2.json"))["detections"]} for e in ("rapidocr", "surya")}
    P = paddle["detections"]
    for i, p in enumerate(P): p["sid"] = f"P{i:03d}"
    pairs = B.match(P, T)

    def score(fn):
        return B.rec_score({j: fn(P[i]) for j, i in pairs.items()}, T)

    def gen(t): return GP.generic(t)[0]
    def leg(t): return GP.suggest(t, dic)[1] or "".join(t.split())
    def f5(p):
        t = p["raw_text"]
        return t if CJK.search(t) or not GP.is_code(t) else pick_code(t, on["surya"].get(p["sid"]))
    def vote(p):
        t = p["raw_text"]
        if CJK.search(t): return t
        c = Counter(gen(x) for x in (t, on["rapidocr"].get(p["sid"], ""), on["surya"].get(p["sid"], "")) if x)
        top = c.most_common(); 
        if top and top[0][1] >= 2 and (len(top) == 1 or top[0][1] > top[1][1]): return top[0][0]
        return gen(f5(p))
    def vote_dic(p):
        v = vote(p)
        if CJK.search(v): return v
        for x in (v, p["raw_text"], on["surya"].get(p["sid"], ""), on["rapidocr"].get(p["sid"], "")):
            s = GP.suggest(x, dic)[1]
            if s and s in dic: return s
        return v

    S = json.load(open(B.RES / "benchmark_summary.json"))["runs"]
    cfg = {"1_rapidocr": S["rapidocr_e2e_x1+x2"]["recognition"], "2_paddleocr": S["paddleocr_e2e_x1+x2"]["recognition"], "3_surya": S["surya_e2e_x1+x2"]["recognition"],
           "4a_paddle+generic": score(lambda p: gen(p["raw_text"])), "4b_paddle+generic+u2dict": score(lambda p: leg(p["raw_text"])),
           "5_paddle+surya_recheck": score(f5), "6a_vote3+generic": score(vote), "6b_vote3+generic+u2dict": score(vote_dic)}
    rows = []
    for k, r in cfg.items():
        for c in ("ALL", "GEOLOGICAL_CODE", "SPECIAL_SYMBOL", "CHINESE_PLACE_NAME", "NUMERIC_ATTITUDE", "LATIN_LABEL", "ON_GEOLOGICAL_LINE"):
            x = r.get(c)
            if x: rows.append({"config": k, "category": c, "n": x["n"], "exact_raw": x["exact_raw"], "acc_raw": x["acc_raw"], "acc_nfkc": x["acc_nfkc"],
                               "cer_raw": x["cer_raw"], "cer_nfkc": x["cer_nfkc"], "acc_raw_ci95": B.wilson(x["exact_raw"], x["n"])})
    w = csv.DictWriter(open(B.RES / "fusion_comparison.csv", "w", newline=""), fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    # per-object geological code errors for the main configs
    err = []
    for j, t in enumerate(T):
        if t["category"] != "GEOLOGICAL_CODE": continue
        i = pairs.get(j); p = P[i] if i is not None else None
        row = {"sample_id": t["sample_id"], "truth": t["raw_text"], "detected_by_paddle": p is not None}
        for k, fn in (("paddle_raw", lambda p: p["raw_text"]), ("surya_on_paddle", lambda p: on["surya"].get(p["sid"], "")), ("rapid_on_paddle", lambda p: on["rapidocr"].get(p["sid"], "")),
                      ("4a_generic", lambda p: gen(p["raw_text"])), ("6b_vote_dict", vote_dic)):
            row[k] = "" if p is None else fn(p)
        row["candidates_4b"] = "" if p is None else " | ".join(f"{c} ({r})" for c, r in GP.suggest(p["raw_text"], dic)[0])
        row["6b_correct"] = p is not None and B.norm(row["6b_vote_dict"], "raw") == B.norm(t["raw_text"], "raw")
        err.append(row)
    w = csv.DictWriter(open(B.RES / "geological_code_errors.csv", "w", newline=""), fieldnames=list(err[0])); w.writeheader(); w.writerows(err)
    json.dump({"legend_dictionary": D, "unresolved_legend_rows": GP.legend_dictionary().get("_unresolved", [])}, open(B.RES / "legend_dictionary.json", "w"), ensure_ascii=False, indent=1)
    print(f"{'config':28s} all    code   special place  (raw exact; n code={cfg['1_rapidocr']['GEOLOGICAL_CODE']['n']})")
    for k, r in cfg.items(): print(f"{k:28s} {r['ALL']['acc_raw']:<6} {r['GEOLOGICAL_CODE']['acc_raw']:<6} {r['SPECIAL_SYMBOL']['acc_raw']:<6} {r['CHINESE_PLACE_NAME']['acc_raw']}")


if __name__ == "__main__":
    main()
