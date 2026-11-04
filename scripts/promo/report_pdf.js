// Exporte un rapport de deal flow HTML en PDF A4 (Chromium de Playwright).
// Usage : node scripts/promo/report_pdf.js <rapport.html> <sortie.pdf> [capture.png]
const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const [src, pdf, shot] = process.argv.slice(2);
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1100, height: 1400 }, deviceScaleFactor: 1 });
  await page.goto("file://" + path.resolve(src));
  await page.evaluate(() => document.fonts.ready);
  if (shot) await page.screenshot({ path: shot, fullPage: true });
  await page.pdf({ path: pdf, format: "A4", printBackground: true, preferCSSPageSize: true });
  await b.close();
})();
