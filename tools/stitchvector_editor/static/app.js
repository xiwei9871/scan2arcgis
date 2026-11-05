// StitchVector Editor V0.1 client. World coordinates = image pixels (x right, y down), same as the GPKG.
const cv = document.getElementById("cv"), ctx = cv.getContext("2d"), main = document.getElementById("main");
const cvL = document.getElementById("cvL"), ctxL = cvL.getContext("2d"), mainL = document.getElementById("mainL");
let hover = null, splitPv = null, textPv = null, selText = null;
let revQueue = [], revIdx = 0, revCur = null;
let aGroup = null, aTarget = null, assigns = {}, skipped = new Set(), hiRes = null;
const img = new Image(); const off = document.createElement("canvas"); let offCtx = null;
let S = null, tool = "pickFace", sel = { layer: "face", ids: [] }, view = { s: 1, x: 0, y: 0 }, drawPts = [], drag = null;
let stroke = null, mergePv = null, healPv = null, suggestPv = null, roiB = null;
const $ = (id) => document.getElementById(id);

function msg(t, ok) { $("msg").style.color = ok ? "#060" : "#b00"; $("msg").textContent = t || ""; }
async function api(op, body) {
  const r = await fetch("/api/" + op, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const j = await r.json(); if (!j.ok) throw new Error(j.error || "error"); return j;
}
async function refresh() {
  S = await (await fetch("/api/state")).json();
  $("dirty").textContent = S.dirty ? "● 未保存" : "";
  const pend = (S.pending || []).reduce((a, p) => a + p.faces.length, 0);
  const tc = S.text_counts || {};
  $("src").innerHTML = `<b>已加载：${S.gpkg.split("/").slice(-1)[0]}</b>${S.compare ? "（对照：" + S.compare.split("/").slice(-1)[0] + "）" : ""}<br>${S.width}×${S.height}  面 ${S.faces.length}  线 ${S.lines.length}  隔离线 ${(S.residue || []).length}  待定碎面 ${pend}` +
    `<br>OCR 候选 ${tc.ocr_candidates_in_json ?? "未提供"} ｜ 独立文字对象 ${tc.text_objects ?? 0} ｜ 无 OCR 记录 ${tc.no_ocr_record ?? "?"} ｜ 与 OCR 相同 ${tc.equal_to_ocr ?? "?"} ｜ 改过 OCR ${tc.edited_from_ocr ?? "?"}（人工确认未记录）` +
    ((tc.text_objects ?? 0) === 0 ? "<br><span style='color:#b00'>本文件没有文字图层：画面里的字形是 B2c 的面/线残影，不是文字对象</span>" : "");
  $("log").textContent = S.log.slice().reverse().map(e => e.op + (e.of ? " (" + e.of + ")" : "") + (e.objects ? "  ×" + e.objects : "")).join("\n") || "（无）";
  const keep = new Set((sel.layer === "face" ? S.faces : S.lines).map(o => o.id)); sel.ids = sel.ids.filter(i => keep.has(i));
  fillLegend(); showSel(); draw();
}
document.fonts && document.fonts.addEventListener && document.fonts.addEventListener("loadingdone", () => { if (S) draw(); });
function toWorld(ev, c) { const r = (c || cv).getBoundingClientRect(); return [(ev.clientX - r.left - view.x) / view.s, (ev.clientY - r.top - view.y) / view.s]; }
function fit() {
  if (!S) return; const w = main.clientWidth, h = main.clientHeight; view.s = Math.min(w / S.width, h / S.height) * 0.95;
  view.x = (w - S.width * view.s) / 2; view.y = (h - S.height * view.s) / 2; draw();
}
function drawLeft() {
  mainL.style.display = $("dual").checked ? "" : "none"; if (!$("dual").checked) return;
  cvL.width = mainL.clientWidth; cvL.height = mainL.clientHeight; ctxL.setTransform(1, 0, 0, 1, 0, 0); ctxL.fillStyle = "#888"; ctxL.fillRect(0, 0, cvL.width, cvL.height);
  if (!S) return; ctxL.setTransform(view.s, 0, 0, view.s, view.x, view.y); ctxL.imageSmoothingEnabled = false; if (img.complete) ctxL.drawImage(img, 0, 0);
  crosshair(ctxL);
}
function crosshair(c) {
  if (!hover || !S) return; c.save(); c.strokeStyle = "#ff00ff"; c.lineWidth = 1 / view.s; c.setLineDash([]);
  c.beginPath(); c.moveTo(hover[0] - 6 / view.s * 3, hover[1]); c.lineTo(hover[0] + 6 / view.s * 3, hover[1]); c.moveTo(hover[0], hover[1] - 6 / view.s * 3); c.lineTo(hover[0], hover[1] + 6 / view.s * 3); c.stroke(); c.restore();
}
function draw() {
  drawLeft();
  cv.width = main.clientWidth; cv.height = main.clientHeight; ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = "#888"; ctx.fillRect(0, 0, cv.width, cv.height);
  if (!S) return; ctx.setTransform(view.s, 0, 0, view.s, view.x, view.y); ctx.imageSmoothingEnabled = false;
  if ($("showImg").checked && img.complete) ctx.drawImage(img, 0, 0);
  const a = $("alpha").value / 100, selSet = new Set(sel.ids);
  if ($("showFaces").checked) {
    ctx.globalAlpha = a;
    for (const f of S.faces) { ctx.beginPath(); for (const ring of f.rings) { ring.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); } ctx.fillStyle = f.rgb; ctx.fill("evenodd"); }
    ctx.globalAlpha = 1;
  }
  if ($("showLines").checked) {
    ctx.lineCap = "round"; ctx.lineJoin = "round";
    const R = new Map((S.render || []).map(r => [r.id, r]));
    for (const l of S.lines) { const r = R.get(l.id) || { dash: [], teeth: [] };
      ctx.beginPath(); l.coords.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.strokeStyle = l.rgb; ctx.lineWidth = Math.max(l.width, 0.5);
      ctx.setLineDash(r.dash || []); ctx.lineCap = (r.dash && r.dash.length) ? "butt" : "round"; ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = l.rgb; for (const t of (r.teeth || [])) { ctx.beginPath(); t.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); ctx.fill(); } }
  }
  if ($("showText").checked && S.texts) { const rm = $("reviewMode") && $("reviewMode").checked, ro = $("revOnly") && $("revOnly").checked;
    for (const t of S.texts) { const rs = t.review_status || "";
      if (rm && ro && rs !== "REVIEW_REQUIRED" && rs !== "REVIEW_SKIPPED") continue;
      ctx.save(); ctx.translate(t.x, t.y); ctx.rotate(-(t.angle_deg || 0) * Math.PI / 180);
      ctx.font = `${t.font_px}px -apple-system, "PingFang SC", sans-serif`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = t.rgb || "#000";
      ctx.fillText(t.text, 0, 0);
      if (rm && (rs === "REVIEW_REQUIRED" || rs === "REVIEW_SKIPPED")) { const w = ctx.measureText(t.text).width;
        ctx.strokeStyle = rs === "REVIEW_REQUIRED" ? "#ff1744" : "#ff9100"; ctx.lineWidth = (t.id === (revCur && revCur.id) ? 3 : 2) / view.s;
        ctx.setLineDash(rs === "REVIEW_REQUIRED" ? [4 / view.s, 2 / view.s] : []); ctx.strokeRect(-w / 2 - 2, -t.font_px / 2 - 2, w + 4, t.font_px + 4); ctx.setLineDash([]); }
      if (selText === t.id) { const w = ctx.measureText(t.text).width; ctx.strokeStyle = "#00e5ff"; ctx.lineWidth = 1.5 / view.s; ctx.strokeRect(-w / 2 - 1, -t.font_px / 2 - 1, w + 2, t.font_px + 2); } ctx.restore(); } }
  if (textPv) { const [x0, y0, x1, y1] = textPv.box; ctx.strokeStyle = "#ffeb3b"; ctx.lineWidth = 2 / view.s; ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
    const by = new Map(S.faces.map(f => [f.id, f])); for (const g of textPv.groups) for (const id of g.faces) { const f = by.get(id); if (!f) continue; ctx.beginPath();
      for (const ring of f.rings) { ring.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); } const gi = textPv.groups.indexOf(g); ctx.fillStyle = g.decision === "merge" ? "#76ff03" : (gi === aGroup ? "#2979ff" : (gi in assigns ? "#00c853" : (skipped.has(gi) ? "#9e9e9e" : "#ff9100"))); ctx.globalAlpha = 0.7; ctx.fill(); ctx.globalAlpha = 1; } }
  drawResidue(); drawAssign();
  ctx.lineWidth = 2 / view.s; ctx.setLineDash([4 / view.s, 3 / view.s]);
  if (sel.layer === "face") for (const f of S.faces) if (selSet.has(f.id)) { ctx.beginPath(); for (const ring of f.rings) { ring.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); } ctx.strokeStyle = "#00e5ff"; ctx.stroke(); }
  if (sel.layer === "line") for (const l of S.lines) if (selSet.has(l.id)) { ctx.beginPath(); l.coords.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.strokeStyle = "#00e5ff"; ctx.lineWidth = Math.max(l.width + 2, 3) ; ctx.globalAlpha = 0.6; ctx.stroke(); ctx.globalAlpha = 1; ctx.lineWidth = 2 / view.s; }
  ctx.setLineDash([]);
  if (drawPts.length) { ctx.beginPath(); drawPts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.strokeStyle = "#ff00ff"; ctx.lineWidth = Math.max(+$("width").value, 1); ctx.stroke(); }
  if (stroke && stroke.pts.length) { ctx.beginPath(); stroke.pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
    if (stroke.kind === "lasso") { ctx.closePath(); ctx.strokeStyle = "#ffeb3b"; ctx.lineWidth = 1.5 / view.s; ctx.stroke(); }
    else { ctx.strokeStyle = "rgba(255,235,59,0.45)"; ctx.lineWidth = 2 * +$("radius").value; ctx.lineCap = "round"; ctx.stroke(); } }
  if (mergePv) for (const g of mergePv.groups) for (const ring of g.outline) { ctx.beginPath(); ring.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath();
    ctx.strokeStyle = (g.colour_conflict_share || 0) > 0.1 ? "#ff1744" : "#76ff03"; ctx.lineWidth = 2.5 / view.s; ctx.stroke(); }
  if (suggestPv) { const by = new Map(S.faces.map(f => [f.id, f]));
    for (const c of suggestPv.candidates) { const f = by.get(c.eid); if (!f) continue;
      ctx.beginPath(); for (const ring of f.rings) { ring.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); }
      ctx.strokeStyle = c.suggested ? "#2979ff" : "#ff9100"; ctx.lineWidth = 2 / view.s; ctx.setLineDash(c.suggested ? [] : [4 / view.s, 3 / view.s]); ctx.stroke(); }
    ctx.setLineDash([]); }
  if (healPv) { const by = new Map(S.faces.map(f => [f.id, f])); const C = { merge: "#76ff03", keep: "#2979ff", uncertain: "#ff9100" };
    for (const c of healPv.candidates) { const f = by.get(c.id); if (!f) continue; ctx.beginPath(); for (const ring of f.rings) { ring.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); }
      ctx.fillStyle = C[c.decision]; ctx.globalAlpha = 0.7; ctx.fill(); ctx.globalAlpha = 1; } }
  if (splitPv) for (const ring of splitPv.outline) { ctx.beginPath(); ring.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); ctx.strokeStyle = "#ffea00"; ctx.lineWidth = 2 / view.s; ctx.stroke(); }
  if (roiB) { ctx.strokeStyle = "#aa00ff"; ctx.lineWidth = 2.5 / view.s; ctx.setLineDash([8 / view.s, 4 / view.s]); ctx.strokeRect(roiB[0], roiB[1], roiB[2] - roiB[0], roiB[3] - roiB[1]); ctx.setLineDash([]); }
  crosshair(ctx);
  if (drag && drag.box) { const [x0, y0] = drag.w0, [x1, y1] = drag.w1; ctx.strokeStyle = drag.roi ? "#aa00ff" : "#ffeb3b"; ctx.lineWidth = 1.5 / view.s; ctx.strokeRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)); }
}
function showSel() {
  if (!S || !sel.ids.length) { $("sel").textContent = "（无）"; return; }
  const list = sel.layer === "face" ? S.faces : S.lines, by = new Map(list.map(o => [o.id, o]));
  const rows = sel.ids.slice(0, 12).map(i => { const o = by.get(i); if (!o) return ""; let mf = "";
    if (sel.layer === "face" && o.attrs.merged_from) { try { mf = `  合并自:${JSON.parse(o.attrs.merged_from).map(e => "#" + e.eid).join(",")}`; } catch (e) { } }
    return sel.layer === "face"
    ? `面 #${i}  ${o.rgb}  source=${o.attrs.source}  label=${o.attrs.label}${mf}`
    : `线 #${i}  ${o.rgb}  宽 ${o.width}  组 ${o.logical_id}  ${o.attrs.line_id}  source=${o.attrs.source}`; });
  $("sel").textContent = `${sel.layer === "face" ? "面" : "线"} 已选 ${sel.ids.length}\n` + rows.join("\n") + (sel.ids.length > 12 ? "\n…" : "");
}
function setSel(layer, ids, add) {
  if (add && sel.layer === layer) { const s = new Set(sel.ids); ids.forEach(i => s.has(i) ? s.delete(i) : s.add(i)); sel.ids = [...s]; } else sel = { layer, ids };
  showSel(); draw();
}
function eyedrop(x, y) {
  if (!offCtx) return; const px = offCtx.getImageData(Math.floor(x), Math.floor(y), 1, 1).data;
  const hex = "#" + [px[0], px[1], px[2]].map(v => v.toString(16).padStart(2, "0")).join("");
  $("colour").value = hex; $("pickedSw").style.background = hex; msg("吸取 " + hex, true);
}
async function guard(fn) { try { await fn(); await refresh(); } catch (e) { msg(e.message); } }

