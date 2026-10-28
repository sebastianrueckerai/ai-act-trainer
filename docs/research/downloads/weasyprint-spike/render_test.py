"""Throwaway spike: render a one-page A4 German PDF with WeasyPrint and verify it.

Runs inside the spike images (weasyprint and pypdf installed). Verifies the
extracted text round-trip, lists embedded fonts, prints the PDF size.
"""

import argparse
from pathlib import Path

import pypdf
import weasyprint
from weasyprint import HTML

PIXEL_FONT = "PressStart2P-Regular.ttf"

PARAGRAPH_1 = (
    "Die KI-Verordnung ist das KI-Gesetz der EU. Ein KI-System ist ein "
    "maschinengestütztes System, das aus Eingaben ableitet, wie es Ausgaben "
    "erzeugt, etwa Texte, Vorhersagen oder Empfehlungen."
)
PARAGRAPH_2 = (
    "Danach kennst du die eine verbotene Praxis, die deinen Arbeitsplatz "
    "trifft, und weißt, wo du nachfragst."
)
CITATIONS = (
    "Rechtsgrundlagen: Art. 26(7) DSGVO, § 87 Abs. 1 Nr. 6 BetrVG, "
    "Art. 4(1) KI-VO und Art. 3(1)."
)
CHECKS = [
    "maschinengestütztes System",
    "erzeugt",
    "weißt",
    "Art. 26(7) DSGVO",
    "§ 87 Abs. 1 Nr. 6 BetrVG",
]

CSS = """
@page { size: A4; margin: 20mm; }
@font-face {
  font-family: "Press Start 2P";
  src: url("PRESSSTART");
}
body { font-family: BODY; font-size: 10pt; line-height: 1.5; }
h1 { font-family: "Press Start 2P"; font-size: 13pt; font-weight: normal; }
"""

HTML_DOC = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<style>
CSS_HERE
</style>
</head>
<body>
<h1>Spickzettel für KI am Arbeitsplatz</h1>
<svg width="180" height="12" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="12" height="12" fill="#33428a"/>
  <rect x="16" y="0" width="12" height="12" fill="#5c6bc0"/>
  <rect x="32" y="0" width="12" height="12" fill="#1a237e"/>
  <rect x="48" y="0" width="12" height="12" fill="#8c9eff"/>
</svg>
<p>P1_HERE</p>
<p>P2_HERE</p>
<p>CIT_HERE</p>
</body>
</html>
"""


def build_html(body_font: str) -> str:
    css = CSS.replace("PRESSSTART", PIXEL_FONT).replace("BODY", body_font)
    return (
        HTML_DOC.replace("CSS_HERE", css)
        .replace("P1_HERE", PARAGRAPH_1)
        .replace("P2_HERE", PARAGRAPH_2)
        .replace("CIT_HERE", CITATIONS)
    )


def embedded_fontfile(font_obj) -> str | None:
    objs = [font_obj]
    if "/DescendantFonts" in font_obj:
        objs.extend(df.get_object() for df in font_obj["/DescendantFonts"])
    for obj in objs:
        if "/FontDescriptor" not in obj:
            continue
        desc = obj["/FontDescriptor"].get_object()
        for key in ("/FontFile", "/FontFile2", "/FontFile3"):
            if key in desc:
                return key
    return None


def report(out: Path) -> None:
    reader = pypdf.PdfReader(str(out))
    print("pages", len(reader.pages))
    page = reader.pages[0]
    mb = page.mediabox
    print("mediabox_pt", float(mb.width), float(mb.height))
    text = " ".join(page.extract_text().split())
    for check in CHECKS:
        print("check", repr(check), "ok" if check in text else "MISSING")
    fonts = page["/Resources"].get("/Font", {})
    for key in fonts:
        font_obj = fonts[key].get_object()
        name = str(font_obj.get("/BaseFont", "?"))
        print("font", key, name, embedded_fontfile(font_obj) or "NOT-EMBEDDED")


def cmap_coverage(font_dir: Path) -> None:
    from fontTools.ttLib import TTFont

    font = TTFont(str(font_dir / PIXEL_FONT))
    cmap = font.getBestCmap()
    for ch in "äöüÄÖÜß§":
        print("cmap", ch, hex(ord(ch)), "yes" if ord(ch) in cmap else "NO")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--body", choices=["sans", "press"], default="sans")
    args = parser.parse_args()

    print("weasyprint", weasyprint.__version__)
    print("pypdf", pypdf.__version__)
    cmap_coverage(args.font_dir)
    body_font = "sans-serif" if args.body == "sans" else '"Press Start 2P", sans-serif'
    HTML(string=build_html(body_font), base_url=str(args.font_dir)).write_pdf(args.out)
    print("pdf_bytes", args.out.stat().st_size)
    report(args.out)


if __name__ == "__main__":
    main()
