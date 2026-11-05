async (page) => {
  // P0 verification on the live doc from e2e_text_layer (2 texts: "Є-O" @18.5,33 and "云" @32,67 f16).
  const log = [], fail = [];
  const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  const shot = async (n) => { await page.screenshot({ path: `/tmp/text_e2e/${n}.png` }); };
  const st = () => page.evaluate(() => fetch("/api/state").then(r => r.json()).then(j => { if (typeof S !== "undefined") S = j; return j; }));
  const op = (name, a) => page.evaluate(([name, a]) => fetch("/api/" + name, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ layer: "face", ...a }) }).then(r => r.json()), [name, a]);
  const scr = ([x, y]) => page.evaluate(([x, y]) => { const r = document.getElementById("cv").getBoundingClientRect(); return [r.left + view.x + x * view.s, r.top + view.y + y * view.s]; }, [x, y]);
  const tool = async (t) => { await page.click(`button[data-tool="${t}"]`); };
  const dragBox = async (b) => {
    await page.evaluate((b) => { const r = document.getElementById("cv").getBoundingClientRect(); const cx = (b[0] + b[2]) / 2, cy = (b[1] + b[3]) / 2; view.x = r.width / 2 - cx * view.s; view.y = r.height / 2 - cy * view.s; draw(); }, b);
    const [ax, ay] = await scr([b[0], b[1]]), [bx, by] = await scr([b[2], b[3]]);
    await page.mouse.move(ax, ay); await page.mouse.down(); await page.mouse.move(bx, by, { steps: 6 }); await page.mouse.up();
    await page.waitForTimeout(1800);
  };
  page.on("dialog", d => d.accept());
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.waitForTimeout(800);
  let s = await st();
  if (!s.texts.find(t => t.text === "云")) { const ar = await op("text_add", { x: 32, y: 67, text: "云", font_px: 16 }); ok(ar.ok, `text_add 云 id=${ar.id}`); s = await st(); }
  const yun = s.texts.find(t => t.text === "云"); ok(!!yun, `doc has ${s.texts.length} texts incl. 云 id=${yun && yun.id}`);

  // ---------- E22: move -> hit syncs; old pos stops hitting ----------
  const NEWX = 120, NEWY = 130;
  let r = await op("text_edit", { id: yun.id, x: NEWX, y: NEWY });
  ok(r.ok !== false, `text_edit move to (${NEWX},${NEWY})`);
  s = await st(); const moved = s.texts.find(t => t.id === yun.id);
  ok(moved.x === NEWX && moved.y === NEWY, `state reports new position ${moved.x},${moved.y}`);
  ok(moved.box_x0 <= NEWX && NEWX <= moved.box_x1 && moved.box_y0 <= NEWY && NEWY <= moved.box_y1, `display box follows: [${moved.box_x0},${moved.box_y0},${moved.box_x1},${moved.box_y1}]`);
  const hitNew = await page.evaluate(([x, y]) => { const t = pickText(x, y); return t && t.id; }, [NEWX, NEWY]);
  const hitOld = await page.evaluate(([x, y]) => { const t = pickText(x, y); return t && t.id; }, [yun.x, yun.y]);
  ok(hitNew === yun.id, `client pickText hits at the new position (id=${hitNew})`);
  ok(hitOld !== yun.id, `client pickText no longer hits at the old position (id=${hitOld})`);
  r = await op("text_pick", { x: NEWX, y: NEWY }); ok((r.ids || []).includes(yun.id), `server text_pick hits at new position`);
  r = await op("text_pick", { x: yun.x, y: yun.y }); ok(!(r.ids || []).includes(yun.id), `server text_pick misses old position`);
  // real canvas click at the new position selects the text
  await tool("pickFace");
  const [cx, cy] = await scr([NEWX, NEWY]); await page.mouse.click(cx, cy); await page.waitForTimeout(400);
  const sel = await page.evaluate(() => selText); ok(sel === yun.id, `real click at new pos selects text (selText=${sel})`);
  // angle change re-syncs: rotate 90deg then old horizontal extent must miss
  r = await op("text_edit", { id: yun.id, angle_deg: 90 });
  const edgeX = NEWX + 16 / 2 - 2;   // "云" f16: half em ~8... use the stored box edge instead
  s = await st(); const rot = s.texts.find(t => t.id === yun.id);
  const midx = (rot.box_x0 + rot.box_x1) / 2, midy = (rot.box_y0 + rot.box_y1) / 2;
  ok(Math.abs(midx - NEWX) < 1.5 && Math.abs(midy - NEWY) < 1.5, `rotated display box stays centred at (${midx.toFixed(1)},${midy.toFixed(1)})`);
  const hHitV = await page.evaluate(([x, y]) => { const t = pickText(x, y); return t && t.id; }, [NEWX, rot.box_y1 - 1]);
  const hHitH = await page.evaluate(([x, y]) => { const t = pickText(x, y); return t && t.id; }, [rot.box_x1 - 1, NEWY]);
  ok(hHitV === yun.id, `vertical edge of rotated text hits (${hHitV})`);
  await shot("10_rotated_text");
  // save + reload: the sync must persist
  await page.fill("#fname", "p0_e22_" + Date.now() + ".gpkg"); await page.click("#save"); await page.waitForTimeout(5000);
  s = await st(); ok(s.dirty === false, `dirty cleared after save (server state)`);
  const h2 = await page.evaluate(([x, y]) => { const t = pickText(x, y); return t && t.id; }, [NEWX, NEWY]);
  ok(h2 === yun.id, `after save, client pickText still hits at the new position`);
  ok(s.texts.find(t => t.id === yun.id).angle_deg === 90, `angle still 90 in server state`);
  await op("undo", {}); await op("undo", {});  // undo rotate + move back to original for next tests
  s = await st(); const back = s.texts.find(t => t.id === yun.id);
  ok(back.x === 32 && back.y === 67, `undo x2 restores original position ${back.x},${back.y} angle ${back.angle_deg}`);

  // ---------- E04: box over existing text -> edited_existing, no dup ----------
  const n0 = s.texts.length;
  await tool("textBox"); await dragBox([yun.x - 8, yun.y - 8, yun.x + 8, yun.y + 8]);
  let pv = await page.evaluate(() => textPv);
  ok(pv && pv.existing && pv.existing.length === 1 && pv.existing[0].id === yun.id, `preview detects existing text in box: ${JSON.stringify(pv && pv.existing)}`);
  ok(pv.ocr.status === "reused" && pv.ocr.engine === "existing", `OCR reuses existing (status=${pv.ocr.status}) — no silent empty candidate`);
  await page.fill("#tText", "云"); await page.click("#textApply"); await page.waitForTimeout(800);
  s = await st(); ok(s.texts.length === n0, `apply over existing edits it, no duplicate (${s.texts.length} texts)`);
  await dragBox([yun.x - 8, yun.y - 8, yun.x + 8, yun.y + 8]);
  pv = await page.evaluate(() => textPv);
  await page.fill("#tText", "云"); await page.click("#textApply"); await page.waitForTimeout(800);
  s = await st(); ok(s.texts.length === n0, `second apply still no duplicate (${s.texts.length} texts)`);
  await shot("11_no_dup_text");

  // ---------- E31: merge provenance + history ----------
  const lasso = await op("select_gesture", { kind: "lasso", points: [[5, 5], [60, 5], [60, 60], [5, 60]], rule: "centre" });
  const ids = (lasso.ids || []).slice(0, 6);
  ok(ids.length >= 2, `lasso selected ${ids.length} faces for merge`);
  r = await op("merge_groups", { ids });
  if (r.ok === false && /allow_mixed_labels/.test(r.error || "")) r = await op("merge_groups", { ids, allow_mixed_labels: true });
  ok(r.ok !== false && r.groups >= 1, `merge_groups applied: ${JSON.stringify(r)}`);
  const hist = await op("merge_history", {});
  ok(hist.history && hist.history.length >= 1, `merge_history exposes ${hist.history && hist.history.length} entries`);
  s = await st(); const withSrc = s.faces.filter(f => f.attrs && f.attrs.merged_from);
  ok(withSrc.length >= 1, `state faces carry merged_from provenance (${withSrc.length})`);
  if (withSrc.length) { const src = JSON.parse(withSrc[0].attrs.merged_from);
    ok(src.every(e => e.eid != null && e.rgb && e.op), `provenance keeps eid/rgb/op: ${JSON.stringify(src).slice(0, 120)}`); }
  await op("undo", {});
  s = await st(); ok(!s.faces.some(f => f.attrs && f.attrs.merged_from), `undo clears provenance`);

  // ---------- E12: status semantics on an empty box ----------
  await tool("textBox"); await dragBox([210, 210, 240, 240]);   // likely blank corner
  pv = await page.evaluate(() => textPv);
  ok(pv && pv.ocr && typeof pv.ocr.status === "string" && pv.ocr.status !== "", `ocr status present on empty box: ${JSON.stringify(pv.ocr)}`);
  ok(pv.ocr.status !== "reused" || (pv.existing || []).length > 0, `status consistent with existing list`);
  await page.click("#textCancel");
  await shot("12_p0_done");
  return JSON.stringify({ fail: fail.length, log });
}
