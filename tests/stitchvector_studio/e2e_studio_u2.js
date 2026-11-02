// Real-browser E2E of StitchVector Studio V0.1 on U2. Placeholders: __PORT__, __U2__, __DL__.
// Upload -> process (B2c + PaddleOCR, default profile) -> layers -> text edit (a real OCR error) -> face/line edit ->
// undo/redo -> visual diff -> save version -> reload page + reopen -> exports (GPKG, SHP) -> download.
async (page) => {
  const log = [], fail = [];
  try { return await (async () => { const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  const st = () => page.evaluate(() => fetch("/api/state").then(r => r.json()));
  page.on("dialog", d => d.accept(d.type() === "prompt" ? (d.message().includes("项目") ? "u2-e2e" : "e2e edit") : undefined));
  await page.setViewportSize({ width: 1600, height: 950 });
  await page.goto("http://127.0.0.1:__PORT__/"); await page.waitForTimeout(1500); await page.evaluate(() => { window.prompt = (m, d) => (String(m).includes("项目") ? "u2-e2e" : "e2e edit"); window.confirm = () => true; });
  await page.waitForFunction(() => document.querySelectorAll("#sProfile option").length >= 3, null, { timeout: 15000 });
  const profs = await page.evaluate(() => [...document.querySelectorAll("#sProfile option")].map(o => ({ v: o.value, d: o.disabled })));
  ok(await page.inputValue("#sProfile") === "legacy-b2c-v01", "default profile legacy-b2c-v01 (B2c + PaddleOCR)");
  ok(profs.some(p => p.v === "legacy-b2c-v01-rapidocr" && !p.d), "RapidOCR profile selectable");
  ok(profs.some(p => p.v === "geology-aware-vnext" && p.d), "geology-aware-vnext listed but disabled (NOT_IMPLEMENTED)");
  await page.click("#sNew"); await page.waitForFunction(() => /已新建项目/.test(document.getElementById("sMsg").textContent), null, { timeout: 15000 });
  await page.setInputFiles("#sFile", "__U2__"); await page.click("#sUpload"); await page.waitForFunction(() => /已导入|错误|error/i.test(document.getElementById("sMsg").textContent), null, { timeout: 30000 });
  ok(/PNG/.test(await page.textContent("#sMsg")), "upload: " + (await page.textContent("#sMsg")));
  await page.click("#sProcess");
  let done = false;
  for (let i = 0; i < 240 && !done; i++) { await page.waitForTimeout(1000); done = /处理完成|FAILED|CANCELLED/.test(await page.textContent("#sMsg")); }
  await page.waitForTimeout(3000);
  const job = await page.textContent("#sJob"); ok(/COMPLETED/.test(job) && /paddleocr@1\.0\.0=COMPLETED/.test(job), "job: " + job.slice(0, 300));
  let s = await st();
  ok(s.faces.length === 17047 && s.lines.length === 606, `editor loaded faces ${s.faces.length}, lines ${s.lines.length}`);
  const drafts = s.texts.filter(t => t.review_status === "OCR_DRAFT");
  ok(s.texts.length > 0 && drafts.length === s.texts.length, `text drafts ${s.texts.length}, all OCR_DRAFT`);
  ok(s.text_counts && s.text_counts.ocr_candidates_in_json === s.texts.length, `OCR candidates ${s.text_counts && s.text_counts.ocr_candidates_in_json} = text objects`);
  // text layer toggle really hides the labels
  // hash after a deterministic redraw (no hover crosshair, no pending async paint)
  const px = () => page.evaluate(() => { hover = null; draw(); const d = ctx.getImageData(0, 0, cv.width, cv.height).data; let h = 0; for (let i = 0; i < d.length; i++) h = (h * 31 + d[i]) | 0; return h; });
  await page.mouse.move(2, 2); await page.waitForTimeout(300);
  await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(800); await px(); await page.waitForTimeout(300);
  await page.uncheck("#showText"); await page.waitForTimeout(300); await page.check("#showText"); await page.waitForTimeout(300);   // prime: first frame after reopen differs (see report)
  await page.evaluate(() => refresh()); await page.waitForTimeout(2500); const a0 = await px(); await page.waitForTimeout(1000); const a1 = await px();
  ok(a0 === a1, `canvas settled before the toggle check (${a0} / ${a1})`);
  await page.uncheck("#showText"); await page.waitForTimeout(400); const a2 = await px(); await page.check("#showText"); await page.waitForTimeout(400); const a3 = await px();
  ok(a1 !== a2 && a1 === a3, `text layer off changes the canvas, on restores it (${a1} / ${a2} / ${a3}, checked ${await page.isChecked("#showText")})`);
  ok(!(await page.isChecked("#showResidueIds")), "isolated-line R numbers on their own toggle (off by default)");
  // a real OCR error: pick a draft whose raw OCR differs from the expected form and fix it
  const target = s.texts.find(t => t.ocr_text === "轩肉镇") || s.texts.find(t => /^Ar2/.test(t.ocr_text)) || s.texts.find(t => t.text !== t.ocr_text);
  ok(!!target, `real OCR error chosen: raw "${target && target.ocr_text}" (draft "${target && target.text}")`);
  const fixed = target.ocr_text === "轩肉镇" ? "轩岗镇" : "Ar₂E";
  await page.evaluate((id) => { selText = id; }, target.id);
  await page.fill("#tText", fixed); await page.click("#textEdit"); await page.waitForTimeout(800);
  s = await st(); let t2 = s.texts.find(t => t.id === target.id);
  ok(t2.text === fixed && t2.ocr_text === target.ocr_text && t2.review_status === "HUMAN_EDITED", `text edited: ocr_text "${t2.ocr_text}" kept, text "${t2.text}", ${t2.review_status}`);
  // move + add + delete text
  await page.evaluate(async (id) => { await api("text_edit", { id, x: 100, y: 100 }); await refresh(); }, target.id);
  s = await st(); t2 = s.texts.find(t => t.id === target.id); ok(Math.abs(t2.x - 100) < 0.01 && Math.abs(t2.y - 100) < 0.01, "text moved to (100,100)");
  await page.evaluate(async () => { await api("text_add", { x: 50, y: 50, text: "J₂d", font_px: 12 }); await refresh(); });
  s = await st(); const added = s.texts.find(t => t.text === "J₂d" && t.x === 50); ok(!!added && added.review_status === "HUMAN_EDITED", "missing text added (J₂d)");
  const delId = s.texts.find(t => t.id !== target.id && t.id !== added.id).id; const nT = s.texts.length;
  await page.evaluate(async (id) => { await api("text_delete", { id }); await refresh(); }, delId);
  s = await st(); ok(s.texts.length === nT - 1, "a wrong text object deleted");
  ok(s.faces.length === 17047 && s.lines.length === 606, "text edits changed no face / line");
  // face and line edit
  const fid = s.faces.find(f => f.rings[0].length > 6).id; const lid = s.lines[0].id;
  await page.evaluate(async ([f, l]) => { await api("recolour", { layer: "face", ids: [f], rgb: "#123456" }); await api("rewidth", { ids: [l], width: 4 }); await refresh(); }, [fid, lid]);
  s = await st(); ok(s.faces.find(f => f.id === fid).rgb === "#123456" && s.lines.find(l => l.id === lid).width === 4, "face recoloured + line width changed");
  await page.click("#undo"); await page.waitForTimeout(600); s = await st(); ok(s.lines.find(l => l.id === lid).width !== 4, "undo line width");
  await page.click("#redo"); await page.waitForTimeout(600); s = await st(); ok(s.lines.find(l => l.id === lid).width === 4, "redo line width");
  // visual diff
  await page.selectOption("#diffMode", "scan_heat"); await page.waitForTimeout(4000);
  ok(/residual_scan_current/.test(await page.textContent("#diffInfo")), "visual diff (scan vs current) computed");
  await page.selectOption("#diffMode", "off"); await page.waitForTimeout(300);
  // save version, reload page, reopen
  await page.click("#sSave"); for (let i = 0; i < 60 && !/已保存/.test(await page.textContent("#sMsg")); i++) await page.waitForTimeout(500); await page.waitForTimeout(3000);
  ok(/已保存 v001；回读一致 true/.test(await page.textContent("#sMsg")), "save: " + (await page.textContent("#sMsg")));
  const pid = await page.evaluate(() => SV.pid);
  const dirtyAfterSave = await page.evaluate(() => fetch("/api/state").then(r => r.json()).then(s => ({ server: s.dirty, client: !!(S && S.dirty) })));
  ok(!dirtyAfterSave.server && !dirtyAfterSave.client, "after save: no unsaved edits " + JSON.stringify(dirtyAfterSave));
  await page.evaluate(() => { S = null; });   // the reload itself is the test step; the dirty flag was checked above
  await page.reload(); await page.waitForTimeout(1500); await page.evaluate(() => { window.prompt = (m, d) => (String(m).includes("项目") ? "u2-e2e" : "e2e edit"); window.confirm = () => true; }); await page.selectOption("#sProj", pid); await page.waitForTimeout(6000);
  s = await st(); t2 = s.texts.find(t => t.text === fixed);
  ok(!!t2 && t2.ocr_text === target.ocr_text && Math.abs(t2.x - 100) < 0.01 && t2.review_status === "HUMAN_EDITED", "after reload + reopen: edited text, raw OCR and position kept");
  ok(s.faces.find(f => f.rgb === "#123456") && s.lines.some(l => l.width === 4), "after reopen: face colour + line width kept");
  // exports: GPKG (with unconfirmed / edited texts), SHP (pixel space, confirmed)
  const exp = {};
  for (const [fmt, pixel] of [["GPKG", false], ["SHP", true]]) {
    await page.selectOption("#sFmt", fmt); if (pixel) await page.check("#sPixelOk");
    await page.check('.sLay[value="text_unconfirmed"]');
    await page.evaluate(() => { const d = document.getElementById("sDl"); if (d) d.innerHTML = ""; });
    await page.click("#sExport"); let m = "";
    for (let i = 0; i < 120; i++) { await page.waitForTimeout(1000); m = await page.textContent("#sMsg"); if (/已导出|失败|错误|error/i.test(m) && !/导出中/.test(m)) break; }
    ok(/回读 通过/.test(m), `${fmt} export: ${m.slice(0, 200)}`);
    await page.waitForSelector("#sDlLink", { timeout: 10000 });
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }), page.click("#sDlLink")]);
    const p = "__DL__/" + dl.suggestedFilename(); await dl.saveAs(p); exp[fmt] = p;
  }
  ok(/PIXEL_SPACE/.test(await page.textContent("#sCoord")), "coordinate mode shown: " + (await page.textContent("#sCoord")));
  return JSON.stringify({ fail: fail.length, log, downloads: exp, project_id: pid, edited: { id: target.id, raw: target.ocr_text, text: fixed } });
  })(); } catch (e) { return JSON.stringify({ fail: fail.length + 1, error: String(e).slice(0, 400), log }); }
}
