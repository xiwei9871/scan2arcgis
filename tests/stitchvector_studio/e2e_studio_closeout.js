async (page) => {
  // Closeout part-2: reopen existing processed project -> text confirm -> diff view -> save -> reload -> exports.
  const log = [], fail = [];
  try { return await (async () => { const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  const st = () => page.evaluate(() => fetch("/api/state").then(r => r.json()));
  const disarm = () => page.evaluate(() => { window.__svNoUnload = true; });
  await page.setViewportSize({ width: 1600, height: 950 });
  await page.evaluate(() => { if (window.S) S.dirty = false; }); await disarm();
  await page.goto("http://127.0.0.1:__PORT__/"); await page.waitForTimeout(1500);
  await page.evaluate(() => { window.prompt = (m, d) => (String(m).includes("项目") ? "u2-e2e" : "e2e edit"); window.confirm = () => true; });
  await disarm();
  await page.waitForFunction(() => [...document.querySelectorAll("#sProj option")].some(o => o.value.startsWith("p-")), null, { timeout: 15000 });
  const pid = await page.evaluate(() => [...document.querySelectorAll("#sProj option")].map(o => o.value).find(v => v.startsWith("p-")));
  await page.selectOption("#sProj", pid); await page.waitForTimeout(6000);
  let s = await st();
  ok(s.faces.length === 17047 && s.lines.length === 606, `project reopened: faces ${s.faces.length}, lines ${s.lines.length}`);
  ok(s.texts.length === 148, `texts ${s.texts.length}`);
  // real text edit -> HUMAN_EDITED (P1.1 semantics)
  const target = s.texts.find(t => t.review_status === "OCR_DRAFT" || t.review_status === "REVIEW_REQUIRED");
  await page.evaluate((id) => { selText = id; }, target.id);
  await page.fill("#tText", target.text + "X"); await page.click("#textEdit"); await page.waitForTimeout(800);
  s = await st(); let t2 = s.texts.find(t => t.id === target.id);
  ok(t2.review_status === "HUMAN_EDITED", `real edit -> HUMAN_EDITED: ${t2.review_status}`);
  // diff view select visible (regression: details must be open)
  await page.selectOption("#diffMode", "scan_heat"); await page.waitForTimeout(4000);
  const dm = await page.evaluate(() => document.getElementById("diffMode").value);
  ok(dm === "scan_heat", "diffMode selectable (details open): " + dm);
  await page.selectOption("#diffMode", "off"); await page.waitForTimeout(300);
  // save version
  await page.click("#sSave");
  for (let i = 0; i < 60 && !/已保存/.test(await page.textContent("#sMsg")); i++) await page.waitForTimeout(500);
  const sm = await page.textContent("#sMsg"); ok(/已保存/.test(sm), "save version: " + sm.slice(0, 120));
  const dirty = await page.evaluate(() => fetch("/api/state").then(r => r.json()).then(x => ({ server: x.dirty, client: !!(S && S.dirty) })));
  ok(!dirty.server && !dirty.client, "no unsaved edits: " + JSON.stringify(dirty));
  await page.evaluate(() => { if (window.S) { S.dirty = false; } S = null; });
  await page.reload(); await page.waitForTimeout(1500);
  await disarm();
  await page.evaluate(() => { window.prompt = (m, d) => (String(m).includes("项目") ? "u2-e2e" : "e2e edit"); window.confirm = () => true; });
  await disarm();
  await page.waitForFunction(() => [...document.querySelectorAll("#sProj option")].some(o => o.value.startsWith("p-")), null, { timeout: 15000 });
  await page.selectOption("#sProj", pid); await page.waitForTimeout(6000);
  s = await st(); t2 = s.texts.find(t => t.id === target.id);
  ok(!!t2 && t2.review_status === "HUMAN_EDITED", "after reload+reopen: edit persisted " + (t2 && t2.review_status));
  // exports: formal must refuse with unreviewed texts (unified gate); draft must succeed
  const exp = {};
  await page.selectOption("#sFmt", "GPKG"); await page.waitForTimeout(300);
  await page.click("#sExport"); let m0 = "";
  for (let i = 0; i < 30; i++) { await page.waitForTimeout(1000); m0 = await page.textContent("#sMsg"); if (/deliverable|失败|错误|error|已导出/i.test(m0) && !/导出中/.test(m0)) break; }
  ok(/deliverable|not in a deliverable state/i.test(m0), "formal export refused by unified gate: " + m0.slice(0, 140));
  for (const fmt of ["GPKG", "SHP"]) {
    await page.selectOption("#sFmt", fmt); await page.waitForTimeout(300);
    await page.check("#sDraft"); await page.check("#sPixelOk"); await page.waitForTimeout(200);
    await page.click("#sExport"); let m = "";
    for (let i = 0; i < 120; i++) { await page.waitForTimeout(1000); m = await page.textContent("#sMsg"); if (/已导出|失败|错误|error/i.test(m) && !/导出中/.test(m)) break; }
    ok(/已导出/.test(m), `${fmt} draft export: ${m.slice(0, 160)}`);
    await page.waitForSelector("#sDlLink", { timeout: 10000 });
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 60000 }), page.click("#sDlLink")]);
    const p = "__DL__/" + dl.suggestedFilename(); await dl.saveAs(p); exp[fmt] = p; }
  return JSON.stringify({ fail: fail.length, log, downloads: exp, project_id: pid });
  })(); } catch (e) { return JSON.stringify({ fail: fail.length + 1, error: String(e).slice(0, 400), log }); }
}
