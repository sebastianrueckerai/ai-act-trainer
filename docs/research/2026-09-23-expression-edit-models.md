# Models for a reaction frame: what exists, what was tried, what each costs

The job: one 64px pixel-art portrait, the same character, a loud expression change (eyes
lit, mouth open), and every pixel outside the face identical to the committed neutral.
Written 2026-09-23 after the owner rejected rounds one to three; probes ran on the pirate.

## What was tried, and the verdict on each

| # | Approach | Result |
|---|----------|--------|
| 1 | rd-plus img2img (input image, strength 0.2) | Re-rendered 100% of pixels; the model does not anchor to its input. Flicker, no expression. |
| 2 | Scripted pixel redraw of the mouth | Drift-free by construction, but the smile reads flat; drawing by coordinates is not art. |
| 3 | rd-plus fresh redraw, same seed | No expression, full re-noise. |
| 4 | Redraw pasted into the mouth box | Nothing to paste: the source carries no expression. |
| 5 | flux-kontext-pro raw, instruction edit | Edits the mouth on instruction, but repaints the whole canvas (its own smoother shading; the background unless pinned; ~2960 changed pixels outside the face). |
| 6 | kontext + paste-back of the located face/mouth box | The expression reads and the rest is byte-identical. Works, but the model recomposes the head slightly inside the box: the owner reads it as "the face shrinks, it does not fit". |
| 7 | flux-fill-dev (true inpainting) in the same box | Preserves by architecture, but at our resolutions the filled area smears; the eye region turns to mud. |

A grid-registration pass (search shifts and crops that minimise the difference to the
neutral outside the face box before decimating to 64px) found no better alignment than
the identity: the shrink lives inside the model's recomposition of the head, not in the
mapping, so it cannot be corrected after the fact. Only the paste-back hides it.

## This round's probe: google/nano-banana-2

Google's Nano Banana 2 (the Gemini image-edit family; `google/nano-banana` and
`google/nano-banana-2` on Replicate) is the other identity-preserving instruction editor
the comparisons rank beside Kontext. Probe result on the pirate: it also works on a
1024px canvas of its own and re-renders the character wholesale — 2248 pixels differ
outside the face box in the raw decimation, the same class of failure as kontext raw.
With the face-box paste it is drift-free like column 6; whether its face art fits better
is on the archived internal m5.15 sheet for the eye to judge.

## What else exists, and what each needs

- **Instruction editors** (edit from a text instruction): FLUX.1 Kontext pro (Replicate,
  credit exists; tried), Nano Banana 2 (Replicate, credit exists; probed), GPT Image
  (OpenAI key, none present), Seedream 4 / SeedEdit (ByteDance; fal.ai only, no FAL_KEY
  in the .env), Qwen-Image-Edit (Apache 2.0; hosted on fal or self-hosted on a GPU;
  not on Replicate), FLUX.2 Kontext and MAI-Image-2.6 (newer entries in the comparisons,
  same hosting situation).
- **Inpainters** (paint only inside a mask, preserve by architecture): flux-fill-dev
  (tried; smears at our scale), SD 3.5 inpaint (same scale problem expected).
- **Pixel-art-native generators**: retro-diffusion rd-plus (tried; no edit discipline),
  RD Animation (sprite/video, separate model), pixel-art LoRAs for SDXL (generation only).
- **A different shape of solution**: generate one canvas holding a row of expressions of
  the same character (an expression sheet) in a single rd-plus call, then split it into
  frames. Drift between cells of one generation is far smaller than between generations,
  and no editing is needed at all. Untested.

## Standing constraints on any of these

- Every model that works at 1024px must come back down to the 64px grid; anything not
  aligned to that grid shows instantly in pixel art.
- The paste-back (neutral outside the face box) is the only guarantee that held across
  all rounds; whatever paints the face, the composite stays.
- Expression must be loud: at 64px, subtle does not exist.

## Recommendation

Two live candidates remain, both payable with the existing Replicate credit: kontext
with the paste-back (round 6, "the face shrinks" inside the box) and nano-banana-2 with
the paste-back (this probe). If neither face fits, the expression-sheet route needs no
editor at all and is the next thing to probe. A FAL_KEY unlocks SeedEdit; an OpenAI key
unlocks GPT Image; both are the owner's call, not purchases to make silently.

## The full set on Seedream v4 edit (2026-09-23, later the same day)

A FAL_KEY arrived; the fal probe (archived internal sheet m5.16) put Seedream v4 edit
ahead of everything tried before, and the owner approved both pirate frames from it.
Scaling the recipe to all five personas (archived internal sheet m5.17)
surfaced two failure modes the pirate round had hidden, both now measured and fixed:

