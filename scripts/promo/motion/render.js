// Rendu image par image de la vidéo (motion.js) vers ffmpeg.
// Usage : node render.js <captures_dashboard> <facts.json> <sortie.mp4> <cues.json>
//   FPS=60 (défaut) · TIMES=1,2.5,8 : mode aperçu, écrit des PNG dans le dossier <sortie.mp4>.
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

(async () => {
  const [shots, factsPath, out, cuesPath] = process.argv.slice(2, 6);
  const fps = Number(process.env.FPS || 60);
  const times = process.env.TIMES ? process.env.TIMES.split(",").map(Number) : null;
  const facts = JSON.parse(fs.readFileSync(factsPath, "utf8"));
  const root = path.resolve(__dirname, "../../..");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on("pageerror", (e) => { console.error("Erreur dans la page :", e.message); process.exit(1); });
  await page.goto("file://" + path.join(__dirname, "index.html"));
  const assets = { logo: "file://" + path.join(root, "docs/img/logo.svg"), shots: "file://" + path.resolve(shots) };
  await page.evaluate(([F, A]) => window.init(F, A), [facts, assets]);
  await page.waitForFunction(
    () => Array.from(document.images).every((i) => i.complete && i.naturalWidth > 0),
    null, { timeout: 30000 },
  );
  await page.evaluate(() => document.fonts.ready);
  const meta = await page.evaluate(() => ({ duration: window.DURATION, cues: window.CUES, sections: window.SECTIONS }));
  if (cuesPath) fs.writeFileSync(cuesPath, JSON.stringify(meta, null, 1));

  if (times) {
    fs.mkdirSync(out, { recursive: true });
    for (const t of times) {
      await page.evaluate((x) => window.renderFrame(x), t);
      await page.screenshot({ path: path.join(out, `f_${t.toFixed(2).padStart(5, "0")}.png`) });
    }
    await browser.close();
    return;
  }

  const total = Math.round(meta.duration * fps);
  const ff = spawn("ffmpeg", [
    "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
    // -tune animation : adapté aux aplats du motion design ; CRF 21 ≈ sans perte visible (SSIM 0,996)
    "-c:v", "libx264", "-preset", "slow", "-tune", "animation", "-crf", process.env.CRF || "21",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart", out,
  ], { stdio: ["pipe", "inherit", "inherit"] });
  const started = Date.now();
  for (let f = 0; f < total; f++) {
    await page.evaluate((x) => window.renderFrame(x), f / fps);
    const buf = await page.screenshot({ type: "jpeg", quality: 95 });
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once("drain", r));
    if (f % 600 === 0) console.error(`  ${f}/${total} images (${((Date.now() - started) / 1000).toFixed(0)} s)`);
  }
  ff.stdin.end();
  await new Promise((res, rej) => ff.on("close", (c) => (c === 0 ? res() : rej(new Error(`ffmpeg a échoué (${c})`)))));
  await browser.close();
  console.error(`  ${total} images rendues en ${((Date.now() - started) / 1000).toFixed(0)} s`);
})();
