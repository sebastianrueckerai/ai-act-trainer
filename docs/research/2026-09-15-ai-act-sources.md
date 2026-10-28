# Research notes: EU AI Act as source material (2026-09-15)

Verified by a background research agent against EUR-Lex/Cellar, Commission pages, BNetzA and gesetze-im-internet.de. Raw downloads are in `downloads/`. They are third-party source material under its own terms: EUR-Lex text under Commission Decision 2011/833/EU, German statutes gemeinfrei per § 5 UrhG, fonts under the SIL Open Font License.

## State of the law
- Regulation (EU) 2024/1689, amended once by the Digital Omnibus on AI, Regulation (EU) 2026/1744 (8 July 2026, in force 27 July 2026). No corrigenda.
- Latest consolidation: 27 July 2026, CELEX `02024R1689-20260727`. Consolidated texts carry no recitals and "have no legal effect"; recitals come from the OJ original (32024R1689).
- Omnibus changes: Annex III high-risk date moved to 2 Dec 2027, Annex I to 2 Aug 2028; new prohibitions Art. 5(1)(ba)/(bb) from 2 Dec 2026; Art. 4 rewritten; Annex XIV added.
- Structure: 13 chapters, 113 numbered articles plus 6 inserted (4a, 60a, 75a-75d), 14 annexes, 180 recitals.

## Getting the text (EN + DE)
- ELI URLs: `https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng` and `/deu`; original `/eli/reg/2024/1689/oj/eng|deu`; Omnibus `/eli/reg/2026/1744/oj/eng`.
- EUR-Lex website blocks curl (HTTP 202 empty). Use Cellar: `http://publications.europa.eu/resource/celex/{CELEX}` with `Accept` (`application/xhtml+xml`, `application/zip;mtype=fmx4`, `application/pdf`) and `Accept-Language: eng|deu`.
- Verified: consolidated XHTML EN 851 KB / DE 900 KB (no Formex, no PDF); OJ original XHTML 1.26 MB, Formex zip EN 171 KB / DE 195 KB, PDF 2.6 MB; Omnibus XHTML 351 KB, Formex 45 KB.
- Reuse: Commission Decision 2011/833/EU allows commercial and non-commercial reuse with attribution, no implied endorsement. Consolidated texts CC BY 4.0. Attribution line: "© European Union, 2024-2026, eur-lex.europa.eu, reused under Commission Decision 2011/833/EU. Only the Official Journal is authentic." German KI-MIG is copyright-free (§ 5 UrhG).
- Existing datasets: jsiddamsetty/aiactbrowser (`data/aiact.json`, post-Omnibus, EN only, licence unverified); maastrichtlawtech/legalviz.eu (GPLv3 CELEX-to-JSON parser); faitholopade/aiact-openrag (HF, per-paragraph chunks, Omnibus status unverified). None offers German plus post-Omnibus. Plan: parse Cellar XHTML (EN+DE) and Formex (recitals) ourselves.

## Article 4 "AI literacy" (KI-Kompetenz), text in force
> 1. Providers and deployers of AI systems shall take measures to support the development of AI literacy of their staff and other persons dealing with the operation and use of AI systems on their behalf, taking into account their technical knowledge, experience, education and training and the context the AI systems are to be used in, and considering the persons or groups of persons on whom the AI systems are to be used. This obligation does not require providers or deployers to guarantee any specific level of AI literacy of any individual.
> 2. The Commission and the Member States shall support and facilitate the efforts of providers and deployers of AI systems, in particular SMEs [...]
> 3. The Board shall adopt recommendations, taking into account European competence frameworks [...]