- **Seedream's magenta is not pure.** It repaints the flattened background with green in
  the 80 to 160 range, which the exact key (g<80) leaves as residue inside the face box.
  Key with g<160. Checked: no neutral portrait has a pixel in that range inside any face
  box, so the wide key cannot eat a real face pixel.
- **Seedream pulls subjects to canvas center.** Center-facing subjects (pirate, jester,
  sergeant) keep their heads in place; side-facing marvin, head at the right edge, was
  displaced 7 to 15 px on every one of seven rolls, and clerk's head drifted +2 to +3 px
  consistently. A displaced head makes the fixed face box sample seams and repainted
  body, and the "strongly changed pixels" count then measures background repaint, not
  expression. Never trust that count without a head-location check on the frame itself.
- **Fixes that held.** A barely-moved head: locate the head in the raw and in the
  neutral (grid-annotated image plus a bbox query), paste the redrawn head back shifted
  by minus the displacement, mask-pasted so keyed pixels keep the neutral. Extend the
  paste box downward first: an open grin sits lower than the neutral mouth (clerk happy).
  A far-moved head: send a head-centered crop instead of the full frame (marvin: a 31x48
  window around the head, upscaled x4), so the model has nothing to recentre; the plain
  face-box paste then works. Both marvin moods passed on the first crop roll after seven
  failed full-frame rolls.
- **Acceptance numbers per frame:** at most 10% of the face box keyed, and at least 80
  strongly-changed pixels (channel-sum difference over 60) inside the box. The approved
  pirate-disappointed frame measures 107; the final set spans 107 to 560, with zero
  changed pixels outside each paste box, zero magenta-hued pixels inside boxes, and zero
  transparent frame pixels where the neutral is opaque.
- **The vision judge on these sprites misreports both ways.** It called the approved
  pirate-disappointed frame "virtually identical to neutral" and, after the magenta was
  provably gone (pixel sweep), kept reporting "magenta blocks covering the face". Pixel
  audits are the gate for artifacts; expression strength is the owner's eye.

## The happy direction is not the disappointed direction (2026-09-23, evening)

The owner's verdict on the m5.17 set: the wrong-answer direction holds, the right-answer
frames are "almost all terrible". The pixel audit says why before the eye does: the
instruction asked for a big open grin with teeth, and after decimation to 64px that is
an irregular dark cavity with white specks — jester carried 89 new-white and 80 new-dark
pixels inside his face box, sergeant 81 and 126. It reads as a grin only on the pirate,
whose mouth is natively a dark slot in a metal shield; his frame was approved and kept.

Four prompt architectures followed for the remaining four personas (sheet:
archived internal sheet m5.18), and the pattern across them matters more than any
single frame:

- **Negations do not bind.** "No teeth, no open mouth, no dark mouth interior" still
  produced open mouths with white flecks (jester white 77, sergeant 85 on the best roll).
- **Positive closed-lips language moves the failure, not the outcome.** "Lips press
  together in a wide smile, one bold simple arc" killed the teeth but painted a thick
  dark band instead (jester new-dark 130).
- **Mouth fidelity is a lottery across decimation.** The same prompt on the same face
  rolls white+dark between 40 and 180. A compact thin smile won the lottery for marvin
  (round two, third roll) and clerk (white 29, dark 25), and lost every roll for jester
  and sergeant (13+ rolls each).
- **The primitive that survives decimation is the arc eye.** Closed happy arcs (^ ^)
  are one bold stroke, dark by design, and read unmistakably as joy at 64px. Sergeant's
  final frame is arcs plus a small closed smile: eye-band dark 35, mouth-band white 0.
  The jester — seventeen rolls of toothy grin, because a jester without one is outside
  the model's prior — got eyes-only arcs with the mouth pinned verbatim.
- **Gate by region, not by box.** A dark-pixel gate calibrated on the cavity failure
  also rejects the arc eyes, which are dark on purpose. Count new-dark and new-white in
  the eye band and the mouth band separately; the cavity signature is white plus dark
  in the mouth band, the arc signature is dark in the eye band with a quiet mouth.

The wrong-answer direction needed none of this: drooping lids and a downturned mouth
are compact shapes that decimate cleanly on every face.

## Round three: orientation is an input-geometry problem (2026-09-24)

The owner's verdict on the m5.18 sheet named three failures with three different root
causes: marvin's face came back frontal ("Depressobot is shown from the side"), the
clerk's came back mirrored, and the jester's read sinister with no smile. What the
round established:

