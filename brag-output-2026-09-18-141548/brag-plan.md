# Brag Plan: BhaktapurAI — dopamine-loop pitch cut

## What is this app?
A bilingual civic platform for Bhaktapur Municipality, Nepal: citizens report issues,
tourists ask questions answered from municipal documents with sources cited, ward
officials see what is overdue, and the mayor sees every ward's performance in public.

## The angle
The user's dopamine-loop framework is written for B2B SaaS sold to business owners.
This is a civic platform, so "upsell the same customer for 2-3x revenue" has no
honest analogue — you do not upsell a resident applying for a birth certificate.
**Resolved by aiming the pitch at the real buyer: the next municipality.** Hashtag
Technology showing what it built for Bhaktapur. The four audiences the user asked for
— citizen, tourist, ward official, mayor — become the framework's four screens.

**Every number on screen is real or omitted.** The framework asks for
"silently costing you ₹[AMOUNT]/year" and a price. Both would be invented, and
fabricated statistics are the single worst defect this product's own audit found
(`/complaint/` claims "94% satisfaction" with zero data). So: no rupee figures, no
invented loss, no price. The value case is carried by things that are true — the real
SLA ladder (1 · 3 · 7 · 14 days), the real source-citing behaviour, and the real
public transparency dashboard. Price is quoted in the DM, which is where the CTA sends them.

## Hook (first 3 seconds) — LAYER 1.1 STAKES
Pattern interrupt in Nepali, against a black screen:
**"सबैभन्दा ठूलो समस्या पैसा होइन।"** — *It was never the budget.*
Then the sensory detail they can feel: one citizen's complaint card, and a day
counter climbing 1 → 23. Nobody has touched it.

## Key moments (the middle)
- **LAYER 2 pain:** "कसको उजुरी कति दिन पुरानो भयो — कसैलाई थाहा छैन।" Then three chips land
  one per beat: *No deadline. · No owner. · No record.*
- **LAYER 1.2 open loop:** "तर असली नोक्सान यो होइन…" — *But this isn't the real loss.* Silence beat.
- **LAYER 1.3 headfake:** "असली नोक्सान — भरोसा।" — *You lose the ones never filed.* The 180°:
  the cost isn't the unresolved complaint, it's every citizen who stops bothering to file.
- **LAYER 3, four screens**, one per audience, 6s each — each shows real product UI.

## Outro / punchline — LAYER 1.4 REHOOK
"तपाईंको नगरपालिकामा कति उजुरी बिनाजवाफ छन्?" — *How many complaints in your municipality
are unanswered right now?* Beat. **"You don't know. That's the problem."**
CTA: **Comment "BLUEPRINT"** → then the Hashtag Technology signature.
The closing question is the rehook: it sends them back to the top.

## User flow worth showing
Entry → key action → result, for each of the four roles:
1. **Citizen** — report an issue → reference number issued → SLA clock starts
2. **Tourist** — ask in either language → sourced answer with its citation
3. **Ward official** — queue shows what is overdue → escalation fires
4. **Mayor** — every ward's SLA compliance, published

## Tone
- Preset: `chaotic` (pacing) crossed with `polished` (visual restraint)
- Creative direction: *performance-marketing pitch cut — fast, punchy, but the product
  UI stays clean and truthful*
- Interpretation: Hard cuts on the beat. Short lines. Silence beats before the twist.
  Peaks every 4-6s rather than 8-10s, because vertical audiences drop faster. The copy
  is aggressive; the product shots are not.

## Format: vertical — 1080x1920
## Duration: 58.1 seconds

