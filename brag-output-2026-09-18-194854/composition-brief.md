# Hyperframes Composition Brief: भक्तपुर AI — cinematic product film

## Objective
A ~57s landscape cinematic product film for **Bhaktapur AI** (company: **Hashtag
Technology**), built from the user's supplied nine-panel Nepali storyboard.

## Output
- Composition: `brag-output-2026-09-18-194854/composition/`
- Video: `brag-output-2026-09-18-194854/brag.mp4`
- Format: **landscape 1920x1080** · Duration: **56.76s**

## Source Material
- `assets/panels/p1.jpg … p8.jpg`, `assets/panels/hero.jpg` — cut from the user's
  `ai1.png` on programmatically detected gutters, upscaled 2.9× lanczos + unsharp.
  Original panel sizes 270-451px wide, so **never display a panel above ~1300px wide**.
- Treatment per scene: the same image twice — a **blurred, darkened full-bleed fill**
  behind (hides upscale entirely) and a **sharp inset card** in front.

## Creative Direction
- Tone: `cinematic`. Apple-style product film, in Nepali.
- Camera: slow push / drift on every scene, card and fill moving at different rates
  (parallax). **No hard cuts** — dissolve-with-scale between scenes.
- **AI interface elements are blue/purple** per the brief: `#60A5FA` → `#A78BFA`,
  glow `rgba(99,102,241,.45)`. Brand red/gold is held back until the hero.
- The art carries emotion; overlays carry product. Keep overlay text minimal.
- **Avoid:** inventing a different-looking CG citizen (breaks continuity with the art),
  excessive text, generic chatbot UI, English-heavy copy, fabricated statistics.

## Copy that must appear verbatim (all from the panels)
`समस्या देखियो` · `AI ले बुझ्छ` · `रिपोर्ट तयार भयो` · `तपाईंको रिपोर्ट दर्ता भयो`
`तपाईंको समाधानको यात्रा` · `सेवा आवेदन` · `आवेदन प्रक्रिया` · `आवेदन पेश भयो`
`समस्या पहिचान` · `स्थान पहिचान` · `विवरण संकलन`
`SL-45872` · `BC-2026-00456` · `समस्या समाधान भयो` · `आवेदन सफल भयो`
`भक्तपुर AI` · `नेपालको आफ्नै AI सिटी असिस्टेन्ट` · `भन्नुहोस्! AI ले गरिदिन्छ!`
`Hashtag Technology`

## Visual Identity
- Field `#07070C` · text `#F6F1E9` · muted `#A8A29E`
- AI blue `#60A5FA` · AI purple `#A78BFA` · AI glow `rgba(99,102,241,.45)`
- Brand (hero only) `#EF4444` → `#F59E0B`
- Syne · DM Sans · Noto Sans Devanagari — all local in `assets/fonts/`

## Storyboard
`brag-plan.md` is the contract. Nine scenes, every boundary on a 2.183s bar line:
0 / 6.55 / 13.10 / 19.65 / 24.01 / 30.56 / 37.11 / 43.66 / 48.02 / 56.76.

## Audio
- Music `assets/happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (109.96 BPM),
  gain ~0.24, fade in 1.0s, fade out final 1.5s. Picture leads; music never drives the cut.
- **Nothing sounds in the first 3s** — music and face only.
- Checkmarks/status rows land on half-bars so they read without rushing.
- Audio-reactive: subtle, AI glow on bass, scenes 2 and 3 only.
- SFX: soft activation, one tick per check/row, confirmation per reference number,
  one warm hit at the hero.

## Requirements
- Reading floor: short label ~0.8s settled, sentence ~0.3s/word. Devanagari lines need
  the full floor — do not rush them.
- `npx hyperframes check` must pass with 0 errors before render.