- **The head-centred crop input, not the prompt, caused both orientation failures.**
  Cropping the head onto a magenta window stops Seedream's centre-pull, but a floating
  head invites the model to canonicalise it: marvin got frontalised (two eyes), the
  clerk got mirrored. Full-frame inputs with the orientation pinned in words kept
  marvin's strict side profile on four rolls out of four ("keeps its exact strict side
  profile view... the head is never turned toward the viewer, both eyes are never
  visible"). Profile-pinning language plus an overlap-aware registration paste
  (below) replaced the crop entirely.
- **Overlap-aware registration.** Matching the raw face box to the neutral by least
  pixel cost over shifts fails vacuously: shifting the box onto empty background
  minimises cost to zero by dropping the overlap. Require at least 60% overlap with
  the neutral box's opaque pixels, then take the argmin. This salvaged four marvin
  rolls from raws after the degenerate matcher had thrown them away.
- **A pixel chirality gate does not survive heavy repaints.** cost(face, neutral) vs
  cost(face, mirrored neutral) separates clean (pirate 2.3-3.9, sergeant 1.8) but both
  costs converge when the repaint is heavy: the blessed side-profile marvin-disappointed
  scores 1.01 and the mirrored clerk 1.12. Orientation stays a vision question; the
  vision judge answers narrow per-portrait questions (eye count, parting side) reliably
  even while it is unreliable about expression.
- **The vision judge contradicts itself across scales on the jester.** The same raw
  read "normal eyes, clean teeth, friendly" on a six-up strip and "squinting shadowed
  eyes, scattered teeth, flawed" magnified. An ASCII map of the face box (one character
  per pixel, classified dark/red/white/mid) settles such disputes: the "clean" roll
  carried an 11x12 solid dark void where the mouth should be. The map, not the judge,
  is the arbiter for expression artifacts.
- **The jester's open grin is unreachable at 64px through this model** (ten more
  rolls this round, twenty-seven across the campaign): every roll decays into the
  cavity, the scattered-teeth mouth, or the dark eye section — often with the mouth
  drawn high into the eye band, where band gates that assume the mouth stays put will
  not see it. The round-three frame is drawn by hand in the sprite's own palette
  instead: solid white triangle eye arcs carved into the dark eye clusters, and a
  symmetric two-tone closed grin over the cleared old smirk, 39 changed pixels, all
  inside the eye and mouth regions.
- **The clerk's visible edit and his mirroring are coupled.** Across nine rolls, every
  frame with a clearly visible smile came back mirrored, and every unmirrored frame was
  near-identical to neutral (strong 8-38 in a 525-pixel box). Mirroring a mirrored
  repaint back fails too: the flip is a hand-drawn canonicalisation, so the restored
  hairline lands 2px off the neutral silhouette. His frame is drawn by hand as well:
  raised lip corners in the sprite's rose red over a cleared mouth, the white grin
  block of the accepted-but-mirrored take centred under it, 50 changed pixels.

## Round four: the clerk, and what the working examples never said (2026-09-24)

The owner's instruction after m5.19: no more hand-drawn pixels, solve the clerk, and
diff the working rounds against the clerk rounds. The diff, prompt by prompt:

- **Every working prompt pins positions and clothes; only the failed clerk prompts
  named FACING.** The blessed sergeant-happy prompt says "The head must not move,
  shift, resize or be redrawd"; the failed clerk prompts added "the same view angle
  and direction", "the parting of the hair", "not mirrored, not turned". Asked to
  think about facing, the model re-rendered the facing — and flipped it. Negations
  do not bind, and neither do orientation instructions; mirroring is stochastic and
  belongs in the gate, not the prompt.
- **Arcs behind glasses are unresolvable at 64px.** One roll of the blessed
  arc-plus-smile formula on the clerk replaced the whole lens area with white
  (57 new-white pixels): the model's resolution for a 2-3px stroke inside a 4px
  glasses frame is a white flood. The sergeant's face carries arcs because his eyes
  sit on open skin. The clerk's readable feature is the mouth.
- **The mouth-only edit lands.** With the eyes and glasses pinned verbatim and only
  the mouth asked to change (m5.17 formula otherwise), the second roll gated: mouth
  band strong 36, eye band strong 4, zero holes, zero outside-box drift — and the
  vision orientation check (head direction, parting side, mirrored yes/no) passes.
  Mouth-only also matches what the owner accepted in the m5.18 shape, where the
  mirror was the only complaint.
