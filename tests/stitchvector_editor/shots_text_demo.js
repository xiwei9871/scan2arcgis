// Real-browser screenshots for the text-layer visual acceptance.
// Same viewport and the same view transform (scale + offset) for every shot, dual view off,
// so pixel (x, y) in every PNG is the same map position. Placeholders: __PORT__, __OUT__, __SHOTS__.
async (page) => {
  const out = "__OUT__"; const shots = __SHOTS__; const log = [];
  await page.setViewportSize({ width: 1500, height: 900 });
  await page.goto("http://127.0.0.1:__PORT__/"); await page.waitForTimeout(1800);
  const header = await page.textContent("#src"); log.push("header: " + header.replace(/\s+/g, " "));
  const set = async (st) => {
    await page.evaluate((st) => {
      document.getElementById("dual").checked = false;
      for (const [k, v] of Object.entries(st)) if (k in { showImg: 1, showFaces: 1, showLines: 1, showText: 1, showResidue: 1 }) document.getElementById(k).checked = v;
      document.getElementById("alpha").value = 100;
      textPv = null; healPv = null; mergePv = null; splitPv = null; sel = { layer: "face", ids: [] }; hover = null; selText = null; hiRes = null;
      draw();
      // fixed transform: 4.5 screen px per image px, map strip (x 0-70, y 0-300) on screen
      const v = st.view || { s: 4.5, x: 20, y: 10 }; view.s = v.s; view.x = v.x; view.y = v.y; draw();
    }, st);
    await page.waitForTimeout(400);
  };
  for (const s of shots) {
    await set({ ...s.state, view: s.view });
    const v = await page.evaluate(() => ({ s: view.s, x: view.x, y: view.y, img: document.getElementById("showImg").checked, faces: document.getElementById("showFaces").checked,
      lines: document.getElementById("showLines").checked, text: document.getElementById("showText").checked, residue: document.getElementById("showResidue").checked,
      alpha: +document.getElementById("alpha").value, dual: document.getElementById("dual").checked }));
    await page.locator("#cv").screenshot({ path: `${out}/${s.name}.png` });
    log.push(`${s.name}: ${JSON.stringify(v)}`);
  }
  await page.screenshot({ path: `${out}/${shots[shots.length - 1].name}_fullpage.png` });
  return JSON.stringify({ log });
}
