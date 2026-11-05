"""StitchVector Studio V0.1 - local web server (stdlib HTTP, binds 127.0.0.1 only).

Usage: python -m tools.stitchvector_studio.server --workspace ~/geomap2arcgis/runs/stitchvector/studio_ws [--port 8820]

Routes
  GET  /                                 Studio page (projects / import / process / export) + editor canvases
  GET  /api/studio/plugins               registry: installed plugins, availability, problems
  GET  /api/studio/pipelines             profiles with per-stage status (NOT_IMPLEMENTED stages shown, never run)
  GET  /api/studio/projects              list
  POST /api/studio/projects              {"name"} -> project
  GET  /api/studio/projects/<id>         project.json
  POST /api/studio/projects/<id>/upload  raw body (Content-Type application/octet-stream), ?filename=
  POST /api/studio/projects/<id>/normalise {"page", "dpi"}
  POST /api/studio/projects/<id>/process {"profile_id", "overrides"} -> run manifest (background job)
  GET  /api/studio/projects/<id>/jobs/<run_id>          manifest (state survives reload / restart)
  POST /api/studio/projects/<id>/jobs/<run_id>/cancel
  GET  /api/studio/projects/<id>/jobs/<run_id>/log?stage=
  POST /api/studio/projects/<id>/adopt   {"run_id"} -> copy run output to working/current.gpkg and open it
  POST /api/studio/projects/<id>/open    {"version"?} -> open working copy (or a saved version) in the editor
  POST /api/studio/projects/<id>/save    {"note"} -> versions/vNNN.gpkg (atomic, verified) and working copy updated
  POST /api/studio/projects/<id>/exports {"format", "layers", "allow_pixel_space"} -> export manifest
  GET  /api/studio/projects/<id>/exports/<export_id>/<file>   download
  GET  /api/studio/projects/<id>/thumb?page=   PDF / TIFF page thumbnail (PNG)
All editor routes of tools/stitchvector_editor (/api/state, /api/<op>, /api/raster/<k>, /image) act on the project
currently opened in the editor. Clients never send server file paths; every file is resolved from a project id.
"""
import argparse, io, json, re, shutil, sys, threading, time, traceback, uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.stitchvector_editor import server as ED  # noqa: E402
from tools.stitchvector_editor.core import EditError  # noqa: E402
from tools.stitchvector_studio import registry as REG, inputs as INP, exports as EXP  # noqa: E402
from tools.stitchvector_studio.projects import Workspace, ProjectError  # noqa: E402
from tools.stitchvector_studio.contracts import sha256_file  # noqa: E402

HERE = Path(__file__).resolve().parent
WS = None
OPEN = {"pid": None, "from": None}
MAX_UPLOAD = INP.MAX_BYTES
PID_RE = re.compile(r"^p-[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
EXP_RE = re.compile(r"^e-[0-9a-f]{10}$")


def _pid(s):
    if not PID_RE.match(s or ""): raise ProjectError("bad project id")
    WS.get(s); return s


def open_in_editor(pid):
    """load the project's working GPKG + normalised raster into the editor STATE (same process, same lock)."""
    work = WS.working(pid); ras = WS.raster_path(pid); d = WS.pdir(pid)
    ocr = d / "working" / "ocr_candidates.json"
    ED.STATE.clear(); ED.STATE["out_dir"] = d / "versions" / "_editor_tmp"; ED.STATE["out_dir"].mkdir(parents=True, exist_ok=True)
    ED.open_doc(ras, work, None, ocr if ocr.exists() else None)
    OPEN.update(pid=pid, opened=time.time())


def close_editor():
    """unload the editor document. Refused while it has unsaved edits (never drop human edits silently)."""
    d = ED.STATE.get("doc")
    if d is not None and d.dirty: raise ProjectError("the open project has unsaved edits: save a version first")
    ED.STATE.clear(); OPEN.update(pid=None)


def editor_doc(pid):
    if OPEN["pid"] != pid or "doc" not in ED.STATE: raise ProjectError("this project is not open in the editor; open it first")
    return ED.STATE["doc"]


def save_version(pid, note):
    """editor document -> versions/vNNN.gpkg (Document.save_as: temp file, read-back verify, rename) -> working copy."""
    import os
    d = editor_doc(pid); vname = WS.next_version(pid); dst = WS.pdir(pid) / "versions" / f"{vname}.gpkg"
    rep = d.save_as(dst, draft=True)                      # a version is a working draft: unreviewed texts stay draft, never silently formal
    edits = list(d.log)
    cur = WS.pdir(pid) / "working" / "current.gpkg"; tmp = cur.with_name(".current.tmp.gpkg")
    shutil.copyfile(dst, tmp); os.replace(tmp, cur)
    WS.record_version(pid, vname, dst, note, edits)
    pj = WS.get(pid); pj["working_from"] = {"version": vname, "kind": "version"}; WS._put(pid, pj)
    open_in_editor(pid)                                   # reopen from the saved file: what you see is what was saved
    return {"version": vname, "path_in_project": f"versions/{vname}.gpkg", "sha256": sha256_file(dst),
            **{k: rep.get(k) for k in ("accepted", "readback_matches_memory", "input_sha256_unchanged")}}


def thumb(pid, page):
    from PIL import Image
    pj = WS.get(pid); src = Path(pj["source"]["path"]); kind = pj["source"]["source_type"]; page = int(page)
    if kind == "PDF":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(src)); pg = pdf[page]; w, h = pg.get_size(); im = pg.render(scale=min(200 / max(w, h), 2.0)).to_pil().convert("RGB"); pdf.close()
    elif kind in ("TIFF", "GEOTIFF"):
        im = Image.fromarray(INP._tiff_page(src, page))
    else:
        im = Image.open(src).convert("RGB")
    im.thumbnail((200, 200)); b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


