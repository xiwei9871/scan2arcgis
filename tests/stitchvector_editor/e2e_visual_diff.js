// Browser check of the residual ("差异") view on the U2 full sheet. Placeholder: __PORT__, __OUT__.
async (page) => {
  const log = []; let fail = 0;
  const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail++; };
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto("http://127.0.0.1:__PORT__/"); await page.waitForFunction(() => /OCR/.test(document.getElementById("src").textContent), null, { timeout: 30000 }); await page.waitForTimeout(500);
  const header = (await page.textContent("#src")).replace(/\s+/g, " ");
  ok(/OCR/.test(header) && /文字/.test(header), "header shows OCR candidates and text-object counts: " + header);
  const modes = await page.evaluate(() => [...document.getElementById("diffMode").options].map(o => o.value));
  ok(modes.length >= 3, "diff modes: " + modes.join(","));
  for (const m of modes) {
    if (!m || m === "off") continue;
    await page.selectOption("#diffMode", m); await page.waitForTimeout(2500);
    const st = await page.evaluate(() => ({ mode: DIFF.mode, heat: !!DIFF.heat, w: DIFF.heat ? DIFF.heat.width : 0, h: DIFF.heat ? DIFF.heat.height : 0 }));
    ok(st.heat && st.w === 805 && st.h === 780, `mode ${m}: residual layer at the scan grid ${st.w}x${st.h}`);
    await page.screenshot({ path: `__OUT__/diff_${m}.png` });
  }
  // threshold: a higher threshold shows no more pixels than a lower one
  const count = () => page.evaluate(() => { const c = DIFF.heat.getContext("2d").getImageData(0, 0, DIFF.heat.width, DIFF.heat.height).data; let n = 0; for (let i = 3; i < c.length; i += 4) if (c[i] > 0) n++; return n; });
  await page.fill("#diffThr", "1"); await page.dispatchEvent("#diffThr", "input"); await page.waitForTimeout(300); const n1 = await count();
  await page.fill("#diffThr", "60"); await page.dispatchEvent("#diffThr", "input"); await page.waitForTimeout(300); const n60 = await count();
  ok(n1 > n60 && n60 > 0, `threshold 1 -> ${n1} px shown, 60 -> ${n60} px`);
  // opacity
  await page.fill("#diffAlpha", "20"); await page.dispatchEvent("#diffAlpha", "input"); await page.waitForTimeout(300);
  const a20 = await page.evaluate(() => { const c = DIFF.heat.getContext("2d").getImageData(0, 0, DIFF.heat.width, DIFF.heat.height).data; for (let i = 3; i < c.length; i += 4) if (c[i] > 0) return c[i]; return 0; });
  await page.fill("#diffAlpha", "90"); await page.dispatchEvent("#diffAlpha", "input"); await page.waitForTimeout(300);
  const a90 = await page.evaluate(() => { const c = DIFF.heat.getContext("2d").getImageData(0, 0, DIFF.heat.width, DIFF.heat.height).data; for (let i = 3; i < c.length; i += 4) if (c[i] > 0) return c[i]; return 0; });
  ok(a90 > a20, `opacity 20% -> alpha ${a20}, 90% -> ${a90}`);
  // synced zoom: wheel on the left pane changes the shared view used by both canvases
  const s0 = await page.evaluate(() => view.s); const r = await page.evaluate(() => { const b = document.getElementById("cvL").getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; });
  await page.mouse.move(r[0], r[1]); await page.mouse.wheel(0, -300); await page.waitForTimeout(300);
  const s1 = await page.evaluate(() => view.s); ok(s1 > s0, `left-pane wheel zooms the shared view ${s0.toFixed(2)} -> ${s1.toFixed(2)}`);
  // click-to-locate: pick a residual pixel and ask what is there
  const hit = await page.evaluate(async () => {
    const W = DIFF.heat.width, raw = DIFF.raw[Object.keys(DIFF.raw).pop()]; let p = null;
    for (let i = 0; i < raw.length; i += 4) if (raw[i] >= 60) { const k = i / 4; p = [k % W + 0.5, Math.floor(k / W) + 0.5]; break; }
    if (!p || typeof diffLocate !== "function") return { p, info: null };
    await diffLocate(p[0], p[1]); return { p, info: document.getElementById("diffInfo").textContent };
  });
  ok(hit.p && hit.info && /面|线/.test(hit.info) && !/残差 0；/.test(hit.info), `click on residual pixel ${JSON.stringify(hit.p)} locates: ${hit.info}`);
  const ed = await page.evaluate(() => fetch("/api/state").then(r => r.json()).then(s => ({ dirty: s.dirty, undo: s.undo })));
  ok(!ed.dirty && ed.undo === 0, "diff view made no edit");
  return JSON.stringify({ fail, log });
}
