#!/usr/bin/env bash
# Vidéo de présentation pme-radar (motion design, 1080p 60 i/s, bande-son synthétisée).
#   1. captures du dashboard sur l'échantillon synthétique (Streamlit lancé temporairement)
#   2. faits affichés (chiffres réels agrégés du run 92, cible synthétique, nombre de tests)
#   3. rendu image par image de scripts/promo/motion (Playwright -> ffmpeg)
#   4. bande-son synchronisée sur les repères de l'animation (numpy)
#   5. assemblage + aperçu GIF du README + affiche
# Prérequis : venv du projet actif, node + playwright, ffmpeg. Durée : quelques minutes.
# Options : FPS=30 ./scripts/promo/build_video.sh (plus rapide) · SILENT=1 (sans bande-son)
set -euo pipefail
cd "$(dirname "$0")/../.."
FPS="${FPS:-60}"
TMP="$(mktemp -d)"
PORT=8611
streamlit run dashboard/app.py --server.headless true --server.port "$PORT" \
  --browser.gatherUsageStats false >/dev/null 2>&1 &
ST_PID=$!
cleanup() { kill "$ST_PID" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

echo "1/5 Captures du dashboard"
node scripts/promo/capture_dashboard.js "$TMP" "$PORT"
kill "$ST_PID" 2>/dev/null || true

echo "2/5 Faits affichés"
python scripts/promo/motion/facts.py "$TMP" > "$TMP/facts.json"

echo "3/5 Rendu image par image (${FPS} i/s)"
FPS="$FPS" node scripts/promo/motion/render.js "$TMP" "$TMP/facts.json" "$TMP/video.mp4" "$TMP/cues.json"

mkdir -p docs/video
OUT=docs/video/pme-radar-promo.mp4
if [ "${SILENT:-0}" = "1" ]; then
  cp "$TMP/video.mp4" "$OUT"
else
  echo "4/5 Bande-son"
  python scripts/promo/motion/soundtrack.py "$TMP/cues.json" "$TMP/audio.wav"
  ffmpeg -y -loglevel error -i "$TMP/video.mp4" -i "$TMP/audio.wav" \
    -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT"
fi

echo "5/5 Aperçu GIF et affiche"
ffmpeg -y -loglevel error -ss 16.6 -t 8.4 -i "$OUT" \
  -vf "fps=10,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
  docs/img/demo.gif
ffmpeg -y -loglevel error -ss 26.2 -i "$OUT" -frames:v 1 -q:v 2 docs/video/pme-radar-promo-poster.jpg
ls -lh "$OUT" docs/img/demo.gif docs/video/pme-radar-promo-poster.jpg
