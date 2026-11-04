// Captures du dashboard (README + vidéo). Prérequis : streamlit lancé sur le port indiqué.
// Usage : node scripts/promo/capture_dashboard.js <dossier_sortie> [port]
const { chromium } = require("playwright");
(async () => {
  const out = process.argv[2];
  const port = process.argv[3] || "8599";
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  for (let i = 0; i < 60; i++) {
    try { await p.goto(`http://localhost:${port}`); break; } catch { await p.waitForTimeout(1000); }
  }
  await p.getByText("Entonnoir d'origination").first().waitFor({ timeout: 90000 });
  await p.waitForTimeout(4000);
  const snap = async (name) => {
    await p.mouse.move(1435, 895); // souris hors des graphiques : pas de barre d'outils au survol
    await p.waitForTimeout(1200);
    await p.screenshot({ path: `${out}/${name}.png` });
  };
  const scrollTo = async (text) => {
    await p.getByText(text, { exact: false }).first().evaluate((el) => el.scrollIntoView({ block: "start" }));
  };
  const tab = async (name) => { await p.getByRole("tab", { name }).click(); await p.waitForTimeout(2500); };

  await snap("overview_top");
  await scrollTo("Distribution des scores");
  await snap("overview_scores");
  await tab("Cibles");
  await scrollTo("Meilleures cibles");
  await snap("targets_table");
  await scrollTo("Fiche cible");
  await snap("targets_detail");
  await scrollTo("Brouillon d'approche");
  await snap("targets_mail");
  await tab("Campagne");
  await scrollTo("KPI de campagne");
  await snap("campaign");
  // État filtré : score minimum 80 (16 pas de 5 au clavier)
  await tab("Vue d'ensemble");
  const handle = p.getByRole("slider").first();
  await handle.focus();
  for (let i = 0; i < 16; i++) await p.keyboard.press("ArrowRight");
  await p.waitForTimeout(3500);
  await p.locator(".pr-hero").first().evaluate((el) => el.scrollIntoView({ block: "end" }));
  await p.locator(".pr-hero").first().evaluate((el) => el.closest("section, [data-testid='stMain']")?.scrollTo?.(0, 0));
  await snap("overview_filtered");
  await b.close();
})();
