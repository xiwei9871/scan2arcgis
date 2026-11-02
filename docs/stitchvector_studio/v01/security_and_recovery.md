# Security and recovery

- Local only: binds 127.0.0.1; not a public service; no auth in V0.1.
- Uploads: size cap 500 MB, content sniffing, decode check, pixel cap 120 M; file names sanitised; stored read-only.
- No client path input: project, run, export ids are regex-checked; downloads resolve `Path(name).name` inside `exports/<id>/`.
- Plugins come only from `plugins/*/manifest.json`; parameters are schema-checked; each stage runs in a subprocess with a timeout.
- Pinned code hash: a plugin edited after a job started makes that stage fail, never silently run new code.
- Saves are atomic (temp → verify → rename); a failed save leaves the previous version and working copy untouched.
- Re-processing cannot replace a working copy with unsaved edits; runs and versions are never overwritten.
- Text clearing: no profile runs it; the editor's text-box tool keeps uncertain fragments pending and is undoable.
- Data protection: scans, PDFs, GPKGs, PNGs and model weights stay local; the repository pre-push hook is not bypassed.
