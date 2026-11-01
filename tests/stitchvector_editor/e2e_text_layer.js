async (page) => {
  // Browser end-to-end for the text layer: box text -> OCR candidate -> confirm -> residue cleaned -> layer toggle -> edit -> undo/redo -> save.
  // Port is set by the caller (replace __PORT__). Boxes are the tester's choice, as a user would draw them.
  const log = [], fail = [], ops = {};
  const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  const op = (k) => { ops[k] = (ops[k] || 0) + 1; };
  const shot = async (n) => { await page.screenshot({ path: `/tmp/text_e2e/${n}.png` }); };
  const st = () => page.evaluate(() => fetch("/api/state").then(r => r.json()));
  const scr = ([x, y]) => page.evaluate(([x, y]) => { const r = document.getElementById("cv").getBoundingClientRect(); return [r.left + view.x + x * view.s, r.top + view.y + y * view.s]; }, [x, y]);
  const tool = async (t) => { await page.click(`button[data-tool="${t}"]`); op("tool:" + t); };
  const dragBox = async (b) => {
    await page.evaluate((b) => { const r = document.getElementById("cv").getBoundingClientRect(); const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2; view.x = r.width / 2 - cx * view.s; view.y = r.height / 2 - cy * view.s; draw(); }, b);
    const [ax, ay] = await scr([b[0], b[1]]), [bx, by] = await scr([b[2], b[3]]);
    await page.mouse.move(ax, ay); await page.mouse.down(); await page.mouse.move(bx, by, { steps: 6 }); await page.mouse.up();
    await page.waitForTimeout(2500); op("box_drag");
  };
  const residue = (s, b) => s.faces.filter(f => { const xs = f.rings[0].map(p => p[0]), ys = f.rings[0].map(p => p[1]);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    return cx > b[0] && cx < b[2] && cy > b[1] && cy < b[3] && f.rings[0].length <= 12; }).length;
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto("http://127.0.0.1:__PORT__/"); await page.waitForTimeout(1500);
  let s = await st(); ok(s.faces.length === 665 && (s.texts || []).length === 0, `loaded faces ${s.faces.length}, texts ${(s.texts || []).length}`);
  ok(await page.isVisible("#showText"), "text layer toggle present");
  // zoom to the map strip
  const [zx, zy] = await scr([30, 120]); await page.mouse.move(zx, zy); for (let i = 0; i < 2; i++) { await page.mouse.wheel(0, -250); await page.waitForTimeout(80); }
  const boxes = [["Є-O", [3, 25, 35, 42]], ["云", [24, 59, 41, 76]]];
  await tool("textBox");
  for (const [t, b] of boxes) {
    await dragBox(b);
    const pv = await page.evaluate(() => textPv); ok(!!pv && pv.preview_id, `${t}: preview ${pv && pv.preview_id}, OCR candidate "${pv && pv.ocr && pv.ocr.text}" (${pv && pv.ocr && pv.ocr.score})`);
    if (t === "Є-O") await shot("01_text_preview");
    const cand = await page.inputValue("#tText"); ok(cand === (pv.ocr.text || ""), `${t}: text field prefilled with the OCR candidate`);
    await page.fill("#tText", t); op("confirm_text");
    await page.click("#textApply"); await page.waitForTimeout(800); op("text_apply");
    s = await st(); const tx = (s.texts || []).find(x => x.text === t);
    ok(!!tx, `${t}: text object created at (${tx && tx.x}, ${tx && tx.y}), font ${tx && tx.font_px}`);
    ok(residue(s, b) === 0, `${t}: no small residue faces left in the box`);
  }
  await shot("02_texts_created");
  // stale preview: preview, then edit, then try to apply
  await dragBox([0, 196, 52, 225]); const stale = await page.evaluate(() => textPv);
  await page.click("#undo"); await page.waitForTimeout(500); await page.click("#redo"); await page.waitForTimeout(500);
  const rs = await page.evaluate((id) => fetch("/api/text_apply", { method: "POST", body: JSON.stringify({ preview_id: id, text: "x" }) }).then(r => r.json()), stale.preview_id);
  ok(rs.ok === false, `stale text preview refused after undo/redo: ${rs.error}`);
  await page.click("#textCancel");
  // layer toggle: text hidden / shown
  const drawnText = () => page.evaluate(() => { let n = 0; const o = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function (...a) { n++; return o.apply(this, a); }; draw(); CanvasRenderingContext2D.prototype.fillText = o; return n; });
  const on = await drawnText(); await page.uncheck("#showText"); const off = await drawnText();
  ok(on >= 2 && off === 0, `text layer toggle: ${on} labels drawn when on, ${off} when off`);
  await shot("03_text_off"); await page.check("#showText");
  // edit text: select the last created text and change size
  const last = (await st()).texts.find(x => x.text === "云");
  await page.evaluate((id) => { selText = id; }, last.id); await page.fill("#tText", "云"); await page.fill("#tFont", "16"); await page.click("#textEdit"); await page.waitForTimeout(500); op("text_edit");
  s = await st(); ok(s.texts.find(x => x.id === last.id).font_px === 16, "edit text: font 13.6 -> 16");
  await page.click("#undo"); await page.waitForTimeout(500); s = await st(); ok(s.texts.find(x => x.id === last.id).font_px !== 16, "undo text edit");
  await page.click("#redo"); await page.waitForTimeout(500); s = await st(); ok(s.texts.find(x => x.id === last.id).font_px === 16, "redo text edit");
  // save
  await page.fill("#fname", "text_ui_e2e.gpkg"); await page.click("#save"); await page.waitForTimeout(2000); op("save");
  const m = await page.textContent("#msg"); ok(/回读一致 true/.test(m) && /面层有效 true/.test(m) && /原文件未变 true/.test(m), "save: " + m);
  s = await st(); ok(s.dirty === false, "after save dirty=false"); await shot("04_saved");
  return JSON.stringify({ fail: fail.length, log, ops });
}
