"""Project workspace + background jobs.

workspace/projects/<project_id>/
  project.json                 name, created, current version, coordinate mode, history of runs/versions
  original/<safe name>         uploaded file, read-only (chmod 0444), never rewritten
  normalized/<doc_id>/         raster.png + raster_document.json (one per page / dpi choice)
  runs/<run_id>/manifest.json  pinned plugins (id, version, code hash, python), params, input/output hashes, stage states
  runs/<run_id>/<stage>/       plugin workdir (outputs + plugin.log)
  working/current.gpkg         the editable copy (never a run artifact itself)
  versions/vNNN.gpkg           saved snapshots (atomic: temp file -> verify -> rename)
  exports/<export_id>/         export packages
  audit/edits.jsonl            one line per saved edit session

Jobs run in a background thread; every plugin stage runs in its own interpreter via stage_runner.py.
A job pins plugin versions and code hashes when it is created, so swapping a plugin later never changes a running job.
"""
import json, os, re, shutil, stat, subprocess, sys, threading, time, uuid
from pathlib import Path
from . import registry as REG, inputs as INP
from .contracts import sha256_file, write_json_atomic, OK

ROOT = Path(__file__).resolve().parents[2]
RUNNER = Path(__file__).resolve().parent / "stage_runner.py"
STATES = ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


class ProjectError(Exception):
    pass


