#!/usr/bin/env bash
# Vidéo de présentation pme-radar (motion design, 1080p 60 i/s, bande-son synthétisée, voix off option.).
#   1. run hors ligne + rapport de deal flow (données synthétiques) ; captures du dashboard et du rapport
#   2. faits affichés (agrégats réels du run 92, dossier de pré-DD de la meilleure cible, nombre de tests)
#   3. rendu image par image de scripts/promo/motion (Playwright -> ffmpeg)
#   4. voix off ElevenLabs si ELEVENLABS_API_KEY est définie, puis bande-son mixée (numpy)
#   5. assemblage (+ sous-titres de la voix off), aperçu GIF du README, affiche
# Prérequis : venv du projet actif, node + playwright, ffmpeg. Durée : quelques minutes.
# Options : FPS=30 (plus rapide) · SILENT=1 (ni musique ni voix) · ELEVENLABS_VOICE_ID=... (voix)
set -euo pipefail
cd "$(dirname "$0")/../.."
# Variables ELEVENLABS_* du .env (lecture ligne à ligne : le .env n'est pas un script shell)
if [ -f .env ]; then
  while IFS='=' read -r key value; do
    case "$key" in ELEVENLABS_*) [ -n "$value" ] && [ -z "${!key:-}" ] && export "$key=$value" ;; esac
  done < .env
fi
FPS="${FPS:-60}"
TMP="$(mktemp -d)"
PORT=8611
streamlit run dashboard/app.py --server.headless true --server.port "$PORT" \
  --browser.gatherUsageStats false >/dev/null 2>&1 &
ST_PID=$!
cleanup() { kill "$ST_PID" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

echo "1/5 Données de démonstration, rapport de deal flow et captures"
pme-radar run --offline --data-dir "$TMP/data" >/dev/null
cp examples/sample_campaign.csv "$TMP/data/out/campaign.csv"
pme-radar report --data-dir "$TMP/data" --top-n 4 --output "$TMP/rapport.html" >/dev/null
node scripts/promo/capture_report.js "$TMP/rapport.html" "$TMP"
node scripts/promo/capture_dashboard.js "$TMP" "$PORT"
kill "$ST_PID" 2>/dev/null || true

echo "2/5 Faits affichés"
python scripts/promo/motion/facts.py "$TMP" "$TMP/data" > "$TMP/facts.json"

echo "3/5 Rendu image par image (${FPS} i/s)"
FPS="$FPS" node scripts/promo/motion/render.js "$TMP" "$TMP/facts.json" "$TMP/video.mp4" "$TMP/cues.json"

mkdir -p docs/video
OUT=docs/video/pme-radar-promo.mp4
SRT=docs/video/pme-radar-promo.srt
if [ "${SILENT:-0}" = "1" ]; then
  cp "$TMP/video.mp4" "$OUT"
else
  VOICE=()
  if [ -n "${ELEVENLABS_API_KEY:-}" ]; then
    echo "4/5 Voix off ElevenLabs"
    python scripts/promo/motion/voiceover.py "$TMP/voice.wav" "$SRT" data/cache/voice
    VOICE=("$TMP/voice.wav")
  else
    echo "4/5 Bande-son (pas de ELEVENLABS_API_KEY : musique seule, sans voix off)"
  fi
  python scripts/promo/motion/soundtrack.py "$TMP/cues.json" "$TMP/audio.wav" ${VOICE[@]+"${VOICE[@]}"}
  if [ ${#VOICE[@]} -gt 0 ]; then
    ffmpeg -y -loglevel error -i "$TMP/video.mp4" -i "$TMP/audio.wav" -i "$SRT" \
      -map 0:v -map 1:a -map 2:s -c:v copy -c:a aac -b:a 192k -c:s mov_text \
      -metadata:s:s:0 language=fre -disposition:s:0 0 -shortest -movflags +faststart "$OUT"
  else
    ffmpeg -y -loglevel error -i "$TMP/video.mp4" -i "$TMP/audio.wav" \
      -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart "$OUT"
  fi
fi

echo "5/5 Aperçu GIF et affiche"
ffmpeg -y -loglevel error -ss 16.6 -t 8.4 -i "$OUT" \
  -vf "fps=10,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
  docs/img/demo.gif
ffmpeg -y -loglevel error -ss 53.8 -i "$OUT" -frames:v 1 -q:v 3 docs/video/pme-radar-promo-poster.jpg
ls -lh "$OUT" docs/img/demo.gif docs/video/pme-radar-promo-poster.jpg
