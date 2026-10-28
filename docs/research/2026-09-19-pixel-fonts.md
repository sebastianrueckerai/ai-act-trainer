# Pixel fonts: licence and readability check (2026-09-19)

## The question

From the M5 gates. Which pixel fonts are Sil Open Font License (OFL)
so we can bundle and redistribute them? And is a proportional pixel font actually
readable for German body text at 2x scale (16 px)?

D17 asks for an 8x8 monospace arcade font for headings and labels, and a proportional
"SNES dialog style" pixel font for body text. The design unit is 4 px, scale 2 or 3.
An 8 px design font renders at 16 px or 24 px. All student-facing text is German, so
the fonts must cover the German set below and the citation forms.

## Candidates and licences

I verified every licence from the `ofl/` directory of the google/fonts GitHub repo.
The licence file in that repo is named `OFL.txt` for every family. Each file carries
the "SIL OPEN FONT LICENSE Version 1.1" header and the standard licence text.

| Family | Designer / foundry | Licence | RFN | Source |
|---|---|---|---|---|
| Press Start 2P | CodeMan38 | OFL 1.1 | yes, "Press Start 2P" | https://github.com/google/fonts/tree/main/ofl/pressstart2p |
| Pixelify Sans | Stefie Justprince | OFL 1.1 | no | https://github.com/google/fonts/tree/main/ofl/pixelifysans |
| Silkscreen | Jason Kottke | OFL 1.1 | no | https://github.com/google/fonts/tree/main/ofl/silkscreen |
| DotGothic16 | Fontworks Inc. | OFL 1.1 | no | https://github.com/google/fonts/tree/main/ofl/dotgothic16 |
| Handjet | Rosetta, David Březina | OFL 1.1 | no | https://github.com/google/fonts/tree/main/ofl/handjet |
| Jersey 20 | Sarah Cadigan-Fried (Soft Type) | OFL 1.1 | no | https://github.com/google/fonts/tree/main/ofl/jersey20 |
| Doto | Óliver Lalan | OFL 1.1 | no | https://github.com/google/fonts/tree/main/ofl/doto |

Doto is my addition. It is a dot-matrix font with a full weight range and real
lowercase, so it fits the body-font profile better than some of the named candidates.

The RFN clause only restricts modified versions. We ship the fonts unmodified, so the
"Press Start 2P" RFN costs us nothing. OFL 1.1 also requires that we keep the licence
file with the font when we bundle it.

TTFs and licence files are saved under `docs/research/downloads/pixel-fonts/<family>/`
(family directories are `press-start-2p`, `pixelify-sans`, `silkscreen`, `dotgothic16`,
`handjet`, `jersey-20`, `doto`).

## Coverage

Method: fonttools `getBestCmap()` on each downloaded TTF.

Required set: `ä ö ü Ä Ö Ü ß „ “ ‚ ‘ – … §`, digits `0-9`, ASCII letters, and the
characters the citation forms need: `( ) .` for "Art. 26(7)", "§ 87 Abs. 1 Nr. 6".

Result: **all candidates cover the full set. Zero missing codepoints.** I also checked
U+201D, U+2019 and U+2014 beyond the listed set. They are present everywhere too.

One caveat that a cmap check cannot catch: **Silkscreen is caps-only.** All 26 lowercase
codepoints exist in the cmap, but each maps to the same glyph as its uppercase letter.
I compared the glyph outlines with fonttools. All 26 pairs are identical. German body
text set in Silkscreen reads as "AUSSER ES WIRD". Case distinction is gone.

Shape facts from the font tables:

| Family | Widths | Lowercase | Cap height at 16/24 px | Notes |
|---|---|---|---|---|
| Press Start 2P | monospace | distinct | 16.0 / 24.0 px | 8 px design grid, so 16 px is 2x and 24 px is 3x |
| Pixelify Sans | proportional | distinct | 11.2 / 16.8 px | variable file, default weight 400 |
| Silkscreen | proportional | copies of uppercase | 11.2 / 16.8 px | fails the lowercase criterion |
| DotGothic16 | monospace | distinct | 12.6 / 18.9 px | dot matrix, designed for Japanese UI text |
| Jersey 20 | proportional | small-cap forms | 9.4 / 14.1 px | design grid needs 34 px per integer step, so 16 and 24 are off-grid |
| Handjet | proportional | distinct | 10.4 / 15.5 px | element-grid variable font, default instance is light |
| Doto | monospace | distinct | 11.2 / 16.8 px | variable file, default instance is weight 900, must pin 400 |