def safe_filename(name):
    base = Path(str(name)).name
    stem, ext = os.path.splitext(base)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)[:60].strip("._") or "upload"
    ext = re.sub(r"[^A-Za-z0-9.]", "", ext)[:8].lower()
    return stem + ext


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve(); (self.root / "projects").mkdir(parents=True, exist_ok=True)
        self.jobs = {}; self.lock = threading.Lock()

    # ---------- projects ----------
    def pdir(self, pid):
        if not ID_RE.match(str(pid)): raise ProjectError("bad project id")
        d = self.root / "projects" / pid
        if not d.is_dir(): raise ProjectError(f"project {pid} not found")
        return d

    def create(self, name):
        name = str(name or "").strip()[:80] or "untitled"
        pid = "p-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        d = self.root / "projects" / pid
        for s in ("original", "normalized", "runs", "working", "versions", "exports", "audit"): (d / s).mkdir(parents=True)
        pj = {"project_id": pid, "name": name, "created": time.time(), "source": None, "document": None, "runs": [], "versions": [],
              "current_version": None, "working_from": None, "coordinate_mode": None}
        write_json_atomic(d / "project.json", pj); return pj

    def get(self, pid):
        return json.load(open(self.pdir(pid) / "project.json", encoding="utf-8"))

    def _put(self, pid, pj): write_json_atomic(self.pdir(pid) / "project.json", pj)

    def list(self):
        out = []
        for p in sorted((self.root / "projects").glob("p-*/project.json")):
            try:
                j = json.load(open(p, encoding="utf-8"))
                out.append({k: j.get(k) for k in ("project_id", "name", "created", "current_version", "coordinate_mode")} | {"source": (j.get("source") or {}).get("name")})
            except Exception: pass
        return out

    # ---------- upload / normalise ----------
    def upload(self, pid, filename, data):
        d = self.pdir(pid); pj = self.get(pid)
        if len(data) > INP.MAX_BYTES: raise ProjectError(f"file too large (max {INP.MAX_BYTES // 2**20} MB)")
        name = safe_filename(filename); dst = d / "original" / name
        if dst.exists(): dst = d / "original" / f"{uuid.uuid4().hex[:6]}_{name}"
        tmp = dst.with_name("." + dst.name + ".part")
        with open(tmp, "wb") as f: f.write(data); f.flush(); os.fsync(f.fileno())
        try: info = INP.probe(tmp)
        except INP.InputError: tmp.unlink(); raise
        os.replace(tmp, dst); os.chmod(dst, stat.S_IRUSR | stat.S_IRGRP)
        pj["source"] = {"name": dst.name, "path": str(dst), "sha256": sha256_file(dst), **info}; self._put(pid, pj)
        return pj["source"]

    def normalise(self, pid, page=0, dpi=300):
        pj = self.get(pid)
        if not pj.get("source"): raise ProjectError("upload a file first")
        did = f"doc-p{int(page)}-d{int(dpi)}"; out = self.pdir(pid) / "normalized" / did
        doc = INP.normalise(pj["source"]["path"], out, page=page, dpi=dpi, document_id=did)
        pj["document"] = {"document_id": did, "path": str(out / "raster_document.json"), "width": doc["width"], "height": doc["height"],
                          "coordinate_mode": doc["coordinate_mode"], "crs": doc["crs"], "transform": doc["transform"]}
        pj["coordinate_mode"] = doc["coordinate_mode"]; self._put(pid, pj); return doc

    def raster_path(self, pid):
        pj = self.get(pid)
        if not pj.get("document"): raise ProjectError("no normalised raster yet")
        return Path(json.load(open(pj["document"]["path"], encoding="utf-8"))["raster_artifact"])

    # ---------- jobs ----------
    def pin_profile(self, profile_id, overrides=None):
        """resolve every stage of a profile to an installed plugin; record version, code hash, python. Raises if not runnable."""
        profs = REG.profiles()
        if profile_id not in profs: raise ProjectError(f"unknown pipeline profile {profile_id}")
        prof = profs[profile_id]; st = REG.profile_status(prof)
        if not st["runnable"]: raise ProjectError(f"profile {profile_id} is not runnable: " + "; ".join(f"{s['stage']}: {s['problem']}" for s in st["stages"] if not s["available"] and not s.get("optional")))
        overrides = overrides or {}; pinned = []
        for s in prof["stages"]:
            if s.get("builtin"): pinned.append({"stage": s["stage"], "plugin": s["plugin"], "builtin": True}); continue
            e = REG.find(s["plugin"])
            if not e["available"]:
                if s.get("optional"): pinned.append({"stage": s["stage"], "plugin": s["plugin"], "skipped": e["problem"]}); continue
                raise ProjectError(f"{s['plugin']}: {e['problem']}")
            m = e["manifest"]; params = REG.validate_params(m, overrides.get(s["stage"], {}))
            pinned.append({"stage": s["stage"], "plugin": m["plugin_id"], "version": m["version"], "entrypoint": m["entrypoint"],
                           "code_files": m["code_files"], "code_hash": e["code_hash"], "python": e["python"], "optional": bool(s.get("optional")),
                           "params": {**m.get("fixed_params", {}), **params}, "input_schemas": m["input_schemas"], "output_schemas": m["output_schemas"],
                           "timeout_s": int(m["runtime"].get("timeout_s", 1800))})
        return prof, pinned

    def start_job(self, pid, profile_id="legacy-b2c-v01", overrides=None):
        pj = self.get(pid)
        if not pj.get("document"): raise ProjectError("normalise the upload first")
        prof, pinned = self.pin_profile(profile_id, overrides)
        rid = "run-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]; rdir = self.pdir(pid) / "runs" / rid; rdir.mkdir()
        doc_path = Path(pj["document"]["path"])
        man = {"run_id": rid, "project_id": pid, "profile_id": profile_id, "profile_kind": prof.get("kind"), "options": prof.get("options", {}),
               "input": {"source_sha256": pj["source"]["sha256"], "document_id": pj["document"]["document_id"], "raster_document_sha256": sha256_file(doc_path),
                         "raster_sha256": sha256_file(self.raster_path(pid))},
               "studio_commit": _git_head(), "created": time.time(), "state": "QUEUED", "stages": [{**s, "state": "QUEUED"} for s in pinned]}
        write_json_atomic(rdir / "manifest.json", man)
        job = {"id": rid, "project_id": pid, "state": "QUEUED", "proc": None, "cancel": False}
        with self.lock: self.jobs[rid] = job
        pj["runs"].append({"run_id": rid, "profile_id": profile_id, "created": man["created"]}); self._put(pid, pj)
        threading.Thread(target=self._run, args=(job, rdir, doc_path), daemon=True).start()
        return man

    def _set(self, rdir, man, **kw):
        man.update(kw); write_json_atomic(rdir / "manifest.json", man)

    def _run(self, job, rdir, doc_path):
        man = json.load(open(rdir / "manifest.json", encoding="utf-8")); t0 = time.time()
        arts = {"raster": {"path": str(doc_path), "schema": "raster_document.v1", "sha256": sha256_file(doc_path)}}
        job["state"] = "RUNNING"; self._set(rdir, man, state="RUNNING", started=t0)
        try:
            for i, s in enumerate(man["stages"]):
                if job["cancel"]: raise _Cancelled()
                if s.get("builtin") or s.get("skipped"):
                    if s.get("plugin") == "builtin.quality" and "vectors" in arts: s["result"] = _quality(arts["vectors"]["path"])
                    s["state"] = "SKIPPED" if s.get("skipped") else "COMPLETED"; self._set(rdir, man); continue
                s["state"] = "RUNNING"; s["started"] = time.time(); self._set(rdir, man)
                sdir = rdir / s["stage"]; sdir.mkdir(exist_ok=True)
                ins = {k: arts[k] for k in ("raster",) if k in arts}
                req = {"run_id": man["run_id"], "stage": s["stage"], "entrypoint": s["entrypoint"], "code_files": s["code_files"], "code_hash": s["code_hash"],
                       "inputs": ins, "params": s["params"], "output_schemas": s["output_schemas"], "workdir": str(sdir), "result_path": str(sdir / "result.json")}
                write_json_atomic(sdir / "request.json", req)
                env = {**os.environ, "PYTHONPATH": str(ROOT)}
                with open(sdir / "stage.log", "w") as lg:
                    p = subprocess.Popen([s["python"], str(RUNNER), str(sdir / "request.json")], cwd=str(ROOT), stdout=lg, stderr=subprocess.STDOUT, env=env)
                    job["proc"] = p
                    while p.poll() is None:
                        if job["cancel"]: p.terminate(); p.wait(10); raise _Cancelled()
                        if time.time() - s["started"] > s["timeout_s"]: p.kill(); raise RuntimeError(f"stage {s['stage']} timed out after {s['timeout_s']} s")
                        time.sleep(0.3)
                    job["proc"] = None
                res = json.load(open(sdir / "result.json", encoding="utf-8")) if (sdir / "result.json").exists() else {"status": "FAILED", "errors": [{"message": f"runner exit {p.returncode}, no result"}]}
                s.update(seconds=round(time.time() - s["started"], 2), result={k: res.get(k) for k in ("status", "stats", "warnings", "errors", "provenance", "outputs")})
                if res.get("status") != OK:
                    s["state"] = "FAILED"
                    if s.get("optional"): self._set(rdir, man); continue          # e.g. OCR failure does not kill the vector result
                    raise RuntimeError(f"stage {s['stage']} ({s['plugin']}) failed: " + "; ".join(e.get("message", "") for e in res.get("errors", [])))
                s["state"] = "COMPLETED"; arts.update(res.get("outputs", {})); self._set(rdir, man)
            if "vectors" not in arts: raise RuntimeError("pipeline produced no vector_layers.v1 output")
            job["state"] = "COMPLETED"; self._set(rdir, man, state="COMPLETED", finished=time.time(), seconds=round(time.time() - t0, 1),
                                                     outputs={k: v for k, v in arts.items() if k != "raster"})
        except _Cancelled:
            job["state"] = "CANCELLED"
            for s in man["stages"]:
                if s["state"] in ("QUEUED", "RUNNING"): s["state"] = "CANCELLED"
            self._set(rdir, man, state="CANCELLED", finished=time.time())
        except Exception as e:
            job["state"] = "FAILED"
            for s in man["stages"]:
                if s["state"] in ("QUEUED", "RUNNING"): s["state"] = "NOT_RUN"
            self._set(rdir, man, state="FAILED", error=f"{type(e).__name__}: {e}", finished=time.time())

    def job(self, pid, rid):
        if not re.match(r"^run-[0-9-]+-[0-9a-f]{6}$", str(rid)): raise ProjectError("bad run id")
        mf = self.pdir(pid) / "runs" / rid / "manifest.json"
        if not mf.exists(): raise ProjectError("run not found")
        return json.load(open(mf, encoding="utf-8"))          # state survives a page reload / server restart (file, not memory)

    def cancel(self, pid, rid):
        self.job(pid, rid); j = self.jobs.get(rid)
        if not j or j["state"] not in ("QUEUED", "RUNNING"): raise ProjectError("job is not running")
        j["cancel"] = True; return True

    def run_log(self, pid, rid, stage):
        if stage not in ("vectorize", "ocr", "preprocess", "quality", "text_process", "geometry"): raise ProjectError("bad stage")
        d = self.pdir(pid) / "runs" / rid / stage; out = ""
        for f in ("stage.log", "plugin.log"):
            if (d / f).exists(): out += f"== {f}\n" + (d / f).read_text(errors="replace")[-20000:]
        return out

    # ---------- working copy / versions ----------
    def adopt_run(self, pid, rid):
        """copy a completed run's vectors (+ OCR candidates) into working/current.gpkg. Refused if the working copy
        has unsaved-to-version edits from another source (never overwrite human edits silently)."""
        pj = self.get(pid); man = self.job(pid, rid)
        if man["state"] != "COMPLETED": raise ProjectError("run not completed")
        d = self.pdir(pid); cur = d / "working" / "current.gpkg"
        if cur.exists() and pj.get("working_from") and pj.get("working_dirty"):
            raise ProjectError("the working copy has edits not saved as a version; save a version first")
        tmp = cur.with_name(".current.tmp.gpkg"); shutil.copyfile(man["outputs"]["vectors"]["path"], tmp); os.replace(tmp, cur)
        ocr = man["outputs"].get("ocr")
        if ocr:
            shutil.copyfile(ocr["path"], d / "working" / "ocr_candidates.json")
            if man.get("options", {}).get("create_text_drafts", True): self.drafts_info = add_text_drafts(cur, ocr["path"], man["run_id"])
        elif (d / "working" / "ocr_candidates.json").exists(): (d / "working" / "ocr_candidates.json").unlink()
        pj["working_from"] = {"run_id": rid, "kind": "run"}; pj["working_dirty"] = False; self._put(pid, pj)
        return cur

    def working(self, pid):
        p = self.pdir(pid) / "working" / "current.gpkg"
        if not p.exists(): raise ProjectError("no working copy; run a pipeline first")
        return p

    def next_version(self, pid):
        n = len(self.get(pid)["versions"]) + 1; return f"v{n:03d}"

    def record_version(self, pid, vname, path, note, edit_log):
        pj = self.get(pid)
        pj["versions"].append({"version": vname, "path": str(path), "sha256": sha256_file(path), "saved": time.time(), "note": str(note)[:200],
                               "from": pj.get("working_from"), "edits": len(edit_log)})
        pj["current_version"] = vname; pj["working_dirty"] = False; self._put(pid, pj)
        with open(self.pdir(pid) / "audit" / "edits.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"version": vname, "saved": time.time(), "edits": edit_log}, ensure_ascii=False, default=str) + "\n")

    def open_version(self, pid, vname):
        pj = self.get(pid); v = next((x for x in pj["versions"] if x["version"] == vname), None)
        if not v: raise ProjectError("unknown version")
        if sha256_file(v["path"]) != v["sha256"]: raise ProjectError(f"version {vname} changed on disk (hash mismatch); refusing to open")
        cur = self.pdir(pid) / "working" / "current.gpkg"; tmp = cur.with_name(".current.tmp.gpkg"); shutil.copyfile(v["path"], tmp); os.replace(tmp, cur)
        pj["working_from"] = {"version": vname, "kind": "version"}; pj["working_dirty"] = False; self._put(pid, pj); return cur

    def mark_dirty(self, pid, dirty=True):
        pj = self.get(pid); pj["working_dirty"] = bool(dirty); self._put(pid, pj)


class _Cancelled(Exception):
    pass


def _quality(gpkg):
    try:
        import pyogrio
        from tools.stitchvector_editor.core import coverage_report
        lay = [l[0] for l in pyogrio.list_layers(gpkg)]; F = pyogrio.read_dataframe(gpkg, layer="colour_faces")
        import numpy as np, shapely
        b = F.total_bounds; W, H = int(round(b[2])), int(round(b[3]))
        rep = coverage_report(F, W, H); area = shapely.area(np.asarray(F.geometry.values, object))
        return {"schema": "quality_report.v1", "faces": len(F), "lines": len(pyogrio.read_dataframe(gpkg, layer="visual_lines")) if "visual_lines" in lay else 0,
                "faces_le_5px2": int((area <= 5).sum()), "coverage": rep, "note": "geometry checks only; no geological truth"}
    except Exception as e:
        return {"schema": "quality_report.v1", "error": f"{type(e).__name__}: {e}"}


def _git_head():
    try: return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT, timeout=5).stdout.strip()
    except Exception: return None


