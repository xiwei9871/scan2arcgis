// StitchVector Studio V0.1 bar: projects, import, pipeline jobs, versions, export / download.
// Runs after the unchanged editor script (editor.js). Every request names a project id; no server paths are sent.
const SV = { pid: null, run: null, poll: null, ocr: null };
const $s = (id) => document.getElementById(id);
function smsg(t, ok) { const m = $s("sMsg"); m.style.color = ok ? "#060" : "#b00"; m.textContent = t || ""; }
async function sapi(method, path, body, raw) {
  const o = { method, headers: {} };
  if (raw) { o.body = raw; o.headers["Content-Type"] = "application/octet-stream"; }
  else if (body !== undefined) { o.body = JSON.stringify(body); o.headers["Content-Type"] = "application/json"; }
  const r = await fetch("/api/studio/" + path, o); const j = await r.json().catch(() => ({ ok: false, error: "bad response " + r.status }));
  if (!j.ok) throw new Error(j.error || ("HTTP " + r.status)); return j;
}
async function sguard(fn) { try { await fn(); } catch (e) { smsg(e.message); } }

async function loadProjects(select) {
  const r = await sapi("GET", "projects"); const s = $s("sProj"); s.innerHTML = '<option value="">（选择项目）</option>';
  for (const p of r.projects) { const o = document.createElement("option"); o.value = p.project_id; o.textContent = `${p.name} (${p.project_id.slice(-6)})`; s.append(o); }
  if (select) s.value = select;
}
async function loadPipelines() {
  const r = await sapi("GET", "pipelines"); const s = $s("sProfile"); s.innerHTML = "";
  for (const p of r.pipelines) { const o = document.createElement("option"); o.value = p.profile_id;
    o.textContent = `${p.profile_id}${p.runnable ? "" : "（未实现，不可运行）"}`; o.disabled = !p.runnable; o.title = p.description || ""; s.append(o); }
  s.value = "legacy-b2c-v01"; SV.pipelines = r.pipelines;
}
async function showProject() {
  if (!SV.pid) return; const p = await sapi("GET", "projects/" + SV.pid);
  const pages = p.source ? p.source.pages || [] : []; const ps = $s("sPage"); ps.innerHTML = "";
  (pages.length ? pages : [{ index: 0 }]).forEach(g => { const o = document.createElement("option"); o.value = g.index; o.textContent = g.index + (g.width ? ` (${g.width}×${g.height})` : ""); ps.append(o); });
  if (p.document) ps.value = p.document.page_index ?? 0;
  $s("sThumb").src = p.source ? `/api/studio/projects/${SV.pid}/thumb?page=${ps.value}&t=${Date.now()}` : "";
  const vs = $s("sVersions"); vs.innerHTML = '<option value="">（版本）</option>';
  for (const v of p.versions || []) { const o = document.createElement("option"); o.value = v.version; o.textContent = `${v.version} ${v.note || ""}`; vs.append(o); }
  if (p.current_version) vs.value = p.current_version;
  const cm = p.document ? p.document.coordinate_mode : null;
  $s("sCoord").textContent = !cm ? "" : cm === "GEOREFERENCED" ? `坐标：GEOREFERENCED ${p.document.epsg ? "EPSG:" + p.document.epsg : ""}` : "坐标：PIXEL_SPACE（成果未进行地理配准）";
  $s("sCoord").className = cm === "PIXEL_SPACE" ? "warn" : "";
  SV.project = p; return p;
}
async function openEditor(version) {
  await sapi("POST", `projects/${SV.pid}/open`, version ? { version } : {});
  await loadOcr(); img.src = "/image?t=" + Date.now();          // editor img.onload -> refresh() -> fit()
}
async function closeEditor() { if (SV.pid) await sapi("POST", `projects/${SV.pid}/close`, {}); S = null; SV.ocr = null; draw(); }
async function loadOcr() { try { SV.ocr = await sapi("GET", `projects/${SV.pid}/ocr`); } catch (e) { SV.ocr = null; } }

$s("sProj").onchange = () => sguard(async () => { SV.pid = $s("sProj").value || null; if (!SV.pid) return; const p = await showProject();
  if (p.has_working) { await openEditor(); smsg("已打开项目工作副本", true); } else { await closeEditor(); smsg("项目没有工作副本：先导入文件并开始矢量化", true); } });
