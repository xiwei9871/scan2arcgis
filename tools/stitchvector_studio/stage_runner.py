"""Runs ONE pinned plugin stage in its own interpreter (process isolation).

Usage: <runtime python> stage_runner.py request.json   ->  writes request["result_path"]
The request is written by the Studio job manager and pins plugin id, version, entrypoint and the code hash taken at job
start. If the plugin code on disk no longer has that hash, the stage fails: an algorithm is never swapped mid-run.
"""
import hashlib, importlib, json, sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.stitchvector_studio.contracts import StageResult, RunContext, FAILED, OK, SCHEMAS, sha256_file, write_json_atomic  # noqa: E402


def code_hash(files):
    h = hashlib.sha256()
    for f in sorted(files):
        p = ROOT / f; h.update(f.encode()); h.update(sha256_file(p).encode() if p.is_file() else b"MISSING")
    return h.hexdigest()


def main(req_path):
    req = json.load(open(req_path, encoding="utf-8")); t0 = time.time(); out = Path(req["result_path"])
    try:
        now = code_hash(req["code_files"])
        if now != req["code_hash"]:
            raise RuntimeError(f"plugin code changed after the job was pinned ({req['code_hash'][:12]} -> {now[:12]}); refusing to run")
        mod, cls = req["entrypoint"].split(":"); plugin = getattr(importlib.import_module(mod), cls)()
        plugin.validate_inputs(req["inputs"], req["params"])
        res = plugin.run(RunContext(req["workdir"], req["run_id"], req["stage"]), req["inputs"], req["params"])
        if not isinstance(res, StageResult): raise TypeError("plugin.run must return a StageResult")
        if res.status == OK:
            for name, a in res.outputs.items():
                if a.get("schema") not in SCHEMAS: raise ValueError(f"output {name}: unknown schema {a.get('schema')}")
                if a["schema"] not in req["output_schemas"]: raise ValueError(f"output {name}: schema {a['schema']} not declared by the manifest")
                if not Path(a["path"]).is_file(): raise ValueError(f"output {name}: file missing")
                if sha256_file(a["path"]) != a.get("sha256"): raise ValueError(f"output {name}: sha256 mismatch")
        d = res.to_dict()
    except Exception as e:
        d = StageResult(FAILED, errors=[{"message": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-3000:]}]).to_dict()
    d["seconds"] = round(time.time() - t0, 2); d["python"] = sys.executable
    write_json_atomic(out, d)
    return 0 if d["status"] == OK else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