cv.addEventListener("mousedown", (ev) => {
  const w = toWorld(ev);
  if (ev.button === 2 || ev.getModifierState(" ") || spaceDown) { drag = { pan: true, x: ev.clientX, y: ev.clientY, vx: view.x, vy: view.y }; return; }
  if (tool === "boxFace" || tool === "textBox" || tool === "roiBox") drag = { box: true, text: tool === "textBox", roi: tool === "roiBox", w0: w, w1: w };
  if (["brushSel", "lassoSel", "heal"].includes(tool)) { stroke = { kind: tool === "lassoSel" ? "lasso" : "brush", pts: [w] }; drag = { gesture: true }; }
});
cv.addEventListener("mousemove", (ev) => {
  hover = toWorld(ev); if (!drag) { draw(); return; }
  if (drag.pan) { view.x = drag.vx + ev.clientX - drag.x; view.y = drag.vy + ev.clientY - drag.y; draw(); }
  else if (drag.box) { drag.w1 = toWorld(ev); draw(); }
  else if (drag.gesture && stroke) { const w = toWorld(ev), q = stroke.pts[stroke.pts.length - 1]; if (Math.hypot(w[0] - q[0], w[1] - q[1]) * view.s > 3) { stroke.pts.push(w); draw(); } }
});
cv.addEventListener("mouseup", async (ev) => {
  const d = drag; drag = null; if (d && d.pan) return;
  if (d && d.gesture && stroke) { const st = stroke; return guard(async () => { await finishGesture(st, ev); }); }
  if (d && d.box && d.text) { const [x0, y0] = d.w0, [x1, y1] = d.w1;
    if (Math.abs(x1 - x0) > 2 && Math.abs(y1 - y0) > 2) return guard(async () => { const r = await api("text_preview", { box: [x0, y0, x1, y1] }); showTextPv(r); }); return; }
  if (d && d.box && d.roi) { const [x0, y0] = d.w0, [x1, y1] = d.w1;
    if (Math.abs(x1 - x0) > 4 && Math.abs(y1 - y0) > 4) return guard(async () => { const r = await api("set_roi", { bounds: [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)] }); roiB = r.roi; $("roiInfo").textContent = `ROI [${roiB.map(v => Math.round(v)).join(", ")}]`; draw(); }); return; }
  if (d && d.box) { const [x0, y0] = d.w0, [x1, y1] = d.w1;
    if (Math.abs(x1 - x0) + Math.abs(y1 - y0) > 1) return guard(async () => { const r = await api("box", { x0, y0, x1, y1, layer: "face" }); setSel("face", r.ids, ev.shiftKey); msg(`框选 ${r.ids.length} 个面`, true); }); }
  if (ev.button !== 0) return;
  const [x, y] = toWorld(ev);
  if (tool === "eyedrop") return eyedrop(x, y);
  if (tool === "assignText") return assignClick(x, y);
  if (tool === "draw") { drawPts.push([x, y]); draw(); return; }
  if (tool === "split") return guard(async () => { if (sel.layer !== "line" || sel.ids.length !== 1) throw new Error("先用“选线”选中一条线"); const r = await api("split", { id: sel.ids[0], x, y }); setSel("line", r.ids); msg("已拆分", true); });
  if (tool === "pickFace") { const t = pickText(x, y); if (t) { selText = t.id; $("tText").value = t.text; $("tFont").value = t.font_px; $("tAngle").value = t.angle_deg; $("tRgb").value = t.rgb;
    if ($("reviewMode") && $("reviewMode").checked && (t.review_status === "REVIEW_REQUIRED" || t.review_status === "REVIEW_SKIPPED")) openReview(t.id);
    msg(`选中文字 ${t.text}`, true); draw(); return; } }
  const layer = (tool === "pickLine") ? "line" : "face";
  guard(async () => { const r = await api("pick", { x, y, layer }); setSel(layer, r.ids, ev.shiftKey); });
});
cv.addEventListener("dblclick", () => {
  if (tool !== "draw" || drawPts.length < 2) return;
  const pts = drawPts.slice(0, -1).length >= 2 ? drawPts.slice(0, -1) : drawPts; drawPts = [];
  const lid = sel.layer === "line" && sel.ids.length ? (S.lines.find(l => l.id === sel.ids[0]) || {}).logical_id : null;
  guard(async () => { const r = await api("draw", { coords: pts, width: +$("width").value, rgb: $("colour").value, logical_id: lid }); setSel("line", [r.id]); msg("已补画 1 条线" + (lid ? "（加入组 " + lid + "）" : ""), true); });
});
cv.addEventListener("contextmenu", (e) => e.preventDefault());
cv.addEventListener("wheel", (ev) => {
  ev.preventDefault(); const r = cv.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top, k = Math.exp(-ev.deltaY * 0.0015);
  view.x = mx - (mx - view.x) * k; view.y = my - (my - view.y) * k; view.s *= k; draw();
}, { passive: false });
let spaceDown = false;
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" && e.target.type !== "range" && e.target.type !== "checkbox") return;
  if (e.code === "Space") spaceDown = true;
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); guard(() => api(e.shiftKey ? "redo" : "undo")); }
  if (e.key === "Escape") { drawPts = []; setSel(sel.layer, []); }
});
document.addEventListener("keyup", (e) => { if (e.code === "Space") spaceDown = false; });
window.addEventListener("beforeunload", (e) => { if (S && S.dirty) { e.preventDefault(); e.returnValue = ""; } });
window.addEventListener("resize", draw);

