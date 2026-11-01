// StitchVector Editor V0.1 client. World coordinates = image pixels (x right, y down), same as the GPKG.
const cv = document.getElementById("cv"), ctx = cv.getContext("2d"), main = document.getElementById("main");
const img = new Image(); const off = document.createElement("canvas"); let offCtx = null;
let S = null, tool = "pickFace", sel = { layer: "face", ids: [] }, view = { s: 1, x: 0, y: 0 }, drawPts = [], drag = null;
let stroke = null, mergePv = null, healPv = null;
const $ = (id) => document.getElementById(id);

function msg(t, ok) { $("msg").style.color = ok ? "#060" : "#b00"; $("msg").textContent = t || ""; }
async function api(op, body) {
  const r = await fetch("/api/" + op, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const j = await r.json(); if (!j.ok) throw new Error(j.error || "error"); return j;
}
async function refresh() {
  S = await (await fetch("/api/state")).json();
  $("dirty").textContent = S.dirty ? "● 未保存" : "";
  $("src").textContent = S.gpkg.split("/").slice(-1)[0] + "  " + S.width + "×" + S.height + "  面 " + S.faces.length + "  线 " + S.lines.length;
  $("log").textContent = S.log.slice().reverse().map(e => e.op + (e.of ? " (" + e.of + ")" : "") + (e.objects ? "  ×" + e.objects : "")).join("\n") || "（无）";
  const keep = new Set((sel.layer === "face" ? S.faces : S.lines).map(o => o.id)); sel.ids = sel.ids.filter(i => keep.has(i));
  showSel(); draw();
}
function toWorld(ev) { const r = cv.getBoundingClientRect(); return [(ev.clientX - r.left - view.x) / view.s, (ev.clientY - r.top - view.y) / view.s]; }
function fit() {
  if (!S) return; const w = main.clientWidth, h = main.clientHeight; view.s = Math.min(w / S.width, h / S.height) * 0.95;
  view.x = (w - S.width * view.s) / 2; view.y = (h - S.height * view.s) / 2; draw();
}
function draw() {
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
    for (const l of S.lines) { ctx.beginPath(); l.coords.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.strokeStyle = l.rgb; ctx.lineWidth = Math.max(l.width, 0.5); ctx.stroke(); }
  }
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
  if (healPv) { const by = new Map(S.faces.map(f => [f.id, f])); const C = { merge: "#76ff03", keep: "#2979ff", uncertain: "#ff9100" };
    for (const c of healPv.candidates) { const f = by.get(c.id); if (!f) continue; ctx.beginPath(); for (const ring of f.rings) { ring.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); }
      ctx.fillStyle = C[c.decision]; ctx.globalAlpha = 0.7; ctx.fill(); ctx.globalAlpha = 1; } }
  if (drag && drag.box) { const [x0, y0] = drag.w0, [x1, y1] = drag.w1; ctx.strokeStyle = "#ffeb3b"; ctx.lineWidth = 1.5 / view.s; ctx.strokeRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0)); }
}
function showSel() {
  if (!S || !sel.ids.length) { $("sel").textContent = "（无）"; return; }
  const list = sel.layer === "face" ? S.faces : S.lines, by = new Map(list.map(o => [o.id, o]));
  const rows = sel.ids.slice(0, 12).map(i => { const o = by.get(i); if (!o) return ""; return sel.layer === "face"
    ? `面 #${i}  ${o.rgb}  source=${o.attrs.source}  label=${o.attrs.label}`
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
  if (tool === "boxFace") drag = { box: true, w0: w, w1: w };
  if (["brushSel", "lassoSel", "heal"].includes(tool)) { stroke = { kind: tool === "lassoSel" ? "lasso" : "brush", pts: [w] }; drag = { gesture: true }; }
});
cv.addEventListener("mousemove", (ev) => {
  if (!drag) return;
  if (drag.pan) { view.x = drag.vx + ev.clientX - drag.x; view.y = drag.vy + ev.clientY - drag.y; draw(); }
  else if (drag.box) { drag.w1 = toWorld(ev); draw(); }
  else if (drag.gesture && stroke) { const w = toWorld(ev), q = stroke.pts[stroke.pts.length - 1]; if (Math.hypot(w[0] - q[0], w[1] - q[1]) * view.s > 3) { stroke.pts.push(w); draw(); } }
});
cv.addEventListener("mouseup", async (ev) => {
  const d = drag; drag = null; if (d && d.pan) return;
  if (d && d.gesture && stroke) { const st = stroke; return guard(async () => { await finishGesture(st, ev); }); }
  if (d && d.box) { const [x0, y0] = d.w0, [x1, y1] = d.w1;
    if (Math.abs(x1 - x0) + Math.abs(y1 - y0) > 1) return guard(async () => { const r = await api("box", { x0, y0, x1, y1, layer: "face" }); setSel("face", r.ids, ev.shiftKey); msg(`框选 ${r.ids.length} 个面`, true); }); }
  if (ev.button !== 0) return;
  const [x, y] = toWorld(ev);
  if (tool === "eyedrop") return eyedrop(x, y);
  if (tool === "draw") { drawPts.push([x, y]); draw(); return; }
  if (tool === "split") return guard(async () => { if (sel.layer !== "line" || sel.ids.length !== 1) throw new Error("先用“选线”选中一条线"); const r = await api("split", { id: sel.ids[0], x, y }); setSel("line", r.ids); msg("已拆分", true); });
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
["showImg", "showFaces", "showLines", "alpha"].forEach(id => $(id).oninput = draw);
$("fit").onclick = fit;
$("clear").onclick = () => setSel(sel.layer, []);
$("group").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中一条线"); const r = await api("group", { id: sel.ids[0] }); setSel("line", r.ids); msg(`整组 ${r.ids.length} 条线`, true); });
$("grow").onclick = () => guard(async () => { if (sel.layer !== "face" || !sel.ids.length) throw new Error("先选中一个面"); const r = await api("grow", { ids: sel.ids }); setSel("face", r.ids); msg(`扩展到 ${r.ids.length} 个相邻同色面`, true); });
$("apply").onclick = () => guard(async () => { if (!sel.ids.length) throw new Error("没有选中对象"); await api("recolour", { layer: sel.layer, ids: sel.ids, rgb: $("colour").value }); msg(`已改色 ${sel.ids.length} 个对象`, true); });
$("rewidth").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中线"); await api("rewidth", { ids: sel.ids, width: +$("width").value }); msg("已改线宽", true); });
$("merge").onclick = () => guard(async () => { if (sel.layer !== "face" || sel.ids.length < 2) throw new Error("至少选中 2 个面"); const r = await api("merge", { ids: sel.ids }); setSel("face", [r.id]); msg("已合并", true); });
$("del").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中线"); await api("delete", { ids: sel.ids }); setSel("line", []); msg("已删除", true); });
$("regroup").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中线"); const r = await api("regroup", { ids: sel.ids }); msg("新组 " + r.logical_id, true); });
$("l2f").onclick = () => guard(async () => { if (sel.layer !== "line" || !sel.ids.length) throw new Error("先选中线"); const r = await api("line_to_face", { ids: sel.ids, width: +$("width").value, rgb: $("colour").value }); setSel("face", []); msg(`线转面完成，面积 ${r.area_px2.toFixed(1)} px²（实验功能）`, true); });
$("undo").onclick = () => guard(async () => { const r = await api("undo"); msg("撤销：" + r.undone, true); });
$("redo").onclick = () => guard(async () => { const r = await api("redo"); msg("重做：" + r.redone, true); });
$("save").onclick = () => guard(async () => {
  const r = await api("save", { name: $("fname").value });
  msg(`已保存 ${r.path.split("/").slice(-1)[0]}；回读一致 ${r.readback_matches_memory}；面层有效 ${r.accepted}；原文件未变 ${r.input_sha256_unchanged}`, r.accepted && r.readback_matches_memory);
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
$("mergeGroups").onclick = () => guard(async () => { if (sel.layer !== "face" || sel.ids.length < 2) throw new Error("至少选中 2 个面"); const r = await api("merge_groups", { ids: sel.ids }); mergePv = null; setSel("face", []); $("preview").textContent = "（无预览）"; msg(`已合并 ${r.groups} 组、${r.faces} 个面`, true); });
$("healApply").onclick = () => guard(async () => { if (!healPv) throw new Error("先用碎面修复刷刷一下"); const r = await api("heal_apply", { plan: healPv.candidates }); healPv = null; $("preview").textContent = "（无预览）"; msg(`已修复：合并 ${r.merged} 个碎面`, true); });
$("healCancel").onclick = () => { healPv = null; mergePv = null; $("preview").textContent = "（无预览）"; draw(); };
