# Studio V0.1 — architecture

```
Browser: editor page (tools/stitchvector_editor/static, unchanged) + Studio bar (tools/stitchvector_studio/static)
   │  /api/studio/*  (projects, upload, process, jobs, versions, exports, download)
   │  /api/<op>, /api/state, /api/raster/*  (editor ops on the project currently open)
Studio server  tools/stitchvector_studio/server.py  (stdlib HTTP, 127.0.0.1 only, one lock)
   ├── Workspace / jobs   projects.py      project folders, background job thread, versions, audit
   ├── Input adapters     inputs.py        any upload → raster_document.v1 + normalised PNG
   ├── Registry           registry.py      plugins/*/manifest.json, profiles/*.json, param schema check
   ├── Stage runner       stage_runner.py  one pinned plugin per subprocess (its own venv)
   ├── Exporter           exports.py       GPKG / Shapefile ZIP / GeoJSON (+ pixel JSON), read-back check
   └── Editor core        tools/stitchvector_editor/core.py (Document)
```

Choices:
- No new framework: the existing canvas editor already does dual view, layers, edits, undo/redo and visual diff; the Studio injects a top bar into the same page.
- Algorithms run out of process. A crash or dependency conflict in an OCR venv cannot take down the server; the B2c and PaddleOCR environments never share an interpreter.
- No queue service: one background thread per job, state written to `runs/<run_id>/manifest.json` after every stage, so a reload or server restart still shows the job state.