document.querySelectorAll("[data-tool]").forEach(b => b.onclick = () => {
  tool = b.dataset.tool; drawPts = []; document.querySelectorAll("[data-tool]").forEach(x => x.classList.toggle("on", x === b)); draw();
});
["showImg", "showFaces", "showLines", "showText", "showResidue", "showResidueIds", "alpha", "dual"].forEach(id => $(id).oninput = draw);
$("fit").onclick = fit;
$("clear").onclick = () => setSel(sel.layer, []);
$("group").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中一条线"); const r = await api("group", { id: sel.ids[0] }); setSel("line", r.ids); msg(`整组 ${r.ids.length} 条线`, true); });
$("grow").onclick = () => guard(async () => { if (sel.layer !== "face" || !sel.ids.length) throw new Error("先选中一个面"); const r = await api("grow", { ids: sel.ids }); setSel("face", r.ids); msg(`扩展到 ${r.ids.length} 个相邻同色面`, true); });
$("apply").onclick = () => guard(async () => { if (!sel.ids.length) throw new Error("没有选中对象"); await api("recolour", { layer: sel.layer, ids: sel.ids, rgb: $("colour").value }); msg(`已改色 ${sel.ids.length} 个对象`, true); });
$("rewidth").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中线"); await api("rewidth", { ids: sel.ids, width: +$("width").value }); msg("已改线宽", true); });
async function mergeWithConfirm(op) {
  try { return await api(op, { ids: sel.ids }); }
  catch (e) {
    if (e.message.includes("different labels") && confirm(e.message + "\n确认仍要合并？来源会记录在 merged_from。"))
      return await api(op, { ids: sel.ids, allow_mixed_labels: true });
    throw e;
  }
}
$("merge").onclick = () => guard(async () => { if (sel.layer !== "face" || sel.ids.length < 2) throw new Error("至少选中 2 个面"); const r = await mergeWithConfirm("merge"); setSel("face", [r.id]); msg("已合并（来源见 merged_from）", true); });
$("del").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中线"); await api("delete", { ids: sel.ids }); setSel("line", []); msg("已删除", true); });
$("regroup").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中线"); const r = await api("regroup", { ids: sel.ids }); msg("新组 " + r.logical_id, true); });
$("l2f").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中线"); const r = await api("line_to_face", { ids: sel.ids, width: +$("width").value, rgb: $("colour").value }); setSel("face", []); msg(`线转面完成，面积 ${r.area_px2.toFixed(1)} px²（实验功能）`, true); });
$("undo").onclick = () => guard(async () => { const r = await api("undo"); msg("撤销：" + r.undone, true); });
$("redo").onclick = () => guard(async () => { const r = await api("redo"); msg("重做：" + r.redone, true); });
$("save").onclick = () => guard(async () => {
  let r;
  try { r = await api("save", { name: $("fname").value }); }
  catch (e) { if (/require review/.test(e.message) && confirm(e.message + "\n以草稿模式导出（保留待审状态并记入 manifest）？")) r = await api("save", { name: $("fname").value, draft: true }); else throw e; }
  msg(`已保存 ${r.path.split("/").slice(-1)[0]}${r.export_mode === "draft" ? "（草稿，待审 " + r.unreviewed + " 条）" : ""}；回读一致 ${r.readback_matches_memory}；面层有效 ${r.accepted}；原文件未变 ${r.input_sha256_unchanged}`, r.accepted && r.readback_matches_memory);
});

