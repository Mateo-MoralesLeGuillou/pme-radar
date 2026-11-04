// Captures du dashboard pour le README (docs/img/dashboard-*.png) et pour la vidéo (cibles, filtre
// « score minimum », fiche ouverte depuis le tableau), avec la position des éléments que la vidéo anime.
// Prérequis : streamlit lancé sur l'échantillon synthétique (PME_RADAR_DATA=sample) sur le port indiqué.
// Usage : node scripts/promo/capture_dashboard.js <dossier_sortie> [port]
const { chromium } = require("playwright");
const fs = require("fs");

(async () => {
  const out = process.argv[2];
  const base = `http://localhost:${process.argv[3] || "8501"}`;
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, locale: "fr-FR" });
  const p = await ctx.newPage();
  for (let i = 0; i < 90; i++) {
    try { await p.goto(base); break; } catch { await p.waitForTimeout(1000); }
  }
  const ready = async (text) => {
    await p.getByText(text).first().waitFor({ timeout: 90000 });
    await p.waitForTimeout(3500);
  };
  const snap = async (name) => {
    await p.mouse.move(1435, 895); // souris hors des graphiques : pas de barre d'outils au survol
    await p.waitForTimeout(900);
    await p.screenshot({ path: `${out}/${name}.png` });
  };
  const open = async (path, text) => {
    await p.goto(`${base}/${path}`);
    await ready(text);
  };
  const center = async (loc) => {
    const r = await loc.boundingBox();
    return [Math.round(r.x + r.width / 2), Math.round(r.y + r.height / 2)];
  };

  // ------------------------------------------------------------------ README
  await ready("À faire maintenant");
  await snap("dashboard-accueil");
  await p.getByRole("combobox").first().click(); // recherche globale
  await p.keyboard.type("pel", { delay: 120 });
  await p.waitForTimeout(1500);
  await snap("dashboard-recherche");
  await p.keyboard.press("Escape");
  await open("entreprise?siren=999000197", "Points forts");
  await snap("dashboard-fiche");
  await p.getByRole("tab", { name: "Valorisation" }).click();
  await p.waitForTimeout(2000);
  await p.getByRole("tab", { name: "Valorisation" }).evaluate((el) => el.scrollIntoView({ block: "start" }));
  await p.waitForTimeout(1200);
  await snap("dashboard-valorisation");
  await open("campagne", "Pipeline par statut");
  await snap("dashboard-contacts");

  // ------------------------------------------------------------------ vidéo
  await open("cibles", "Sélections rapides");
  const handle = p.locator('[data-testid="stSlider"]').filter({ hasText: "Score minimum" }).getByRole("slider");
  const layout = { slider_from: await center(handle) };
  await snap("screener");
  await handle.focus();
  for (let i = 0; i < 16; i++) await p.keyboard.press("ArrowRight"); // score minimum 80 (pas de 5)
  await p.waitForTimeout(4000);
  layout.slider_to = await center(handle);
  layout.count = await p.getByText(/entreprises? sur \d+/).first().evaluate((el) => {
    const range = document.createRange(); // étendue du texte, pas de toute la colonne
    range.selectNodeContents(el);
    const r = range.getBoundingClientRect();
    return [r.left, r.top, r.right, r.bottom].map(Math.round);
  });
  const grid = await p.locator('[data-testid="stDataFrame"]').first().boundingBox();
  layout.open = [Math.round(grid.x + 77), Math.round(grid.y + 54)]; // bouton « Ouvrir » de la 1re ligne
  await snap("screener_filtered");
  await p.mouse.click(layout.open[0], layout.open[1]);
  await ready("Points forts"); // la fiche s'ouvre : le clic visé est le bon
  await snap("company");
  fs.writeFileSync(`${out}/layout.json`, JSON.stringify(layout));
  await b.close();
})();