$s("sNew").onclick = () => sguard(async () => { const n = prompt("项目名称", "u2"); if (!n) return; const p = await sapi("POST", "projects", { name: n });
  SV.pid = p.project_id; S = null; SV.ocr = null; draw(); await loadProjects(SV.pid); await showProject(); smsg("已新建项目 " + p.project_id, true); });
$s("sUpload").onclick = () => sguard(async () => {
  if (!SV.pid) throw new Error("先新建或选择项目"); const f = $s("sFile").files[0]; if (!f) throw new Error("先选择文件");
  smsg("上传中…", true); const r = await sapi("POST", `projects/${SV.pid}/upload?filename=${encodeURIComponent(f.name)}`, undefined, await f.arrayBuffer());
  await showProject(); smsg(`已导入 ${r.source.filename}：${r.source.source_type}，${(r.source.pages || []).length} 页`, true); });
$s("sPage").onchange = () => { if (SV.pid) $s("sThumb").src = `/api/studio/projects/${SV.pid}/thumb?page=${$s("sPage").value}&t=${Date.now()}`; };

function showJob(m) {
  const st = (m.stages || []).map(s => `${s.stage}:${s.plugin.split(".").pop()}${s.version ? "@" + s.version : ""}=${s.state}${s.seconds ? " " + s.seconds + "s" : ""}`).join(" | ");
  $s("sJob").textContent = `${m.run_id} ${m.state}  ${st}${m.error ? "  错误：" + m.error : ""}`;
}
$s("sProcess").onclick = () => sguard(async () => {
  if (!SV.pid) throw new Error("先选择项目");
  await sapi("POST", `projects/${SV.pid}/normalise`, { page: +$s("sPage").value, dpi: +$s("sDpi").value }); await showProject();
  const m = await sapi("POST", `projects/${SV.pid}/process`, { profile_id: $s("sProfile").value }); SV.run = m.run_id; showJob(m); smsg("任务已提交（后台运行）", true);
  clearInterval(SV.poll); SV.poll = setInterval(pollJob, 1000); });
async function pollJob() {
  if (!SV.run) return; let m;
  try { m = await sapi("GET", `projects/${SV.pid}/jobs/${SV.run}`); } catch (e) { smsg(e.message); clearInterval(SV.poll); return; }
  showJob(m);
  if (["COMPLETED", "FAILED", "CANCELLED"].includes(m.state)) {
    clearInterval(SV.poll);
    if (m.state === "COMPLETED") {
      await sguard(async () => { await sapi("POST", `projects/${SV.pid}/adopt`, { run_id: m.run_id }); await showProject(); await openEditor();
        const v = (m.stages.find(s => s.stage === "vectorize") || {}).result || {}; const o = (m.stages.find(s => s.stage === "ocr") || {}).result || {};
        smsg(`处理完成：面 ${(v.stats || {}).faces}，线 ${(v.stats || {}).lines}，OCR 候选 ${(o.stats || {}).candidates ?? "—"}（候选未确认）`, true); });
    } else smsg(`任务 ${m.state}${m.error ? "：" + m.error : ""}`);
  }
}
$s("sCancel").onclick = () => sguard(async () => { if (!SV.run) throw new Error("没有运行中的任务"); await sapi("POST", `projects/${SV.pid}/jobs/${SV.run}/cancel`); smsg("已请求取消", true); });
$s("sSave").onclick = () => sguard(async () => {
  if (!SV.pid) throw new Error("先选择项目"); const note = prompt("版本说明（可空）", "") ?? ""; const r = await sapi("POST", `projects/${SV.pid}/save`, { note });
  await showProject(); await openEditor(); smsg(`已保存 ${r.version}；回读一致 ${r.readback_matches_memory}；面层有效 ${r.accepted}`, r.accepted && r.readback_matches_memory); });
$s("sOpenV").onclick = () => sguard(async () => { const v = $s("sVersions").value; if (!v) throw new Error("先选择版本"); await openEditor(v); await showProject(); smsg("已打开版本 " + v, true); });
$s("sExport").onclick = () => sguard(async () => {
  if (!SV.pid) throw new Error("先选择项目"); const layers = [...document.querySelectorAll(".sLay")].filter(x => x.checked).map(x => x.value);
  smsg("导出中…", true); const r = await sapi("POST", `projects/${SV.pid}/exports`, { format: $s("sFmt").value, layers, allow_pixel_space: $s("sPixelOk").checked, draft: $s("sDraft").checked });
  const a = document.createElement("a"); a.href = r.download; a.textContent = `下载 ${r.file}（${(r.bytes / 1024).toFixed(0)} KB）`; a.id = "sDlLink"; a.download = r.file;
  $s("sDl").innerHTML = ""; $s("sDl").append(a);
  const rb = Object.entries(r.readback.layers).map(([k, v]) => `${k} ${v.features}/${v.expected}`).join("，");
  smsg(`已导出 ${r.format}（${r.coordinate_mode}${r.export_mode === "draft" ? "，草稿" : ""}${r.note ? "，" + r.note : ""}）；回读 ${r.readback.ok ? "通过" : "失败"}：${rb}`, r.readback.ok); });

