#!/usr/bin/env bash
# Génère docs/video/pme-radar-promo.mp4 (1080p, 30 fps, sans audio). Prérequis : node + playwright, ffmpeg.
set -euo pipefail
cd "$(dirname "$0")/../.."
TMP=$(mktemp -d)
node scripts/promo/render.js "$TMP"
FPS=30
dur=(0 4 6 7 7 8 7 7 6 6)           # durée (s) de chaque scène 1..9
zoom=(0 0 0 0 0 0 1 1 0 0)          # 1 = léger zoom lent (captures du dashboard)
i=1; : > "$TMP/list.txt"
while [ $i -le 9 ]; do
  d=${dur[$i]}; frames=$((d*FPS))
  if [ "${zoom[$i]}" = 1 ]; then
    vf="zoompan=z='1+0.07*on/${frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=${frames}:s=1920x1080:fps=${FPS}"
  else
    vf="scale=1920:1080,fps=${FPS}"
  fi
  ffmpeg -loglevel error -y -loop 1 -i "$TMP/s$i.png" -t "$d" \
    -vf "${vf},fade=t=in:st=0:d=0.5,format=yuv420p" \
    -c:v libx264 -crf 20 -preset medium "$TMP/c$i.mp4"
  echo "file 'c$i.mp4'" >> "$TMP/list.txt"; i=$((i+1))
done
ffmpeg -loglevel error -y -f concat -safe 0 -i "$TMP/list.txt" -c copy -movflags +faststart docs/video/pme-radar-promo.mp4
ffmpeg -loglevel error -y -i docs/video/pme-radar-promo.mp4 -vf "select=eq(n\,100)" -frames:v 1 docs/video/pme-radar-promo-poster.png 2>/dev/null || true
rm -rf "$TMP"; ls -lh docs/video
