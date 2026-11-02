# Plugin contract (api_version 1)

A plugin is a folder `tools/stitchvector_studio/plugins/<name>/` with `manifest.json` and a Python module. Installing one is an administrator action (add the folder); uploads never carry code.

## manifest.json
| Key | Meaning |
|---|---|
| `plugin_id`, `version` | identity; registry picks the highest version unless pinned |
| `api_version` | must equal 1 |
| `stage` | one of `input, legend, preprocess, vectorize, ocr, text_process, geometry, quality, export` |
| `entrypoint` | `module:Class` |
| `input_schemas`, `output_schemas` | from `raster_document.v1, vector_layers.v1, ocr_candidates.v1, quality_report.v1, legend.v1` |
| `runtime` | `{"type": "python_subprocess", "python": "studio" or path, "timeout_s"}` |
| `parameters` | `{name: {type, default, min, max, enum}}`; checked before a job starts, unknown keys rejected |
| `fixed_params` | parameters recorded with the run but not user-settable |
| `code_files` | files hashed into `code_hash` |

## Interface
```python
class Plugin:
    def validate_inputs(self, inputs: dict, params: dict) -> None: ...
    def run(self, ctx: RunContext, inputs: dict, params: dict) -> StageResult: ...
```
`inputs` maps names to artifacts `{path, schema, sha256}`. `RunContext` gives only `workdir`, `run_id`, `stage`, `log()`. `StageResult(status, outputs, stats, warnings, errors, provenance)`; outputs are built with `contracts.artifact(path, schema)`.

The stage runner rejects an output whose schema is not declared, whose file is missing, or whose hash does not match. Plugins never read each other's temporary files: only declared artifacts pass between stages.

## Version pinning
At job creation the Studio records plugin id, version, entrypoint, code hash, interpreter and params in `runs/<run_id>/manifest.json`. Before running, the stage runner recomputes the code hash; if the code on disk changed, the stage fails instead of running different code.

## Installed plugins
| plugin_id | version | stage | runtime |
|---|---|---|---|
| stitchvector.vectorize.b2c | 1.0.0 | vectorize | .venv-sv |
| stitchvector.ocr.paddleocr | 1.0.0 | ocr (default) | runs/ocr_poc01/venvs/paddle |
| stitchvector.ocr.rapidocr | 1.0.0 | ocr (fallback) | .venv-ocr |
| stitchvector.vectorize.mock | 0.1.0 | vectorize (test) | .venv-sv |
| stitchvector.ocr.mock | 0.1.0 | ocr (test) | .venv-sv |
