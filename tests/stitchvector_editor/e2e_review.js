async (page) => {
  // P1 OCR review e2e on real U2 data (219 OCR drafts): classify -> red boxes -> queue -> confirm/edit/skip -> save gate.
  const log = [], fail = [];
  const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  const shot = async (n) => { await page.screenshot({ path: `/tmp/p1_eval/shots/${n}.png` }); };
  const st = () => page.evaluate(() => fetch("/api/state").then(r => r.json()).then(j => { if (typeof S !== "undefined") S = j; return j; }));
  page.on("dialog", d => d.accept());
  await page.setViewportSize({ width: 1500, height: 950 });
  await page.waitForTimeout(1200);
  let s = await st();
  ok(s.texts.length === 219, `loaded ${s.texts.length} OCR draft texts`);

  // classify at 0.90
  await page.fill("#revTh", "0.90"); await page.click("#classifyReview"); await page.waitForTimeout(2500);
  s = await st();
  ok(s.review.required > 100 && s.review.auto_accepted > 20, `classify@0.90: required=${s.review.required} auto=${s.review.auto_accepted}`);
  ok(!(s.texts || []).some(t => t.review_status === "OCR_CONFIRMED"), "no text marked OCR_CONFIRMED by auto classify");
  const cnt = await page.textContent("#revCounters");
  ok(/待审/.test(cnt), `counters line: ${cnt.trim()}`);

  // red review boxes drawn on canvas
  const redbox = await page.evaluate(() => {
    let n = 0; const o = CanvasRenderingContext2D.prototype.strokeRect;
    CanvasRenderingContext2D.prototype.strokeRect = function (...a) { if (this.strokeStyle === "#ff1744") n++; return o.apply(this, a); };
    draw(); CanvasRenderingContext2D.prototype.strokeRect = o; return n;
  });
  ok(redbox > 100, `red review boxes drawn on map: ${redbox}`);
  await shot("20_review_mode_redboxes");

  // queue panel opened for the first item
  const first = await page.evaluate(() => revCur && { id: revCur.id, status: revCur.status, reasons: revCur.reasons });
  ok(first && first.status === "REVIEW_REQUIRED", `review panel opened on first queued item #${first && first.id}`);
  const info = await page.textContent("#revInfo");
  ok(/OCR/.test(info) && /原因/.test(info), `panel shows ocr + reasons: ${info.slice(0, 80).replace(/\n/g, "|")}`);
  await shot("21_review_panel");

  // revOnly filter hides non-queued texts
  await page.check("#revOnly");
  const drawnOnly = await page.evaluate(() => { let n = 0; const o = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function (...a) { n++; return o.apply(this, a); }; draw(); CanvasRenderingContext2D.prototype.fillText = o; return n; });
  s = await st(); ok(drawnOnly === s.review.required, `revOnly draws only queued texts (${drawnOnly}/${s.texts.length})`);
  await page.uncheck("#revOnly");

  // confirm item #1 -> leaves queue, counters update, auto-advance
  const id1 = first.id;
  await page.click("#revConfirm"); await page.waitForTimeout(700);
  s = await st();
  ok(s.texts.find(t => t.id === id1).review_status === "OCR_CONFIRMED", `item ${id1} confirmed`);
  ok(s.review.required === 0 || s.review.required < 219, `required now ${s.review.required}`);
  const cur2 = await page.evaluate(() => revCur && revCur.id);
  ok(cur2 !== id1, `auto-advanced to next item #${cur2}`);

  // edit & confirm path: revEdit fills fields -> textEdit -> HUMAN_EDITED, leaves queue
  await page.click("#revEdit"); await page.waitForTimeout(300);
  const tname = await page.inputValue("#tText");
  await page.fill("#tText", tname + "改"); await page.click("#textEdit"); await page.waitForTimeout(900);
  s = await st(); const edited = s.texts.find(t => t.text === tname + "改");
  ok(!!edited && edited.review_status === "HUMAN_EDITED", `edit path -> HUMAN_EDITED and left queue`);

  // skip path
  const cur3 = await page.evaluate(() => revCur && revCur.id);
  await page.click("#revSkip"); await page.waitForTimeout(700);
  s = await st();
  ok(s.texts.find(t => t.id === cur3).review_status === "REVIEW_SKIPPED", `item ${cur3} skipped`);
  ok(s.review.skipped === 1, `skipped counter = ${s.review.skipped}`);

  // save gate: formal save must refuse with pending review; explicit draft export succeeds
  const gate = await page.evaluate(() => fetch("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "gate_formal.gpkg" }) }).then(r => r.json()));
  ok(gate.ok === false && /require review/.test(gate.error || ""), `formal save refused: ${gate.error && gate.error.slice(0, 60)}`);
  const dr = await page.evaluate(() => fetch("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "gate_draft.gpkg", draft: true }) }).then(r => r.json()));
  ok(dr.ok === true && dr.export_mode === "draft" && dr.unreviewed > 100, `draft export ok: mode=${dr.export_mode} unreviewed=${dr.unreviewed}`);
  s = await st(); ok(s.dirty === false, `dirty cleared after draft save`);
  await shot("22_after_save");

  // counters summary for the report
  log.push(`INFO final counters: ${JSON.stringify(s.review)}`);
  return JSON.stringify({ fail: fail.length, log });
}