def studio_page():
    """editor page (unchanged file) + Studio bar: one source of truth for the editor controls."""
    html = (ROOT / "tools/stitchvector_editor/static/index.html").read_text(encoding="utf-8")
    bar = (HERE / "static/studio_bar.html").read_text(encoding="utf-8")
    html = html.replace("<title>", "<title>StitchVector Studio V0.1 | ", 1)
    html = html.replace("</head>", '<link rel="stylesheet" href="/studio.css"></head>', 1)
    html = html.replace('<div id="side">', bar + '<div id="side">', 1)
    html = html.replace('<script src="/app.js"></script>', '<script src="/editor.js"></script><script src="/studio.js"></script>', 1)
    return html.encode("utf-8")


class H(ED.H):
    def _json(self, code, obj): return self._send(code, obj)

    def _studio(self, method, parts, q, body):
        # parts: after /api/studio/
        if parts == ["plugins"] and method == "GET":
            return {"plugins": [{"plugin_id": e["manifest"].get("plugin_id"), "version": e["manifest"].get("version"), "stage": e["manifest"].get("stage"),
                                 "available": e["available"], "problem": e["problem"], "capabilities": e["manifest"].get("capabilities", []),
                                 "parameters": e["manifest"].get("parameters", {}), "code_hash": e.get("code_hash"), "notes": e["manifest"].get("notes")}
                                for e in REG.discover()]}
        if parts == ["pipelines"] and method == "GET":
            return {"pipelines": [{**REG.profile_status(p), "description": p.get("description"), "options": p.get("options", {})} for p in REG.profiles().values()]}
        if parts == ["projects"]:
            if method == "GET": return {"projects": WS.list()}
            close_editor(); return WS.create(str((body or {}).get("name", "project"))[:80])
        if not parts or parts[0] != "projects" or len(parts) < 2: raise ProjectError("unknown studio route")
        pid = _pid(parts[1]); rest = parts[2:]
        if not rest and method == "GET":
            pj = WS.get(pid); pj["open_in_editor"] = OPEN["pid"] == pid
            pj["has_working"] = (WS.pdir(pid) / "working" / "current.gpkg").exists(); return pj
        if rest == ["upload"] and method == "POST":
            fn = (q.get("filename") or ["upload"])[0]; src = WS.upload(pid, fn, body)
            return {"source": {k: v for k, v in src.items() if k != "path"} | {"filename": src["name"]}}
        if rest == ["normalise"] and method == "POST":
            b = body or {}; return {"document": WS.normalise(pid, int(b.get("page", 0)), int(b.get("dpi", 300)))}
        if rest == ["process"] and method == "POST":
            b = body or {}; return WS.start_job(pid, str(b.get("profile_id", "legacy-b2c-v01")), b.get("overrides") or {})
        if len(rest) >= 2 and rest[0] == "jobs":
            rid = rest[1]
            if len(rest) == 2 and method == "GET": return WS.job(pid, rid)
            if rest[2:] == ["cancel"] and method == "POST": WS.cancel(pid, rid); return {"cancel_requested": True}
            if rest[2:] == ["log"] and method == "GET": return {"log": WS.run_log(pid, rid, (q.get("stage") or ["vectorize"])[0])}
        if rest == ["adopt"] and method == "POST":
            WS.adopt_run(pid, str((body or {}).get("run_id"))); open_in_editor(pid); return {"opened": True}
        if rest == ["open"] and method == "POST":
            v = (body or {}).get("version")
            if v: WS.open_version(pid, str(v))
            open_in_editor(pid); return {"opened": True, "version": v}
        if rest == ["close"] and method == "POST":
            if OPEN["pid"] == pid: close_editor()
            return {"closed": True}
        if rest == ["save"] and method == "POST":
            return save_version(pid, (body or {}).get("note", ""))
        if rest == ["exports"] and method == "POST":
            b = body or {}; d = editor_doc(pid)
            if d.dirty: raise ProjectError("unsaved edits: save a version first (exports are made from a saved version)")
            pj = WS.get(pid); doc = json.load(open(pj["document"]["path"], encoding="utf-8"))
            eid = "e-" + uuid.uuid4().hex[:10]; out = WS.pdir(pid) / "exports" / eid
            meta = EXP.export(WS.working(pid), doc, str(b.get("format", "GPKG")), b.get("layers") or list(EXP.DEFAULT_LAYERS), out,
                              allow_pixel_space=bool(b.get("allow_pixel_space")), draft=bool(b.get("draft")))
            meta.pop("path", None); meta["export_id"] = eid; meta["download"] = f"/api/studio/projects/{pid}/exports/{eid}/{meta['file']}"
            meta["from_version"] = pj.get("current_version"); return meta
        if rest == ["ocr"] and method == "GET":
            f = WS.pdir(pid) / "working" / "ocr_candidates.json"
            if not f.exists(): return {"items": [], "engine": None}
            o = json.load(open(f, encoding="utf-8"))
            return {"engine": o.get("engine"), "items": [{k: it.get(k) for k in ("id", "quad", "text", "score", "status")} for it in o.get("items", [])]}
        if rest == ["thumb"] and method == "GET":
            return ("png", thumb(pid, (q.get("page") or ["0"])[0]))
        raise ProjectError("unknown studio route")

    def _studio_download(self, pid, eid, fn):
        if not EXP_RE.match(eid): raise ProjectError("bad export id")
        f = WS.pdir(_pid(pid)) / "exports" / eid / Path(fn).name
        if not f.is_file() or f.name.endswith(".manifest.json") and False: raise ProjectError("file not found")
        b = f.read_bytes(); self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream"); self.send_header("Content-Length", str(len(b)))
        self.send_header("Content-Disposition", f'attachment; filename="{f.name}"'); self.send_header("X-SHA256", sha256_file(f))
        self.end_headers(); self.wfile.write(b)

    def _route(self, method):
        u = urlparse(self.path); p = u.path; q = parse_qs(u.query)
        if p in ("/", "/index.html", "/studio"): return self._send(200, studio_page(), "text/html; charset=utf-8")
        if p == "/studio.css": return self._send(200, (HERE / "static/studio.css").read_bytes(), "text/css; charset=utf-8")
        if p == "/studio.js": return self._send(200, (HERE / "static/studio.js").read_bytes(), "text/javascript; charset=utf-8")
        if p == "/editor.js": return self._send(200, (ROOT / "tools/stitchvector_editor/static/app.js").read_bytes(), "text/javascript; charset=utf-8")
        if not p.startswith("/api/studio/"): return None
        parts = [x for x in p.removeprefix("/api/studio/").split("/") if x]
        try:
            if method == "GET" and len(parts) == 5 and parts[0] == "projects" and parts[2] == "exports":
                with ED.LOCK: return self._studio_download(parts[1], parts[3], parts[4])
            body = None
            if method == "POST":
                n = int(self.headers.get("Content-Length", 0))
                if n > MAX_UPLOAD: return self._send(413, {"ok": False, "error": "upload too large"})
                raw = self.rfile.read(n)
                body = raw if parts[-1:] == ["upload"] else (json.loads(raw or b"{}"))
            with ED.LOCK: r = self._studio(method, parts, q, body)
            if isinstance(r, tuple) and r[0] == "png": return self._send(200, r[1], "image/png")
            return self._send(200, {"ok": True, **r})
        except (ProjectError, INP.InputError, EXP.ExportError, EditError, ValueError, KeyError) as e:
            return self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc(); return self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        if self._route("GET") is not None: return
        p = self.path.split("?")[0]
        if p in ("/api/state", "/image") or p.startswith("/api/raster/"):
            if "doc" not in ED.STATE: return self._send(409, {"ok": False, "error": "no project open in the editor"})
            if p == "/api/state":
                with ED.LOCK:
                    s = ED.STATE["doc"].state(); pj = WS.get(OPEN["pid"])
                    s.update(image=pj["source"]["name"], gpkg=f"{pj['name']} / {pj.get('current_version') or 'working (from run)'}", out_dir=None, compare=None,
                             text_counts=ED.text_counts(ED.STATE["doc"]), project_id=OPEN["pid"], coordinate_mode=pj["document"]["coordinate_mode"],
                             working_from=pj.get("working_from"))
                    return self._send(200, s)
        return super().do_GET()

    def do_POST(self):
        if self._route("POST") is not None: return
        if "doc" not in ED.STATE: return self._send(409, {"ok": False, "error": "no project open in the editor"})
        op = self.path.split("?")[0].removeprefix("/api/")
        if op == "save": return self._send(400, {"ok": False, "error": "use Studio 'save version' (versions are kept in the project)"})
        super().do_POST()
        if OPEN["pid"] and op not in ("pick", "box", "group", "grow", "select_gesture", "grow_sel", "shrink_sel", "merge_preview", "heal_preview",
                                      "split_face_preview", "text_preview"):
            try: WS.mark_dirty(OPEN["pid"], ED.STATE["doc"].dirty)
            except Exception: pass


def main(argv=None):
    global WS
    ap = argparse.ArgumentParser(description="StitchVector Studio V0.1")
    ap.add_argument("--workspace", required=True); ap.add_argument("--port", type=int, default=8820); a = ap.parse_args(argv)
    WS = Workspace(Path(a.workspace).expanduser().resolve())
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"StitchVector Studio V0.1: http://127.0.0.1:{a.port}/  (workspace {WS.root})", flush=True)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass


if __name__ == "__main__":
    sys.exit(main())
