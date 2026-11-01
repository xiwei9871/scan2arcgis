"""StitchVector Editor V0.1 - local HTTP server (stdlib only, binds 127.0.0.1).
Usage: python -m tools.stitchvector_editor.server --image scan.png --gpkg result.gpkg --out-dir edits/ [--port 8765]
The input GPKG is opened read-only; saves go to new files inside --out-dir only."""
import argparse, json, re, sys, threading, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image
from .core import Document, EditError, FACE, LINE

HERE = Path(__file__).resolve().parent
STATE = {}
LOCK = threading.Lock()   # one request touches the document at a time (ThreadingHTTPServer)


def open_doc(image, gpkg, compare=None, ocr_json=None):
    import numpy as np
    im = Image.open(image).convert("RGB"); a = np.asarray(im)
    STATE.update(image=Path(image).resolve(), gpkg=Path(gpkg).resolve(), doc=Document(gpkg, im.size, a), scan=a,
                 compare=Path(compare).resolve() if compare else None, ocr_json=Path(ocr_json).resolve() if ocr_json else None)
    STATE["ocr_candidates"] = None
    if ocr_json:
        STATE["ocr_candidates"] = len(json.load(open(ocr_json)).get("items", []))


def text_counts(d):
    """what the text layer really holds.
    ocr_candidates_in_json: OCR detections in the JSON (never turned into objects by the editor).
    text_objects: rows of text_labels (independent text objects).
    no_ocr_record: objects whose ocr_text is empty, so it is unknown whether a human confirmed the text
      (the full-sheet audit wrote the automatic OCR string into `text` and left ocr_text empty).
    equal_to_ocr / edited_from_ocr: objects with an OCR record whose text equals / differs from it.
    Human confirmation itself is not stored; none of these counts proves it."""
    T = d.T; n = len(T)
    o = [("" if v is None or (isinstance(v, float) and v != v) else str(v)) for v in (T["ocr_text"] if n else [])]
    t = [str(v) for v in (T["text"] if n else [])]
    none = sum(1 for x in o if not x); same = sum(1 for a, b in zip(t, o) if b and a == b)
    return {"ocr_candidates_in_json": STATE.get("ocr_candidates"), "text_objects": n, "no_ocr_record": none,
            "equal_to_ocr": same, "edited_from_ocr": n - none - same}


def _render_doc(d):
    from . import render as R
    return R.render_frames(d.F, d.L, None, (d.H, d.W))


def _render_compare():
    from . import render as R
    if STATE.get("compare") is None: raise EditError("no --compare GPKG given")
    if "compare_rgb" not in STATE: STATE["compare_rgb"] = R.render(STATE["compare"], STATE["scan"].shape[:2])[0]
    return STATE["compare_rgb"]


