// Interaction check on the DEMO GPKG (u2_text_demo.gpkg): text toggle, scan overlay, undo/redo, save + reopen.
// Placeholder: __PORT__. Makes one reversible edit (text font) only to test undo/redo; saves to a NEW file.
async (page) => {
  const log = [], fail = []; const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  const st = () => page.evaluate(() => fetch("/api/state").then(r => r.json()));
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto("http://127.0.0.1:__PORT__/"); await page.waitForTimeout(1800);
  const head = (await page.textContent("#src")).replace(/\s+/g, " ");
  ok(head.includes("u2_text_demo.gpkg") && head.includes("文字 3") && head.includes("待定碎面 16"), "header shows demo file: " + head);
  let s = await st(); const v0 = s.version;
  // text layer toggle changes the right canvas
  const shot = () => page.evaluate(() => document.getElementById("cv").toDataURL());
  await page.click("#viewC"); await page.waitForTimeout(300); const on = await shot();
  await page.click("#viewB"); await page.waitForTimeout(300); const off = await shot();
  ok(on !== off, "text layer on/off changes the vector canvas");
  ok(await page.evaluate(() => !document.getElementById("showImg").checked && +document.getElementById("alpha").value === 100), "view B: scan overlay off, faces 100%");
  await page.click("#viewA"); await page.waitForTimeout(300); const a = await shot();
  ok(a !== off && await page.evaluate(() => document.getElementById("showImg").checked), "view A: scan overlay on");
  s = await st(); ok(s.version === v0 && !s.dirty, "view switching made no edit");
  // undo / redo on a text edit
  const t = s.texts.find(x => x.text === "云");
  await page.evaluate((id) => { selText = id; }, t.id); await page.fill("#tText", "云"); await page.fill("#tFont", "18"); await page.click("#textEdit"); await page.waitForTimeout(500);
  s = await st(); ok(s.texts.find(x => x.id === t.id).font_px === 18 && s.dirty, "text edit applied, unsaved marker on");
  await page.click("#undo"); await page.waitForTimeout(400); s = await st(); ok(s.texts.find(x => x.id === t.id).font_px === t.font_px, "undo restores font");
  await page.click("#redo"); await page.waitForTimeout(400); s = await st(); ok(s.texts.find(x => x.id === t.id).font_px === 18, "redo re-applies font");
  await page.click("#undo"); await page.waitForTimeout(400);
  s = await st(); const pend = s.pending.reduce((n, p) => n + p.faces.length, 0);
  ok(s.faces.length === 550 && s.lines.length === 28 && s.texts.length === 3 && s.residue.length === 7 && pend === 16, "state back to demo: 550/28/3/7/16");
  // save to a new file and report readback
  await page.fill("#fname", "demo_reopen_check.gpkg"); await page.click("#save"); await page.waitForTimeout(2000);
  const m = await page.textContent("#msg"); ok(m.includes("回读一致 true") && m.includes("原文件未变 true"), "save: " + m);
  return JSON.stringify({ fail: fail.length, log });
}