## Visual identity (from the project)
- Background: `#0C0C14` · Text: `#F6F1E9` · Muted: `#A8A29E`
- Accent gradient: `#EF4444` → `#F59E0B` (the site's real H1 treatment)
- Alarm/overdue state: `#EF4444` · Resolved/OK state: `#6EE7B7`
- Surface: `#17171f` / `#1e1e28`, borders `rgba(255,255,255,0.10)`
- Display: **Syne** 700/800 · Body: **DM Sans** 300/400/500 · Nepali: **Noto Sans Devanagari**
- Safe zone: keep all copy inside the middle 1600px — Reels UI eats top and bottom.

## Share copy (draft)
Most municipalities don't lose complaints. They lose the citizens who stop filing them.
Here's the system we built for Bhaktapur. Comment BLUEPRINT for the breakdown.

## Audio direction
- Role: dense rhythmic layer — this is the one tone where music drives the cut.
- Music: `happy-beats-business-moves-vol-1-by-ende-dot-app.mp3` (120.19 BPM, 164s).
  Chosen over vol-10 because 120 BPM gives a 0.5005s beat and a 2.002s bar, which is
  the natural cut length for this format.
- Music treatment: start 0.0s, gain ~0.30, duck to ~0.16 under the twist (16.0-20.0s)
  so the headfake lands in relative quiet, back up for the four screens, fade across
  the final 1.2s.
- Music cue guidance: preset read from `assets/music/cues/…vol-1….json` — tempo
  120.19 BPM, grid verified at 3.02/3.52/4.02/4.53/5.03 → constant 0.5005s spacing,
  extrapolated as `0.02 + k × 0.5005`. **Every scene boundary sits on a bar line**
  (0.02 + 4k × 0.5005): 6.03 / 12.03 / 16.04 / 20.04 / 26.05 / 32.05 / 38.06 / 44.06
  / 50.07 / 58.08. **Strong cue at 17.02s** — lock the headfake line there.
  The three pain chips use consecutive bars, not raw beats, so each stays readable.
- Audio-reactive treatment: subtle — the alarm glow behind the pain scenes breathes on
  bass; the gradient presence on the CTA breathes on RMS. No bars, no equalizers.
- SFX posture: moderate and motion-matched — denser than the cinematic cut because the
  format expects it, but still nothing on text that merely fades.
- Audio-coupled moments: the day counter ticking, the three pain chips, the reference
  number landing, the answer card arriving, the overdue flag flipping red, the four
  dashboard rows, the CTA stamp.
- Restraint rule: no riser into every scene, no whoosh on every cut, no sound under
  the silence beat at 15.5-16.0s — that gap is the point.

## Storyboard

### Scene 1 — STAKES — 0.00 → 6.03s
Black. **"सबैभन्दा ठूलो समस्या पैसा होइन।"** sets hard, holds ~2.2s. Beneath: *It was never
the budget.* At 3.00 a complaint card slides up — a real category, a ward — and a day
counter starts climbing 1 → 23, digits ticking. Red alarm glow builds behind it.
Sequential/interaction: **yes** — counter ticks per frame, not a single fade.
Audio intent: confident open, then unease as the counter climbs.
Audio-coupled idea: a soft tick under the counter, accelerating.
Transition mood: hard cut → Scene 2.

### Scene 2 — THE HIDDEN PROBLEM — 6.03 → 12.03s
**"कसको उजुरी कति दिन पुरानो भयो — कसैलाई थाहा छैन।"** holds ~2.4s. Then three chips land on
consecutive bars (8.03 / 10.03 / 11.03): **No deadline. · No owner. · No record.**
Sequential/interaction: **yes** — three chips, one per bar, all three held together.
Audio intent: each chip is a small hit; the problem accumulates.
Transition mood: hard cut → Scene 3.

### Scene 3 — THE BIG QUESTION — 12.03 → 16.04s
Everything strips away. **"तर असली नोक्सान यो होइन…"** / *But this isn't the real loss.*
Then a held silence beat from ~15.5 — music ducks, nothing moves.
Audio intent: the duck IS the beat. Do not fill it.
Transition mood: hard cut on the strong cue → Scene 4.

### Scene 4 — THE HEADFAKE — 16.04 → 20.04s
// beat-locked 17.02s strong cue: **"असली नोक्सान — भरोसा।"** slams in the gradient.
Beneath: *You don't lose complaints. You lose the ones never filed.*
Audio intent: the biggest impact in the video.
Transition mood: hard cut → the solution block.

### Scene 5 — SCREEN 1 · THE CITIZEN — 20.04 → 26.05s
Label **01 · THE ALERT SYSTEM**. Nepali: "नागरिक: ३० सेकेन्डमा रिपोर्ट।" Real UI: complaint
submitted → reference **BK-I7LQN5** lands → chip flips **SUBMITTED** → an SLA row
appears: **MEDIUM · 7 days · due 25 Sep**. The deadline is the product.
Sequential/interaction: **yes** — reference resolves, chip flips, SLA row slides in.
Transition mood: hard cut → Scene 6.

### Scene 6 — SCREEN 2 · THE TOURIST — 26.05 → 32.05s
Label **02 · THE ENGAGEMENT ENGINE**. Nepali: "पर्यटक: नेपाली वा अंग्रेजीमा सोध्नुहोस्।"
Ask bar types **"When is Bisket Jatra?"**, answer card rises with **📚 Municipal records**
visible. Then the same question in Devanagari gets the same answer — the bilingual proof.
Sequential/interaction: **yes** — typing, then answer, then the language flip.
Transition mood: hard cut → Scene 7.

### Scene 7 — SCREEN 3 · THE WARD OFFICIAL — 32.05 → 38.06s
Label **03 · THE AUTOMATION LAYER**. Nepali: "वडा अधिकारी: को ढिलो भयो, आफैं थाहा।"
A ward queue of three rows; one flips to **OVERDUE** in red and auto-escalates.
No manual chasing — the queue sorts itself by what is late.
Sequential/interaction: **yes** — three rows, then one flips red on a bar line.
Transition mood: hard cut → Scene 8.

### Scene 8 — SCREEN 4 · THE MAYOR — 38.06 → 44.06s
Label **04 · THE ACCOUNTABILITY MULTIPLIER** *(the framework's "revenue multiplier",
honestly renamed — a municipality's multiplier is public trust, not upsells)*.
Nepali: "मेयर: हरेक वडाको प्रदर्शन, सार्वजनिक।" The transparency dashboard assembles: the
real SLA ladder **CRITICAL 1d · HIGH 3d · MEDIUM 7d · LOW 14d** and per-ward compliance.
Sequential/interaction: **yes** — four SLA rows arrive on consecutive bars.
Transition mood: hard cut → Scene 9.

### Scene 9 — THE VALUE CASE — 44.06 → 50.07s
**"एउटै प्रणाली। चार प्रयोगकर्ता।"** — *One system. Four users.* Four role pills across the
frame, then the two true claims: **"Every answer cites its source."** and
**"1 · 3 · 7 · 14 days — measured, not promised."** No price, no invented ROI.
Transition mood: hard cut → Scene 10.

### Scene 10 — REHOOK & CTA — 50.07 → 58.08s
**"तपाईंको नगरपालिकामा कति उजुरी बिनाजवाफ छन्?"** holds. Beat. *You don't know. That's the
problem.* Then the CTA stamps in: **Comment "BLUEPRINT"** — *and I'll send the full
system breakdown.* Finally the wordmark **BhaktapurAI** and **A HASHTAG TECHNOLOGY PRODUCT**.
Audio intent: resolve, one final stamp, fade.
Transition mood: fade to black.

**Music mood for this video:** upbeat rhythmic, driving the cut
**Audio summary:** Driving 120 BPM bed with every cut on a bar line, ducked hard for the
silence beat before the twist, biggest impact on the headfake, then rhythmic hits through
the four screens and one final stamp on the CTA.
