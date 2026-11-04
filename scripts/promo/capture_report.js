// Captures de trois pages du rapport de deal flow (vidéo) : synthèse, ouverture du premier dossier,
// questions de due diligence. Usage : node scripts/promo/capture_report.js <rapport.html> <dossier>
const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const [src, out] = process.argv.slice(2);
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1100, height: 1420 }, deviceScaleFactor: 1.4 });
  await p.goto("file://" + path.resolve(src));
  await p.evaluate(() => document.fonts.ready);
  const scrollTo = (loc, margin) =>
    loc.evaluate((el, m) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - m), margin);
  await p.screenshot({ path: `${out}/report_p1.png` });
  const first = p.locator(".dossier").first();
  await scrollTo(first, 20);
  await p.screenshot({ path: `${out}/report_p2.png` });
  await scrollTo(first.locator("h3", { hasText: "Valorisation et montage" }), 30);
  await p.screenshot({ path: `${out}/report_p3.png` });
  await b.close();
})();
