# API (server binds 127.0.0.1 only)

| Method | Path | Body / query | Result |
|---|---|---|---|
| GET | /api/studio/plugins | | installed plugins, availability, problems, code hash |
| GET | /api/studio/pipelines | | profiles with per-stage status |
| GET/POST | /api/studio/projects | `{name}` | list / new project |
| GET | /api/studio/projects/{id} | | project.json + `has_working`, `open_in_editor` |
| POST | …/{id}/upload?filename= | raw bytes | source info (type by content) |
| POST | …/{id}/normalise | `{page, dpi}` | raster_document |
| POST | …/{id}/process | `{profile_id, overrides}` | run manifest (job runs in background) |
| GET | …/{id}/jobs/{run_id} | | manifest (from disk) |
| POST | …/{id}/jobs/{run_id}/cancel | | |
| GET | …/{id}/jobs/{run_id}/log?stage= | | stage + plugin log |
| POST | …/{id}/adopt | `{run_id}` | working copy from run, opened in editor |
| POST | …/{id}/open | `{version?}` | open working copy or a version |
| POST | …/{id}/save | `{note}` | new version (verified) |
| POST | …/{id}/exports | `{format, layers, allow_pixel_space}` | export manifest + download URL |
| GET | …/{id}/exports/{eid}/{file} | | file download (`X-SHA256` header) |
| GET | …/{id}/ocr, …/{id}/thumb?page= | | OCR candidates / page thumbnail |

Editor routes (`/api/state`, `/api/<op>`, `/api/raster/<k>`, `/image`) act on the project open in the editor; `/api/save` is refused (use versions). Errors: HTTP 400 `{ok:false, error}` for user errors, 409 when no project is open, 413 upload too large, 500 with exception type. Clients never send server paths; ids are regex-checked and every file is resolved inside the project folder.
