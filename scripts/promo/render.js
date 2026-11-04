// Rend chaque scène de scenes.html en PNG 3840x2160 (devicePixelRatio 2). Usage : node render.js <outdir>
const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const out = process.argv[2];
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const file = "file://" + path.resolve(__dirname, "scenes.html");
  for (let i = 1; i <= 9; i++) {
    await page.goto(`${file}?s=${i}`);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${out}/s${i}.png` });
  }
  await b.close();
})();
