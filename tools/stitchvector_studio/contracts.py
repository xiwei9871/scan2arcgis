"""Data contracts shared by the Studio server, the stage runner and every plugin.

Standard library only: this module is imported inside each plugin's own interpreter (e.g. the RapidOCR venv).

Schemas (version suffix is part of the name; a plugin declares which ones it reads and writes):
  raster_document.v1  JSON: normalised RGB raster + source provenance + coordinate mode / CRS / affine
  vector_layers.v1    GPKG: colour_faces (Polygon) + visual_lines (LineString), pixel coordinates (x right, y down)
  ocr_candidates.v1   JSON: {"schema", "engine", "items": [{"id", "quad", "text", "score", "status": "OCR_CANDIDATE"}]}
  quality_report.v1   JSON: topology + line/face residual statistics (appearance only, not geology)
  legend.v1           JSON: legend entries with status LEGEND_PENDING / LEGEND_CONFIRMED (interface only in V0.1)
"""
import hashlib, json, os, time, traceback
from pathlib import Path

API_VERSION = 1
SCHEMAS = ("raster_document.v1", "vector_layers.v1", "ocr_candidates.v1", "quality_report.v1", "legend.v1")
STAGES = ("input", "legend", "preprocess", "vectorize", "ocr", "text_process", "geometry", "quality", "export")
OK, FAILED = "OK", "FAILED"
TEXT_STATUSES = ("OCR_CANDIDATE", "OCR_DRAFT", "HUMAN_EDITED", "OCR_CONFIRMED", "TEXT_VECTOR_CREATED", "BACKGROUND_CLEAR_PENDING", "TEXT_LAYER_COMPLETE")


def sha256_file(p, chunk=1 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""): h.update(b)
    return h.hexdigest()


def write_json_atomic(path, obj):
    path = Path(path); tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, indent=1, ensure_ascii=False, default=str); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def artifact(path, schema):
    if schema not in SCHEMAS: raise ValueError(f"unknown schema {schema}")
    p = Path(path)
    if not p.is_file() or p.stat().st_size == 0: raise ValueError(f"artifact {p.name} missing or empty")
    return {"path": str(p), "schema": schema, "sha256": sha256_file(p), "bytes": p.stat().st_size}


class RunContext:
    """what a plugin may use: its own output folder, the run id, a log. Nothing else of the Studio."""
    def __init__(self, workdir, run_id, stage):
        self.workdir = Path(workdir); self.run_id = run_id; self.stage = stage
        self.workdir.mkdir(parents=True, exist_ok=True); self._log = open(self.workdir / "plugin.log", "a", encoding="utf-8")

    def log(self, msg):
        self._log.write(f"{time.strftime('%H:%M:%S')} {msg}\n"); self._log.flush()


class StageResult:
    def __init__(self, status=OK, outputs=None, stats=None, warnings=None, errors=None, provenance=None):
        self.status, self.outputs, self.stats = status, outputs or {}, stats or {}
        self.warnings, self.errors, self.provenance = warnings or [], errors or [], provenance or {}

    def to_dict(self):
        return {"status": self.status, "outputs": self.outputs, "stats": self.stats, "warnings": self.warnings,
                "errors": self.errors, "provenance": self.provenance}

    @staticmethod
    def failed(msg, exc=None):
        return StageResult(FAILED, errors=[{"message": str(msg), "trace": traceback.format_exc()[-3000:] if exc else ""}])


class PluginError(Exception):
    pass
