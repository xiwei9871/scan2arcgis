"""Plugin registry: discovers plugins/*/manifest.json, checks them, answers "which plugins serve stage X".

Manifests are JSON (no extra dependency). Plugins are installed by an administrator by adding a folder under
tools/stitchvector_studio/plugins/; uploaded files never carry code and are never loaded as plugins.
"""
import hashlib, json
from pathlib import Path
from .contracts import API_VERSION, SCHEMAS, STAGES, sha256_file

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = Path(__file__).resolve().parent / "plugins"
REQUIRED = ("plugin_id", "version", "api_version", "stage", "entrypoint", "input_schemas", "output_schemas", "runtime", "parameters", "code_files")
PARAM_TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool}


def code_hash(files):
    h = hashlib.sha256()
    for f in sorted(files):
        p = ROOT / f; h.update(f.encode()); h.update(sha256_file(p).encode() if p.is_file() else b"MISSING")
    return h.hexdigest()


def _check(m, src):
    miss = [k for k in REQUIRED if k not in m]
    if miss: return f"{src}: missing {miss}"
    if m["api_version"] != API_VERSION: return f"{src}: api_version {m['api_version']} not supported (Studio speaks {API_VERSION})"
    if m["stage"] not in STAGES: return f"{src}: unknown stage {m['stage']}"
    bad = [s for s in m["input_schemas"] + m["output_schemas"] if s not in SCHEMAS]
    if bad: return f"{src}: unknown schemas {bad}"
    if m["runtime"].get("type") != "python_subprocess": return f"{src}: runtime type must be python_subprocess"
    for k, p in m["parameters"].items():
        if p.get("type") not in PARAM_TYPES: return f"{src}: parameter {k} has bad type"
    return None


def resolve_python(runtime):
    """runtime.python: 'studio' or a repo-root-relative/absolute interpreter path."""
    import sys
    py = runtime.get("python", "studio")
    if py == "studio": return sys.executable
    p = Path(py).expanduser()
    if not p.is_absolute(): p = ROOT / p
    return str(p)


def discover(plugin_dir=PLUGIN_DIR):
    """-> list of entries {manifest, available, problem, code_hash, python}. Broken plugins are listed, not loaded."""
    out = []
    for mf in sorted(Path(plugin_dir).glob("*/manifest.json")):
        try: m = json.load(open(mf, encoding="utf-8"))
        except Exception as e: out.append({"manifest": {"plugin_id": mf.parent.name}, "available": False, "problem": f"bad JSON: {e}"}); continue
        prob = _check(m, mf.parent.name)
        e = {"manifest": m, "available": prob is None, "problem": prob}
        if prob is None:
            missing = [f for f in m["code_files"] if not (ROOT / f).is_file()]
            py = resolve_python(m["runtime"])
            if missing: e.update(available=False, problem=f"code files missing: {missing}")
            elif not Path(py).exists(): e.update(available=False, problem=f"runtime python not found: {py}")
            e["code_hash"] = code_hash(m["code_files"]); e["python"] = py
        out.append(e)
    return out


def find(plugin_id, version=None, plugin_dir=PLUGIN_DIR):
    c = [e for e in discover(plugin_dir) if e["manifest"].get("plugin_id") == plugin_id and (version is None or e["manifest"].get("version") == version)]
    if not c: raise KeyError(f"plugin {plugin_id}{'@' + version if version else ''} not installed")
    c.sort(key=lambda e: [int(x) if x.isdigit() else x for x in e["manifest"]["version"].split(".")]); return c[-1]


def validate_params(manifest, params):
    """fills defaults, rejects unknown keys and wrong types (schema check at the trust boundary)."""
    spec = manifest["parameters"]; params = dict(params or {})
    unknown = set(params) - set(spec)
    if unknown: raise ValueError(f"{manifest['plugin_id']}: unknown parameters {sorted(unknown)}")
    out = {}
    for k, p in spec.items():
        v = params.get(k, p.get("default"))
        t = PARAM_TYPES[p["type"]]
        if v is None or (isinstance(v, bool) and p["type"] in ("number", "integer")) or not isinstance(v, t):
            raise ValueError(f"{manifest['plugin_id']}: parameter {k} must be {p['type']}")
        if "enum" in p and v not in p["enum"]: raise ValueError(f"{manifest['plugin_id']}: {k} must be one of {p['enum']}")
        if "min" in p and v < p["min"] or "max" in p and v > p["max"]: raise ValueError(f"{manifest['plugin_id']}: {k} out of range")
        out[k] = v
    return out


PROFILE_DIR = Path(__file__).resolve().parent / "profiles"


def profiles():
    return {p.stem: json.load(open(p, encoding="utf-8")) for p in sorted(PROFILE_DIR.glob("*.json"))}


def profile_status(prof, plugin_dir=PLUGIN_DIR):
    """per stage: plugin id + availability; NOT_IMPLEMENTED stages are reported as such and make the profile not runnable."""
    inst = {e["manifest"].get("plugin_id"): e for e in discover(plugin_dir)}; st = []
    for s in prof["stages"]:
        if s.get("status") == "NOT_IMPLEMENTED": st.append({**s, "available": False, "problem": "NOT_IMPLEMENTED"}); continue
        if s.get("builtin"): st.append({**s, "available": True, "problem": None}); continue
        e = inst.get(s["plugin"]); ok = bool(e and e["available"])
        st.append({**s, "available": ok, "problem": None if ok else (e["problem"] if e else "not installed")})
    return {"profile_id": prof["profile_id"], "kind": prof.get("kind"), "runnable": all(x["available"] or x.get("optional") for x in st), "stages": st}