img.onload = () => { off.width = img.width; off.height = img.height; offCtx = off.getContext("2d", { willReadFrequently: true }); offCtx.drawImage(img, 0, 0); refresh().then(fit); };
img.src = "/image";

async function finishGesture(st, ev) {
  const radius = +$("radius").value;
  if (tool === "heal") {
    const r = await api("heal_preview", { points: st.pts, radius }); healPv = r; mergePv = null;
    const c = r.counts || { merge: 0, keep: 0, uncertain: 0 };
    $("preview").textContent = `修复预览：候选 ${r.candidates.length}\n并入 ${c.merge}（绿） 保留 ${c.keep}（蓝） 待定 ${c.uncertain}（橙）\n点“执行修复”只合并绿色项；待定项不动。` +
      "\n" + r.candidates.slice(0, 12).map(x => `#${x.id} ${x.decision} ${x.reason} 面积${x.area.toFixed(1)} dE${x.dE ?? "-"}`).join("\n");
    msg(`修复预览：${r.candidates.length} 个候选`, true); stroke = null; draw(); return;
  }
  const mode = ev.shiftKey ? "add" : (ev.altKey ? "subtract" : $("selMode").value);
  const r = await api("select_gesture", { kind: st.kind, points: st.pts, radius, layer: "face", rule: $("selRule").value, mode,
                                          current: sel.layer === "face" ? sel.ids : [] });
  sel = { layer: "face", ids: r.ids }; stroke = null; mergePv = null; healPv = null; showSel(); draw(); msg(`选区 ${r.ids.length} 个面（${mode}）`, true);
}
$("growSel").onclick = () => guard(async () => { if (sel.layer !== "face" || !sel.ids.length) throw new Error("先选面"); const r = await api("grow_sel", { ids: sel.ids }); setSel("face", r.ids); msg(`外扩到 ${r.ids.length} 个面`, true); });
$("shrinkSel").onclick = () => guard(async () => { if (sel.layer !== "face" || !sel.ids.length) throw new Error("先选面"); const r = await api("shrink_sel", { ids: sel.ids }); setSel("face", r.ids); msg(`内缩到 ${r.ids.length} 个面`, true); });
$("mergePreview").onclick = () => guard(async () => {
  if (sel.layer !== "face" || sel.ids.length < 2) throw new Error("至少选中 2 个面"); const r = await api("merge_preview", { ids: sel.ids }); mergePv = r; healPv = null;
  $("preview").textContent = `合并预览：${r.groups.length} 组，其中可合并 ${r.mergeable_groups} 组\n` + r.groups.map((g, i) => `组${i + 1}: ${g.faces.length} 面 面积${g.area.toFixed(0)} 颜色冲突 ${((g.colour_conflict_share || 0) * 100).toFixed(0)}%` + ((g.colour_conflict_share || 0) > 0.1 ? "  ⚠ 可能越过真实边界" : "")).join("\n");
  draw(); msg("绿色轮廓 = 合并后边界；红色 = 组内原图颜色差异大，请检查", true); });
$("mergeGroups").onclick = () => guard(async () => { if (sel.layer !== "face" || sel.ids.length < 2) throw new Error("至少选中 2 个面"); const r = await mergeWithConfirm("merge_groups"); mergePv = null; setSel("face", []); $("preview").textContent = "（无预览）"; msg(`已合并 ${r.groups} 组、${r.faces} 个面（来源见 merged_from）`, true); });
$("healApply").onclick = () => guard(async () => { if (!healPv) throw new Error("先用碎面修复刷刷一下"); const r = await api("heal_apply", { preview_id: healPv.preview_id }); healPv = null; $("preview").textContent = "（无预览）"; msg(`已修复：合并 ${r.merged} 个碎面`, true); });
$("healCancel").onclick = () => { healPv = null; mergePv = null; $("preview").textContent = "（无预览）"; draw(); };