// OCR candidate boxes: their own overlay, independent of the text layer (candidates are never text objects)
$s("sShowOcr").onchange = () => draw();
const _drawStudio0 = draw;
draw = function () {
  _drawStudio0();
  if (!$s("sShowOcr").checked || !SV.ocr || !S) return;
  for (const c of [ctx, ctxL]) { c.save(); c.setTransform(view.s, 0, 0, view.s, view.x, view.y); c.strokeStyle = "#ff6d00"; c.lineWidth = 1.2 / view.s; c.setLineDash([3 / view.s, 2 / view.s]);
    for (const it of SV.ocr.items) { c.beginPath(); it.quad.forEach((p, i) => i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1])); c.closePath(); c.stroke(); }
    c.restore(); }
};

sguard(async () => { await loadPipelines(); await loadProjects(); smsg("选择或新建项目，导入地图后点“开始矢量化”", true); });

// ---------- text editing: double-click a text object to edit in place (Enter = save, Esc = cancel) ----------
function textInfo(t) {
  if (!t) return "";
  let c = []; try { c = JSON.parse(t.candidate_texts || "[]"); } catch (e) { }
  return `文字 #${t.id} [${t.review_status}]  OCR 原文「${t.ocr_text || "（无，手工添加）"}」 置信度 ${t.ocr_score ?? "—"}  引擎 ${t.ocr_engine || t.source || "—"}` +
    (c.length > 1 ? `  规则候选：${c.join(" / ")}` : "") + `  底图字形：${t.geometry_status || "未记录"}（未清除）`;
}
function textAtScreen(ev) { const [x, y] = toWorld(ev); return { x, y, t: pickText(x, y) }; }
function inlineEdit(t, x, y, initial, onSave) {
  const old = $s("sInline"); if (old) old.remove();
  const r = cv.getBoundingClientRect(); const i = document.createElement("input"); i.id = "sInline"; i.value = initial;
  i.style.cssText = `position:fixed;left:${r.left + view.x + x * view.s - 60}px;top:${r.top + view.y + y * view.s - 12}px;width:140px;z-index:50;font-size:14px;border:2px solid #0059c1`;
  document.body.append(i); i.focus(); i.select();
  i.onkeydown = (e) => { if (e.key === "Escape") i.remove(); if (e.key === "Enter") { const v = i.value; i.remove(); sguard(() => onSave(v)); } };
}
cv.addEventListener("dblclick", (ev) => {
  if (tool !== "pickFace" || !S) return; const h = textAtScreen(ev); if (!h.t) return;
  ev.stopPropagation(); selText = h.t.id; smsg(textInfo(h.t), true);
  inlineEdit(h.t, h.t.x, h.t.y, h.t.text, async (v) => { await api("text_edit", { id: h.t.id, text: v }); smsg(`已修改 #${h.t.id}：${h.t.text} → ${v}（未保存版本）`, true); });
}, true);
cv.addEventListener("click", (ev) => {
  if (!S) return;
  if (tool === "addText") { const [x, y] = toWorld(ev); inlineEdit(null, x, y, "", async (v) => { const r = await api("text_add", { x, y, text: v, font_px: 12 }); selText = r.id; smsg(`已添加文字 #${r.id}「${v}」`, true); }); return; }
  if (tool === "moveText") { const [x, y] = toWorld(ev);
    if (selText === null) return smsg("先用“选面”工具单击选中一个文字");
    sguard(async () => { await api("text_edit", { id: selText, x, y }); smsg(`文字 #${selText} 已移到 (${x.toFixed(1)}, ${y.toFixed(1)})`, true); }); return; }
  if (tool === "pickFace") { const h = textAtScreen(ev); if (h.t) smsg(textInfo(h.t), true); }
});