def _quad_metrics(q):
    """text geometry from an OCR quad: glyph height = SHORT edge length (never the rotated bounding box height),
    reading angle = LONG edge direction normalised to (-90, 90]. Keeps rotated/vertical labels at a sane size."""
    import math
    if len(q) < 4: return 4.0, 0.0
    edges = [(q[(i + 1) % 4][0] - q[i][0], q[(i + 1) % 4][1] - q[i][1]) for i in range(4)]
    lens = [math.hypot(*e) for e in edges]
    li = max(range(4), key=lambda i: lens[i]); dx, dy = edges[li]
    ang = -math.degrees(math.atan2(dy, dx))
    while ang <= -90: ang += 180
    while ang > 90: ang -= 180
    if abs(ang) < 3: ang = 0.0
    return max(min(lens), 1.0), round(ang, 1)


def add_text_drafts(gpkg, ocr_json, run_id):
    """OCR candidates -> editable text_labels points (review_status OCR_DRAFT, geometry_status BACKGROUND_NOT_CLEARED).
    raw OCR string kept in ocr_text; `text` starts as the generic-rule suggestion (or the raw string); candidates and
    rule reasons kept as JSON. Faces and lines are not touched (no glyph removal)."""
    import geopandas as gpd, pyogrio
    from shapely.geometry import Point
    o = json.load(open(ocr_json, encoding="utf-8")); rows, pts = [], []
    for i, it in enumerate(o.get("items", [])):
        q = it["quad"]; xs = [p[0] for p in q]; ys = [p[1] for p in q]
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        h, ang = _quad_metrics(q)
        rows.append({"label_id": f"T{i:03d}", "text": it.get("suggested_text") or it["text"], "ocr_text": it["text"], "ocr_score": float(it.get("score", 0)),
                     "font_px": round(max(4.0, 0.8 * h), 1), "angle_deg": ang, "anchor": "center", "rgb": "#000000",
                     "box_x0": x0, "box_y0": y0, "box_x1": x1, "box_y1": y1, "source": f"ocr:{o.get('engine')}", "review_status": "OCR_DRAFT",
                     "geometry_status": "BACKGROUND_NOT_CLEARED", "candidate_texts": json.dumps(it.get("candidate_texts") or [it["text"]], ensure_ascii=False),
                     "rule_reasons": json.dumps(it.get("rule_reasons") or [], ensure_ascii=False), "ocr_engine": str(o.get("engine")), "ocr_model": str(o.get("model")),
                     "ocr_candidate_id": it.get("id"), "run_id": run_id})
        pts.append(Point((x0 + x1) / 2, (y0 + y1) / 2))
    if rows: gpd.GeoDataFrame(rows, geometry=pts).to_file(gpkg, layer="text_labels", driver="GPKG", engine="pyogrio")
    return {"drafts": len(rows), "rule_changed": sum(1 for r in rows if r["text"] != r["ocr_text"])}
