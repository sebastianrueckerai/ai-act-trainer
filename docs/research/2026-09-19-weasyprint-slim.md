# WeasyPrint on the slim final image (2026-09-19)

## The question

From the M5 gates. Does WeasyPrint run on the final stage of
`deploy/Dockerfile` (`python:3.12-slim-bookworm`)? What does it cost in image size? How do
fonts work: system fonts from apt, or TTFs bundled in the repo?

## Method

I built throwaway images that mirror the final stage without the app:
`python:3.12-slim-bookworm` plus `useradd --system --uid 10001 --create-home trainer`. On
that base I added one apt layer and two pip layers, each as its own `RUN`, so `docker
history` shows the cost of each step. I rendered the test PDF inside each image with the
script mounted from the host, then checked the text with pypdf, the embedded fonts with
pypdf and `pdffonts`, and the pixels with `pdftoppm` plus an image check.

The test page is one A4 page. It carries German sentences from
`content/de/chapters/01-warum-es-dich-betrifft.yaml` (with ü and ß), the citations
"Art. 26(7) DSGVO" and "§ 87 Abs. 1 Nr. 6 BetrVG", a heading in Press Start 2P loaded
through `@font-face` from a file path, and an inline SVG strip of four colored rects.

Throwaway artifacts: `docs/research/downloads/weasyprint-spike/` holds the Dockerfile, the
render script `render_test.py` and two sample PDFs. The Press Start 2P TTF for a rerun
lives at `docs/research/downloads/pixel-fonts/press-start-2p/` with its `OFL.txt`, so the
spike directory holds no second copy.

## Measurements

### Apt set

WeasyPrint 70.0 needs Pango, fontconfig and harfbuzz-subset at runtime. The gdk-pixbuf and
shared-mime-info entries from older install guides are no longer needed. The inline SVG
rendered without them. The working set on bookworm:

```sh
apt-get install -y --no-install-recommends \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0
```

This pulls 18 packages in total, 15.6 MB:

fontconfig 2.14.1-4, fontconfig-config 2.14.1-4, fonts-dejavu-core 2.37-6,
libbrotli1 1.0.9-2+b6, libdatrie1 0.2.13-2+b1, libexpat1 2.5.0-1+deb12u3,
libfontconfig1 2.14.1-4, libfreetype6 2.12.1+dfsg-5+deb12u4, libfribidi0 1.0.8-2.1,
libglib2.0-0 2.74.6-2+deb12u9, libgraphite2-3 1.3.14-1+deb12u1,
libharfbuzz-subset0 6.0.0+dfsg-3, libharfbuzz0b 6.0.0+dfsg-3, libpango-1.0-0 1.50.12+ds-1,
libpangoft2-1.0-0 1.50.12+ds-1, libpng16-16 1.6.39-1+deb12u5, libthai-data 0.1.29-1,
libthai0 0.1.29-1.

The pip install resolved to weasyprint 70.0 with pydyf 0.12.1, tinycss2 1.5.1,
cssselect2 0.10.1, pyphen 0.18.1, pillow 12.3.0, fonttools 4.65.0, cffi 2.1.1 and
tinyhtml5 2.1.0. pypdf 6.19.0 served the checks inside the image and is not a product
dependency.

### Image size

| Image | Added over base | Size | Layer costs |
|---|---|---|---|
| spike-base | useradd | 124 MB | |
| spike-weasy | apt set, pip weasyprint, pip pypdf | 221 MB | apt 15.6 MB, weasyprint 76.8 MB, pypdf 3.79 MB |
| spike-weasy-dejavu | plus fonts-dejavu-core | 221 MB | no change |

The real cost for the product image is the apt set plus the weasyprint install, about
92 MB. pypdf was test-only. Installing `fonts-dejavu-core` on top added nothing, because
the minimal apt set already ships it: Debian fontconfig depends on a font package and the
default is fonts-dejavu-core.

### Font behaviour

All runs inside the images, the script mounted from the host.

- With the apt set, DejaVu Sans is present. The body text in `sans-serif` rendered in
  DejaVu Sans, the heading in Press Start 2P.
- Press Start 2P loaded through `@font-face` with `src: url("PressStart2P-Regular.ttf")`
  relative to the `base_url` passed to `HTML(...)`. Its cmap covers ä ö ü Ä Ö Ü ß and §.
  The heading "Spickzettel für KI am Arbeitsplatz" shows a correct ü in the pixel font.
- Both fonts were embedded as CID TrueType subsets with Identity-H encoding, `/FontFile2`
  and a ToUnicode map. `pdffonts` reports emb yes, sub yes, uni yes for
  YDBTMP+Press-Start-2P and XKQQSR+DejaVu-Sans.
- pypdf read the text back. All check strings survived the round trip:
  "maschinengestütztes System", "erzeugt", "weißt", "Art. 26(7) DSGVO",
  "§ 87 Abs. 1 Nr. 6 BetrVG". The rendered pixels show no tofu and the SVG rects are
  drawn.
- Zero system fonts is not a normal Debian state. I had to force it with
  `dpkg --remove --force-depends fonts-dejavu-core`. WeasyPrint then warns at import of
  the text module: `UserWarning: No fonts configured in FontConfig. Expect ugly output.`
  The render still succeeded. The body text fell back to the `@font-face` font, so the
  whole page sat in the pixel font. Text and umlauts stayed correct. Do not aim for this
  state in the product image.
- A run as uid 10001 (the trainer user from the Dockerfile) produced the same PDF with no
  fontconfig cache warnings and no HOME setup.

### PDF size

One A4 page, three paragraphs, one heading, one SVG strip: 9357 bytes with two embedded
fonts (dejavu-sans.pdf) and 4833 bytes with one (zerofonts-sans.pdf). PDF size is not a
concern at cheat-sheet scale.

## Recommendation for M5

1. Add `weasyprint>=70` to the `dependencies` list in `backend/pyproject.toml`. The final
   stage receives it through the venv copy from the backend build stage. No pip step in
   the final stage.
2. Add one apt line to the final stage of `deploy/Dockerfile`, before the venv copy:

   ```dockerfile
   RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    && rm -rf /var/lib/apt/lists/*
   ```

3. Font strategy: bundle the TTFs in the repo and load them with `@font-face`. The pick
   from [2026-09-19-pixel-fonts.md](2026-09-19-pixel-fonts.md) is Press Start 2P for
   headings and labels and Pixelify Sans for body text. Keep each `OFL.txt` next to its
   TTF, the licence requires it. In the render code, pass the font directory as
   `base_url` to `HTML(...)` and reference the files as `src: url("<file>.ttf")` relative
   to it. Copy the font directory into the image next to the render templates.
4. Install no `fonts-*` apt package. DejaVu Sans arrives as a dependency of fontconfig and
   serves as the fallback for any glyph the bundled fonts miss. This covers German
   without further work.
5. Open point: the spike tested the static Press Start 2P file. Pixelify Sans is a
   variable font (`PixelifySans[wght].ttf`). Test its weight axis under WeasyPrint before
   the cheat sheet relies on it.

## What stays throwaway

Everything under `docs/research/downloads/weasyprint-spike/` documents the spike and ships
nowhere: the Dockerfile, `render_test.py` and the two sample PDFs. The spike images were
removed after the measurements. A rerun needs the Dockerfile, the script and
`--font-dir` pointed at `docs/research/downloads/pixel-fonts/press-start-2p/`.
