# Supports de présentation

| Fichier | Rôle |
|---|---|
| `build_video.sh` | Construit `docs/video/pme-radar-promo.mp4`, l'aperçu `docs/img/demo.gif` et l'affiche |
| `motion/` | Moteur d'animation de la vidéo (HTML + JavaScript), rendu image par image |
| `capture_dashboard.js` | Captures du dashboard (README et vidéo) sur l'échantillon synthétique |
| `capture_report.js`, `report_pdf.js` | Pages du rapport de deal flow pour la vidéo ; export PDF d'un rapport |
| `banner.html`, `render_brand.js` | Bannière du README et logo PNG |

## Régénérer la vidéo

```bash
. .venv/bin/activate
./scripts/promo/build_video.sh            # 1080p 60 i/s, avec bande-son
FPS=30 ./scripts/promo/build_video.sh     # plus rapide
SILENT=1 ./scripts/promo/build_video.sh   # sans bande-son ni voix
# Voix off : ELEVENLABS_API_KEY (et ELEVENLABS_VOICE_ID, une voix française) dans .env ou l'environnement
```

Prérequis : Node.js avec Playwright (Chromium) et ffmpeg. Compter quelques minutes.

## Comment c'est fait

- **Animation** (`motion/motion.js`) : chaque image est une fonction pure du temps. `render.js` appelle
  `renderFrame(t)` pour chaque image, en fait une capture et l'envoie à ffmpeg. Le rendu est donc
  fluide (60 i/s) et identique d'une exécution à l'autre.
- **Fil rouge** : les 343 points sont les 343 sociétés du run réel des Hauts-de-Seine. Ils apparaissent
  sur le radar, traversent le pipeline (29 exclues pour procédure collective, 35 qualifiées), puis la
  caméra plonge sur une cible.
- **Bande-son** (`motion/soundtrack.py`) : synthétisée avec numpy, sans fichier audio tiers ni droits à
  gérer, et calée sur les repères émis par l'animation (balayage radar, transitions, compteurs, cloche
  du score, tampon, clics, frappe).

## Ce qui est réel, ce qui est synthétique

`motion/facts.py` rassemble tout ce qui est affiché :

- **réels** : les chiffres agrégés du run du 4 novembre 2026 (343 sourcées, 29 exclues, 314 notées,
  35 qualifiées), repris du README ; le nombre de tests, collecté par pytest au moment du rendu ;
- **synthétiques** : la cible, son score, son dossier de pré-DD, son brouillon, les pages du rapport et
  les captures du dashboard viennent d'un run hors ligne sur les données synthétiques (les mêmes que
  `examples/`). La vidéo l'indique à l'écran (« Cible synthétique », « Démo sur données synthétiques »).

## Voix off (ElevenLabs)
- `motion/narration.py` : le texte, segment par segment, calé sur la timeline (91 s). Le texte affiché
  en sous-titres et le texte lu sont distincts (nombres en toutes lettres).
- `motion/voiceover.py` : un appel text-to-speech par segment, mis en cache dans `data/cache/voice` ;
  un segment trop long est accéléré (x1,15 au plus) ; sortie : piste voix + sous-titres SRT.
- `motion/soundtrack.py` mixe la voix (niveau calé sur sa moyenne) et abaisse la musique de 12 dB
  sous la voix. Les sous-titres sont ajoutés au MP4 comme piste désactivable.
- Sans clé, la vidéo est construite avec la musique seule.

