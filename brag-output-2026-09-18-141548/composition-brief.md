# Hyperframes Composition Brief: BhaktapurAI — dopamine-loop pitch cut

## Objective
A ~58s vertical performance-marketing pitch cut for **BhaktapurAI**, built by
**Hashtag Technology**, aimed at the next municipality. Uses the user's supplied
5-layer dopamine-loop framework as the structural contract.

## Output
- Composition: `brag-output-2026-09-18-141548/composition/`
- Video: `brag-output-2026-09-18-141548/brag.mp4`
- Format: **vertical — 1080x1920** · Duration: **58.08s**

## Source Material
- Project root: `/home/kali-linux/Desktop/municipal_ai`
- Product: **BhaktapurAI** · Company: **Hashtag Technology**
- Real UI reference: `../brag-output-2026-09-18-113907/capture/screenshots/scroll-000.png`
- **Verbatim copy that must appear:**
  - `सबैभन्दा ठूलो समस्या पैसा होइन।`
  - `असली नोक्सान — भरोसा।`
  - `When is Bisket Jatra?` · `📚 Municipal records`
  - `BK-I7LQN5` · `SUBMITTED` · `OVERDUE`
  - `CRITICAL 1d · HIGH 3d · MEDIUM 7d · LOW 14d`
  - `Comment "BLUEPRINT"`
  - `A HASHTAG TECHNOLOGY PRODUCT`

## Creative Direction
- Tone: `chaotic` pacing × `polished` product shots
- Framework layers, in order: **STAKES → PAIN → BIG QUESTION → HEADFAKE →
  4 SCREENS → VALUE CASE → REHOOK/CTA**
- Peaks every 4-6s (vertical audiences drop faster than the framework's 8-10s assumes)
- **Avoid:** any invented rupee figure, any invented percentage, any price, any
  fabricated statistic. The audit on this very product found hardcoded fake metrics —
  do not reproduce that failure in its marketing. Value is carried by the real SLA
  ladder, the real citation behaviour, and the real public dashboard.
- **Avoid:** generic SaaS language, abstract filler, equalizer/waveform visuals.

## Visual Identity
- bg `#0C0C14` · text `#F6F1E9` · muted `#A8A29E`
- gradient `#EF4444` → `#F59E0B` · alarm `#EF4444` · ok `#6EE7B7`
- surface `#17171f` / `#1e1e28` · border `rgba(255,255,255,0.10)`
- Syne 700/800 · DM Sans 300/400/500 · Noto Sans Devanagari 500/700 (all local in `assets/fonts/`)
- **Safe zone:** all copy inside the middle 1600px of the 1920px height.

## Storyboard
`brag-plan.md` is the creative contract. Ten scenes, every boundary on a 2.002s bar line:
0 / 6.03 / 12.03 / 16.04 / 20.04 / 26.05 / 32.05 / 38.06 / 44.06 / 50.07 / 58.08.

## Audio
- Music: `assets/music/happy-beats-business-moves-vol-1-by-ende-dot-app.mp3` (120.19 BPM)
- Gain ~0.30; **duck to ~0.16 across 15.5-20.0s** so the silence beat and headfake land; fade final 1.2s
- Beat grid: `0.02 + k × 0.5005` (verified against the bundled cue preset)
- **// beat-locked 17.02s** — the headfake line
- **// beat-grid** — pain chips on bars 8.03 / 10.03 / 11.03; SLA rows on consecutive bars
- Audio-reactive: subtle — alarm glow on bass during pain scenes, CTA gradient on RMS
- SFX: moderate, motion-matched. Counter ticks, chip hits, reference landing, answer
  arrival, overdue flip, dashboard rows, final stamp. **Nothing in the 15.5-16.0s gap.**

## Requirements
- Show real product UI in all four screen scenes.
- Reading floor: short label ~0.8s settled, sentence ~0.3s/word.
- `npx hyperframes check` must pass before render.