def safe_name(name):
    name = Path(str(name)).name
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name): raise EditError("file name may only use letters, digits, . _ -")
    return name if name.endswith(".gpkg") else name + ".gpkg"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"): return self._send(200, (HERE / "static/index.html").read_bytes(), "text/html; charset=utf-8")
        if p == "/app.js": return self._send(200, (HERE / "static/app.js").read_bytes(), "text/javascript; charset=utf-8")
        if p == "/image": return self._send(200, STATE["image"].read_bytes(), "image/png")
        if p == "/api/state":
            with LOCK:
                s = STATE["doc"].state(); s.update(image=str(STATE["image"]), gpkg=str(STATE["gpkg"]), out_dir=str(STATE["out_dir"]),
                                                   compare=str(STATE["compare"]) if STATE.get("compare") else None, text_counts=text_counts(STATE["doc"]))
                return self._send(200, s)
        if p.startswith("/api/raster/"):
            # PNG at the scan's exact pixel grid. render_current / render_compare: deterministic vector render.
            # residual_*: RAW per-pixel max |dR|,|dG|,|dB| as an 8-bit grey PNG (value = difference, no threshold).
            from . import render as R
            k = p.removeprefix("/api/raster/")
            try:
                with LOCK:
                    scan = STATE["scan"]
                    if k == "render_current": a = _render_doc(STATE["doc"])[0]
                    elif k == "render_compare": a = _render_compare()
                    elif k == "residual_scan_current": a = R.residual(scan, _render_doc(STATE["doc"])[0])[1]
                    elif k == "residual_scan_compare": a = R.residual(scan, _render_compare())[1]
                    elif k == "residual_compare_current": a = R.residual(_render_compare(), _render_doc(STATE["doc"])[0])[1]
                    else: return self._send(404, {"error": "unknown raster"})
                return self._send(200, R.png_bytes(a), "image/png")
            except EditError as e: return self._send(400, {"ok": False, "error": str(e)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > 2_000_000: return self._send(413, {"error": "request too large"})
        try: a = json.loads(self.rfile.read(n) or b"{}")
        except ValueError: return self._send(400, {"error": "bad json"})
        op = self.path.split("?")[0].removeprefix("/api/")
        with LOCK: return self._post(op, a)

    def _post(self, op, a):
        d = STATE["doc"]
        try:
            lay = LINE if a.get("layer") == "line" else FACE
            if op == "pick": r = {"ids": d.pick(float(a["x"]), float(a["y"]), lay)}
            elif op == "box": r = {"ids": d.box(float(a["x0"]), float(a["y0"]), float(a["x1"]), float(a["y1"]), lay)}
            elif op == "group": r = {"ids": d.group(int(a["id"]))}
            elif op == "grow": r = {"ids": d.adjacent_similar([int(i) for i in a["ids"]], float(a.get("de", 15)))}
            elif op == "recolour": d.recolour(lay, a["ids"], a["rgb"]); r = {}
            elif op == "rewidth": d.rewidth(a["ids"], a["width"]); r = {}
            elif op == "regroup": r = {"logical_id": d.new_group(a["ids"])}
            elif op == "delete": d.delete_lines(a["ids"]); r = {}
            elif op == "split": r = {"ids": d.split_line(int(a["id"]), float(a["x"]), float(a["y"]))}
            elif op == "draw": r = {"id": d.add_line(a["coords"], float(a.get("width", 2)), a.get("rgb", "#000000"), a.get("logical_id"))}
            elif op == "merge": r = {"id": d.merge_faces(a["ids"])}
            elif op == "line_to_face": r = d.line_to_face(a["ids"], a.get("width"), a.get("rgb"))
            elif op == "select_gesture":
                g = d.gesture(a["kind"], a["points"], float(a.get("radius", 0)))
                ids = d.select_region(g, lay, a.get("rule", "touch"), a.get("max_area"))
                base = set(int(i) for i in a.get("current", [])); mode = a.get("mode", "replace")
                ids = sorted(base | set(ids)) if mode == "add" else (sorted(base - set(ids)) if mode == "subtract" else sorted(ids))
                r = {"ids": ids}
            elif op == "grow_sel": r = {"ids": d.grow(a["ids"], int(a.get("steps", 1)))}
            elif op == "shrink_sel": r = {"ids": d.shrink(a["ids"], int(a.get("steps", 1)))}
            elif op == "merge_preview": r = d.merge_preview(a["ids"])
            elif op == "merge_groups": r = d.merge_components(a["ids"])
            elif op == "heal_preview": r = d.heal_preview(d.gesture("brush", a["points"], float(a.get("radius", 4))), float(a.get("max_area", 12)))
            elif op == "heal_apply": r = d.heal_apply(str(a["preview_id"]), a.get("accept_uncertain", []))
            elif op == "set_role": d.set_role(a["ids"], str(a["role"])); r = {}
            elif op == "apply_legend": d.apply_legend(lay, a["ids"], str(a["legend_id"])); r = {}
            elif op == "set_style": d.set_style(str(a["legend_id"]), dict(a["style"])); r = {}
            elif op == "split_face_preview": r = d.split_face_preview(int(a["id"]))
            elif op == "split_face_apply": r = d.split_face_apply(str(a["preview_id"]))
            elif op == "text_preview": r = d.text_preview([float(v) for v in a["box"]])
            elif op == "text_apply": r = d.text_apply(str(a["preview_id"]), a["text"], a.get("font_px"), float(a.get("angle_deg", 0)), a.get("rgb", "#000000"), a.get("assign"))
            elif op == "text_edit": d.edit_text(int(a["id"]), **{k: a[k] for k in ("text", "font_px", "angle_deg", "rgb", "x", "y") if k in a}); r = {}
            elif op == "text_delete": d.delete_text(int(a["id"])); r = {}
            elif op == "restore_residue": d.restore_residue_lines(a["ids"]); r = {}
            elif op == "undo": r = {"undone": d.undo_op()}
            elif op == "redo": r = {"redone": d.redo_op()}
            elif op == "save": r = d.save_as(STATE["out_dir"] / safe_name(a["name"]))
            else: return self._send(404, {"error": f"unknown op {op}"})
            return self._send(200, {"ok": True, **r})
        except (EditError, KeyError, ValueError, TypeError) as e:
            return self._send(400, {"ok": False, "error": str(e)})
        except Exception as e:
            traceback.print_exc(); return self._send(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})


def main(argv=None):
    ap = argparse.ArgumentParser(description="StitchVector Editor V0.1")
    ap.add_argument("--image", required=True); ap.add_argument("--gpkg", required=True); ap.add_argument("--out-dir", required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--compare", help="optional second GPKG (e.g. the original B2c) for the B2c / edited difference view")
    ap.add_argument("--ocr-json", help="optional OCR candidate JSON, only counted (never turned into text objects)"); a = ap.parse_args(argv)
    out = Path(a.out_dir).resolve(); out.mkdir(parents=True, exist_ok=True); STATE["out_dir"] = out
    open_doc(a.image, a.gpkg, a.compare, a.ocr_json)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"StitchVector Editor V0.1: http://127.0.0.1:{a.port}/  (image {a.image}, gpkg {a.gpkg}, saves to {out})", flush=True)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass


if __name__ == "__main__":
    sys.exit(main())