- Applies to all providers and deployers, including a firm whose staff use ChatGPT (Commission Q&A, updated 27 July 2026). In force since 2 Feb 2025. Market surveillance enforcement from 2 Aug 2026.
- No direct fine: Art. 4 is not in the Art. 99(3)-(5) tiers; § 15 KI-MIG lists Art. 21, 27, 45, 86 breaches only. Consequences are indirect (aggravating factor, Organisationsverschulden, civil liability, complaints to BNetzA).
- **The law mandates neither yearly training nor records.** Q&A: "There is no need for a certificate"; organisations "can keep an internal record". BNetzA: measures "sollten dokumentiert werden" (type, content, duration, participants), recommends regular evaluation and needs-based refresh. Yearly cycles are industry practice, not statute.
- "Sufficient level" no longer mandated post-Omnibus. Minimum per Q&A: general AI understanding, own role, risk analysis, tailored measures; generative-AI risks (hallucination) must be covered; instructions of use alone are not enough.

## Suggested application-focused chapter outline
| # | Chapter | Articles / sources |
|---|---|---|
| 1 | What the AI Act is and why it reaches your desk (timeline, provider vs deployer, our firm as deployer) | Art. 1-3 (3(1), 3(3), 3(4), 3(56)), Art. 113, Rec. 20 |
| 2 | How AI tools work and fail (hallucination, bias, prompt injection, confidentiality) | Art. 4, Commission Q&A, DSK OH 2024 |
| 3 | The risk pyramid: prohibited, high-risk, transparency, minimal, GPAI | Art. 5, 6, Annex III, Art. 50, Ch. V (51-55) |
| 4 | Red lines at work (workplace emotion recognition, manipulation, social scoring, face scraping, intimate imagery, CSAM) | Art. 5(1)(a)-(h), new (ba)/(bb) from 2 Dec 2026 |
| 5 | High-risk AI in HR and daily work (recruitment, promotion, task allocation, monitoring, credit, education) | Annex III pts 3-5, Art. 6, 14, 26(1),(2),(4),(5),(7),(11), 27, 86; from 2 Dec 2027 |
| 6 | Transparency duties you can trigger (chatbots, AI images, deepfakes, AI text on public matters) | Art. 50(1)-(4), Art. 111; from 2 Aug 2026, legacy 2 Dec 2026 |
| 7 | Data protection and secrets when prompting (company accounts, no personal data, no trade secrets, DPIA) | Art. 2(7), GDPR, DSK OH 6 May 2024 |
| 8 | Your role, your rights, where to report (AI policy, incidents, complaints, right to explanation, KI-Service Desk) | Art. 4, 26(5), 73, 85, 86, § 2 KI-MIG, BNetzA Beschwerdestelle |

## German context
- KI-MIG (Gesetz zur Marktüberwachung und Innovationsförderung von künstlicher Intelligenz), BGBl. 2026 I Nr. 223 (one source says 233), in force 29 July 2026. § 2(1): Bundesnetzagentur is the market surveillance authority (hybrid: BaFin, Landesmedienanstalten keep sectors). BNetzA hosts KoKIVO, KI-Marktüberwachungskammer, Reallabor, Beschwerdestelle. Text: https://www.gesetze-im-internet.de/ki-mig/
- German helper documents: BNetzA KI-Kompetenz page, KI-Service Desk (Factsheet KI-VO, Factsheet KMU, FAQ, KI-Compliance-Kompass), Commission AI literacy Q&A (DE), AI Act Service Desk FAQ (DE), DSK Orientierungshilfe KI und Datenschutz (6 May 2024), DSK OH on TOMs (June 2025) and RAG (Oct 2025), BfDI Handreichung KI in Behörden (Dec 2025).

## Comparable tools
No open-source self-hostable Art. 4 employee quiz found. Closest: regulatoryai.eu AI Literacy Essentials (free tier, 6 modules, 8-question quiz, self-issued certificate), QA.com module, Commission repository of AI literacy practices, FLI directory, awesome-eu-ai-act (CC0), KI-Campus, BNetzA KI-Compliance-Kompass.

## Not verified
Consolidated PDF via Cellar; aiactbrowser licence; aiact-openrag Omnibus status; BGBl number; whether Art. 4(2) practical examples are published.
