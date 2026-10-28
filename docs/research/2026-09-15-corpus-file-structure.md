# Research notes: structure of the corpus source files (2026-09-15)

Verified by an explorer against the files under `docs/research/downloads/`. Facts for the parser.

## Consolidated XHTML (`cons_en.xhtml`, `cons_de.xhtml`, CELEX 02024R1689-20260727)
- Language-independent ids and classes. DE and EN share the structure; only heading text differs (`Artikel 1`, `KAPITEL I`).
- Chapter: `<div id="cpt_I">` with `<p class="title-division-1">CHAPTER I</p>` and `<p class="title-division-2"><span class="boldface">TITLE</span></p>`. 13 chapters.
- Section: `<div id="cpt_III.sct_1">` with two `<p class="title-gr-seq-level-1">` (number, then name).
- Article: `<div class="eli-subdivision" id="art_26">` with `<p class="title-article-norm">Article 26</p>` and `<div class="eli-title" id="art_26.tit_1"><p class="stitle-article-norm">Title</p></div>`. 113 articles in each language (`art_N` ids unique).
- Numbered paragraph: `<div class="norm"><span class="no-parag">1.  </span><div class="norm inline-element">text</div></div>`. No id; derive from the order of `no-parag` spans inside the article.
- Points: `<div class="grid-container grid-list"><div class="list grid-list-column-1"><span>(a) </span></div><div class="grid-list-column-2"><p class="norm">text</p>[nested grid-container for (i)]</div></div>`. Nesting depth 2-3, same pattern each level. No ids.
- Annex: `<div id="anx_III">` with `<p class="title-annex-1">ANNEX III</p>` and `<p class="title-annex-2">subtitle</p>`; body uses the grid-list point pattern. 14 annexes (`anx_I`..`anx_XIV`).
- Amendment markers: standalone `<p class="modref"><a href="...celex/32026R1744" title="32026R1744: REPLACED">▼M1</a></p>` between blocks (glyph U+25BC, `▼B` for base text). 69 in EN.
- Footnotes: inline `<a href="#E0001" id="src.E0001"><span class="superscript">1</span></a>`; texts at document end in `<p class="footnote">`.
- Tables: 8 `<table>` in EN, mostly cover-page layout; points are divs, not tables.
- Pitfalls: 2,576 non-breaking spaces (numbering spans like `"1.\xa0\xa0"`); no soft hyphens; smart quotes and `<span class="italics">` inline; footnote refs must be dropped when flattening text; the consolidated text has no recitals.

## Recitals
- Not in the consolidated file. In `orig_en.xhtml`: `<div class="eli-subdivision" id="rct_1">` wrapping a two-column table (`(1)` | `<p class="oj-normal">text</p>`). 180 recitals.
- Formex zip `fmx_32024R1689_eng.zip` (16 files, body `L_202401689EN.000101.fmx.xml`): `<GR.CONSID>` with 180 `<CONSID><NP>(1) text</NP></CONSID>`; articles `<ARTICLE IDENTIFIER="026"><TI.ART>Article 26</TI.ART><STI.ART>..</STI.ART><PARAG IDENTIFIER="026.002">2.text</PARAG>`; points `<LIST TYPE="alpha|roman|ARAB"><ITEM><NP>(a)text</NP></ITEM></LIST>`; `<NOTE NOTE.ID="E0001">`. Counts: 113 ARTICLE, 509 PARAG, 598 ALINEA, 29 DIVISION. The DE zip has the same shape.

## KI-MIG (`kimig/BJNR0DF0B0026.xml`, DTD gii-norm)
- Root `<dokumente>` with 31 flat `<norm>` elements. Structural norms (`doknr` contains `BJNG`): `<gliederungseinheit><gliederungskennzahl>020</gliederungskennzahl><gliederungsbez>Teil 2</gliederungsbez><gliederungstitel>..</gliederungstitel>` (10). Provisions (`doknr` contains `BJNE`): `<enbez>§ 2</enbez><titel>..</titel><textdaten><text format="XML"><Content><P>(1) ..</P><P>(2) ..</P></Content></text></textdaten>` (20 sections). Each Absatz is its own `<P>` prefixed `(N)`.

## Commission AI literacy Q&A (EN and DE pages, HTTP 200)
- Europa Component Library accordion: `<details class="ecl-accordion__item"><summary class="ecl-accordion__toggle">question</summary><div class="ecl-accordion__content">answer html</div></details>`, grouped under `<h2 id="ecl-inpage-...">`. 37 items in each language. Parse directly with lxml.

## Recommended approach and id scheme
- lxml with XPath. Body from the consolidated XHTML (in-force text, stable ids). Recitals from Formex `CONSID` in document order, cross-checked against `rct_N` in the OJ XHTML.
- Ids: `art_26`, `art_26.2` (paragraph by position, mirrors Formex `026.002`), `art_5.1.a`, `art_5.1.a.i`, `anx_III`, `anx_III.4`, `rct_20`, `kimig_2`, `kimig_2.1`, `qa_3`.
- Citation strings map one to one: `Art. 26(2)`, `Art. 5(1)(a)(i)`, `Annex III pt. 4`, `Rec. 20`, `KI-MIG § 2(1)`, `Q&A 3`.

## Model ids verified live on 2026-09-15
- Groq: `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.6-27b`, `qwen/qwen3.8-27b` (plus safeguard and prompt-guard models). The dev LiteLLM config's `strong` and `fast` ids exist.
- DeepSeek: `deepseek-v4-pro`, `deepseek-flash`.
