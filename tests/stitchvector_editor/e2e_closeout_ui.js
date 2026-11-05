async (page) => {
  const log = [], fail = [];
  const ok = (c, m) => { log.push((c ? "PASS " : "FAIL ") + m); if (!c) fail.push(m); };
  await page.goto("http://127.0.0.1:8791/", { waitUntil: "networkidle" });
  await page.waitForSelector("#cv", { timeout: 30000 });
  await page.waitForTimeout(3000);
  ok(await page.$("#cv") !== null, "page + canvas load");
  ok(await page.$("#fragSelect") !== null, "fragSelect button present");
  ok(await page.$('[data-tool="joinEnds"]') !== null, "joinEnds tool button present");
  const h3s = await page.$$eval("h3", hs => hs.map(h => h.textContent).join("|"));
  ok(h3s.includes("④"), "workflow-numbered h3: " + h3s.slice(0, 80));
  ok((await page.$$("details")).length >= 3, "advanced sections collapsed in details");
  ok(await page.$("#undo") !== null && await page.$("#redo") !== null, "undo/redo buttons present");
  // fragSelect: pick a small face via API pick then apply filter through real UI click
  const S = await page.evaluate(() => fetch("/api/state").then(r => r.json()));
  const small = S.faces.filter(f => { const r = f.rings[0]; let a = 0;
    for (let i = 0; i < r.length; i++) { const p = r[i], q = r[(i + 1) % r.length]; a += p[0] * q[1] - q[0] * p[1]; } return Math.abs(a / 2) <= 60; });
  ok(small.length > 0, `small faces exist in U2 for frag filter: ${small.length}`);
  // click centre of a small face with neighbours, then press fragSelect
  const scr = ([x, y]) => page.evaluate(([x, y]) => { const r = document.getElementById("cv").getBoundingClientRect();
    return [r.left + view.x + x * view.s, r.top + view.y + y * view.s]; }, [x, y]);
  let picked = null;
  for (const f of small) { const r = f.rings[0];
    const cx = r.reduce((a, p) => a + p[0], 0) / r.length, cy = r.reduce((a, p) => a + p[1], 0) / r.length;
    const [sx, sy] = await scr([cx, cy]); await page.mouse.click(sx, sy); await page.waitForTimeout(300);
    const n = await page.evaluate(() => sel.ids.length);
    if (n === 1) { picked = f; break; } }
  ok(picked !== null, "picked a face via real canvas click");
  if (picked) { await page.click("#fragSelect"); await page.waitForTimeout(800);
    const msg = await page.$eval("#msg", e => e.textContent);
    const n = await page.evaluate(() => sel.ids.length);
    log.push("INFO fragSelect msg: " + msg + " sel=" + n);
    ok(n >= 1 && !msg.includes("Error"), "fragSelect ran through UI (adds neighbours or reports none)"); }
  // joinEnds tool: two real clicks on endpoints
  const gapEnds = await page.evaluate(() => { const S = window.S || null; return fetch("/api/state").then(r => r.json()).then(S => {
    let best = null;
    for (const a of S.lines) for (const b of S.lines) { if (a.id >= b.id) continue;
      for (const p of [a.coords[0], a.coords[a.coords.length-1]]) for (const q of [b.coords[0], b.coords[b.coords.length-1]]) {
        const d = Math.hypot(p[0]-q[0], p[1]-q[1]); if (d > 0.5 && d < 20 && (!best || d < best.d)) best = {a, b, p, q, d}; } }
    return best; }); });
  if (gapEnds) { await page.click('[data-tool="joinEnds"]');
    const [sx1, sy1] = await scr(gapEnds.p); await page.mouse.click(sx1, sy1); await page.waitForTimeout(300);
    const je1 = await page.evaluate(() => window.joinEnd !== null && typeof joinEnd === "object");
    ok(je1, `first endpoint picked (line ${gapEnds.a.id}, gap ${gapEnds.d.toFixed(1)}px)`);
    const [sx2, sy2] = await scr(gapEnds.q); await page.mouse.click(sx2, sy2); await page.waitForTimeout(600);
    const info = await page.$eval("#joinInfo", e => e.textContent);
    ok(info.includes("链接顺序"), "joinEnds produced join preview: " + info.replace(/\n/g, " ").slice(0, 90));
  } else ok(false, "no endpoint gap pair found in U2");
  const errs = await page.evaluate(() => window.__consoleErrs || []);
  return JSON.stringify({ fail: fail.length, log, errs });
}