## Readability evidence

Method: a scratch HTML page in `/tmp` (not in the repo). It renders one real German
paragraph from `content/de/chapters/01-warum-es-dich-betrifft.yaml` (section s5, it has
umlauts, ß and the citation Art. 5(1)(f)) and the cite line "§ 87 Abs. 1 Nr. 6 BetrVG
(Art. 26 Abs. 7)" from `content/de/chapters/03-was-dein-arbeitgeber-tun-muss.yaml`.
Each body candidate renders the paragraph at exactly 16 px and 24 px. A sans-serif
system font block is the reference. A pairing table puts each candidate next to a
Press Start 2P heading line. Font sizes are exact px. I forced no font smoothing or
rendering tricks.

Renderer: Playwright 1.63.0 with its downloaded Chrome Headless Shell 153.0.8010.12,
device scale factor 1. `document.fonts.check()` confirmed all seven webfonts loaded
(true for each). No OS libraries were missing.

Screenshots:

- [downloads/pixel-fonts/readability-sheet.png](downloads/pixel-fonts/readability-sheet.png)
  full comparison at natural zoom, 1:1 pixels.
- [downloads/pixel-fonts/readability-magnified.png](downloads/pixel-fonts/readability-magnified.png)
  4x nearest-neighbour crops of "außer es wird" at 16 px and "Führt dein" at 24 px per
  candidate, so glyph quality is visible.

## Readability assessment

Based on the two screenshots:

- **Pixelify Sans: readable at 16 px and 24 px.** Square pixels stay sharp at both
  sizes. Umlauts and ß stay clear. Lowercase is distinct and proportional spacing
  keeps word shapes intact. It is the only candidate that meets every D17 body
  criterion.
- **DotGothic16: readable at 16 px and 24 px.** Crisp dot matrix with generous
  counters. It is monospace, which deviates from the "proportional" wording in D17.
  It looks the most like an actual console dialog font.
- **Doto: readable at 16 px and 24 px.** Round dot grid, clean and calm. Monospace as
  well, and the variable file must be pinned to weight 400 because its default
  instance is Black 900.
- **Jersey 20: 24 px only, and weak there.** At 16 px the strokes go soft because 16
  is off its 34 px design grid. Its lowercase letters are small-cap forms, so case
  distinction is weak. Not a body candidate.
- **Handjet: 24 px only.** The element grid makes dense texture inside each letter.
  At 16 px the letters blur together. Stylized enough to stay a display font.
- **Silkscreen: fails for body text.** Caps-only, see the coverage caveat. It could
  still serve as a label or badge font, but not for German prose.
- **Press Start 2P: crisp at 16 px and 24 px.** Integer 2x and 3x of its 8 px grid.
  The "§ 87 ABS. 1 NR. 6" label in the pairing table stays sharp.

## Recommendation

The reviewing session looks at the screenshots and rules. My recommendation:

- Heading and label font: **Press Start 2P** (16 px for labels, 24 px for headings).
- Body font: **Pixelify Sans** at 16 px, with 24 px for legal quotes if a stronger
  quote voice is wanted. It is the only proportional candidate with true lowercase
  that stays crisp at both sizes.
- Alternative body font if the dot-matrix console look wins: **DotGothic16** at 16 px.
  That choice accepts a monospace body and should be recorded as a D17 amendment.
- Accessibility switch body stack: `system-ui, "Segoe UI", Roboto, "Helvetica Neue",
  Arial, sans-serif` at the same sizes. Press Start 2P stays for headings, as D17
  says the switch swaps only the body font.
- Drop Silkscreen, Jersey 20 and Handjet from the body shortlist.

**Superseded by D53:** the shipped body font is Jersey 10 (not evaluated above) at
20 px on a 2 px grid, not Pixelify Sans; see D53.

## Reproduction pointers

The scratch page and scripts lived in `/tmp/claude-1000/pw-pixelfonts/` (compare.html,
shoot.js, magnify.py) and are not part of the repo. The coverage and geometry checks
are two fonttools scripts run with `uv run --with fonttools python`. Any rerun only
needs the TTFs under `docs/research/downloads/pixel-fonts/`.
