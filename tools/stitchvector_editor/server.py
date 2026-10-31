"""StitchVector Editor V0.1 - local HTTP server (stdlib only, binds 127.0.0.1).
Usage: python -m tools.stitchvector_editor.server --image scan.png --gpkg result.gpkg --out-dir edits/ [--port 8765]
The input GPKG is opened read-only; saves go to new files inside --out-dir only."""
import argparse, json, re, sys, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image
from .core import Document, EditError, FACE, LINE

HERE = Path(__file__).resolve().parent
STATE = {}


def open_doc(image, gpkg):
    im = Image.open(image); STATE.update(image=Path(image).resolve(), gpkg=Path(gpkg).resolve(), doc=Document(gpkg, im.size))


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
            s = STATE["doc"].state(); s.update(image=str(STATE["image"]), gpkg=str(STATE["gpkg"]), out_dir=str(STATE["out_dir"])); return self._send(200, s)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        if n > 2_000_000: return self._send(413, {"error": "request too large"})
        try: a = json.loads(self.rfile.read(n) or b"{}")
        except ValueError: return self._send(400, {"error": "bad json"})
        d = STATE["doc"]; op = self.path.split("?")[0].removeprefix("/api/")
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
    ap.add_argument("--port", type=int, default=8765); a = ap.parse_args(argv)
    out = Path(a.out_dir).resolve(); out.mkdir(parents=True, exist_ok=True); STATE["out_dir"] = out
    open_doc(a.image, a.gpkg)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"StitchVector Editor V0.1: http://127.0.0.1:{a.port}/  (image {a.image}, gpkg {a.gpkg}, saves to {out})", flush=True)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass


if __name__ == "__main__":
    sys.exit(main())