// ---- T10 smart merge suggest: click main face -> candidates w/ risk flags -> group or merge ----
$("suggestBtn").onclick = () => guard(async () => {
  if (sel.layer !== "face" || !sel.ids.length) throw new Error("先用选面点中主面");
  suggestPv = await api("merge_suggest", { ids: sel.ids });
  const box = $("suggestBox"); box.style.display = "block";
  box.innerHTML = `建议 ${suggestPv.candidates.length} 个候选（勾选后点归组或合并；⚠=风险项默认不勾）<br>` +
    suggestPv.candidates.map(c =>
      `<label><input type="checkbox" class="sgc" value="${c.eid}" ${c.suggested ? "checked" : ""}> ` +
      `#${c.eid} 面积${c.area} dE${c.dE} ${c.label ?? ""} ` +
      (c.risks.length ? `<span style="color:#b00">⚠${c.risks.join("/")}</span>` : "") + "</label>").join("<br>");
  msg(`建议候选 ${suggestPv.candidates.length}（可省 ${suggestPv.total_px_ops_saved} 次逐点）`, true); draw();
});
function suggChecked() { return [...document.querySelectorAll(".sgc:checked")].map(x => +x.value); }
$("suggestGroup").onclick = () => guard(async () => {
  const ids = suggChecked(); if (ids.length < 2) throw new Error("至少勾选 2 个面");
  const r = await api("group_faces", { ids }); suggestPv = null; $("suggestBox").style.display = "none";
  msg(`已逻辑归组 ${r.group_id}（几何未动，可撤销）`, true);
});
$("suggestMerge").onclick = () => guard(async () => {
  const ids = suggChecked(); if (ids.length < 2) throw new Error("至少勾选 2 个面");
  setSel("face", ids); const r = await mergeWithConfirm("merge");
  suggestPv = null; $("suggestBox").style.display = "none";
  setSel("face", [r.id]); msg("已几何合并（来源见 merged_from）", true);
});

// ---- left pane: pan / zoom / crosshair only (read-only; no edits) ----
let dragL = null;
cvL.addEventListener("mousedown", (ev) => { dragL = { x: ev.clientX, y: ev.clientY, vx: view.x, vy: view.y }; });
cvL.addEventListener("mousemove", (ev) => { hover = toWorld(ev, cvL); if (dragL) { view.x = dragL.vx + ev.clientX - dragL.x; view.y = dragL.vy + ev.clientY - dragL.y; } draw(); });
window.addEventListener("mouseup", () => { dragL = null; });
cvL.addEventListener("wheel", (ev) => {
  ev.preventDefault(); const r = cvL.getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top, k = Math.exp(-ev.deltaY * 0.0015);
  view.x = mx - (mx - view.x) * k; view.y = my - (my - view.y) * k; view.s *= k; draw();
}, { passive: false });
cvL.addEventListener("contextmenu", (e) => e.preventDefault());

// ---- line roles, split faces, legend ----
function fillLegend() {
  const sel_ = $("legend"), cur = sel_.value; sel_.innerHTML = "";
  for (const [k, v] of Object.entries(S.styles || {})) { const o = document.createElement("option"); o.value = k; o.textContent = `${k} · ${v.kind === "line" ? "线" : "面"} · ${v.name}`; sel_.appendChild(o); }
  if (cur && S.styles[cur]) sel_.value = cur; showStyle();
}
function showStyle() { const st = (S.styles || {})[$("legend").value]; if (!st) return;
  $("stRgb").value = st.rgb; $("stWidth").value = st.width; $("stType").value = st.line_type || "solid"; $("stDash").value = st.dash || "";
  $("stSpacing").value = st.tooth_spacing; $("stSize").value = st.tooth_size; $("stSide").value = st.tooth_side || "left"; }
$("legend").onchange = showStyle;
$("setRole").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中线"); await api("set_role", { ids: sel.ids, role: $("role").value }); msg(`已设 ${sel.ids.length} 条线为 ${$("role").value}`, true); });
$("applyLegend").onclick = () => guard(async () => { if (!sel.ids.length) throw new Error("没有选中对象"); await api("apply_legend", { layer: sel.layer, ids: sel.ids, legend_id: $("legend").value }); msg(`已应用图例 ${$("legend").value}（几何不变）`, true); });
$("saveStyle").onclick = () => guard(async () => { const id = $("legend").value; const st = S.styles[id];
  await api("set_style", { legend_id: id, style: { ...st, rgb: $("stRgb").value, width: +$("stWidth").value || st.width, line_type: st.kind === "line" ? $("stType").value : "",
    dash: $("stDash").value, tooth_spacing: +$("stSpacing").value, tooth_size: +$("stSize").value, tooth_side: st.kind === "line" ? $("stSide").value : "" } });
  msg(`图例 ${id} 已更新，所有用它的对象已重绘`, true); });
$("splitPreview").onclick = () => guard(async () => { if (sel.layer !== "line" || sel.ids.length !== 1) throw new Error("先选中一条 SPLIT 线");
  const r = await api("split_face_preview", { id: sel.ids[0] }); splitPv = r; $("preview").textContent = `切面预览：切开 ${r.faces_cut} 个面，生成 ${r.pieces} 块（黄色轮廓）`; msg("黄色轮廓 = 切开后的面", true); });
$("splitApply").onclick = () => guard(async () => { if (!splitPv) throw new Error("先预览切面"); const r = await api("split_face_apply", { preview_id: splitPv.preview_id }); splitPv = null; $("preview").textContent = "（无预览）"; msg(`已切开 ${r.faces_cut} 个面`, true); });

function showTextPv(r) {
  textPv = r; const o = r.ocr || {};
  $("ocrCand").textContent = `${o.text || "（空）"}  置信度 ${o.score ?? "—"}  (${o.engine || "-"})` +
    (o.status && o.status !== "ok" && o.status !== "off" ? `  状态:${o.status}${o.reason ? " " + o.reason : ""}` : "") + (o.low_confidence ? "  ⚠低置信" : "");
  $("tExist").textContent = (r.existing || []).length ? `框内已有文字：${r.existing.map(e => `#${e.id}「${e.text}」`).join(" ")}；确认 = 编辑已有对象，不产生重复` : "";
  $("tText").value = (o.text) || ""; $("tFont").value = (0.8 * (r.box[3] - r.box[1])).toFixed(1);
  const c = r.counts; $("tGroups").textContent = `残影面 ${c.residue_faces}：并入 ${c.merge_faces}（绿） 待定 ${c.uncertain_faces}（橙）  隔离线 ${c.residue_lines}\n` +
    r.groups.map((g, i) => g.decision === "uncertain" ? `组${i} 待定 ${g.faces.length} 面，可并入：` + (g.grounds || []).join("/") : "").filter(Boolean).join("\n") +
    (c.uncertain_faces ? "\n（待定组默认不合并；用“点选归属”逐组决定，或跳过）" : "");
  aGroup = null; aTarget = null; assigns = {}; skipped = new Set(); showAssign();
  msg("请确认文字内容（OCR 只是候选）", true); draw();
}
$("textApply").onclick = () => guard(async () => { if (!textPv) throw new Error("先用“框文字”框一个区域");
  const assign = { ...assigns };
  const r = await api("text_apply", { preview_id: textPv.preview_id, text: $("tText").value, font_px: +$("tFont").value, angle_deg: +$("tAngle").value, rgb: $("tRgb").value, assign,
    existing_mode: $("tForceNew").checked ? "create" : "edit", line_ids: resLineIds() });
  textPv = null; selText = r.text_id; $("tGroups").textContent = ""; $("tExist").textContent = ""; $("tResLines").textContent = ""; resetAssign();
  msg(r.mode === "edited_existing" ? `已更新已有文字 #${r.text_id}；并入残影面 ${r.merged_faces}，隔离线 ${r.moved_lines}`
      : `已建文字 #${r.text_id}；并入残影面 ${r.merged_faces}，隔离线 ${r.moved_lines}`, true); });
