async (page) => {
  // Browser end-to-end for the line-repair + legend + dual-view workflow (u2 B2c, port 8791).
  // Line roles used here are test assumptions, not verified geology.
  const log = [], fail = [], ops = {};
  const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  const op = (k) => { ops[k] = (ops[k] || 0) + 1; };
  const shot = async (n) => { await page.screenshot({ path: `/tmp/lr_e2e/${n}.png` }); };
  const st = () => page.evaluate(() => fetch("/api/state").then(r => r.json()));
  const scr = ([x, y]) => page.evaluate(([x, y]) => { const r = document.getElementById("cv").getBoundingClientRect(); return [r.left + view.x + x * view.s, r.top + view.y + y * view.s]; }, [x, y]);
  const clickW = async (p, opt) => { const [sx, sy] = await scr(p); await page.mouse.click(sx, sy, opt); await page.waitForTimeout(250); };
  const tool = async (t) => { await page.click(`button[data-tool="${t}"]`); op("tool:" + t); };
  const drawLine = async (pts) => {
    await tool("draw");
    for (const p of pts) await clickW(p);
    const [sx, sy] = await scr(pts[pts.length - 1]); await page.mouse.dblclick(sx, sy); await page.waitForTimeout(600); op("draw_line");
  };
  const brush = async (pts) => {
    let [sx, sy] = await scr(pts[0]); await page.mouse.move(sx, sy); await page.mouse.down();
    for (const p of pts.slice(1)) { [sx, sy] = await scr(p); await page.mouse.move(sx, sy, { steps: 6 }); }
    await page.mouse.up(); await page.waitForTimeout(900); op("brush_stroke");
  };
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto("http://127.0.0.1:8791/"); await page.waitForTimeout(1500);
  let s = await st();
  ok(s.faces.length === 665 && s.lines.length === 35, `loaded faces ${s.faces.length}, lines ${s.lines.length}`);
  ok(s.lines.every(l => l.role === "UNKNOWN"), "all existing lines default to UNKNOWN");

  // ---- dual view: left original (read-only), right vector, one shared view ----
  await page.check("#dual"); await page.dispatchEvent("#dual", "input"); await page.waitForTimeout(300);
  const boxes = await page.evaluate(() => [document.getElementById("cvL").getBoundingClientRect(), document.getElementById("cv").getBoundingClientRect()].map(r => [r.left, r.width]));
  ok(boxes[0][1] > 100 && boxes[1][1] > 100 && boxes[0][0] < boxes[1][0], `dual view: left ${boxes[0][1].toFixed(0)} px, right ${boxes[1][1].toFixed(0)} px`);
  const v0 = await page.evaluate(() => ({ ...view }));
  const lb = await page.evaluate(() => { const r = document.getElementById("cvL").getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; });
  await page.mouse.move(lb[0], lb[1]); for (let i = 0; i < 2; i++) { await page.mouse.wheel(0, -250); await page.waitForTimeout(80); }
  const v1 = await page.evaluate(() => ({ ...view }));
  ok(v1.s > v0.s * 1.3, `zoom on the LEFT pane zooms both (shared scale ${v0.s.toFixed(2)} -> ${v1.s.toFixed(2)})`);
  await page.mouse.move(lb[0], lb[1]); await page.mouse.down(); await page.mouse.move(lb[0] + 60, lb[1] + 30, { steps: 5 }); await page.mouse.up(); await page.waitForTimeout(200);
  const v2 = await page.evaluate(() => ({ ...view }));
  ok(Math.abs(v2.x - v1.x - 60) < 2 && Math.abs(v2.y - v1.y - 30) < 2, "pan on the LEFT pane pans both");
  const nEdits0 = (await st()).log.length;
  ok(nEdits0 === 0, "left pane interaction made no edit");
  const hov = await page.evaluate(() => hover); ok(Array.isArray(hover = hov) && hov.length === 2, `cross-hair position tracked in image pixels ${JSON.stringify(hov.map(v => +v.toFixed(1)))}`);
  await shot("01_dual_view");
  await page.click("#fit"); await page.waitForTimeout(200);

  // ---- COVER case: F3 (role assumed COVER), missing piece 43.7,269.6 -> 27.3,283.5 ----
  const gap = [[43.7, 269.6], [35.5, 276.6], [27.3, 283.5]];
  // zoom to the gap
  const [gx, gy] = await scr(gap[1]); await page.mouse.move(gx, gy); for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, -250); await page.waitForTimeout(80); }
  await page.fill("#width", "1.5"); await page.evaluate(() => { document.getElementById("colour").value = "#c0392b"; });
  const nl0 = (await st()).lines.length;
  await drawLine(gap);
  s = await st(); const drawn = s.lines.find(l => l.attrs.source === "edited_drawn");
  ok(s.lines.length === nl0 + 1 && drawn, `drew 1 line (${drawn ? drawn.coords.length : 0} vertices)`);
  ok(drawn && drawn.role === "UNKNOWN", "new line starts as UNKNOWN");
  // heal while UNKNOWN: nothing under the line may be proposed for merging
  await tool("heal"); await page.fill("#radius", "4"); await brush(gap);
  let pv = await page.evaluate(() => healPv);
  const underU = pv ? pv.candidates.filter(c => (c.under_split_or_unknown_share || 0) >= 0.5) : [];
  ok(pv && underU.every(c => c.decision !== "merge"), `UNKNOWN: ${underU.length} faces under the line, none proposed for merge`);
  await page.click("#healCancel");
  // select the new line, set COVER
  await tool("pickLine"); await clickW(gap[1]);
  let sel = await page.evaluate(() => sel); ok(sel.layer === "line" && sel.ids.includes(drawn.id), `picked the new line #${drawn.id}`);
  await page.evaluate((id) => { sel = { layer: "line", ids: [id] }; showSel(); draw(); }, drawn.id);
  await page.selectOption("#role", "COVER"); await page.click("#setRole"); await page.waitForTimeout(400); op("set_role");
  s = await st(); ok(s.lines.find(l => l.id === drawn.id).role === "COVER", "role set to COVER");
  // heal along the line
  const nf0 = s.faces.length;
  await tool("heal"); await brush(gap);
  pv = await page.evaluate(() => healPv);
  const c = pv ? pv.counts : {}; ok(pv && pv.preview_id && c.merge > 0, `heal preview ${pv && pv.preview_id}: merge ${c.merge}, keep ${c.keep}, uncertain ${c.uncertain}`);
  await shot("02_cover_heal_preview");
  // a stale preview must be refused: edit, then try to apply the old preview id through the API
  const stalePid = pv.preview_id;
  await page.click("#healApply"); await page.waitForTimeout(800); op("heal_apply");
  s = await st(); ok(s.faces.length < nf0 && s.faces.length === nf0 - c.merge || s.faces.length < nf0, `heal applied: faces ${nf0} -> ${s.faces.length}`);
  const stale = await page.evaluate((pid) => fetch("/api/heal_apply", { method: "POST", body: JSON.stringify({ preview_id: pid }) }).then(r => r.json()), stalePid);
  ok(stale.ok === false, `re-using the applied/stale preview is refused: ${stale.error}`);
  const forged = await page.evaluate(() => fetch("/api/heal_apply", { method: "POST", body: JSON.stringify({ plan: [{ id: 1, target: 2, decision: "merge" }] }) }).then(r => r.json()));
  ok(forged.ok === false, `a client-made plan without preview id is refused: ${forged.error}`);
  // legend: teeth on the line
  await page.evaluate((id) => { sel = { layer: "line", ids: [id] }; showSel(); draw(); }, drawn.id);
  const geomBefore = JSON.stringify(s.lines.find(l => l.id === drawn.id).coords);
  await page.selectOption("#legend", "L_TEETH_RED"); await page.click("#applyLegend"); await page.waitForTimeout(500); op("apply_legend");
  s = await st(); let rl = s.render.find(r => r.id === drawn.id);
  ok(rl && rl.line_type === "teeth" && rl.teeth.length > 0, `teeth legend rendered: ${rl ? rl.teeth.length : 0} teeth`);
  ok(JSON.stringify(s.lines.find(l => l.id === drawn.id).coords) === geomBefore, "applying the legend left the centre line unchanged");
  await shot("03_teeth_left");
  // change tooth spacing and side in the style panel -> re-render immediately
  const n1 = rl.teeth.length, apex1 = rl.teeth[0][2];
  await page.fill("#stSpacing", "5"); await page.selectOption("#stSide", "right"); await page.click("#saveStyle"); await page.waitForTimeout(500); op("edit_style");
  s = await st(); rl = s.render.find(r => r.id === drawn.id);
  ok(rl.teeth.length > n1, `spacing 10 -> 5: teeth ${n1} -> ${rl.teeth.length}`);
  const mid1 = rl.teeth[0].slice(0, 2), apex2 = rl.teeth[0][2];
  ok(JSON.stringify(apex2) !== JSON.stringify(apex1), "side left -> right flips the tooth apex");
  ok(JSON.stringify(s.lines.find(l => l.id === drawn.id).coords) === geomBefore, "style edit left the centre line unchanged");
  await shot("04_teeth_right_dense");

  // ---- SPLIT case: C (role assumed SPLIT), cut the green face along it ----
  await page.click("#fit"); await page.waitForTimeout(200);
  const cut = [[-1.6, 69.2], [0, 68], [29, 46], [30.6, 44.8]];
  // stay at the fitted scale so every vertex (incl. x < 0) lands on the right-hand canvas
  await page.evaluate(() => { document.getElementById("colour").value = "#202020"; });
  const nl1 = (await st()).lines.length; await drawLine(cut);
  s = await st(); const cl = s.lines.filter(l => l.attrs.source === "edited_drawn").sort((a, b) => b.id - a.id)[0];
  ok(s.lines.length === nl1 + 1 && cl.id !== drawn.id, `drew the cut line #${cl.id}`);
  await page.evaluate((id) => { sel = { layer: "line", ids: [id] }; showSel(); draw(); }, cl.id);
  // split refused while UNKNOWN
  await page.click("#splitPreview"); await page.waitForTimeout(400);
  let m = await page.textContent("#msg"); ok(!(await page.evaluate(() => splitPv)), `split on UNKNOWN refused: ${m}`);
  await page.selectOption("#role", "SPLIT"); await page.click("#setRole"); await page.waitForTimeout(400); op("set_role");
  const nf1 = (await st()).faces.length;
  await page.click("#splitPreview"); await page.waitForTimeout(600); op("split_preview");
  const sp = await page.evaluate(() => splitPv); ok(sp && sp.faces_cut > 0, `split preview: ${sp && sp.faces_cut} faces -> ${sp && sp.pieces} pieces; msg=${await page.textContent('#msg')}; coords=${JSON.stringify(cl.coords)}; role=${((await st()).lines.find(l => l.id === cl.id) || {}).role}`);
  await shot("05_split_preview");
  await page.click("#splitApply"); await page.waitForTimeout(900); op("split_apply");
  s = await st(); ok(s.faces.length === nf1 + (sp.pieces - sp.faces_cut), `split applied: faces ${nf1} -> ${s.faces.length}`);
  await page.selectOption("#legend", "L_SOLID_BLACK"); await page.click("#applyLegend"); await page.waitForTimeout(400); op("apply_legend");
  // undo / redo the legend, then the face count stays as split
  await page.click("#undo"); await page.waitForTimeout(400); s = await st(); ok(s.lines.find(l => l.id === cl.id).legend_id !== "L_SOLID_BLACK", "undo legend");
  await page.click("#redo"); await page.waitForTimeout(400); s = await st(); ok(s.lines.find(l => l.id === cl.id).legend_id === "L_SOLID_BLACK", "redo legend");
  // face legend: give one split piece a fill legend
  const piece = s.faces.filter(f => f.attrs.source === "edited_split")[0];
  await page.evaluate((id) => { sel = { layer: "face", ids: [id] }; showSel(); draw(); }, piece.id);
  await page.selectOption("#legend", "F_GREEN"); await page.click("#applyLegend"); await page.waitForTimeout(400); op("apply_legend");
  s = await st(); ok(s.faces.find(f => f.id === piece.id).rgb === "#cfe3a5", "face legend F_GREEN applied to a split piece");
  await shot("06_split_done");

  // ---- save ----
  await page.click("#fit"); await page.fill("#fname", "lr_ui_e2e.gpkg"); await page.click("#save"); await page.waitForTimeout(2000); op("save");
  m = await page.textContent("#msg"); s = await st();
  ok(/回读一致 true/.test(m) && /面层有效 true/.test(m) && /原文件未变 true/.test(m), "save: " + m);
  ok(s.dirty === false, "after save dirty=false");
  await shot("07_saved");
  return JSON.stringify({ fail: fail.length, log, ops, edits: s.log.length });
}
