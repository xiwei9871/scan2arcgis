async (page) => {
  const log = []; const fail = [];
  const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  const shot = async (n) => { await page.screenshot({ path: `/tmp/sve_e2e/${n}.png` }); };
  const st = () => page.evaluate(() => fetch("/api/state").then(r => r.json()));
  const scr = ([x, y]) => page.evaluate(([x, y]) => { const r = document.getElementById("cv").getBoundingClientRect(); return [r.left + view.x + x * view.s, r.top + view.y + y * view.s]; }, [x, y]);
  const clickW = async (p, opt) => { const [sx, sy] = await scr(p); await page.mouse.click(sx, sy, opt); await page.waitForTimeout(300); };
  const getSel = () => page.evaluate(() => sel);
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("http://127.0.0.1:8765/"); await page.waitForTimeout(1500);
  let s = await st(); ok(s.faces.length === 665 && s.lines.length === 35, `loaded image ${s.width}x${s.height}, faces ${s.faces.length}, lines ${s.lines.length}`); await shot("01_loaded");
  // zoom in on PN2 (G13) with the mouse wheel, keeping the target on the canvas
  const g13 = s.lines.filter(l => l.logical_id === "G13"); const mid = g13[0].coords[Math.floor(g13[0].coords.length / 2)];
  const [mx, my] = await scr(mid); await page.mouse.move(mx, my); for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, -250); await page.waitForTimeout(80); }
  const v = await page.evaluate(() => view.s); ok(v > 3, `wheel zoom: scale ${v.toFixed(2)}`); await shot("02_zoomed");
  // S1 PN2: pick line, select logical group, eyedropper, recolour, rewidth
  await page.click('button[data-tool="pickLine"]'); await clickW(mid);
  let sel = await getSel(); ok(sel.layer === "line" && sel.ids.length === 1, `click selects one line: ${JSON.stringify(sel)}`);
  await page.click("#group"); await page.waitForTimeout(300); sel = await getSel(); ok(sel.ids.length === 2, `logical_id group selects ${sel.ids.length} lines`);
  const grp = sel.ids.slice();
  await page.click('button[data-tool="eyedrop"]'); await clickW([mid[0] + 0.3, mid[1]]); const col = await page.inputValue("#colour"); ok(col !== "#ff0000", `eyedropper from scan: ${col}`);
  await page.click("#apply"); await page.waitForTimeout(400);
  await page.fill("#width", "4"); await page.click("#rewidth"); await page.waitForTimeout(400);
  s = await st(); let gl = s.lines.filter(l => grp.includes(l.id)); ok(gl.every(l => l.rgb === col && l.width === 4), `group recolour + rewidth: ${gl.map(l => l.rgb + "/" + l.width).join(", ")}`);
  ok(s.dirty === true, "unsaved-changes marker shown"); await shot("03_pn2_recolour_rewidth");
  // undo / redo (buttons and keyboard)
  await page.click("#undo"); await page.waitForTimeout(400); s = await st(); ok(s.lines.filter(l => grp.includes(l.id)).every(l => l.width !== 4), "undo button reverts width");
  await page.keyboard.press("Meta+Shift+z"); await page.waitForTimeout(400); s = await st(); ok(s.lines.filter(l => grp.includes(l.id)).every(l => l.width === 4), "redo shortcut restores width");
  // S1b: experimental line-to-face on the group
  await page.evaluate((ids) => { sel = { layer: "line", ids }; showSel(); draw(); }, grp);
  const nf0 = s.faces.length; await page.click("#l2f"); await page.waitForTimeout(800); const m1 = await page.textContent("#msg");
  s = await st(); ok(s.faces.some(f => f.attrs.source === "edited_line_to_face") && s.lines.length === 33, `line-to-face: faces ${nf0} -> ${s.faces.length}, lines -> ${s.lines.length} (${m1})`); await shot("04_pn2_line_to_face");
  // S3: faces - pick a face, grow, merge with a direct neighbour
  await page.click("#fit"); await page.waitForTimeout(200);
  await page.click('button[data-tool="pickFace"]');
  const big = s.faces.reduce((a, b) => (b.rings[0].length > a.rings[0].length ? b : a));
  const inside = await page.evaluate(() => fetch("/api/pick", { method: "POST", body: JSON.stringify({ x: 10, y: 20, layer: "face" }) }).then(r => r.json()));
  await clickW([10, 20]); sel = await getSel(); ok(sel.layer === "face" && sel.ids.length === 1 && sel.ids[0] === inside.ids[0], `click selects face #${sel.ids[0]}`);
  const seedId = sel.ids[0];
  const grown = await page.evaluate((id) => fetch("/api/grow", { method: "POST", body: JSON.stringify({ ids: [id], de: 999 }) }).then(r => r.json()), seedId);
  const nbId = grown.ids.find(i => i !== seedId); const nbFace = await page.evaluate((id) => S.faces.find(f => f.id === id), nbId);
  const xs = nbFace.rings[0].map(p => p[0]), ys = nbFace.rings[0].map(p => p[1]); let other = null;
  for (let y = Math.min(...ys) + 0.5; y < Math.max(...ys) && !other; y += 1) for (let x = Math.min(...xs) + 0.5; x < Math.max(...xs); x += 1) {
    const r = await page.evaluate((q) => fetch("/api/pick", { method: "POST", body: JSON.stringify({ x: q[0], y: q[1], layer: "face" }) }).then(r => r.json()), [x, y]);
    if (r.ids.length && r.ids[0] === nbId) { other = [x, y]; break; } }
  log.push(`edge-adjacent neighbour #${nbId}, click point ${JSON.stringify(other)}`);
  await page.keyboard.down("Shift"); await clickW(other); await page.keyboard.up("Shift"); sel = await getSel(); ok(sel.ids.length === 2, `shift-click adds a neighbour: ${JSON.stringify(sel.ids)}`);
  const nfm = (await st()).faces.length; await page.click("#merge"); await page.waitForTimeout(500); s = await st(); const mm = await page.textContent("#msg");
  ok(s.faces.length === nfm - 1, `merge two adjacent faces: ${nfm} -> ${s.faces.length} (${mm})`); await shot("05_face_merge");
  // box select + batch recolour
  await page.click('button[data-tool="boxFace"]'); const [ax, ay] = await scr([60, 100]), [bx, by] = await scr([85, 125]);
  await page.mouse.move(ax, ay); await page.mouse.down(); await page.mouse.move(bx, by, { steps: 6 }); await page.mouse.up(); await page.waitForTimeout(400);
  sel = await getSel(); ok(sel.layer === "face" && sel.ids.length > 1, `box selects ${sel.ids.length} faces`); const boxed = sel.ids.slice();
  await page.evaluate(() => { document.getElementById("colour").value = "#336699"; }); await page.click("#apply"); await page.waitForTimeout(400);
  s = await st(); ok(boxed.every(i => s.faces.find(f => f.id === i).rgb === "#336699"), `batch recolour of ${boxed.length} faces`); await shot("06_box_recolour");
  // S2-like: split a long line by clicking on it, then draw a short connecting line
  await page.click('button[data-tool="pickLine"]'); const long = s.lines.reduce((a, b) => (b.coords.length > a.coords.length ? b : a)); const q = long.coords[Math.floor(long.coords.length / 2)];
  await clickW(q); sel = await getSel(); const nl0 = s.lines.length;
  await page.click('button[data-tool="split"]'); await clickW(q); s = await st(); ok(s.lines.length === nl0 + 1, `split line by click: lines ${nl0} -> ${s.lines.length}`);
  await page.click('button[data-tool="draw"]'); await clickW([20, 280]); await clickW([30, 282]); const [dx, dy] = await scr([40, 279]); await page.mouse.dblclick(dx, dy); await page.waitForTimeout(500);
  s = await st(); ok(s.lines.length === nl0 + 2 && s.lines.some(l => l.attrs.source === "edited_drawn"), `draw a new line: lines -> ${s.lines.length}`);
  // delete the drawn line
  await page.click("#del"); await page.waitForTimeout(400); s = await st(); ok(s.lines.length === nl0 + 1, `delete selected line: lines -> ${s.lines.length}`);
  // display controls
  await page.uncheck("#showFaces"); await shot("07_lines_only"); await page.check("#showFaces"); await page.uncheck("#showLines"); await shot("08_faces_only"); await page.check("#showLines");
  await page.evaluate(() => { const a = document.getElementById("alpha"); a.value = 90; a.dispatchEvent(new Event("input")); }); await shot("09_alpha90");
  // save as new GPKG
  await page.fill("#fname", "ui_e2e.gpkg"); await page.click("#save"); await page.waitForTimeout(2500); const ms = await page.textContent("#msg");
  ok(/回读一致 true/.test(ms) && /面层有效 true/.test(ms) && /原文件未变 true/.test(ms), "save: " + ms);
  s = await st(); ok(s.dirty === false, `after save dirty=${s.dirty}, edit log ${s.log.length} entries`); await shot("10_saved");
  return JSON.stringify({ fail: fail.length, log });
}