$("textCancel").onclick = () => { textPv = null; $("tGroups").textContent = ""; $("tResLines").textContent = ""; resetAssign(); draw(); };
// T11: residue preview from the selected text object's own box; risky lines start unchecked and can be left alone.
$("textResidue").onclick = () => guard(async () => {
  if (selText === null) throw new Error("先用“选面”工具点中一个文字对象");
  const rr = await api("text_residue", { ids: [selText] }); const t = rr.texts[0];
  const te = S.texts.find(x => x.id === selText) || {};
  showTextPv({ preview_id: t.preview_id, box: t.box, groups: t.groups, lines: t.lines, line_info: t.line_info,
               ocr: { text: te.text || "", score: te.ocr_score, engine: "existing", status: "reused" },
               existing: [{ id: selText, text: te.text, anchor_in_box: true, review_status: te.review_status }], counts: t.counts });
  $("tText").value = te.text || "";
  $("tResLines").innerHTML = (t.line_info || []).map(l =>
    `<label><input type="checkbox" class="trl" value="${l.id}" ${l.suggested ? "checked" : ""}> 线#${l.id} 内${(l.inside_share * 100).toFixed(0)}% 长${l.length}` +
    (l.role ? ` ${l.role}` : "") + (l.risks.length ? ` <span style="color:#b00">⚠${l.risks.join("/")}</span>` : "") + "</label>").join("<br>");
  msg(`残影候选：面 ${t.counts.residue_faces}（并 ${t.counts.merge_faces}/待定 ${t.counts.uncertain_faces}） 线 ${t.counts.residue_lines}（风险 ${t.counts.risky_lines} 默认不勾）`, true);
});
function resLineIds() { const c = document.querySelectorAll(".trl"); return c.length ? [...c].filter(x => x.checked).map(x => +x.value) : null; }

// ---- T14: ROI clear / audit ----
$("roiClear").onclick = () => guard(async () => { await api("set_roi", { bounds: null }); roiB = null; $("roiInfo").textContent = ""; msg("已清除处理范围", true); draw(); });
$("roiReport").onclick = () => guard(async () => {
  const r = await api("roi_report", {});
  $("roiInfo").textContent = r.roi === null ? "未设 ROI" :
    `ROI [${r.roi.join(", ")}]\n面 内${r.faces.inside}/跨${r.faces.crossing}/外${r.faces.outside}  线 内${r.lines.inside}/跨${r.lines.crossing}/外${r.lines.outside}  字 内${r.texts.inside}/跨${r.texts.crossing}/外${r.texts.outside}` +
    (r.faces.outside + r.lines.outside + r.texts.outside ? "\n⚠ 存在完全域外对象：正式导出会被拒绝（可草稿导出）" : "\n无完全域外对象");
});
$("textEdit").onclick = () => guard(async () => { if (selText === null) throw new Error("先在文字上用“选面”工具点一下，或刚建好的文字");
  const b = { id: selText }; if ($("tText").value.trim()) b.text = $("tText").value;
  if (+$("tFont").value > 0) b.font_px = +$("tFont").value; if ($("tAngle").value !== "") b.angle_deg = +$("tAngle").value; if ($("tRgb").value) b.rgb = $("tRgb").value;
  await api("text_edit", b); msg("已修改文字", true);
  if ($("reviewMode") && $("reviewMode").checked && revQueue.length) { await refreshQueue(); if (revQueue.length) openReview(revQueue[Math.min(revIdx, revQueue.length - 1)].id); else { $("revPanel").style.display = "none"; revCur = null; } } });
$("textDelete").onclick = () => guard(async () => { if (selText === null) throw new Error("先选中文字"); await api("text_delete", { id: selText }); selText = null; msg("已删除文字", true); });

// ---------- OCR review mode (P1): classify -> red boxes -> queue -> decide ----------
async function refreshQueue() { const r = await api("review_queue", {}); revQueue = r.queue || []; const c = r.review || S.review;
  $("revCounters").textContent = c ? `待审 ${c.required}  已跳过 ${c.skipped}  自动放行(未核实) ${c.auto_accepted}  已确认 ${c.confirmed}  人工改 ${c.human_edited}  共 ${c.total}` : ""; }
$("classifyReview").onclick = () => guard(async () => { const r = await api("review_classify", { threshold: +$("revTh").value });
  await refreshQueue(); $("reviewMode").checked = true; revIdx = 0;
  msg(`分流完成：待审 ${r.review.required}、自动放行 ${r.review.auto_accepted}（未核实、不算人工确认）`, true); draw();
  if (revQueue.length) openReview(revQueue[0].id); });
$("reviewMode").onchange = () => { draw(); };
$("revOnly").onchange = () => { draw(); };

function openReview(id) {
  const i = revQueue.findIndex(q => q.id === id); if (i < 0) { $("revPanel").style.display = "none"; revCur = null; return; }
  revIdx = i; revCur = revQueue[i];
  const t = S.texts.find(x => x.id === id); if (!t) return;
  $("revPanel").style.display = "block";
  const b = revCur.box && revCur.box.every(v => v != null) ? revCur.box : [t.x - 10, t.y - 8, t.x + 10, t.y + 8];
  const c = $("revCrop"), cx = c.getContext("2d"); cx.fillStyle = "#fafafa"; cx.fillRect(0, 0, c.width, c.height);
  const w = Math.max(b[2] - b[0], 4), h = Math.max(b[3] - b[1], 4), k = Math.min(c.width / (w + 8), c.height / (h + 8));
  cx.drawImage(img, b[0] - 4, b[1] - 4, w + 8, h + 8, (c.width - w * k) / 2, (c.height - h * k) / 2, w * k, h * k);
  $("revInfo").textContent = `#${id} 「${t.text}」  OCR:「${t.ocr_text ?? ""}」 分 ${t.ocr_score ?? "—"}\n状态 ${revCur.status}  原因 ${(revCur.reasons || []).join(", ") || "低置信度"}\n队列 ${revIdx + 1}/${revQueue.length}`;
  const r = document.getElementById("cv").getBoundingClientRect(); view.x = r.width / 2 - t.x * view.s; view.y = r.height / 2 - t.y * view.s; draw();
}
async function decide(action) {
  if (!revCur) return;
  const r = await api("review_decide", { ids: [revCur.id], action });
  await refreshQueue();
  if (revQueue.length) openReview(revQueue[Math.min(revIdx, revQueue.length - 1)].id);
  else { $("revPanel").style.display = "none"; revCur = null; msg("审核队列清空", true); }
  draw();
}
$("revConfirm").onclick = () => guard(() => decide("confirm"));
$("revSkip").onclick = () => guard(() => decide("skip"));
$("revEdit").onclick = () => guard(async () => {
  if (!revCur) return; selText = revCur.id;
  const t = S.texts.find(x => x.id === revCur.id);
  $("tText").value = t.text; $("tFont").value = t.font_px; $("tAngle").value = t.angle_deg; $("tRgb").value = t.rgb || "#000000";
  msg("在“文字”区改内容/字号/角度后点「应用文字修改」，即记为人工修改并离开队列", true);
});
function textEm(t) { let w = 0; for (const ch of String(t || "")) { const o = ch.codePointAt(0); w += (o >= 0x2E80 && o <= 0x9FFF) || (o >= 0x3000 && o <= 0x303F) || (o >= 0xFF00 && o <= 0xFFEF) ? 1.0 : 0.58; } return w; }
// text hit test = the RENDERED extent (anchor point + font + angle), not the OCR detection box. Mirrors core._text_*.
function pickText(x, y) {
  if (!S || !S.texts || !$("showText").checked) return null;
  const pad = 2 / view.s;
  for (const t of S.texts) {
    const h = t.font_px / 0.8 / 2, w = Math.max(h, t.font_px * textEm(t.text) / 2);
    const a = (t.angle_deg || 0) * Math.PI / 180, dx = x - t.x, dy = y - t.y;
    const lx = dx * Math.cos(a) - dy * Math.sin(a), ly = dx * Math.sin(a) + dy * Math.cos(a);
    if (Math.abs(lx) <= w + pad && Math.abs(ly) <= h + pad) return t;
  }
  return null;
}


