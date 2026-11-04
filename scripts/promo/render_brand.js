// Rend la bannière du README et le logo PNG. Usage : node scripts/promo/render_brand.js
const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const root = path.resolve(__dirname, "../..");
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1280, height: 320 }, deviceScaleFactor: 2 });
  await page.goto("file://" + path.join(__dirname, "banner.html"));
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(root, "docs/img/banner.png") });
  // Logo : le SVG ouvert directement (128 px) rendu en 2x, fond transparent
  const logo = await b.newPage({ viewport: { width: 128, height: 128 }, deviceScaleFactor: 2 });
  await logo.goto("file://" + path.join(root, "docs/img/logo.svg"));
  await logo.waitForTimeout(200);
  await logo.screenshot({ path: path.join(root, "docs/img/logo.png"), omitBackground: true });
  await b.close();
})();
