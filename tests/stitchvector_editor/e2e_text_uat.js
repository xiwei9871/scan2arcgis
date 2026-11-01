async (page) => {
  const log = []; const fail = []; const ops = {};
  const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  const op = (k) => { ops[k] = (ops[k] || 0) + 1; };
  const shot = async (n) => { await page.screenshot({ path: `/tmp/text_uat/${n}.png` }); };
  const st = () => page.evaluate(() => fetch("/api/state").then(r => r.json()));
  const scr = ([x, y]) => page.evaluate(([x, y]) => { const r = document.getElementById("cv").getBoundingClientRect(); return [r.left + view.x + x * view.s, r.top + view.y + y * view.s]; }, [x, y]);
  const clickW = async (p) => { const [sx, sy] = await scr(p); await page.mouse.click(sx, sy); await page.waitForTimeout(250); };
  const tool = async (t) => { await page.click(`button[data-tool="${t}"]`); op("tool:" + t); };
  const dragBox = async (b) => {
    await page.evaluate((b) => { const r = document.getElementById("cv").getBoundingClientRect(); const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2; view.x = r.width / 2 - cx * view.s; view.y = r.height / 2 - cy * view.s; draw(); }, b);
    const [ax, ay] = await scr([b[0], b[1]]), [bx, by] = await scr([b[2], b[3]]);
    await page.mouse.move(ax, ay); await page.mouse.down(); await page.mouse.move(bx, by, { steps: 6 }); await page.mouse.up();
    await page.waitForTimeout(2500); op("box_drag");
  };
  // interior point of a face (centroid of its first ring's vertices, nudged until inside)
  const inside = (ids) => page.evaluate((ids) => { for (const id of ids) { const f = S.faces.find(o => o.id === id); if (!f) continue;
      const r = f.rings[0]; let xs = r.map(p => p[0]), ys = r.map(p => p[1]);
      for (let y = Math.min(...ys) + 0.5; y < Math.max(...ys); y += 1) for (let x = Math.min(...xs) + 0.5; x < Math.max(...xs); x += 1) if (hitWorld(f.rings, x, y)) return [x, y]; } return null; }, ids);
  await page.setViewportSize({ width: 1500, height: 950 });
  await page.goto("http://127.0.0.1:__PORT__/"); await page.waitForTimeout(1500);
  let s = await st(); const src0 = s.source_sha256;
  ok(s.faces.length === 665 && s.texts.length === 0, `loaded faces ${s.faces.length}, texts ${s.texts.length}`);
  // three-state buttons
  await page.click("#viewB"); op("view_B");
  let v = await page.evaluate(() => ({ img: $("showImg").checked, f: $("showFaces").checked, l: $("showLines").checked, t: $("showText").checked, a: +$("alpha").value }));
  ok(!v.img && v.f && v.l && !v.t && v.a === 100, `view B: image off, faces+lines on, text off, opacity ${v.a}`);
  await page.click("#viewA"); v = await page.evaluate(() => ({ img: $("showImg").checked, f: $("showFaces").checked }));
  ok(v.img && !v.f, "view A: original only"); await page.click("#viewC"); op("view_C");
  v = await page.evaluate(() => ({ img: $("showImg").checked, t: $("showText").checked, a: +$("alpha").value }));
  ok(!v.img && v.t && v.a === 100, "view C: vector 100% + text");
  // zoom on Ar2E
  const [zx, zy] = await scr([26, 210]); await page.mouse.move(zx, zy); for (let i = 0; i < 4; i++) { await page.mouse.wheel(0, -250); await page.waitForTimeout(80); }
  await tool("textBox"); await dragBox([0, 196, 52, 225]);
  const pv = await page.evaluate(() => textPv);
  const unc = pv.groups.map((g, i) => [g, i]).filter(([g]) => g.decision === "uncertain");
  ok(unc.length >= 1 && unc.every(([g]) => g.decision === "uncertain" && g.target === null), `Ar₂E preview: ${unc.length} uncertain groups, ${pv.counts.uncertain_faces} faces, none has a target by default (box ${JSON.stringify(pv.box)})`);
  ok(unc.every(([g]) => (g.options || []).length >= 2), "every uncertain group lists >= 2 candidate ground faces with before/after outlines");
  await shot("01_Ar2E_preview");
  await page.fill("#tText", "Ar₂E"); op("confirm_text");
  // click-assign: group A -> pink (largest ground), group B -> skip, rest untouched
  await tool("assignText");
  const [gA, iA] = unc[0]; const pinkId = gA.options.map(o => o.target).sort((a, b) => (s.faces.find(f => f.id === b).rings[0].length) - (s.faces.find(f => f.id === a).rings[0].length))[0];
  const pA = await inside(gA.faces); await clickW(pA); op("click_group");
  ok(await page.evaluate(() => aGroup) === iA, `click on orange group selects group ${iA}`);
  // click a point of the pink target near the group
  const pT = await page.evaluate(([gi, t]) => { const g = textPv.groups[gi]; const o = g.options.find(x => x.target === t); const f = S.faces.find(q => q.id === t);
      for (const ring of o.before) for (const p of ring) for (const [dx, dy] of [[0.5, 0.5], [-0.5, 0.5], [0.5, -0.5], [-0.5, -0.5]]) { const x = p[0] + dx, y = p[1] + dy; if (hitWorld(f.rings, x, y) && faceAt(g.faces, x, y) === null) return [x, y]; } return null; }, [iA, pinkId]);
  await clickW(pT); op("click_target");
  ok(await page.evaluate(() => aTarget) === pinkId, `click on candidate face previews merge into #${pinkId}`);
  await shot("02_assign_preview"); await page.click("#aConfirm"); op("confirm_assign");
  ok((await page.evaluate(() => assigns))[iA] === pinkId, "assignment recorded");
  const [gB, iB] = unc[1]; await clickW(await inside(gB.faces)); await page.click("#aSkip"); op("skip_group");
  ok(await page.evaluate((i) => skipped.has(i) && !(i in assigns), iB), `group ${iB} skipped (stays uncertain)`);
  // wrong target click is refused (a face that is not a candidate of group B)
  await clickW(await inside(gB.faces)); const wrong = await page.evaluate(() => aTarget);
  const pW = await page.evaluate((gi) => { const g = textPv.groups[gi]; const bad = new Set([...(g.grounds || []), ...textPv.groups.flatMap(x => x.faces)]);
      for (const f of S.faces) { if (bad.has(f.id) || f.rings[0].length < 4) continue; const xs = f.rings[0].map(q => q[0]), ys = f.rings[0].map(q => q[1]);
        const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
        if (Math.abs(cx - 26) < 60 && Math.abs(cy - 210) < 40 && hitWorld(f.rings, cx, cy) && faceAt([...bad], cx, cy) === null) return [cx, cy, f.id]; } return null; }, iB);
  await clickW([pW[0], pW[1]]); ok(await page.evaluate(() => aTarget) === wrong, `click on non-candidate face #${pW[2]} does not set a target`);
  await page.evaluate(() => { aGroup = null; aTarget = null; showAssign(); });
  await page.click("#textApply"); await page.waitForTimeout(900); op("text_apply");
  s = await st(); const left = (await page.evaluate(() => 1)) && s;
  ok(s.texts.length === 1 && s.texts[0].text === "Ar₂E", "Ar₂E text created");
  const groupFacesLeft = unc.filter(([g, i]) => i !== iA).every(([g]) => g.faces.every(id => s.faces.some(f => f.id === id)));
  const groupALeft = gA.faces.some(id => s.faces.some(f => f.id === id));
  ok(groupFacesLeft && !groupALeft, `only the assigned group merged; other ${unc.length - 1} uncertain groups untouched`);
  // residue lines list, highlight, restore
  const nRes = s.residue.length; ok(nRes === 3, `3 isolated lines listed with numbers: ${s.residue.map(r => "R" + r.id).join(", ")}`);
  await page.click(`button[data-res="${s.residue[0].id}"]`); op("highlight_residue");
  ok(await page.evaluate(() => hiRes) === s.residue[0].id, "residue line highlighted");
  await shot("03_residue_highlight");
  const nl = s.lines.length; await page.click(`button[data-restore="${s.residue[0].id}"]`); await page.waitForTimeout(500); op("restore_residue");
  s = await st(); ok(s.lines.length === nl + 1 && s.residue.length === nRes - 1, `restore: lines ${nl} -> ${s.lines.length}, isolated ${nRes} -> ${s.residue.length}`);
  // undo / redo of restore and of the text box
  await page.click("#undo"); await page.waitForTimeout(400); s = await st(); ok(s.residue.length === nRes, "undo restore");
  await page.click("#undo"); await page.waitForTimeout(400); s = await st(); ok(s.texts.length === 0 && s.faces.length === 665, "undo text box: back to 665 faces, no text");
  await page.click("#redo"); await page.waitForTimeout(400); await page.click("#redo"); await page.waitForTimeout(400);
  s = await st(); ok(s.texts.length === 1 && s.residue.length === nRes - 1, "redo both");
  await page.click("#viewB"); await shot("04_view_B"); await page.click("#viewC"); await shot("05_view_C");
  ok(s.source_sha256 === src0, "source GPKG hash unchanged in the session");
  await page.fill("#fname", "text_uat_e2e.gpkg"); await page.click("#save"); await page.waitForTimeout(2000); op("save");
  const m = await page.textContent("#msg"); ok(m.includes("回读一致 true") && m.includes("原文件未变 true"), "save: " + m);
  return JSON.stringify({ fail: fail.length, log, ops });
}