// ---------- three-state view ----------
function setView(img, faces, lines, text) { $("showImg").checked = img; $("showFaces").checked = faces; $("showLines").checked = lines; $("showText").checked = text; $("alpha").value = 100; draw(); }
$("viewA").onclick = () => setView(true, false, false, false);
$("viewB").onclick = () => setView(false, true, true, false);
$("viewC").onclick = () => setView(false, true, true, true);

// ---------- uncertain-group assignment by clicking ----------
function ringPath(rings) { const p = new Path2D(); for (const r of rings) { r.forEach((q, i) => i ? p.lineTo(q[0], q[1]) : p.moveTo(q[0], q[1])); p.closePath(); } return p; }
function faceHit(id, x, y) { const f = S.faces.find(o => o.id === id); return f && ctx.isPointInPath(ringPath(f.rings), x * view.s + view.x, y * view.s + view.y, "evenodd"); }
function hitWorld(rings, x, y) { const p = ringPath(rings); ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); const m = new DOMMatrix([view.s, 0, 0, view.s, view.x, view.y]); const q = new Path2D(); q.addPath(p, m); const r = ctx.isPointInPath(q, x * view.s + view.x, y * view.s + view.y, "evenodd"); ctx.restore(); return r; }
function faceAt(ids, x, y) { for (const id of ids) { const f = S.faces.find(o => o.id === id); if (f && hitWorld(f.rings, x, y)) return id; } return null; }
function assignClick(x, y) {
  if (!textPv) return msg("先用“框文字”框一个区域");
  const unc = textPv.groups.map((g, i) => [g, i]).filter(([g]) => g.decision === "uncertain");
  for (const [g, i] of unc) if (faceAt(g.faces, x, y) !== null) { aGroup = i; aTarget = null; showAssign(); draw(); return msg(`已选待定组 ${i}，现在点它旁边的候选底面`, true); }
  if (aGroup === null) return msg("先点一个橙色待定组");
  const g = textPv.groups[aGroup]; const t = faceAt(g.grounds || [], x, y);
  if (t === null) return msg("这里不是该组的候选底面；候选面已用彩色轮廓标出");
  aTarget = t; showAssign(); draw(); msg(`预览：组 ${aGroup} 并入面 #${t}（绿色实线 = 合并后边界，白色虚线 = 合并前）`, true);
}
function showAssign() {
  if (!textPv) { $("aInfo").textContent = ""; return; }
  const unc = textPv.groups.map((g, i) => [g, i]).filter(([g]) => g.decision === "uncertain");
  $("aInfo").textContent = unc.length ? unc.map(([g, i]) => `组${i}：${g.faces.length} 面，候选 ${(g.grounds || []).map(t => "#" + t).join("/")} → ` +
    (i in assigns ? `并入 #${assigns[i]}` : skipped.has(i) ? "跳过（不合并）" : "待定（默认不合并）") + (i === aGroup ? "  ◀ 当前" : "")).join("\n") : "（本框没有待定组）";
}
function resetAssign() { aGroup = null; aTarget = null; assigns = {}; skipped = new Set(); $("aInfo").textContent = ""; }
$("aConfirm").onclick = () => { if (aGroup === null || aTarget === null) return msg("先点待定组，再点目标底面"); assigns[aGroup] = aTarget; skipped.delete(aGroup); aGroup = null; aTarget = null; showAssign(); draw(); msg("已记录归属；点“确认文字并清理残影”时才执行", true); };
$("aSkip").onclick = () => { if (aGroup === null) return msg("先点一个待定组"); delete assigns[aGroup]; skipped.add(aGroup); aGroup = null; aTarget = null; showAssign(); draw(); msg("已跳过，此组保持待定，不合并", true); };
$("aClear").onclick = () => { assigns = {}; skipped = new Set(); aGroup = null; aTarget = null; showAssign(); draw(); };
function strokeRings(rings, col, w, dash) { ctx.beginPath(); for (const r of rings) { r.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); } ctx.strokeStyle = col; ctx.lineWidth = w / view.s; ctx.setLineDash(dash.map(d => d / view.s)); ctx.stroke(); ctx.setLineDash([]); }
function drawAssign() {
  if (!textPv || aGroup === null) return; const g = textPv.groups[aGroup]; if (!g || !g.options) return;
  for (const o of g.options) { const f = S.faces.find(x => x.id === o.target); if (f) strokeRings(f.rings, o.target === aTarget ? "#00e5ff" : "#ffd600", 1.5, [3, 2]); }
  const o = g.options.find(x => x.target === aTarget); if (!o) return;
  strokeRings(o.before, "#ffffff", 1.5, [4, 3]); strokeRings(o.after, "#00e676", 2.5, []);
}