- **A keyed gate must count only visible holes.** Pixels that are transparent in
  both the raw box and the neutral (background inside the face box) are not holes;
  counting them rejected six healthy rolls before the paste was even the problem.

## The video option, first contact (2026-09-24)

The owner asked whether an AI can make a ~0.5s video of the sprite that starts and
ends on the neutral frame. Kling v2.1 standard image-to-video (fal) holds the
clerk's identity perfectly across 121 frames and does paint a readable grin
mid-clip — the video model resolves the smile that the edit model cannot. But:
the head tilts and leans, one frame blurs, the transparent background renders
white (second run feeds the magenta-flattened sprite to fix that), and the video
never returns to its first frame, so a loop has to be cut and ping-ponged. Post
processing decimates every frame to 64px and snaps it to the neutral's palette,
so colour drift and blur cannot survive — only motion does. The tightened retry
("locked static camera, the head and body perfectly still", magenta-flattened
input) holds the silhouette within one pixel across all 121 frames, holds the
identity, and paints the readable grin; the remaining flaws are the missing
relax (the ping-pong cut manufactures it) and slight frame-to-frame shimmer in
the redrawn face. Verdict: viable as a motion source for reactions, at about
25 cents a clip; the picker would need to accept an animated asset.

## The shade shift, and the mask paste (2026-09-24)

The owner blessed the round-four clerk frame with one flaw: the face darkens when it
smiles. Measured: the repaint returns 197 of 213 skin pixels darker, mean brightness
178.7 to 163.1, and the full-box paste carries the shift with the smile. The fix needs
no roll: re-paste the same raw through a mask of only the structurally changed pixels
(channel-sum diff above 90, no dilation — a dilated ring re-imports darkened skin, and
thresholds near 40 do too). 32 pixels survive, exactly the smile's dark underline, its
white teeth and its outline; every other face pixel is the neutral's own byte, so the
tone cannot shift by construction. Side finding: a class-map read can mistake a
26-unit shade shift on an already-red lip pixel for a structural change; check raw
channel values before believing a "lost" pixel.

## The frowns, on the mask-paste pipeline (2026-09-24)

The m5.17 frowns carried the same defect the owner rejected on the clerk smile: the
repaint's global skin darkening, minus 13.9 percent mean brightness on the sergeant,
minus 30 on the clerk (the jester's face has no skin-class pixels to measure, but the
same repaint produced it). All three frowns are rebuilt on the mask paste: the m5.17
disappointed language verbatim (it never named facing — that poison came later), a
closed downturned mouth for the jester because his open mouths always decay, and the
clerk's frown re-pasted from the surviving m5.17 raw with no new generation. Both
fresh rolls gated on the first attempt and passed the vision orientation check
(same head, same orientation, readable frown, no artifacts).

## Frown verdicts and the band mask (2026-09-24)

The owner's verdicts on m5.21: the jester's expression good but ruined by dark lines
at the top and bottom of the insert; the sergeant horrible (his first look said good,
his second corrected it). Causes: the mask paste had admitted the model's darkened
rows at the face-box edges, where no expression lives; and the m5.17 "the mouth opens
in a deep downturned frown" had decayed under the sergeant's mustache into a white
block with dark bars — the cavity again, on the sad side. Two rules drop out:

- **The mask needs a band, not just a threshold.** Paste only within the eye and
  mouth rows; the box's edge rows (hat brim, chin, collar) are context the model
  darkens and no expression occupies. The jester's fix re-pasted the same raw with
  the mask held to y34-48: the frown is byte-identical, the lines are gone by
  construction.
- **Open mouths decay in both directions.** The open grin's cavity failure repeats
  for the open frown. Closed strokes — downturned closed lips, heavy lids — are the
  decimation-proof primitives for both moods. The sergeant's gated re-roll is
  closed: heavy shut lids and a downturned red line, 54 pixels in the band.

## Registration joins the mask paste (2026-09-24)

The owner blessed the sergeant's alternate frown (quieter lids, bolder mouth). The
jester's frown he called the right direction with two flaws, both from the paste: the
raw sat one pixel lower than the neutral — invisible in a still, glaring in the
animated swap, every feature jumping — and the paste band reached the chin rows,
where the model's redraw had shrunk the chin. The mask paste now registers first
(overlap-aware least cost over shifts on the face box) and the jester's band stops at
the mouth stroke, so the chin below is the neutral's own. Rule: the swap animation is
the registration test; a still frame hides a one-pixel miss that the swap turns into
a jump.