// ---------- residue (isolated) lines ----------
function drawResidue() {
  if (!$("showResidue").checked || !S.residue) return;
  for (const r of S.residue) { ctx.beginPath(); r.coords.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]));
    ctx.strokeStyle = r.id === hiRes ? "#ffea00" : "#d500f9"; ctx.lineWidth = (r.id === hiRes ? 3 : 1.5) / view.s; ctx.setLineDash([3 / view.s, 2 / view.s]); ctx.stroke(); ctx.setLineDash([]);
    if (!$("showResidueIds") || !$("showResidueIds").checked) continue; const m = r.coords[Math.floor(r.coords.length / 2)]; ctx.fillStyle = "#d500f9"; ctx.font = `${11 / view.s}px ui-monospace, monospace`; ctx.fillText("R" + r.id, m[0] + 2 / view.s, m[1] - 2 / view.s); }
}
function showResidueList() {
  const L = (S && S.residue) || []; const el = $("resList");
  if (!L.length) { el.textContent = "（无）"; return; } el.innerHTML = "";
  for (const r of L) { const d = document.createElement("div");
    d.innerHTML = `R${r.id} ${r.line_id || ""} 长 ${r.length} <span class="sw" style="background:${r.rgb}"></span> `;
    const b1 = document.createElement("button"); b1.textContent = "高亮"; b1.dataset.res = r.id; b1.onclick = () => { hiRes = r.id; const m = r.coords[0]; draw(); msg(`R${r.id} 已高亮（黄色）`, true); };
    const b2 = document.createElement("button"); b2.textContent = "恢复为地质线"; b2.dataset.restore = r.id; b2.onclick = () => guard(async () => { await api("restore_residue", { ids: [r.id] }); hiRes = null; msg(`R${r.id} 已恢复到线层`, true); });
    d.append(b1, b2); el.append(d); }
}
const _refresh0 = refresh; refresh = async function () { await _refresh0(); showResidueList(); };

// ---------- visual residual mode (server renders on the scan's own pixel grid; no registration) ----------
const DIFF = { mode: "off", imgs: {}, raw: {} };
function loadImg(url) { return new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = url + "?t=" + Date.now(); }); }
function rawOf(i) { const c = document.createElement("canvas"); c.width = i.width; c.height = i.height; const x = c.getContext("2d"); x.drawImage(i, 0, 0); return x.getImageData(0, 0, i.width, i.height).data; }
function heatCanvas(raw, w, h, thr, alpha) {   // raw residual (grey value = max |dRGB|) -> red heat, values < thr hidden
  const c = document.createElement("canvas"); c.width = w; c.height = h; const x = c.getContext("2d"); const im = x.createImageData(w, h);
  for (let i = 0; i < w * h; i++) { const v = raw[i * 4]; const o = i * 4;
    if (v < Math.max(thr, 1)) { im.data[o + 3] = 0; continue; }
    im.data[o] = 255; im.data[o + 1] = Math.round(255 * (1 - v / 255)); im.data[o + 2] = 0; im.data[o + 3] = Math.round(255 * alpha); }
  x.putImageData(im, 0, 0); return c;
}
async function diffLoad() {
  const m = $("diffMode").value; DIFF.mode = m; DIFF.imgs = {}; DIFF.raw = {};
  if (m === "off") { $("diffInfo").textContent = ""; draw(); return; }
  try {
    const keys = m === "cmp_cur" ? ["render_compare", "render_current", "residual_compare_current"]
               : m === "scan_heat" ? ["residual_scan_current"] : ["render_current", "residual_scan_current"];
    for (const k of keys) { DIFF.imgs[k] = await loadImg("/api/raster/" + k); if (k.startsWith("residual")) DIFF.raw[k] = rawOf(DIFF.imgs[k]); }
    const rk = keys.find(k => k.startsWith("residual")); const r = DIFF.raw[rk]; let n = 0, s = 0, mx = 0;
    for (let i = 0; i < r.length; i += 4) { const v = r[i]; if (v > 0) n++; s += v; if (v > mx) mx = v; }
    const N = r.length / 4; DIFF.stat = { key: rk, px: N, changed: n, mean: s / N, max: mx };
    $("diffInfo").textContent = `${rk}: 像素 ${N}，有差异 ${n}（${(100 * n / N).toFixed(2)}%），平均 ${(s / N).toFixed(2)}，最大 ${mx}\n残差 = 逐像素 max(|dR|,|dG|,|dB|)，未配准、未变形；阈值只影响显示`;
    diffRebuild();
  } catch (e) { msg("差异图加载失败：" + e.message); }
}
function diffRebuild() {
  const rk = Object.keys(DIFF.raw)[0]; if (!rk) return; const im = DIFF.imgs[rk];
  DIFF.heat = heatCanvas(DIFF.raw[rk], im.width, im.height, +$("diffThr").value, +$("diffAlpha").value / 100); $("diffThrV").textContent = $("diffThr").value; draw();
}
$("diffMode").onchange = diffLoad; $("diffReload").onclick = diffLoad; $("diffThr").oninput = diffRebuild; $("diffAlpha").oninput = diffRebuild;
function diffPaint(c, side) {   // called after the normal drawing of each pane
  if (DIFF.mode === "off" || !S) return; c.save(); c.setTransform(view.s, 0, 0, view.s, view.x, view.y); c.imageSmoothingEnabled = false;
  const I = DIFF.imgs;
  if (side === "L") { if (DIFF.mode === "cmp_cur" && I.render_compare) c.drawImage(I.render_compare, 0, 0); else if (img.complete) c.drawImage(img, 0, 0); }
  else {
    if (DIFF.mode === "scan_vector" && I.render_current) c.drawImage(I.render_current, 0, 0);
    if (DIFF.mode === "cmp_cur" && I.render_current) c.drawImage(I.render_current, 0, 0);
    if (DIFF.mode === "scan_heat") { c.fillStyle = "#fff"; c.fillRect(0, 0, S.width, S.height); }
    if (DIFF.heat) c.drawImage(DIFF.heat, 0, 0);
  }
  if (hover) crosshair(c); c.restore();
}
const _draw0 = draw; draw = function () { _draw0(); diffPaint(ctxL, "L"); diffPaint(ctx, "R"); };
// click on a residual pixel (diff mode) -> show its value and pick the vector objects there
async function diffLocate(x, y) {
  if (DIFF.mode === "off" || !S) return null; const xi = Math.floor(x), yi = Math.floor(y);
  if (xi < 0 || yi < 0 || xi >= S.width || yi >= S.height) return null;
  const rk = Object.keys(DIFF.raw).find(k => k.startsWith("residual")); const v = rk ? DIFF.raw[rk][(yi * S.width + xi) * 4] : null;
  const f = await api("pick", { x: xi + 0.5, y: yi + 0.5, layer: "face" }); const l = await api("pick", { x: xi + 0.5, y: yi + 0.5, layer: "line" });
  DIFF.last = { x: xi, y: yi, residual: v, faces: f.ids, lines: l.ids }; setSel(l.ids.length ? "line" : "face", l.ids.length ? l.ids : f.ids);
  const t = `像素 (${xi}, ${yi}) 残差 ${v}；面 ${JSON.stringify(f.ids)}；线 ${JSON.stringify(l.ids)}`;
  const base = ($("diffInfo").textContent || "").split("\n定位：")[0]; $("diffInfo").textContent = base + "\n定位：" + t; msg(t, true); return DIFF.last;
}
cv.addEventListener("click", (ev) => { if (DIFF.mode === "off" || !S) return; const [x, y] = toWorld(ev); guard(() => diffLocate(x, y)); }, true);
