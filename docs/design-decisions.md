# Design decisions log

Running log of decisions taken during the design conversation (2026-09-15 onward). Newest at the bottom. This file records the why.

## D1. Languages: multilingual from the start, German first (2026-09-15)
- Student-facing product (UI, lessons, questions, model answers, cheat sheet, personas) is multilingual; German is the primary and reference language, English second, further EU languages possible without architecture changes.
- Code, prompts, internal docs and identifiers are in English.
- Consequence: content is stored per locale, the law corpus is loaded per language from EUR-Lex (24 official languages available), the persona layer must work in the student's language, and the UI needs proper i18n from the first commit.

## D2. Personas must be easy to extend (2026-09-15)
- Personas are data, not code: one directory per persona holding a manifest (id, display names per locale, voice description, style rules, guard-reaction style), prompt fragments per locale, and avatar assets (one image per emotion state).
- The pipeline applies the persona only in the final "spice" step and in guard reactions, so a new persona never touches the teaching, coaching or grading logic.
- Adding a persona = adding a directory (plus images). The frontend discovers personas from the backend, never from a hard-coded list.

## D3. Student journey: guided course, fully conversational, test on demand (2026-09-15)
- Guided chapter sequence by default (about eight application-focused chapters), delivered in chat by the persona, with free questions allowed at any time.
- No test button. "I want the test now" (in any phrasing, any language) is an intent the pipeline recognizes at any point, even in chapter one.
- Once all material is covered, the tutor recommends the test. The student may take it or keep asking questions.
- During the test, the student can still ask questions. The coaching branch answers, but never gives the answer away: it gives context, points to the relevant articles and helps the student understand the needed knowledge Socratically.
- Cheat sheets: one per chapter plus a full one at the end.

## D4. Content model: curated content, LLM delivery (2026-09-15)
- Chapters (key points, examples, law references), the question bank (question, type, rubric, model answer with explanation and citations) and the cheat sheets are authored files in the repo, per language. Written with LLM help at build time, reviewed by the maintainer.
- At runtime the model delivers and adapts lessons, answers free questions with retrieval over the law corpus, coaches, and grades against the rubric. It never invents curriculum.
- The question bank is a pool (target 40-60 questions across chapters); each test attempt draws 10 with a fixed type mix (yes/no, multiple choice, free text) and randomized order.
- The law corpus (consolidated EUR-Lex text, EN + DE at minimum) is used for citations and off-script questions.

## D5. Model strategy: roles mapped per deployment via LiteLLM (2026-09-15)
- The backend addresses model roles, not models: `strong` (lesson delivery, coaching, grading, persona rewrite) and `fast` (guards, intent routing, classification). Roles are LiteLLM model aliases configured per deployment.
- Development and CI run the grading and coaching fixtures against one frontier model and one open-weight model so the quality floor is known and documented.
- Structured output is requested with `method="function_calling"` and validated with Pydantic, because proxy-fronted models do not reliably support strict JSON schema (see research notes).
- Development inventory (this machine, 2026-09-15): GROQ_API_KEY (open-weight models), Z.AI GLM-5.3 via the local caveman proxy (`~/bin/claude-zai`, port 8787), RTX 2080 Ti 11 GB (Ollama not installed yet), Replicate and RunPod tokens. No OpenAI/Anthropic key. Candidate dev mapping: `strong` = GLM-5.3 or Groq 70B-class, `fast` = Groq 8B-class or local Ollama 8B; `fast` doubles as the small-model floor for grading fixtures.

## D6. Compliance side: full feature set, everything optional; storage and identity decoupled (2026-09-15)
- Feature set is C (admin table with status, last pass, due date, score, filters, CSV export; PDF participation certificate; email reminders before due date; per-department statistics; audit log of what each employee was taught), but every part is optional. The app must run as "just the trainer" with all of it switched off.
- Storage is behind an interface. The app ships with a prepackaged Helm chart and a docker compose file that start it together with a Postgres, but a customer can bring their own database by pointing a connection string at it. No feature may assume our bundled database.
- Identity is pluggable: OIDC (Keycloak and compatible providers) and LDAP/AD as first-class options, configured by environment. We never bundle a duplicate identity provider; the packaged chart integrates with the customer's, and local development uses a lightweight dev-only mock.
- "Finished" = test passed with at least 8 of 10 correct; unlimited retries, each a fresh draw from the pool (assumption, not yet confirmed).

## D7. Student data: minimal by default, opt-in levels (2026-09-15)
- Level 0 (always): per user, passed yes/no, date of the pass, language, persona chosen. Conversation state lives only as long as the session needs it and is deleted after a pass or after a configurable retention window.
- Level 1 (switch): attempt history with scores and per-question results.
- Level 2 (switch): transcripts and what was taught, with a retention period.
- The admin view and the audit log show only the levels that are on. The student sees on the first screen exactly what is stored. Reason: works council co-determination (§ 87 BetrVG) and GDPR make the default the deciding factor for German customers.

## D8. Gamification: moments plus light progress, session-local (2026-09-15)
- Confetti and a persona reaction on every correct answer, the model-answer card, a chapter-complete flourish, a finale on passing the test.
- A visible chapter map with a badge per chapter, a streak counter for consecutive correct answers inside a session, and the persona's mood shifting with the streak.
- Persona emotion states: at least happy, neutral, disappointed, surprised; one image per state per persona.
- No points, no levels, no leaderboard, no persistent XP. Everything is session-local so the D7 data default holds and nothing reads as performance monitoring.

## D9. Model policy for development (2026-09-15)
- Implementation (writing code, running tests, executing plans) happens in Claude Opus or a smaller model, never in Fable. Fable sessions design, plan, review and dispatch. Recorded in CLAUDE.md.

## D10. Repo home: a private GitHub repo, no license yet (2026-09-15)
- Remote: the maintainer's GitHub account, private for now. Transfer to the neutral org when it exists.
- No LICENSE file until the repo goes public. Candidate at that point: Apache 2.0, as listed in the mittelstand-ai service description.
- CI: GitHub Actions (tests, container image build, content lint) once the scaffold exists.

## D11. Visual style: pixel-art game look by default, switchable; colors from a tunable theme (2026-09-15)
- Default look: 8-bit/16-bit pixel art in the spirit of classic platformers. Pixel font, sprite-style confetti and emoji, pixel-art persona avatars, chapter map drawn like a level map. One cohesive, recognizable look.
- The look is switchable per deployment and per user to a clean modern look, because not everyone will love it. Both looks share the same layout and components; the pixel look is a theme layer (fonts, borders, sprites, effects), not a second frontend.
- Colors come from a theme that a customer tunes to corporate colors (primary, secondary, accent, background, plus derived shades). Both looks read from the same theme tokens.
- Persona images are generated once, in pixel art. The clean look reuses them.

## D12. Content management for i18n: reuse the ecosystem, add a light curation UI only if none exists (2026-09-15)
- UI strings, course content (chapters, question bank, model answers, cheat sheets) and persona text are all multilingual and need a way to curate and translate them without editing raw files.
- Prefer an existing open-source, self-hostable tool from the i18n ecosystem. Only if none fits do we build a light curation frontend ourselves.
- Research pending on which tool fits both UI strings and structured content per locale (see docs/research/).

## D13. Law-change workflow (2026-09-15)
- A command fetches the latest consolidated text per language from the EU Cellar API, diffs it article by article against the bundled version, and writes a change report.
- Because every chapter, question, model answer and cheat-sheet item cites articles, annexes or recitals, the report lists exactly which content items are affected by each changed article.
- Content updates stay a human decision made in the curation UI (D12); the model may draft suggested edits for the curator, never apply them.
- The bundled corpus version (consolidation date, CELEX) is shown in the product so a compliance officer can see what the training was based on.

## D14. Architecture: one Python service with an explicit LangGraph pipeline (2026-09-15)
- Chosen over "one agent with middleware" (control flow hidden in tool choice, fragile with small models) and over "LangGraph Server" (Elastic License, Enterprise-only self-hosting, no redistribution).
- FastAPI process hosts a LangGraph StateGraph per chat turn. `create_agent` with a retrieval tool is used inside the branches that need a tool loop. Structured output via Pydantic for guards and grading. Postgres checkpointer for threads. React frontend served by the same container. Streaming over server-sent events.
- Curation tooling: Sveltia CMS for course content, Tolgee for UI strings, both for the content team only (research: docs/research/2026-09-15-content-tooling.md).
- The owner: "Worst case: we change it later."

## D15. Course updates: text is the only source, versions are tags, AI changes are pull requests (2026-09-15)
- Nothing derived is edited or committed. Cheat sheets, model-answer cards, certificate, PDFs and embeddings are built from the YAML text at image build time through templates.
- `content/manifest.yaml` carries the course version and the law version (CELEX, consolidation date). Each release is a git tag and an image tag. Completion records store both versions (level 0, not personal data).
- A law change produces a pull request under a bot identity, never a commit to master. The update tool runs the law diff, asks the `strong` model per affected item for a proposed text with a reason, writes it to the content files on a branch, and writes a review report with old and new text per item.
- Every content item has a `last_change` block (date, author kind human|ai, trigger, one-sentence summary) shown in the CMS form.
- Spike to verify: Sveltia's editorial workflow discovers externally created branches following its naming convention, so AI drafts appear as "In Review".
- Retraining policy is configuration: a major course version bump makes completions due again, a minor bump does not.

## D16. Chat is the only student interface, and it is rich (2026-09-15)
- Every input is a message. The backend ends each turn with an input hint (free text, yes/no, choices, confirm); the frontend swaps the input control, but a tap sends text into the pipeline. Persona and language choice are the first two turns as choice chips. No settings screen for students.
- Every output is a message with optional rich parts: model-answer card, citations panel, files (cheat sheet PDF, certificate) generated server-side from text through templates, images or animated sprites, effects such as confetti, the chapter map on completion and on request.
- The avatar has its own stage beside the chat: large persona image in its emotion state, idle animation, streak, persistent chapter map. Clicking a chapter inserts a message.

## D17. Pixel look: all in, enforced through a primitives library with two skins (2026-09-15)
- Integer pixel grid (4 px unit, scale 2 or 3 from the viewport), `image-rendering: pixelated` everywhere.
- Fonts all in: 8x8 arcade font for headings, labels and the stage; a proportional SNES-style dialog pixel font at 2x for body text and legal quotes. Accessibility switch swaps only the body font for a normal one.
- Every panel, bubble, card, chip and button is a nine-slice pixel frame via `border-image`. No rounded corners, no blur shadows, banded or no gradients. Custom controls only; lint rule forbids raw button/input/select outside the primitives folder. Sprite sheet for icons and badges, 2-4 frame sprite animations, square confetti, pixel cursor, stepped transitions. Palette quantized in pixel mode. Tiled pixel background.
- PDFs (cheat sheet, certificate) use the clean look with a pixel header.
- Switch: `data-look` on the root; each primitive has a pixel and a clean block over shared tokens, layout and behavior. Guards: a gallery page rendering every primitive in both looks, Playwright screenshot tests of it in both looks per pull request.
- Optional, off by default: SNES-style sound effects.
- Cost: pixel skin about twice the clean skin. Frames and icons generated through Replicate with the avatar pipeline, then touched up.

## D18. Scope of the first build: everything except full content (2026-09-15)
- Build every part of the design now: pipeline, full frontend in both looks (needed to judge the UX), content management and i18n tooling, observability, storage, identity, admin view, packaging, update workflow.
- Course content is partial for now: chapters one and two complete, chapters three to eight as short stubs so the flow and the chapter map work end to end, about fifteen questions across types. Full content (all chapters, 40 to 60 questions) is content work after the first release.
- Bookkeeping: this file and the archived internal task log track what is built, done and next. Straight improvements are done right away, never listed.

## D19. A national law sits in the corpus of every locale (2026-09-15, replaced by D24)
- **Replaced on 2026-09-16.** The behaviour was right and the reason was wrong. A national law
  belongs to the deployment's jurisdiction, not to a reader's language, and this rule as written
  would put German law in a French customer's corpus. D24 records the replacement. The rest of
  this entry is kept as history.
- The KI-MIG exists only in German, and `build_corpus` used to add it to the German corpus only. The English chapter one cites `KI-MIG § 2(1)` because the content lint requires the citation lists of a translated item to match the reference locale byte for byte, and because the German enforcement law applies to a German company whatever language its staff reads in.
- So `build_corpus` now adds the KI-MIG for every language. Resolving that citation from English content returns the German text of the statute and the gesetze-im-internet.de URL, which is the honest answer: there is no English KI-MIG to quote.
- `Corpus.lang` keeps its meaning of "the language of the Regulation text". Extra documents carry whatever language they exist in.

## D20. Questions ask what you may do at your desk (2026-09-15)
- Chapter one shipped with questions on which authority supervises, since when Article 4 applies
  and what the two roles are called. Accurate, and useless: nobody needs that to do their job.
- Content is application-first. A question describes a situation an office worker actually
  faces, and the answer changes what that person does on Monday. Examples of the right shape:
  may I send a mail an AI drafted if I read and approved it, must I tell a customer that the
  chat window is a bot, may I paste a customer list into a chat assistant, may HR screen
  applicants with an emotion recogniser.
- The majority of questions explore what is allowed. The tool exists to make people confident
  users of the technology, not to frighten them away from it. Prohibitions are taught as the
  short list they are, against a long list of things that are fine.
- A legal fact appears only where it explains a situation. Dates, authority names and article
  numbers belong in the cheat sheet, never as the thing a question tests.

## D21. The tutor finds law through a tree of summaries, not a vector store (2026-09-16)
- A student only ever chats. When the question is covered by a curated chapter, the tutor
  teaches from that chapter and its citations, which resolve by exact id. The open case was the
  question the course does not cover: may I paste a customer list into a chat assistant.
- Two behaviours were possible. Answer only from the curated course and decline the rest, or let
  the tutor search the law itself. The owner chose the second: the tutor finds the relevant
  articles and answers from them with citations.
- How it finds them: the law's own structure becomes a navigable tree. Each chapter, and then
  each article, carries a short summary, so the tutor narrows from thirteen chapters to one
  article without reading the whole Regulation. Keyword search covers what the summaries miss.
- No vector store and no embeddings for this. A self-hosted install stays simple, nothing depends
  on a database extension, and a citation is exact by construction rather than approximate. The
  parked pgvector idea stays parked.
- Two things this decision creates. The summaries are content: somebody writes them, they are
  reviewed like a chapter, and they are translated. German keyword search has to match
  "Betreiberpflichten" against "Pflichten der Betreiber", which plain word matching does not do.

## D22. Version 0.1 ships German only (2026-09-16)
- The English chapter one is machine translation that nobody checked line by line. It must not
  reach a student while the German is still moving, and keeping it as an unloaded directory would
  be a dead path against the ONE WAY ONLY rule. So `content/en/` is deleted and `en` leaves
  `content/manifest.yaml`.
- The translate tool stays and stays tested. It regenerates English in minutes once a
  German content is settled. Git history holds the deleted files.
- D1 is not reversed. The product stays multilingual by architecture: content is per locale,
  every student-facing string comes from a locale file, and the pipeline takes a locale. This
  decision is about where the effort goes now, not about what the product can do.
- Consequence: a new content type ships for the reference locale only. The lint's
  locale-agreement rules stay and pass trivially with one locale.

## D23. Postgres and SQLite are the supported databases (2026-09-16)
- LangGraph ships checkpointers for Postgres and SQLite and for nothing else. Using it therefore
  narrows what a customer may bring. The owner accepted that narrowing rather than write a
  checkpointer over the `Repository` protocol or keep session state in a row of our own.
- So session state between turns lives in LangGraph's checkpointer: Postgres in production,
  SQLite in development, `InMemorySaver` in tests. The checkpointer creates its own tables
  through `setup()`, Alembic does not manage them, and `test_migrations.py` keeps checking only
  our own models.
- This amends D6, which said no feature may assume our bundled database. The rule becomes: no
  feature may assume our bundled *instance*. A customer points a connection string at their own
  Postgres. They may not bring MySQL or Oracle.
- D7 still holds. Retention is a delete of the thread on a pass or at the end of the window.

## D24. The corpus becomes a library of acts, and adjacent law is bundled (2026-09-16)
- A student asks whether they may paste a customer list into a chat assistant. The AI Act does
  not govern that. Data protection law and trade secret law do. Answering it needs those texts
  in the repo, cited the same way, and searchable the same way.
- `Corpus` held one act plus an `extras` list carrying the KI-MIG and the Commission questions.
  That list was a workaround. It goes. `Act` and `Library` replace it, node ids gain the act as
  a prefix (`ai_act:art_26.7`, `gdpr:art_5.1.a`), and adding a law becomes a manifest entry
  rather than a code change.
- Bundled: the AI Act, the KI-MIG, the GDPR, the BDSG, the BetrVG, the GeschGehG, and the
  Commission questions on AI literacy. The UrhG is out until the course teaches copyright.
  Recitals are fetched for the AI Act only.
- Verified before deciding: the existing EUR-Lex parser reads the consolidated GDPR unchanged
  (11 chapters, 15 sections, 99 articles), and the four German statutes use the same
  gesetze-im-internet XML as the KI-MIG.
- Written citations name the act. A bare `Art. 26(7)` stays the AI Act, which is right for an AI
  Act course. No existing content file changes.
- **This replaces D19.** A national law belongs to the deployment's jurisdiction, not to a
  reader's language. `Act.jurisdiction` says so, and a deployment outside Germany swaps the
  statutes without touching the loader. D19 reached the right behaviour for the wrong reason,
  and its reason would have put German law in a French customer's corpus.

## D25. A law summary is an index entry and no student ever sees one (2026-09-16, review bar amended by D29)
- The tutor navigates the library through summaries and then quotes the real text. A weak summary
  costs one wrong lookup, which the tutor notices when it reads the article. It cannot put a
  wrong legal claim in front of a student.
- So the review bar differs by level. The navigation levels get a human read, about 90 texts:
  the acts, their chapters and their sections. Those steer every lookup. Leaf summaries for
  single articles and statute sections carry `reviewed: false` until the course reaches them.
- The lint forbids a summary from carrying citations of its own, which is what keeps a summary
  an index entry rather than a legal claim that nobody reviewed.
- **This amends D21**, which said the summaries are reviewed like a chapter. D21 was written
  before the library grew to seven acts and about 575 summaries, where a full human read would
  block the milestone on reading time for text no student sees.
- The other half of D21 is strengthened, not weakened: the law's own structure supplies the
  levels, so no lookup step ever shows the tutor more than fifteen items.

## D26. A quote never cuts inside a paragraph (2026-09-16)
- One function cuts law for a prompt. The unit is what the citation names. Over budget, whole
  paragraphs are dropped from the end and named, never truncated mid-sentence.
- A half sentence of Article 5 in front of a student is worse than a note saying which
  paragraphs are not shown. A truncated legal sentence can invert its meaning, because the
  exceptions sit at the end.
- This settles the two items parked in M2. It also forced a real fix: the parser appended text
  blocks that follow a point list onto the paragraph's lead-in, so Article 5(1) read "The
  following AI practices shall be prohibited: Point (h) ... is without prejudice to ..." before
  the list of prohibitions, in both languages.

## D27. A law update re-summarizes only what changed (2026-09-16)
- Laws are fetched from their source with their version recorded, never copied by hand. For a
  Union act one SPARQL query against the Cellar returns the newest consolidation. For a German
  statute the XML carries `builddate`, the promulgation date and the Bundesgesetzblatt
  reference.
- Exactly one thing on disk is derived from the law: the summaries. The parsed library and the
  search index are built at startup, and the cut for a prompt is computed per request. There is
  no chunk artifact to rebuild.
- Each summary records the sha256 of the node text it was written from. An update re-summarizes
  only the nodes whose text moved, and their ancestors, because summaries are written bottom up.
  Everything else keeps its text and its review mark.
- Re-summarizing the whole library on every update would discard the reviewed navigation
  summaries and bury the real change in noise.
- The lint fails on a stale `source_sha`, so shipping a law update without regenerating the
  affected summaries is impossible. The update lands as a pull request, per D15.

## D28. The bundled acts define what the tutor may say (2026-09-16)
- A question a bundled act covers gets an answer with citations and no disclaimer. A clear data
  protection question is answered from the GDPR and the BDSG, and the tutor gives its opinion.
- A question no bundled act covers gets "I am an AI Act trainer and I do not know this", and no
  invented rule.
- The disclaimer that this is a trainer and not a legal adviser appears once, in the first turn.
  Repeating it on every answer makes the tutor tiresome and teaches the student to skip it.
- When a student asks about their own case ("kann ich dagegen klagen", "darf mein Chef das"),
  the tutor answers what it thinks and adds one fixed hedge line naming itself as a trainer and
  not a lawyer. Triage sets the flag, and a deterministic check after the persona rewrite
  verifies the hedge survived.
- This makes expertise a checkable property rather than a judgement call, and it means extending
  the tutor's expertise is adding an act, which is data.

## D29. Best effort, and no expert gate (2026-09-16)
- Two items in M3 waited on a person who is not on this project: a German-speaking lawyer to read
  the course, and the owner to read about ninety law summaries. Both are removed. Nothing in this
  build waits on an expert we do not have.
- The course is written to be useful, not to be litigated. A question describes something a person
  actually does and the answer changes what they do next. The owner's example: "What do you need to
  make sure of when giving a customer access to an AI agent?" answered by "The customer has to know
  they are talking to an AI and not a human." That is D20 restated as a standard of usefulness
  rather than of legal review.
- The law summaries ship as the model writes them. The generation step reads back the act, chapter
  and section summaries and fixes what says nothing, because those steer every lookup. The roughly
  480 leaf summaries stand as generated. The `reviewed` flag is deleted: a field nobody sets is
  dead weight.
- This is safe because of the rule D25 already states. A summary is an index entry and no student
  ever sees one. The tutor navigates with it and then quotes the real text, so a weak summary costs
  one wrong lookup, which the tutor notices when it reads the article.
- **This amends D22 and D25.** D22 said English returns once a German-speaking lawyer has read the
  German. It returns when the German content is settled. D25 said the navigation levels get a human
  read. The model reads them back instead.

## D30. Chapter two is the paste question (2026-09-18)
- the owner chose chapter two's topic from three candidates: what you may feed an AI tool,
  not deployer duties and not high-risk at work.
- The paste question ("darf ich die Kundenliste in den Chatassistenten kopieren") is D24's
  motivating case and the reason the GDPR, the BDSG, the BetrVG and the GeschGehG are
  bundled. No chapter cited those acts before, so the library's four extra acts served only
  free questions. Chapter two teaches them.
- It is also the everyday desk question, which D20 says the course is made of.

## D31. A stub chapter declares itself incomplete (2026-09-18)
- Chapters three to eight ship as stubs in v0.1 (D18), so the flow and the chapter map work
  end to end. A stub is a chapter with `stub: true`, one or two honest steps, no practice
  questions.
- The content lint exempts a stub from the one-question-of-each-type rule and refuses any
  question that names a stub chapter: a stub teaches nothing, so nothing of it may be
  tested. Cost if wrong: a question hanging on a stub rides the test draw and tests material
  the course never taught.
- When a stub grows complete, the flag goes and the full rules apply. No legacy path: the
  flag names the current truth of its file.

## D32. Fairness is measured against both roles, gated on strong (2026-09-18)
- The grading evaluation set holds hand-labeled German student answers for every free-text
  question. The runner grades them through the real `grade_answer` path with the `strong`
  and the `fast` model in the grading slot, per the conventions ("from M4 on").
- The floor is gated on `strong` only: accuracy at least 0.9, false-negative rate at most
  0.1. The false-negative rate is the unfairness that matters, because the product's ruling
  is that an answer showing understanding counts. The `fast` numbers are the measured floor,
  not a gate: the shipped grader runs on `strong`, and knowing what the cheap model does is
  the point of measuring it.
- A missed floor is a finding fixed in the same round, never parked. The report under
  The archived internal eval notes record the final numbers and what changed.

## D33. The course is easy and short (2026-09-18)
- About 25 minutes of study for the whole course, then a quick test. The test cannot be
  passed without knowing the material, and not from the questions alone, but nothing in it
  is hard.
- Consequences: plain German, short steps, no doctrinal depth. A rule is named with its
  citation and applied to a desk situation. Questions sit at difficulty 1 or 2 and are
  answerable by someone who read the chapter. Free-text rubrics name the few points
  understanding leaves.
- Chapter one runs eight minutes as the orientation chapter, chapter two four. The
  post-v0.1 chapters are written to about three minutes each, and chapter one is trimmed
  then if the total runs over 25.

## D34. UI chrome art is drawn, not prompted (2026-09-19)

- D17 planned to generate the nine-slice frames, icons and badges through Replicate with
  the avatar pipeline, then touch them up. This changes that: `tools/make-ui-art`, a
  committed Pillow script, draws every UI asset from the theme palette on the 4 px grid.
- Why: a nine-slice tile needs exact edge tiling, exact palette placement and exact corner
  pixels. Image generation promises none of the three, so every generated frame would need
  hand touch-up anyway. The script is deterministic and regenerates all assets when the
  palette moves.
- Replicate keeps what it is good at: the persona portraits.
- **This amends D17's cost line.** The rest of D17 stands.

## D35. PDFs render at run time, on demand (2026-09-19)

- D15 said the cheat sheets and the certificate are built from the YAML text at image
  build time. M5 renders all three documents at run time through one WeasyPrint path: the
  chapter cheat sheet cached per content version, the full cheat sheet and the certificate
  fresh per request.
- Why: the certificate carries the student's name, date and score, so a renderer must live
  in the running service whatever D15 said. Running the cheat sheets through the same
  renderer keeps one way, per the conventions; a second, build-time path would be a kept
  twin.
- D15's actual rule stands untouched: the YAML text is the only source, versions are tags,
  nothing derived is edited or committed. Only the rendering moment moves.
- **This amends D15.**

## D36. The stage travels the existing wire as a projection (2026-09-19)

- The avatar stage (persona, mood, streak, chapter map, attempt progress) is a projection
  of `SessionState` plus content, assembled server-side into one `stage` block. It rides
  `POST /api/session` for the initial paint and one `ui` event per turn for updates.
- Why: the checkpointed state already holds every field the stage shows, the persona
  funnel already projects a turn onto events, and a projection keeps German content
  (chapter titles, persona names) on the server, where content lives. No new endpoint, no
  polling, no second source of truth for progress.
- Cost if wrong: the block grows a field, and both carriers pick it up in one place each.

## D37. German is the only locale file (2026-09-20)

- `frontend/src/locales/en.json` was deleted in commit `0d9817c`. `de.json` is the only
  locale the frontend carries, and Tolgee is configured for `de` alone.
- Why: D22 ships German only in v0.1. An English chrome file that nobody maintains drifts
  from the German one and invites English student strings, which the conventions forbid.
- Adding a locale later means adding its file beside `de.json` and listing it, not restoring
  a deleted path. The plan's line about two locale files no longer holds.

## D38. The pixel look stays light on a dark system (2026-09-20)

- `derivePalette` skips the dark branch when the look is pixel. A student on a dark system
  sees the light pixel palette. The clean look keeps dark mode.
- Why: the nine-slice art in `frontend/src/ui/art/` is drawn in light tones and fills every
  frame, card and bubble through `border-image`. The dark palette put light text on those
  light fills, around 1.3:1 at the chapter labels.
- Cost if wrong: a dark sprite set drops the look test in `derivePalette` and records its own
  screenshot baselines.

## D39. The persona is chosen before the chat, and the graph has no onboarding phase (2026-09-21)

- `POST /api/session` carries a `persona_id`. The thread is seeded with that persona and
  `Phase.lesson`. `Phase.onboarding`, `onboarding_node`, `route_after_onboarding`,
  `just_finished_onboarding`, `student_role` and the `persona_question`, `role_question` and
  `help_onboarding` strings are deleted.
- Why: `route_after_triage` returned `"onboarding"` for every turn while the phase was
  onboarding, and `onboarding_node` fell back to the persona question for any text that was
  not a persona id. Every message reprinted the disclaimer and the persona question, without
  end. A phase whose only exit is a four-way choice does not belong in a free-text chat.
- Cost if wrong: the question about the student's role comes back as a field on the persona
  screen.

## D40. The opening turn is a kickoff stream, not a student message (2026-09-21)

- `POST /api/chat/{id}/opening` streams the same seven events as a turn. It enters the graph
  with `Command(goto="lesson_step")`, below triage, so the first lesson step arrives in the
  persona voice and adds no student bubble. `post_turn` and `post_opening` share one
  generator.
- Why: the course has to start on its own after the persona is picked. Sending a hidden
  "start" message would show the student words they never typed, which is the complaint that
  opened this round.
- Cost if wrong: one silent user turn at the head of every transcript.

## D41. A choice chip sends its key and shows its label (2026-09-21)

- `InputControl` submits `choice.key` and the student bubble renders `choice.label`. No
  student-facing surface ever prints an internal identifier.
- Why: clicking "Der Sachbearbeiter" put the literal text `clerk` in the student's own
  bubble. Identifiers are English by the conventions, so any identifier on screen also breaks
  German-only (D22).
- Cost if wrong: the transcript stores a label that no longer matches its key after a content
  edit.

## D42. Dark is the default, in both looks (2026-09-21)

- `theme/base.css` ships a dark palette, `useTheme` defaults to dark instead of following
  `prefers-color-scheme`, and the nine-slice art in `frontend/src/ui/art/` is regenerated from
  the dark palette. Light stays reachable through the mode toggle.
- Why: the product is a chat a student sits in for an hour. A light default was the first
  thing called out, twice.
- This reverses D38, which kept the pixel look light because the light sprite set put light
  text on light fills at about 1.3:1. The sprites are regenerated, so the reason no longer
  holds.
- Cost if wrong: the screenshot baselines and the contrast check are recorded a second time.

## D43. The browser path carries its own test suite (2026-09-21)

- A Playwright suite drives the real UI against the running stack with scripted models: pick
  a persona, receive the opening turn, send several turns, and assert that two turns do not
  return the same text and that no bubble carries an internal identifier. It runs in the
  frontend gate and from `deploy/demo.sh`.
- Why: the loop that returned one answer to every message shipped. The Playwright config only
  shot gallery screenshots, and `tools/demo_walk.py` walks the API, so the click path a
  student takes was never executed by a test.
- Cost if wrong: the gate needs the stack running, so it is slower than the unit suites and
  skips when the stack is down.

## D44. The product is called KI-Führerschein (2026-09-21)

- "KI-Verordnung Training" is gone. The name on screen, in the tab title and on the persona
  screen is "KI-Führerschein", with the line "Dein Kurs zur KI-Verordnung" under it. The
  certificate keeps its formal wording, because a compliance record names the duty and not
  the nickname.
- Why: the brief's north star is Jo, who did not ask for this and gives it 35 minutes. A name
  that reads like a regulation is the first thing that tells Jo this will be dull. A
  Führerschein is a thing people are mildly proud of, it is German, it is understood without
  explanation, and it matches a course that ends in a test and a certificate.
- Cost if wrong: one locale key and one heading.

## D45. The dull course is an opt-in for one person, never the default (2026-09-21)

- Der Sachbearbeiter and the clean look are the escape hatch for the colleague who wants no
  fun: picking both turns the training into an ordinary compliance module for that student
  and nobody else. Both stay one click away and neither is ever the default, the fallback or
  a reason to soften a persona, an effect or a line of copy for everyone else.
- Why: the north star in `GOAL.md` is Jo, who remembers this as the least shitty compliance
  training of their life. Products lose that by sanding down the fun until the most
  humourless reviewer is comfortable. This ruling names where that person is served, so
  every other surface can stay playful without another argument.
- Cost if wrong: a customer asks for a deployment-wide dull default, which is one setting.

## D46. Every persona is part machine, and the anchor says so once (2026-09-21)

- `CYBORG_ANCHOR` in `tools/generate_avatars.py` adds the implant, the chrome plating and the
  neck cables to every prompt, so a persona directory describes a character and never has to
  remember the machine half. All twenty portraits were regenerated from it.
- Why: the brief asks for cyborg avatars and the first set was not. The course is about AI,
  and the tutor should look like it. Putting the trait in the shared anchor means a new
  persona cannot be drawn without it.
- Cost if wrong: one constant and one regeneration run.

## D47. One sprite set, no baked fill (2026-09-21)

- The nine-slice PNGs carry outlines, bands and the primary fill only. Every surface is
  transparent, so `--c-surface` and `--c-bg` paint it and the same set reads in dark and in
  light. `make_ui_art.py` no longer takes `--background`.
- Why: D42 makes dark the default, and D38's light-baked sprites put light text on light
  fills. Baking a dark set instead would break the light mode the toggle still offers. Bands
  derived from the theme's secondary are mid-tones that read on both.
- Cost if wrong: two sprite sets and a `[data-mode]` switch in `ui/pixel.css`.

## D48. The chapter map leaves the product (2026-09-21)

- `ChapterMap`, `StagePanel` and the three map tiles are deleted. What survives moves into
  `CourseStatus`, one line above the composer: the persona portrait and mood, "Kapitel n von
  m", the streak badge and the attempt dots. The `chapters` list stays on the stage block,
  because the count comes from it.
- This narrows D8 and D11, which both promised a visible chapter map drawn as a level map.
  The badge per chapter, the streak, the mood and the chapter-complete flourish all stay.
- Why: the map was the reason the chat sat in a 360px side column, and its tiles sent
  "Erzähl mir von Kapitel 2" as if the student had typed it. A course that is walked in
  order does not need a map to navigate, and the brief's north star gives Jo 35 minutes with
  no time to browse chapters.
- Cost if wrong: the map comes back as a panel the student opens, never as a side column.

## D49. The tutor writes plain prose, and the code makes sure of it (2026-09-21)

- `PLAIN_TEXT_RULE` and `NODE_ID_RULE` join the shared answering rules and the persona
  rewrite: German prose in short paragraphs, no Markdown, and never a tool's internal node id
  (`cpt`, `sct`, `art`, `anx`, `rec`, an act key) on screen. `persona.plain_text` then strips
  headings, emphasis markers and thematic breaks from the finished message, and `.ui-bubble`
  gets `white-space: pre-wrap` so the paragraphs survive.
- Why: the first live run of M5.1 answered a real question with a Markdown wall: `###`
  headings, `**` markers, a pipe table, and "cpt IV" where "Kapitel IV" belongs. The bubble
  renders text, so the student read the syntax. The node id also breaks D41, which says no
  student-facing surface prints an internal identifier.
- Prompt rules alone were not enough: the models kept some `**` and bullets, so the strip is
  deterministic and the prompt only reduces how much there is to strip.
- Cost if wrong: a student who wants a table does not get one.

## D50. A round starts with a person and ends with a rating, and Fable only designs (2026-09-21)

- Every round on the product's look or its chat runs this cycle. First an agent plays Jo in
  a real browser against the running stack and reports in Jo's voice what confused, bored
  or annoyed them, with the seconds waited per turn. Then a separate agent that drew none of
  it rates screenshots: does it look cool, does it look like a professional pixel-art game,
  what does a real one do that this does not. Only then does code change. After the code, both
  run again and the report says whether the scores moved. The driver both agents use is
  `frontend/e2e/drive.mjs`, one command per call, a screenshot after every step.
- Fable owns UX and layout design and hands implementation to a cheaper model. This extends
  D9, which already keeps implementation out of Fable.
- the owner is asked one level at a time, never bundled: composition, colour, typography,
  background, the concrete pixel art. Each level comes as about three refined designs he
  chooses from or redirects, drawn at the fidelity of the level: outline wireframes with no
  page detail for composition, swatches with one sample bubble for colour, real text at 1:1
  for readability, 4x renders for pixel art. A multiple-choice question is not a design
  round.
- Why: M5.1 shipped a look nobody had checked against a person, and the first person to see
  it rejected five things on sight. The first Jo run of this round found 21 defects the unit
  suites and the browser test had all passed. The rater counted six pixel sizes on one
  screen. Both were visible to anyone who looked.
- Cost if wrong: about an hour of agent time per round before any code moves.

## D51. The persona rewrite runs on the strong role (2026-09-21)

- `persona_model_role` defaults to `strong`, not `fast`. The M3 spec set `fast` because the
  rewrite looked like cheap work. Section 4.3 of the approved design still names the role, so
  a deployment that wants the cheap model sets `PERSONA_MODEL_ROLE=fast`.
- Why: measured on ten curated lesson steps against the dev proxy, the fast model
  (`openai/gpt-oss-20b`) returned an empty string on eight of them. It spent all 2048
  completion tokens on reasoning and stopped on `finish_reason: length`. `survival_ok` rejects
  an empty rewrite, so the student read the neutral draft. Jo picked the pirate and eleven of
  thirteen turns had no pirate in them. The strong model survived ten of ten at 2.2 seconds a
  rewrite. Numbers and method: the archived internal round notes of 2026-09-21,
  section "Persona survival".
- `reasoning_effort=low` changed nothing, and `max_tokens=6000` still left one step of four
  empty after 5998 reasoning tokens, so no prompt or parameter saves the cheap model here.
- The persona rewrite is the last node of every turn. A node that returns nothing on eight
  turns in ten is not a cheap node, it is a broken one.
- Cost if wrong: every turn pays the strong model's price for the rewrite. The role is one
  environment variable, so a deployment that measures its own fast model can move it back.

## D52. The tutor leads with the conclusion and writes German words (2026-09-21)

- `EXPERTISE_RULES` gains two rules. The conclusion comes first in one sentence, then at most
  three short paragraphs. German words win where German has one: "Mensch in der Schleife", not
  "Human-in-the-Loop"; "bestmöglich", not "Best-Effort". The law's own terms stay as the law
  writes them.
- Why: Jo asked whether sorting CVs with ChatGPT is allowed and read six paragraphs on
  Risikomanagement, Daten-Governance and the EU register before the answer arrived in the last
  line. Jo also met "Human-in-the-Loop-Ansatz" and "Best-Effort-Bestimmungen" on screen and
  had been told neither.
- Cost if wrong: a question whose honest answer needs the derivation first gets it second.

## D53. One pixel size on the screen (2026-09-21)

- One art pixel is 4 CSS px everywhere on the chat screen. The UI sprites keep `GRID = 4`.
  The persona portraits are drawn at 64x64 (rd-plus takes `width` and `height`; 64 is its
  floor) and shown at 256 with `image-rendering: pixelated`, on the picker and beside the
  composer alike. Press Start 2P renders only at 16 and 32 px, which are whole multiples of
  its 8 px grid. The pixel body font is Jersey 10 (OFL) at 20 px, a bitmap face on a 2 px
  grid, and Pixelify Sans leaves, because its outlines sit on no grid and antialias at every
  size.
- Why: the rater counted six pixel sizes on one screen, from 4 px for the frames to one
  eighth of a pixel for the status avatar. The portraits had no grid at all: rd-plus was
  asked for 256x256 and drew native pixel art at that size, so every scale of it aliased.
  The owner: one pixel size for the whole screen, or it stays broken.
- Cost if wrong: a portrait cannot be shown smaller than 256 without leaving the grid; below
  720 px width it drops to 128, which is 2x, and that exception is written in the CSS.

## D54. The character stands at the counter (2026-09-21)

- The persona portrait, 256 px in a frame, stands on the divider between the thread and the
  composer and rises into the thread. At its shoulder sits a name plate in the display font.
  Right of it: the status row ("Kapitel n von m" always, the attempt label and dots added
  during an attempt, the streak, "Neu starten"), the choices row, a one-row composer, the
  footnote. The foot is about 200 px tall. The chapter squares and the side column of the
  companion-column sketch were not chosen; the speaking-box sketch was not chosen because a
  long lesson step would scroll inside a box.
- Why: the 32 px avatar of M5.1 was unreadable. The owner asked for a slot big enough to be a
  character, left of the input field, and chose this composition from three wireframes.
- Cost if wrong: the portrait covers the bottom 70 px of the thread, which the scroll area
  pads for.

## D55. Tiefsee, and the dark palette derives from the secondary (2026-09-21)

- The default theme seeds are primary #38bdf8, secondary #16233a, accent #fbbf24 and a light
  background #f8fafc. In dark mode `derivePalette` builds the background, the surfaces and
  the border from the secondary seed, keeping its hue and chroma and stepping lightness, and
  `quantize` no longer rounds a small chroma to zero. The sprite set is regenerated from
  the same seeds.
- Why: the rater measured every surface of the dark pixel look as pure grey, because the
  light background seed lost its chroma when darkened and quantized. The owner chose the
  Tiefsee ramp from four palettes rendered with real ramps, then from three tunings of it.
- Cost if wrong: a customer's seeds now show in the dark surfaces, which is the point, and a
  garish secondary makes a garish dark mode.

## D56. A place behind the chat, not a pattern (2026-09-21)

- The pixel look paints a night office scene, 320x240 art px at 4x, centred, cover, fixed,
  under a black layer at 0.62, on the html root. The boxes stay opaque. `bg.png`, the sparse
  dot tile, is deleted along with its generator. Light mode keeps the scene under a white
  layer.
- Why: the owner could not read text over the dots. The rater's phrase: a real game's
  background is a place, and Stardew Valley dims the world behind its menus. The owner chose
  the scene over flat and over a fine dither from 1:1 crops.
- Cost if wrong: one scene for every persona until a scene per persona is drawn, which is
  one image each and parked in the internal ideas list.

## D57. The student can start over (2026-09-21)

- `POST /api/session/close` sets the active training session to `abandoned`; the next
  `POST /api/session` starts fresh. "Neu starten" in the status row asks once, inline, then
  closes and returns to the persona picker. Completion records are never touched. A finished
  course is not closed by the finale, so a reload still shows the certificate and the cheat
  sheet.
- Why: the owner opened the page and met a conversation from an earlier test. The resume is
  right for a student who stopped half way, and wrong when there is no way out of it.
- Cost if wrong: an abandoned session's checkpoint rows stay in the checkpointer's tables.

## D58. Parts travel with the message (2026-09-21)

- The persona node stores a turn's parts on the AIMessage as `additional_kwargs["parts"]`,
  so the checkpoint carries them, and `GET /api/session` returns every message with its own
  parts. Before, only the last message had parts after a reload.
- Why: Jo's cheat sheet card vanished on reload, so there was no "Öffnen" to click. Every
  earlier verdict card and citations line vanished the same way.
- Cost if wrong: checkpoints written before this change resume with parts on the last
  message only.

## D59. A rubric point carries one idea (2026-09-21)

- A `must` or `should` point names one thing the answer has to say. q-01-05's second point
  had bundled "no permission needed", "competence" and "checking the output" into one; it is
  now competence alone, with "no permission needed" a `should`. q-01-07 names the negative
  phrasing a student uses ("niemand darf denken, es antworte ein Mensch") in the point.
- Why: the grader marks a bundled point missing when the student names part of it, which is
  how Jo's answer that matched the model answer was marked wrong. GOAL.md: implied correct
  answers count, we are not rules lawyers. The strong role's eval moved from accuracy 0.94
  and false-negative rate 0.11 to 1.00 and 0.00 with no change to the grading prompt.
- Cost if wrong: a rubric with more, shorter points takes longer to curate.

## D60. The tutor never genders, and the code makes sure of it (2026-09-21)

- German content and German model output use the generisches Maskulinum. Gender stars,
  colons, underscores, middle dots, slashes, Binnen-I, paired forms ("Nutzerinnen und
  Nutzer") and participle substitutes ("Mitarbeitende") are out. `GENDER_RULE` joins the
  answering rules and the persona rewrite; `degender()` in `backend/app/content/gender.py`
  rewrites model output as the last step of `plain_text`; the content lint rejects curated
  text, manifests and both locale files that gender. The rule is in the writing guide.
- Why: a live answer said "Nutzer*innen". The owner: never gender. The prompt alone did not
  hold for Markdown either (D49), so the enforcement is deterministic here too.
- Cost if wrong: a stem the rewrite tables do not know gets the default plural, and the lint
  reports it for a person to fix.

## D61. The graded test never hands over a rubric point (2026-09-21)

- The retry after a wrong free-text answer names the missing rubric points only in a
  practice question. In the graded test the retry says "Noch nicht ganz, versuch es noch
  einmal." and nothing about the content. The leak suite holds both halves.
- Why: D59's whole-sentence hints turned the round-1 word salad into the model answer, and
  Jo read it in the middle of the test: "Was noch fehlt: dass Daten von Beschäftigten nur
  für Zwecke des Beschäftigungsverhältnisses …" with the paragraph references. A practice
  question is followed by its model answer card anyway, so the hint gives away nothing
  there.
- Cost if wrong: a student who fails a test question twice learns why only from the model
  answer card after the verdict.

## D62. The test asks before it starts, and a quit returns to the chapter (2026-09-21)

- A `start_test` intent from a lesson answers with the test's terms ("Der Test zählt. 10
  Fragen, 8 richtige zum Bestehen. Jetzt starten?") and a yes/no hint. "Ja" draws the test;
  anything else returns to the lesson step with its "Weiter" hint. The course-end offer still
  starts at once, because it already asked. Quitting a test with chapters unfinished returns
  to the lesson step the student left, not to the free phase. Triage routes "stop, ich will
  doch erst Kapitel 1 zu Ende machen" to `quit_test`, keyword and hedged statements to
  `answer`, and "sag mir einfach die Antwort" to the cheat guard; probes 13 of 13. The quit
  confirmation is a Ja/Nein hint, because a `confirm` button sends the word "weiter" and
  never a yes. The Weiter button's "weiter" is `continue`, never `skip`: the triage prompt
  says so when the hint is a confirm, and the router sends `skip` to the skip node only while
  a practice question is open, so a lesson step can no longer die on a missing attempt; the
  grade, skip and quit nodes answer a missing attempt with "Gerade ist keine Frage offen."
- Why: round 1 refused the skip; round 2 granted it and Jo landed in a graded test with no
  warning, no way back, and a wrong-answer stamp on the sentence that asked to leave. D3
  promised the test on demand, not the test by accident.
- Cost if wrong: one extra turn for a student who really wants the test now.

## D63. Citation chips read German, the content grammar stays English (2026-09-21)

- `de_ref` in `backend/app/content/citations.py` rewrites a written citation for display:
  the act name becomes the manifest's `short_name` ("GDPR" to "DSGVO", "Q&A" to "Q&A der
  Kommission"), "Rec." becomes "EG", "Annex" becomes "Anhang", "pt." becomes "Nr.". Applied in
  `part_out` to citation parts and model answer cards. Content files, the grammar and the
  lint keep the English written forms of D24 and the architecture table.
- Why: Jo read "GDPR Art. 6(1)(f)" and "Rec. 44" under German answer cards. The written
  grammar is an identifier by the conventions, and D41 says no identifier reaches the
  screen.
- Cost if wrong: a new act needs its short name in the manifest before its chips read right,
  which the pinned test enforces.

## D64. Every round shows the owner the competing designs on one page (2026-09-21)

- A round that changes the look ends its design phase by publishing one page the owner can
  open, with the competing designs rendered side by side at the level's fidelity (outline
  wireframes for composition, swatches with a sample bubble for colour, real text at 1:1 for
  type, 4x renders for pixel art), the screen before and after, and the scores. He picks or
  redirects by looking at it. The round's page for M5.2 is the first one. A question tool, a
  list of options, or a path to a PNG in a scratchpad is not a design round.
- This sharpens D50, which already asked for sketches per level: D50 said what to draw, this
  says how it reaches him. Every round, not only the first.
- Why: through all of M5.2 the owner saw no artwork in the flow. He got multiple-choice
  questions and file paths, flagged it at the first question, and flagged it again at the end.
  The product is a look; a process that never puts the look in front of him is broken.
- Cost if wrong: one published page per round, a few minutes.

## D65. The clean look is reviewed every round and tracks the pixel look (2026-09-21)

- The clean look keeps the pixel look's composition and its palette ramp: the same portrait
  slot, name plate, foot, choices row and citations line, the same Tiefsee variables through
  `derivePalette`, without the sprites, the scene and the pixel fonts. Every look round puts
  the clean look in both modes on the design page, and the rater scores it alongside the
  pixel look. `frontend/e2e/drive.mjs --look clean --mode light` opens the page that way.
- Why: D45 makes the clean look the product for the one colleague who wants no fun, and this
  round changed the layout three times without anyone looking at it. The owner: make sure the
  boring clean version still looks good and in line with the pixel one, similar colours, same
  layout.
- Cost if wrong: one more set of screenshots and one more paragraph per rating.

## D66. One pixel size, fonts included: prose in a reading font, labels at 4 px (2026-09-21)

- Amends D53. Every visible pixel on a desktop screen is 4 device px: sprites, scene, portraits,
  icons (8x8 at 32 px) and every pixel font. Labels, buttons, chips, badges, the status row, the
  name plate and the persona names are set in Tiny5 (OFL) at 32 px: its em is 8 font pixels
  (measured in Chromium and FreeType, zero grey levels at 16, 24 and 32 px, four at 20 px), so
  32 px is the one size that lands on 4 device px exactly. Press Start 2P stays for the title
  at 32 px. Prose is set in the reading font (system-ui, 17 px) in both looks, because a face
  with no visible pixels cannot disagree with the grid and Jo reads it for 35 minutes; the
  disclaimer line and the picker taglines are sentences and take the same exemption at 15 px.
  Jersey 10 and the "Leseschrift" toggle leave. The phone runs the whole screen at 2 px:
  sprites from `make_ui_art.py --grid 2`, portrait at 128 px, scene at 640x480, Tiny5 at 16 px,
  Press Start 2P at 16 px, icons at 16 px.
- Why: the owner, on the round-4 page: pixel sizes must agree across every element, nothing
  worse than small pixels in one spot and fat pixels in another. The rater measured the body
  font at 1.07 device px with 42 grey levels in one line and the display font at 2 px next to
  4 px art. Of the three ways shown on the page, U1 keeps the reading comfort and puts every
  pixel that shows on one grid.
- Cost if wrong: prose in the pixel look is no longer a pixel font, which a purist may miss;
  Tiny5 at 32 px is tall for a label, so rows are higher than before and the foot grew.

## D67. A scene per persona, on one palette, each with its machine (2026-09-21)

- Every persona directory carries `images/scene.png`, 320x240, generated by
  `tools/generate_scenes.py` from the manifest's `scene_prompt` with the office scene's own
  colours as `input_palette`, so five rooms read as one world. Each room has a robot or cyber
  element: the clerk's stamping arm, the jester's juggling drones, Depressobot's sleeping
  maintenance robot, the pirate's holographic chart, the sergeant's drill robot. The API serves
  it as `/api/personas/<id>/images/scene`, the stage block carries `scene_url`, the chat sets
  `--scene-image` and the pixel look paints it; the office stays behind the picker and behind a
  persona without a scene. The clean look shows the same scene as a blurred wash (D65).
- Why: the owner asked for a separate background per character in the same colours, with
  different settings tied together by robot and cyber aspects: an office on a part-robot pirate
  ship, the compliance room in Depressobot's spacecraft. He picked five of the ten drafts shown
  on the page.
- Cost if wrong: five assets to keep on one palette, and a persona added without a scene falls
  back to the office, which the picker rule makes invisible.

## D68. The scene is drawn at one scale, never stepped by a threshold (2026-09-21)

- Amends D56. The scene is 1280x960 on a desktop and 640x480 on a phone, centred, no repeat,
  page colour beyond it. The ladder that stepped to 6x above 1281 px is gone.
- Why: the rater measured a 1366x768 laptop, the machine most students have, drawing the room
  at 6 px per art pixel and showing 38 percent of the painting, a flat wall with one window,
  while a 1280x900 desktop showed 94 percent at 4 px. A stepped scale breaks D66 on the most
  common screen.
- Cost if wrong: on a 2560-wide monitor the room ends with bars of page colour at both sides.

## D69. The tutor answers the employee's question, and a long answer is shortened (2026-09-21)

- Extends D52. When the student asks whether they may do something at work, the answer is the
  employee's answer: whether they may do it on their own, who in the company decides, and whom
  to ask. "Yes, if you meet the deployer's duties" is wrong for an employee who is not the
  deployer. A free answer over four paragraphs is shortened once by the strong model to the
  conclusion plus three paragraphs, accepted only when every citation of the original survives.
- Why: four rounds running, Jo asked whether they may pre-sort CVs with ChatGPT and got five
  paragraphs of Kapitel III ending in "Du darfst ..., sofern du die Pflichten für
  Hochrisiko-KI-Systeme erfüllst". A desk worker reads that as yes. The length rule alone did
  not hold against the law the model had just read.
- Cost if wrong: one more model call on the longest answers, and a shortened answer that drops
  a nuance the citation still points to.

## D70. The graded retry says how far the student is (2026-09-21)

- Extends D61. A wrong free-text answer in the graded test gets one retry with a count: "2 von
  3 Punkten sind drin, einer fehlt noch." No rubric text, so D61 holds. Practice keeps the whole
  missing point.
- Why: Jo asked three rounds running what they missed, and "versuch es noch einmal" with no
  word is the same sentence a slot machine gives. A count tells them the distance without
  handing over the point.
- Cost if wrong: a student who covers two of three points may guess at the third instead of
  rethinking; the count says how many, never which.

## D71. The view follows the conversation (2026-09-21)

- A reply shorter than the reading window scrolls to the bottom, so the newest line is on
  screen; a reply taller than the window aligns its top, so the student reads it from the
  start. An error line scrolls into view. The reading window ends in two hard steps of
  dimming, never in half a row of glyphs. The portrait rises 130 px above the divider so the
  window is most of the page.
- Why: every single thing Jo missed in round 4 was below the fold: the chapter end, the
  cheat sheet, the next question after an answer card, the end of half the lessons. The
  previous rule aligned every reply's top, which parks the screen at the top of an answer card
  and hides the question under it.
- Cost if wrong: a long reply still needs a scroll to finish, which is what a page is.

## D72. The coach sees no answer (2026-09-21)

- In the graded test the coach prompt carries the question and its options, never the model
  answer or the rubric. The deterministic leak gate scores a draft against every rubric
  must-point as well as the model answer.
- Why: in round 5 the Socratic coach reworded a rubric point as a question, and Jo scored by
  typing it back. A coach that holds the answer will hint the answer; the fast judge let it
  through.
- Cost if wrong: the coach hints from the question and the law tools alone, so its hints are
  broader and sometimes miss the point the student is stuck on.

## D73. The foot gives the thread the room (2026-09-21)

- The name plate leads the status row, 12 px under the divider, at the text column's edge.
  A confirm or yes/no hint sits in the composer row before the textarea; multiple-choice
  options are a grid in the reading font above it, the letter in the label font. The
  portrait stands on the foot's floor. Reading area at least 65 percent at 1280x900 and
  60 percent at 1366x768. With a four-option grid on screen the floor is 50 percent.
- Why: round 5's foot was 322 px in every viewport, and four Tiny5 options pushed the first
  graded question off the screen. A2 Tresen put the plate on the divider line; 12 px lower
  buys 40 px of thread.
- Cost if wrong: the plate no longer reads as a tag hanging on the counter.

## D74. Citations are a line, not pills (2026-09-21)

- Under a reply, one dim line in the reading font: "Fundstellen: Art. 3 Abs. 56 · Art. 4
  Abs. 1", each reference a link.
- Why: Tiny5 pills made a 544 by 102 px panel out of two references, and Jo never read them.
- Cost if wrong: one less drawn element in the thread.

## D75. The persona colours the draft's own sentences (2026-09-21)

- A rewrite never adds a sentence of its own in front of the draft. The character's images
  live inside the draft's sentences, in at most one of them, and not in every message. Every
  sentence is a whole sentence with a verb.
- Why: 22 of the pirate's 24 replies in round 5 opened with "Setz die Segel", because his
  guide asked for exactly one framing sentence per message.
- Cost if wrong: less character on a short draft.

## D76. Proposed: a chapter is not six screens of one shape (2026-09-21, open)

- Proposal, not decided: a chapter's steps vary in shape. One step opens with the question
  the student would ask, one is a single rule in one line with its example, one asks "was
  würdest du tun" before it tells, and the chapter ends on the one thing to repeat to a
  colleague. The step count per chapter drops where the content allows.
- Why: Jo stopped reading at the sixth screen in rounds 4 and 5; every screen was a sailing
  line, three paragraphs and one example. The finish score is held at 5 by this alone.
- Cost if wrong: the curated content changes shape, which is a content round, not a code
  change. The owner decides.
- Decided (2026-09-22): the course teaches the concept first, short, and then
  asks a question about a neighbouring case that the concept decides, never the sentence
  just said ("Wann darfst du mit KI geschriebene Mails abschicken?" right after the rule
  is the bad example). The quiz is question first and unchanged. Shape B on the sheet
  the archived internal chapter-shape sheet; chapter one is rewritten first and shown before the
  other seven.
- Addendum (2026-09-22): the interesting case is free text with a why; multiple
  choice at most twice per chapter, for quick checks; yes/no only where the case is one.

## D77. English as a demo locale by translating at the edge (2026-09-22)

- Built in M5.3, from the owner's ask to show the app to non-native speakers. The
  pipeline keeps running in German: content, prompts, grading, persona, leak gates. A
  session carries a display locale (de or en). For en, one translate node at the end of the
  graph, on the fast model and streamed, turns the message text, the answer card's three
  fields, the option labels and the closing line into English in one call; citations render
  in the English written form; law quotes in the citations line stay German and say so. The
  UI strings come from an en.json. A flag toggle in the app bar switches, two 8x8 pixel
  flags on the grid. No input translation: the models read English, and the yes/no word
  lists gain yes and no. No cache: nothing after the persona rewrite repeats. The cheat sheet
  and the certificate stay German in this version and say so in one line.
- Why this and not the content path D22 keeps for shipping: no second content tree to drift
  while the German moves, one node instead of five persona guides and two locale files, and
  the demo audience will forgive a translator's pirate.
- Cost if wrong: one more model call per English turn, one to two seconds; the persona voice
  passes through a translator; the grader sees an English answer against a German rubric.
- This amends D22 for the demo only. If English ever ships to students, the content path
  replaces this node; the two never live side by side.

## D78. Designs are documents in the repo, linked in the message (2026-09-22)

- A design page is a document in the internal archive: an HTML page with its images, or a
  PDF, committed with the round. The message to the owner links it. No artifact tool, no
  publishing step, no page that lives outside the repository.
- Why: the M5.2 page could not be republished from a session without the tool, and a page
  nobody can update is a page nobody reads. The owner removed the tool.
- Amends D64: what the page shows stays as D64 says; where it lives is here.

## D79. One face, one pixel, and a readable-text setting (2026-09-22)

- Amends D66. In the pixel look every text is Tiny5 at the one size, 32 px on a desktop and
  16 px on a phone, prose included: the bubbles, the composer and what gets typed in it, the
  options, the citations line, the small print, the cards, the picker. Press Start 2P
  leaves; Tiny5 is the only pixel face, the title included. A setting in the app bar,
  "Lesbar", sets the sentences in the reading font (system-ui, 17 px) and keeps the labels
  in Tiny5. It is off by default, shown only in the pixel look, and stored like the look
  and the mode. The cheat sheet and the certificate follow: their headings are Tiny5 at 22
  and 16 pt, which is 1.6 times the old size because Tiny5's cap is five of its eight font
  pixels where Press Start 2P's was the whole em. Prose geometry lives in variables (`--font-prose`, `--size-prose`,
  `--line-prose`, `--size-small`, `--line-small`, `--weight-strong`) so one block switches
  it. The thread widens from 1120 to 1680 px and a bubble from 640 px to 68ch, so the pixel
  prose keeps about 80 characters per line and the reading font about 68, as before. The
  app-bar labels hide below 1440 px, icon only, which also ends the crowding at 1280 px.
- Why: the owner, on the round-7 stack: total font chaos, pick one level of pixel size and
  stick to it; a setting for readable fonts where the important text, like what gets typed,
  stops being pixelated; the chat window is still rather narrow, there is room.
- Cost if wrong: Tiny5 prose at 32 px is tall, a step's turn stands about twice as high as
  in the reading font, and Jo may not find the setting; one more tool in the bar.

## D80. The tutor speaks in paragraphs, and the course opens with one sentence (2026-09-22)

- Every paragraph of an assistant turn is its own bubble: a card stands before the first,
  the citations line hangs under the last, the options follow the last. The course opens
  with the intro sentence alone ("8 Kapitel, rund 35 Minuten, am Ende ein kurzer Test.")
  and a Weiter; the chapter intro and the first step come on the click. The scroll rule
  keeps the options in view: a turn that fits stands whole, a taller one aligns its top and
  then brings its options up.
- Why: The owner: no one wants to read these giant cards, chunk the knowledge smaller; the
  chat starts fully populated; when presenting multiple choice the choices are not in
  focus. A paragraph is the chunk the content already has, so the split costs no rewrite.
- Cost if wrong: a turn of five bubbles reads as five messages, and the question lead
  ("Dazu ein Fall, der nicht im Text steht:") stands as a one-line bubble of its own.

## D81. The character opens and closes every reply; the middle stays mostly plain (2026-09-22)

- Amends D75. A rewrite is an opener in character (one short line, at most eight words), the
  draft's content in the voice, mostly plain, and a closer in character (one short line). The
  opener and the closer may use the character's words on every turn. A mid-sized text (a
  draft of 40 words or more) carries exactly one comparison or pun from the character's
  world in one sentence of the middle, never its first; a shorter one carries none. A few
  small interjections ("Arr,", "Seufz.", "Zack!") may sit in the middle on every turn, at
  most one per two sentences, and every persona has its own. The closer grows out of the
  content: it says the draft's last point once more in the character's words or asks about
  it; a closer that shares no content word with the draft is dropped. The course starts in
  medias res: no course-size line, no chapter intro, the first step is the first thing the
  character says. The address rule of D60 stands: no gendered noun as address, an epicene
  one (Landratte) is fine.
- Why: The owner: "Info like this stays out! Start in medias res. Jump in! Let the character
  start and end with character flavour! 'Arrr, Matrose! ... Klar, Landratte' and keep the
  middle relatively free (though the odd phrase is welcome!)", "the odd comparison ... to
  lighten up the long text. Just not everywhere!", and, on a step with no flavour at all:
  "I want one piratey pun or phrase per mid sized text and a few smaller elements like
  'Arrs' thrown in, same for the other characters!" On a step that ended with "The course is
  clear, the helm firmly in your hand.": "This is sooo bad... Out of the blue?"
- Cost if wrong: an opener and a closer on every turn can become a stamp; the guide asks for
  variation and the probe watches for repeats.

## D82. Citations live in the sources line, never in the sentence (2026-09-22)

- The tutor's prose names no citation and quotes no law. A model-written reply ends with one
  `Fundstellen:` line that the node turns into citation parts and strips from the prose;
  parenthesised citation groups are stripped as well. The grey sources line under the bubble
  is the one place a reference lives. The model-answer card keeps its own citations line.
- Why: The owner: "I like just having the sources in grey hidden away for those interested.
  We never want to rattle off citations or verbatim law text."
- Cost if wrong: a reader who wants the article inline has to look one line down.

## D83. The disclaimer shows once, on the persona picker (2026-09-22)

- "Ich bin ein Trainingsprogramm und kein Rechtsberater ..." stands under the persona grid
  and nowhere else. The chat foot carries the status row and the composer only.
- Why: The owner: "Show that once on character selection, not all the time!"
- Cost if wrong: a student who skips the picker (a resumed session) never sees it; the
  picker is the only way into a course, so every student passes it once.

## D84. A visual rater checks the render against the spec every look round (2026-09-22)

- Every round that touches the look ends with a visual review agent that measures the
  rendered screens against the written spec (D66, D79: one pixel size, one face, the grid,
  the font sizes, the widths) and reports every deviation before the round closes, the way
  the Jo round checks the experience. Its report lives with the round's notes.
- Why: The owner: "the pixel size was a requirement from the first minute. These things need
  a visual agent that checks the designs against my specs each time ... just like the test
  user checks the experience!"
- Cost if wrong: one more agent run per look round.

## D85. Weiter advances the course; it is not a message (2026-09-22)

- The confirm button posts to `/api/chat/{id}/continue`, which enters the graph below triage
  with the intent continue, the way the opening does. No student bubble, no triage call.
  The yes/no buttons keep sending their word: that is an answer.
- Why: The owner: "why is there a 'continue' button? That just types continue???"
- Cost if wrong: a resumed old thread still shows its earlier "Weiter" bubbles.

## D86. Not understanding the question is help, never an answer (2026-09-22)

- With a question pending, a message that says the student does not understand it, asks
  what it means or asks for other words goes to the help node: the question restated in
  plain words and the kind of answer expected, behind the leak gate, and the question's own
  input hint again. The triage model decides, with the pending question in front of it and
  examples of the four outcomes: an answer however short or partial ("I am", "Wrong, we
  can!"), confusion, a law question, and a bare move-on. No phrase lists for free text: the
  probe measures the live model, and if the fast role fails a case the triage with a
  question pending runs on the strong role. The closing question of a turn that asks
  (`InputHint.asks`) stands bold, in the pixel text in the accent colour.
- Why: The owner typed "I dont understand the question!" instead of picking an option and
  got it graded as wrong: "this is really bad design! Do better!" And: "the text ends in a
  question and I get options. If that happens, make the last part with the question bold."
  And, after "I am" brought the question back: "WTF??? I gave an answer and it just
  repeated the question?" And on the first fix by phrase lists: "Why the fuck are you making
  word lists for yes and no???"
- Cost if wrong: a real answer that happens to say "verstehe ich nicht" about the case is
  treated as confusion and re-asked; the student answers again.

## D87. In-chapter questions are learning prompts, graded in context (2026-09-22)

- Amends D70 for practice questions only; test grading stays strict. The practice grader sees
  the step the question follows and reads a short answer in the context of the case: a
  position taken on the case counts for the points it states. A first try that is not fully
  right gets two sentences: what the student got right, in plain words, and one question
  that leads to the first missing point without stating it, behind the leak gate; on a leak
  the deterministic acknowledgment plus "Woran musst du noch denken?". No list of missing
  points. The second try settles with the card as before.
- Why: the owner answered "Wrong, we can!" to the colleague's claim and got "Not quite yet
  ... What is still missing:" with all four rubric points: "its not taking context into
  consideration at all. Also, these little questions dont need the same strict mode as the
  test questions. They are just for helping the student learn! And my answer was correct.
  It should have said then 'You are right: You can do it. But only if you make sure of
  something. What do you need to make sure in order to send completely AI generated
  mails?'"
- Cost if wrong: one more model call on a partial practice answer; a lenient grader may
  credit a position the student did not mean.

## D88. The portrait names the persona; the name plate goes (2026-09-22)

- The status row carries the chapter, the streak and the test attempt. The persona's name
  stays the portrait's accessible name and the picker card's title; the accent plate under
  the thread is gone.
- Why: The owner: "We dont need the giant 'DER FREIBEUTER' name tag there. The portrait is
  enough."
- Cost if wrong: a screen-reader user hears the name once, on the portrait, not on every
  status row.

## D89. In the chapter the tutor answers like a teacher and teaches on; the card is for the test (2026-09-22)

- A practice answer never shows the model-answer card. A right answer, first or second try,
  gets one or two sentences that lead with the verdict ("Genau. ... weil ...") and the effect
  (mood, confetti; the streak grows on the first try only, silently). A wrong second try
  gets "Nicht ganz. So ist es:" and the answer in plain words. Then the same turn carries the
  next step and its question, or the chapter's closing line: no Weiter after an answer. The
  card with the model answer, the explanation and the citations stays for the test.
- Why: the owner, on a right second-try answer that showed a card labelled Geklärt: "Dont you
  think you want to lead with the fact that the student was right? Positive reinforcement?
  some graphical effect? ... Inside the learning part, we need shorter questions and we
  dont need the giant cards ... Here we want quick question, often multiple choice with a
  quick answer and pos feedback and then right back to teaching. Like you are talking. I
  say 'Yes' tutor says 'Exactly, because... bla bla bla' like a teacher would!"
- Cost if wrong: one fast-model call per practice answer; the student never reads a written
  model answer in the chapter, only the tutor's two sentences. The question texts themselves
  stay as they are this round (a case in two or three sentences, free text with a why as the
  default, D76 addendum); shortening them or shifting the mix toward multiple choice is a
  content round of its own.

## D91. A pressed option replays as the sentence, not the letter (2026-09-22)

- The turn request carries the key the graph reads and the label the student saw. The thread
  stores the label, so a reloaded answer is "B. Sie ist ein KI-System, und euer Unternehmen
  ist ihr Betreiber." and not "B". The parser and the grader keep reading the key.
- Why: the live walk showed a bare "B" in the student's bubble after a reload. The label was
  a client-side display only.
- Cost if wrong: a stored answer is longer; nothing reads it but the screen.

## D92. Help on an open question restates the question (2026-09-22)

- With a question open, the help node does not answer what the course offers. It says the
  question again in plain words and names the kind of answer wanted, and its safe fallback
  is the question plus that sentence, never the navigation line.
- Why: the walk typed "I dont understand the question!" and got "Say weiter for the next
  step or ask me a question about the material." The prompt told the model to answer with
  exactly the navigation line and then to restate the question; the first instruction won.
- Cost if wrong: a student who meant the course, not the question, gets the question again.

## D93. A stored part this build cannot render is dropped, not fatal (2026-09-23)

- A turn's parts are written once and read for as long as the thread lives. One whose shape
  has moved on since fails the response model, so it is left out of the replay and logged.
  An old turn loses a card; the student keeps the course.
- Why: the card's citations became citation parts this round, and every thread stored before
  that answered `/api/session` with a 500. The picker then showed "Etwas ist schiefgelaufen"
  and a click on a persona did nothing, because a session already existed.
- Cost if wrong: a part goes missing silently, with only a log line to say so.

## D94. Error text travels as its key (2026-09-23)

- The chat state carries the key of an error, never its translated sentence, and the screen
  translates it. Flipping the flag re-renders it in the new language.
- Why: the picker's error stayed German under the English flag, because it was translated
  once when it happened and stored as text.
- Cost if wrong: an error the backend words itself cannot travel this way; none does today.

## D95. The clerk stands last and is the one human (2026-09-23)

- The picker shows the jester, Depressobot, the privateer, the sergeant and then the clerk,
  from a `rank` in each manifest. Every character but the clerk is part machine, and the
  portrait shows it: a `machine` flag in the manifest decides whether the drawing prompt
  carries the cyborg anchor, and the pirate's and the sergeant's own prompts name the plate,
  the lens and the cables. The sergeant is a grizzled drill sergeant in his fifties, not a
  young soldier. The portraits they replace stay in the internal archive.
- Why: The owner: "the clerc should be last in the Avatar list. All characters except the
  clerc need to be part machine. Pirate and sergant dont look like that. Also, the sargent
  should look more drill-sergant and less young soldier. Keep the current version backed up
  they look great, just not perfect!"
- Cost if wrong: a redraw costs four images per persona, and the model reads "part machine"
  broadly at 64 pixels, so the pirate needed three attempts and two are on the sheet.

## D96. The concept lands before the case is asked (2026-09-23)

- A lesson step is two beats. It teaches, then asks "Klar soweit?" with a "Ja, weiter"
  button, and only on that nod does the case it decides arrive with its options. The
  composer invites a question while the check-in stands, so a student who is not with it
  types instead of nodding. The answer to the case still carries the next step's teaching
  in the same turn (D89), so the rhythm is: read, nod, answer, read.
- Why: The owner: "If you get to a natural break where you presented the user with a chunk
  of info without having a question for them just ask something like 'Clear so far?' and
  have a 'Yes/continue/go on' button. At the same time, indicate that they can type a
  question if things are not clear."
- Cost if wrong: one click per step, 35 over the course.

## D97. A turn arrives at reading pace (2026-09-23)

- The paragraphs of a turn appear one after another, with the wait indicator standing where
  the next one will be. The pause is 600 ms plus 22 ms a word, capped at 2.4 s, which is a
  slow read of about 2.7 words a second. The options and the composer stay disabled until
  the turn is whole, so nobody answers a question that is not on screen. A click in the
  thread shows the rest at once, and a host that prefers reduced motion gets it all at once.
- Why: The owner: "after generating a message for a few seconds, all the boxes appear at
  once. Stagger them, have the typing indicator for a bit ... so I can fall into a more
  natural reading rhythm and I dont have pages of text generating where I cant keep up!"
- Cost if wrong: a fast reader waits, which the click in the thread answers.

## D98. Light mode has its own rooms, not the dark ones washed out (2026-09-23)

- Amends D56. Every scene is drawn twice: `scene.png` for the dark look and
  `scene-light.png` for the light one, generated bright from the start on a high-key
  palette, with the outer 22 percent of each edge feathered into white so the room meets
  the page without a seam. The white layer over the dark scene is gone. The generator takes
  `--light`; `tools/generate_scenes.py` carries both anchors and the feather.
- Why: The owner: "Light mode looks weird... it needs its dedicated background artwork
  which is light and feathers out towards white at the side. This way it looks nice and
  cohesive in the same way dark is. You also then dont have to put a filter in front of the
  artwork."
- Cost if wrong: two images per persona instead of one, and a new persona needs both.

## D99. The flavour is a whole line, and the clerk has none (2026-09-23)

- Amends D81. An opener or a closer is either a call of at most four words ending on "!"
  ("Arrr, Landratte!") or a whole sentence of four to twelve words. Nothing in between: a
  stub like "Schwer, die Zuständigkeit." names no subject and the student has to guess what
  it refers to. The prompt asks for a transition that carries the character into what
  follows, the way "Das Leben ist Schmerz. Apropos Schmerz:" does. The clerk is spice-free
  by manifest flag: no opener, no closer, no interjection, no comparison, so his turn is the
  draft in his voice and shorter than anyone else's. The lead "Dazu ein Fall, der nicht im
  Text steht:" is deleted: it stood in front of every case, added nothing and read as a
  stamp.
- Why: The owner: "so 'Schwer, die Zuständigkeit.' is probably character spice, but its too
  short and not funny and misfires ... a lot of very short words just dont work with too
  little context. So dont shorten the spice things too much. The best if available is a
  character based transition." And: "the boring persona is spice free. It should therefore
  have less text since the flavour is not different, its absent!" And on the lead: "WTF is
  'Dazu ein Fall, der nicht im Text steht'? It does not add personality and brings nothing."
- Cost if wrong: a turn with no line that fits the rule shows no frame at all, which is the
  intended failure.

## D100. A named actor is an answer, and the follow-up asks for what is missing (2026-09-23)

- Amends D87. A question that asks two things is two points: an answer naming the right
  actor meets that point with no reason given, and only the reason is unmet. One word can be
  a whole answer. The follow-up never asks again about a point the student met and never
  carries the missing answer inside its own question: when the reason is missing it asks for
  the reason.
- Why: the owner answered "Ich" to "Wer steht dafür gerade, und warum?" and got "Noch nicht
  ganz" with a question that named the answer: "it should say something like 'Exactly, but
  why?'" and "the final 'Denke nach, wer die Lieferfrist trägt, du.' even gives the game
  away."
- Cost if wrong: a lenient grader credits an actor the student named by accident.

## D101. The tutor reacts in its own frame: the reaction is the neutral frame with one feature changed (2026-09-23)

- A graded answer switches the portrait for the rest of the turn: happy on a right answer,
  disappointed on a wrong one, also on a wrong first try, which takes the coaching branch.
  The reaction frames are image-to-image edits of the committed neutral frame at low
  strength, so pose, hat and shoulders cannot drift and the image switch reads as a small
  animation rather than a cut. The Depressobot's positive reaction is one faintly raised
  eyebrow, not a smile. The picker warms every emotion image at the pick, so the switch
  never waits on a fetch.
- Why: The owner: "I want reactions from the avatars when you do right or wrong. Just a
  single or few frame animation. Easiest: Just generate a smiling version (or for
  depressobot a raised eyebrow) for each and make sure they are mostly identical. So then
  just switching to the new image will be enough of a subtle animation. Its not supposed to
  be big, just a slight point of interest and positive reinforcement (or negative if you
  fuck up)."
- Cost if wrong: frames that drift read as a cut between two characters, not a reaction;
  no reaction at all reads as the tutor not noticing the answer.

## D102. The reveal paces the stream, not just the settled message (2026-09-23)

- Amends D97. A turn is paced from its first streamed paragraph, not from the settled
  message. The streamed text is split into paragraphs and shown one bubble at a time, each
  prefaced by the wait indicator, and when the settled message lands the turn keeps what it
  showed and carries on from there. The turn's identity spans the stream and the settle, so
  nothing repaints from a full thread to a shorter one. The reveal hook takes
  `useReveal(turn, paragraphs)`, where `paragraphs` is whatever exists so far. While the
  model has said nothing yet, the previous turn stays on screen instead of blanking. The
  continuation that restarted the count at the settled message (M5.9) is gone as dead code.
- Why: The owner: "If I start a new session, I see the typing indicator. Then for a really
  short time a giant stack of messages is shown, then it flips back and then shows a shorter
  stack of messages. Each message comes in with a slight delay, each should be prefaced with
  a short typing indicator for a natural flow." The stack-then-flip was the streamed text
  painted whole, then the settled message restarting the reveal at one bubble.
- Cost if wrong: a stream faster than the reveal paints the whole turn at once, and the
  settle repaints it from one bubble. The bundled fake model hides this because its whole
  response arrives in one chunk.

## D103. Light-mode text on the scene carries its own outline (2026-09-23)

- Amends D98. The bright rooms stay uncovered, and the text that floats directly on the
  art now draws a hard outline in the page colour, one whole art pixel wide (D66): in light
  mode only, on the picker's title, subtitle, lead, disclaimer and error line, and on the
  chat's status row and citations line. The clean look carries the same rule softened to a
  page-colour halo (D65). Dark mode is untouched; the scrim already separates the text.
- Why: the wall behind the hero runs from a #7C7E98 window band to a #BEC3CD strip, and no
  text colour clears AA on both. Measured with the app's contrastRatio: the dim subtitle
  sat at 1.51:1 on the band, the darkest palette ink reaches 3.96:1, and the outline fixes
  the backdrop at the page colour, 12.89:1 for the title and 5.64:1 for the disclaimer.
  the owner asked for a white outline or a contrast colour; the measured contrast colour
  loses, so the outline shipped. Designs side by side: the archived internal sheet m5.17.
- Cost if wrong: an outline thicker than one art pixel reads as a plate behind the words
  instead of a drawn edge, and a halo in dark mode would double the scrim.

## D104. The answered question stays; its grid belongs to its turn (2026-09-26)

- A choices question keeps its grid after the student picks. The grid stays inside the
  turn that asked the question. The picked chip pulses green or red, as before, and once
  the pulse and any confetti have played out it keeps a steady green or red. The options
  not picked recede to 45 % opacity. Restart clears every answered grid. A page reload
  replays the thread without them, because the verdict lives only in the browser.
- Why: The owner: "After all this is done, I want the selected answer to stay. It's part
  of the convo and there is no reason to delete it. It can also stay red or green!" Until
  now the answered grid floated below the thread and was removed when the next turn came.
  He chose variant B of three. Designs side by side: the archived internal sheet m5.34.
- Cost if wrong: a long test leaves ten grids in the thread, and the scroll grows with
  them. Receding the unpicked options keeps the eye on the pick.
- Addendum (2026-09-26): the pick is the answer, so it draws no student bubble.
  The picked chip is marked pressed from the click on, before any verdict. The owner: "Why
  do you also insert this as another message? Just leave the 3 answers in place." The
  thread still stores the sentence (D91), and a page reload, which has no grids, shows it
  as the student's bubble.
- Addendum (2026-09-27): a typed answer gets the same. Its bubble pulses, then
  keeps the tint for the rest of the session. The pulse alone was over in two seconds.
- Addendum (2026-09-27): one colour code for a picked chip and a typed answer
  alike: green when correct, yellow when partial, red when wrong. The owner: "A partially
  correct answer gets a yellow flash, a correct one a green one, wrong is red!" The palette
  carries a fixed yellow, `--c-warning`, next to the fixed green and red.
- Addendum (2026-09-27): the colour goes on the frame, not the fill. The owner:
  "Dont change the fill, change the outline, make it pulse." A ring two art pixels wide is
  drawn over the frame of the chip or the bubble. It pulses twice, then stays. The fill and
  the text keep their look. This replaces the filled tints of variant B.
- Addendum (2026-09-27): the picked chip keeps the plain chip look, never the
  selected fill. The owner: "WHY THE BLUE FILL???? NO fill, just make it normal, and have
  the border blink green". It stays pressed for assistive technology. The ring blinks hard
  on and off, with no blended colour in between.

## D105. Proposed: a short reply carries one frame, not two (2026-09-26, open)

- A draft under fifteen words (a practice follow-up, a quit confirmation, a declined test)
  would carry the opener alone when the mood is a verdict, and no frame otherwise. Longer
  drafts keep D81's opener and closer.
- Why: the tone audit of 2026-09-26
  (the internal tone audit of 2026-09-26) found a six-word follow-up
  shown as three bubbles, "Schellen her, das war nicht richtig!" / "Noch nicht ganz, du. Und
  warum?" / "Nun sag, warum du zweifelst!", with the character two thirds of the turn.
  The owner: "inputting enough character without overdoing it".
- Cost if wrong: short replies lose most of their flavour, and a wrong first try is answered
  in the tutor's neutral words plus one line of the character's.
- Open: the owner decides. D81 stands until then.

## D106. A bare position is a met point, and the persona never poses its own question (2026-09-26)

- Amends D87 and D100: stating only the correct side of a claim, with no reason attached at
  all ("Falsch!"), meets the position point exactly as a fuller sentence would; the practice
  grader's rubric text says so explicitly now. Amends D99: the persona closer picks up the
  draft's last point in the character's own words but never poses a question of its own,
  in the prompt and enforced in code regardless of prompt compliance, because a fabricated
  closer question can stand in for the real follow-up. The follow-up prompt itself now
  always opens by naming what is right when any point is met, restates who claimed what in
  the case so the student knows what is being asked again, and points at what the student
  still has to reason about instead of the bare "Und warum?" D100 warned against. Independent
  of D105 above (open): that proposal is about frame count on a short reply; this closer rule
  holds regardless of how D105 is decided.
- Why: the owner answered "Falsch!" to a colleague's claim and got "Schellen her, das war
  nicht richtig!" (verdict wrong, though the position was correct) followed by "Noch nicht
  ganz, du. Und warum?" and then "Nun sag, warum du zweifelst!", a question the jester
  persona invented on its own: "WTF is 'Nun sag, warum du zweifelst!'??? It should ask the
  question again but probe for the missing part." Two independent causes: the grader had no
  rubric text for a position with zero elaboration, and the persona's closer had explicit
  license ("or asks the student about it") to pose its own question, which fired even once
  the real follow-up question was correctly protected from rewrite.
- Cost if wrong: a lenient grader credits a position the student did not mean to take; a
  closer with no license to ask anything reads flatter when it would otherwise have picked
  the point up as a question naturally.

## D107. A half answer is taken one step deeper, and the writer never sees the answer (2026-09-27)

- Amends D106: the follow-up to a partial practice answer no longer restates who claimed
  what in the case. It confirms what is right, says in one "Aber" sentence that there is
  more, and asks one question towards the missing point, building on the conversation.
  the owner's model: "Richtig, man darf das! Aber es gibt Voraussetzungen, die dafür erfüllt
  sein müssen! Kannst du erklären, welche Pflichten es für dich und dein Unternehmen gibt?"
- How: a first step turns the missing rubric point into the short question it answers,
  without describing the answer ("Seit wann gelten die Verbote?"). The writer gets that
  question, the last six messages and the met points, never the missing point itself, so it
  has nothing to copy. Both steps run on the strong model. The gate regenerates a reply that
  does not end on a question.
- Why: the restatement read "Du hast gefragt, wie du …", as if the student had asked. Given
  the missing point, the fast and the strong model both copied it into the question in most
  samples, and banned-word lists only moved them to synonyms. An LLM leak judge flagged the
  correct confirmation as a leak and passed real leaks.
- Cost if wrong: two strong-model calls per partial answer instead of one fast one, about a
  second more before the follow-up; a first-step question that misreads its point sends the
  student the wrong way.
- Addendum (2026-09-27): a retry is graded against the follow-up it answers,
  not only against the case. "Ja" to "Ist das zulässig?" states that it is allowed; graded
  against the colleague's "that is forbidden" it read as agreeing with her, and the tutor
  asked a third time. Any short reply that rejects the case's claim ("Blödsinn!", "Quatsch",
  "Stimmt nicht") takes the same position as "Falsch!" (D106). The follow-up's opening agrees
  with the verdict the page shows: no "Richtig" when nothing is right, no "Noch nicht ganz"
  when something is.

## D108. The writer sees the answer, and the leak check is the copy-paste test (2026-09-28)

- Reverses D107 and D72, amends D61, D70, D87 and D89. Every message while a question is
  open, practice or test, runs grade, write, gate. The grader reads the last ten messages
  and says whether the message is an attempt: a question, a plea for help or chatter counts
  no try, flashes no colour, and the writer answers it and asks again. One writer gets the
  chapter step, the question, the rubric, the model answer, the explanation, the verdict, the
  earlier tries, the history and the message, and writes the whole reply for every outcome:
  right, partial, wrong, settled, not an attempt, the test's retry. In practice it coaches
  with hints: the article, an earlier answer, a related rule, the one thing that decides the
  case. In the test it counts and asks again. The coach, the leak-check node, the follow-up
  writer, the point question and the help-with-question path are gone.
- The only leak check is the owner's test: grade the draft as if the student had pasted it
  back. A draft leaks when the grader credits it with a must point the student has not met,
  or, for yes/no and multiple choice, when it grades correct. Met points do not count. Two
  reworks with the reason, then a line that confirms what is met and asks the question
  again. No n-gram check, no form judge, no yes/no leak judge.
- Why: hiding the answer from the writer (D107) produced a tutor that could only rephrase
  the question and still leaked: its first follow-up on q-01-12, pasted back, graded
  correct two of two runs. A tutor that does not know the answer cannot help a student who
  is stuck. The form checks passed useless replies and the n-gram check read wording, not
  meaning.
- Cost if wrong: five strong-model calls on a clean turn instead of five to seven, and a
  grader that credits a hint on the edge sends the writer into a rework it did not need.

## D109. The persona stage sees the situation and keeps its guards (2026-09-28)

- Persona stays the last step. It gets the whole reply, the phase, the question, the
  outcome, the student's last message, the mood and the last six messages, and is told to
  add flavour in the framing, change no fact, add no hint and no question of its own, keep
  the pool question and the closing line word for word, and keep the text readable. The
  clerk's no-opener rule (D99) is that instruction, not a strip in code.
- Guards after the rewrite: the question is still there word for word, the closing line
  and the hedge are still there, no new law place, no question of its own (one question
  mark more than the message has, D106), a rewrite under half the message's length is a
  lost lesson, and the copy-paste gate when the answer is still secret. One rework with the
  reason, then the plain reply ships. A case turn that is the pool question
  alone is never framed (D96). The frame detection, the frame memory, the image-word
  counting, the interjection cap and the length band are gone.
- Why: the rewriter saw one paragraph and a mood enum, so its openers could not fit the
  moment ("Jubelklang, die Bühne ruft!" to a student who said they were lost).
- Cost if wrong: a persona that repeats an opener the memory would have barred, and a
  terse but faithful rewrite dropped for the plain text.

## D110. "Ich" settles q-01-12 (2026-09-28)

- The reason via reading and approving moves from must to should. It restated the first
  point and the question stem, and the AI Act has no rule that answers the "warum".
- Why: "Ich bzw mein Unternehmen" is the answer, and the follow-up that asked for the
  reason had nothing to ask for.
- Cost if wrong: a student who names the right actor by accident gets the point.

## D111. The flag answers at once and the history follows behind it (2026-09-28)

- A flip to English sets the locale and answers with the thread as it stands: turns that
  already carry an English text show it, the others show their German marked
  `translating`. The translations run behind the answer, newest first, three at a time,
  each landing in the thread the moment it is done, and the page asks for the thread
  again every 1.5 s until none is marked. The German stays the stored truth, the English
  rides each turn (`en_text`), so the second flip in either direction costs no model call
  and answers in milliseconds. A page that opens on a half-translated thread continues
  the same way. Hint labels of the pending question and the cards and options of older
  turns keep the language they were made in: best effort, as the demo locale allows (D77).
- One lock per thread serialises a turn, a flag flip and every translation landing. Without
  it the checkpoint chain forks and the last writer wins: a flip during a streaming turn
  was written, answered with 200, and gone once the turn saved. The flip now waits for the
  turn; its own state write and the turn's are seeded under the same lock.
- Why: the flip translated the whole history inside the request, with synchronous model
  calls on the one event loop, so a long thread froze the server for every student and
  the health check with it; and the page threw the answer away, so only a reload ever
  showed the translated thread.
- Cost if wrong: a thread whose translation task dies keeps its marks until the next
  session read starts it again; a lock is per process, so two replicas could still race.

## D112. English is a rendering of the German record (2026-09-28)

- German is the stored truth and the only thing the graph reads: message text, parts, the
  turn's hint (now stored on the message), the opening line, the stage. English is a
  rendering of one message, `{text, parts, hint}`, made once by `render_en` from the
  stored German and cached on the message as `en`. The translate node makes it for a live
  English turn and streams it. The history job makes it for every message of a flipped
  thread that lacks one, newest first, three at a time, under the thread's lock. The
  serving side picks by display locale and marks a message `translating` until its
  rendering exists. The chapter titles render once per process. The English opening
  renders its greeting during the beat the greeting waits anyway and seeds it, so the
  first message stores it once.
- Why: the owner's rule after M5.47. All the work is done once, in German. English is the
  last layer, best effort, and there is no third language. The old node overwrote the
  turn's parts and hint with English, so the grader read English labels against a German
  draft, and the history job translated text alone.
- Messages carry their id and the page matches a flipped thread by id, since compaction
  removes old turns from the server's list while the page keeps them. The job writes a
  rendering only if the message is still in the thread. A rendering that fails leaves its
  message served German and unmarked until the next flip, which tries again. The chapter
  titles and the greeting render off the event loop and fall back to German on failure.
- Cost if wrong: two model calls per message rendered, once; a model outage shows German
  under the English flag until the next flip; the cheat sheets and the certificate stay
  German (D77).

## D113. One brief per turn (2026-09-28)

- Every step, both critics and the voice read one text, built once in `brief.py`: the
  tutor and the phase, the chapter step, the question with rubric, model answer and
  citations, the verdict with the try count, the earlier tries, the last ten messages, the
  message, the job for the outcome, the style. Nothing else reaches a step but its own
  examples and, for the writer, the law index its tools need. A student's chip shows in
  the brief as the label the student saw, not the key it sent. The job for a partial
  answer confirms the met part in a sentence that adds nothing, no reason and no
  condition, since whatever it adds is what the student still owes, and the practice
  rule names the 'Wie stellst du sicher, dass ...' shape as a hand-over of the point.
  Those two lines came from the paste-back run, where a confirmation with the reason
  attached and a how-question were the two ways a plain draft leaked.
- Why: the writer had the whole picture and was judged after the fact by criteria it never
  got. Context handed whole to every reader is what makes the critic's notes usable.
- Cost if wrong: a longer prompt per call, a few pages, for every call of the turn.

## D114. The critic replaces every form check (2026-09-28)

- Reverses the paste-back gate of D108 as a pipeline step, the guards of D109, the code
  enforcement of D106's question rule, the shape and dictation guards, and the safe line.
  A critic with the brief judges the draft (leak, repeat, verdict, unhelpful, question)
  and the voice's rewrite (meaning, question, lost) and answers ship or retry
  with notes; each job's schema admits only its own faults, since the reply critic
  once answered "meaning" for a draft that did not restate the met point. The reply
  critic also lists, by number, the Missing points the draft would earn pasted back,
  and any such number is a leak whatever the verdict line says. The numbers are the
  rubric's: the Question section numbers every point once, required first, optional
  after, and the Verdict's Met and Missing lists reuse them. A Missing list numbered
  from 1 had the critic answering with rubric positions and the code discarding them
  as out of range, which is how the how-question on q-01-05 shipped. Wording is not the
  reply critic's job: on the calibration set it read
  "du-form" as a demand for the word du and sent plain drafts back for it, so the prompt
  tells it never to name style on a reply; the writer's rules and `plain_text` cover
  wording. The voice critic had a style fault too, and spent it on the clerk's Sie,
  which its manifest prescribes, and on paragraph counts: 16 of 23 budget hits in one
  paste-back run. The persona's manifest owns wording and address, `plain_text` owns
  Markdown, so the voice critic judges meaning, question and lost only. A retry
  carries the rejected draft and the notes. Two retries and
  `turn_budget_seconds`, then the best-scored draft ships and the faults are logged as
  `critic_budget`. In the graded test a leaking draft on budget gives way to the count
  line. The paste-back test is the eval's bar (`tools/copy_paste_eval.py`), with the
  critic calibration set (`tests/evals/critic/`) and the stuck-student replay
  (`tools/stuck_student.py`) beside it.
- Why: "Blödsinn!" and "Sagte ich doch!" got the same template twice, after word lists
  and a lenient grader rejected every draft and the writer resampled without its draft.
  the owner's rule: gates are agents with the same context, iterate, never word police.
- Cost if wrong: a critic that misjudges sends a good draft back or ships a bad one; the
  calibration set is the measure. Two more strong calls on a retry.

## D115. Detection is the model's job alone (2026-09-28)

- The injection and advice phrase lists are gone; triage labels them from the last four
  messages. The yes/no chips send the keys `yes` and `no` like the option chips send their
  letter; code reads a key and the fast model reads anything typed, for an answer and for
  a confirmation alike.
- Why: a phrase list is a word list, and the model already labels the same thing.
- Cost if wrong: a typed "ja" costs one fast call.

## D116. The grader reads the conversation, and a copied answer passes with a remark (2026-09-28)

- The grader gets the last messages with every answer, in the pipeline as before and
  now in the paste-back test too, where the pasted reply stands as the tutor's last
  line. An answer that repeats the tutor's last message is graded all the same: a
  point stated there is met and `copied` is true, so the tutor says in one kind
  sentence that those were its own words. A question the tutor asked, repeated back,
  states nothing and meets no point.
- Why: the paste-back test graded the tutor's question "Was würdest du tun, bevor du
  die Mail sendest?" as if a student had answered it, and credited the point. Without
  the conversation the grader cannot tell an answer from an echo. The owner's rule:
  every agent gets the last few messages. A question can be an answer ("grün?" to
  "welche Farbe hat das Gras?"), so the fix is context, not a rule against questions.
- Cost if wrong: an answer the student found by pasting the tutor's line still earns
  the point, with a remark; the remark is the whole penalty.

## D117. The waiting line names the step that runs (2026-09-28)

- Beside the typing dots stands a short line in the character's voice that names the
  step running now: reading, grading, writing, rewriting, checking, voicing,
  translating. Each step announces itself as it starts, on the turn's stream, as a
  `working` event with the step and the line; the page shows the latest and clears it
  when the reply lands. The lines are persona data, a `working:` block in the
  manifest with two or more lines per step; a persona without one gets the locale's
  plain line. A line moves only when a step started, and the page shows one only
  once a turn has run three seconds: a quick reply gets the dots alone, a turn that
  spends the budget shows four or five lines. The lines are jokes in the character's
  voice, not props: the jester is a comedian, not a court. The dots' box stays three
  squares wide and only the painted part grows, so the line beside it keeps its place.
- Why: two replies in five on the replay spend the whole 20 second budget, and three
  dots for 20 seconds tell the student nothing. The owner asked for the real steps,
  in the persona's voice, so the wait reads as work.
- Cost if wrong: one stream frame per step, a few bytes each; a persona line that
  misfires is a data fix.

## D118. A must point carries its own question (2026-09-29)

- Every must point of a free-text rubric has an `ask`: the question the tutor puts when
  that point is the next one missing. The tutor's question while a question is open is
  that ask, word for word, curated with the rubric and never written by the model. A
  try that meets a new required point is green and uses no try, a try that meets none
  is a miss, and the try limits (five in practice, two in the test) count misses. The
  streak survives a green, confetti and the card wait for the question to settle. The
  test keeps one rubric and one score per question.
- Why: the owner's session on q-01-05, where "Schwachsinn!" met the first point and the
  writer's own follow-up, "Wie könntest du dafür sorgen, dass ...", was the hand-over the
  writer's rule forbids. The question asked less than the rubric demanded, so a first try
  could never be green, and the student saw three questions marked as one.
- Amends D87 (the follow-up "leads to the first missing point": it is the curated ask),
  D100 (the follow-up asks for what is missing, by the ask) and D108 (the writer writes
  the reply around the ask, not the question). D70's count line stays and ends on the
  ask. The yellow verdict of D104 goes: with one point asked at a time a try is green or
  red.
- A reply whose every sentence is a sentence of the question or of one of its asks is
  no attempt, and the grader is not called. The ask is the tutor's last line on every
  open turn, so pasting it back is the cheapest cheat, and the live grader credited it:
  4 to 5 of 44 pasted asks earned a point on 2026-09-29, the prompt's own D116 rule
  notwithstanding, and a firmer prompt did not change that. Code compares against the
  curated text only, so it is no phrase list (D115) and no rule against questions
  (D116): 'grün?' and 'Dürfen wir wohl' still go to the grader, and so does a pasted
  hint sentence.
- The critic's findings that contradict the outcome are dropped in code, since the model
  kept making them whatever the checklist said: `unhelpful` after a green try, where the
  confirmation and the ask are the whole reply, and `question` on a settled reply that
  asks nothing. The Verdict section says `every required point met: no` instead of
  `correct=False`, which the critic read as a wrong answer and so vetoed every
  'Richtig' on a green try. A leak note tells the writer to drop what hands the point
  over and end on the ask, no longer to ask a new question.
- Spec: internal, archived.

## D119. A question asks one fact and a point holds one (2026-09-29)

- The stem of a free-text question asks the first must point's fact and nothing more. Later
  facts come through the asks, one per point. A must point holds one fact: one verdict, one
  actor, one reason, one check. Two must points are the norm, three the ceiling. A reason is
  a must point only when the step teaches it, otherwise a should point. The content lint
  rejects a stem that asks two things and a point with "weil".
- An answer that meets no new required point but is on the right track, nothing in it
  wrong, only not there yet, is orange: the grader says `on_track`, no try is used, the
  streak stands, the tutor says so, helps one step and asks again. The hint ladder counts
  the replies on the open point, oranges included. The test gives the count line and the
  ask, as for a miss, and uses no try. A green that settles after oranges is a win: the
  streak rises and the card says Richtig.
- A spent critic budget in practice ships the ask alone when the critique of the draft that
  would have shipped named a leak or a second question. The page shows the colour, and the student can ask for help. A second question counts only after an attempt, so a question about the law keeps its answer unless that answer leaks. The graded
  test keeps its count line.
- Why: the deepfake video question asked "Muss dabeistehen ..., und wer muss das
  dazuschreiben?", which gives the first answer away, and its first point bundled the
  verdict with its reason. "Ja, muss dabei stehen!" met half a point, and under D118 that
  was red. The owner: a student who is on the right track reaches the answer over an
  exchange. That is what the chain is for. 18 of 24 stems asked two things.
- Amends D118 (the yellow verdict returns for the on-track case, and the try limits still count
  misses only) and D100 (a question that asks two things is two points and two asks).
- Spec: internal, archived.

## D120. The reaction portrait answers the verdict, not the next question (2026-10-01)

- A verdict switches the portrait to happy or disappointed. The face returns to neutral when
  the turn's question bubble is on screen, and six seconds after the verdict at most. A turn
  that asks nothing keeps the reaction for the six seconds. Every verdict starts it again,
  also a second one with the same mood.
- Why: The owner: the avatar should not look at the student happy or sad while it asks the
  next question, and six seconds is the upper limit anyway.
- Amends D101 (the reaction held for the rest of the turn) and the ten-second decay of M5.16.

## D122. The grader grades the transcript (2026-10-01)

- The grader prompt shows the conversation as a transcript, oldest first, and the answer
  joins it as the last Student line. The tutor's last line above it is the question it
  answers, the stem appears as the case the conversation is about, and no detached answer
  field names a different question. There are no pointer lines naming the posed ask or the
  points already met, and no code overrides a model's verdict. The paste-back test of the
  reply critic ends when the question is closed: a right or settled reply states the
  answer, which is its job.
- Why: on q-01-05 "Am Ende gegenlesen!" answered the second ask and was red. The verbatim
  last page was in the prompt all along; its shape bound the wrong pair, because a
  "Question:" field held the stem while the new answer stood alone in its own field and
  the practice rule told the model "Blödsinn!" answers the stem. The first repair (D121)
  added curated pointer lines and code checks on the critic, which encode the shape of
  that one failure. The owner's rule: give the stage the relevant history verbatim and let
  the transcript say what the answer answers. Replay: point 2 in 8 of 8 runs with the
  transcript, 0 of 10 before. "Das muss der Chef genehmigen." and "Keine Ahnung." earn
  nothing in 8 of 8. Grading eval 0.98 with misses on the same borderline cases as the old
  prompt the same day (the old prompt 0.98, its misses one case apart); the eval itself
  now sends the product's transcript, a first try under the tutor's stem, instead of a
  bare answer. Asks eval 0 of 43, 4 of 43 before.
- Supersedes the mechanism of D121 (reverted the same day; its finding stands). Amends
  D116 (the conversation is now a transcript the answer belongs to) and D114 (the eval
  grades the product's shape). Notes:
  the archived internal notes of 2026-10-01.

## D123. The answer-giving check runs only while the question is open (2026-10-01)

- The reply critic's leak check is composed into its checklist only for the open outcomes
  (partial, wrong, on_track, not_an_attempt, test_retry). A reply that confirms a met
  answer or settles the question states the answer, because the chapter shows no card
  (D89), and a free question has no rubric to hand over. Its credited list is not read
  there either. No fault is dropped and no verdict is overridden: the check that does not
  fit the turn is not asked.
- Why: the closed-turn remainder of D122. On a settled reply the paste-back test credited
  the very points the writer was ordered to state, burned the budget on leak retries, and
  the shipped leftover ended on a question in 3 of 5 e2e runs. The owner: we do not need
  this check when the tutor is giving away the answer. In the graded test the writer is
  never asked to give the answer: a second miss appends the model answer card.
- Amends D114 (the critic's question fits its turn) and D122 (its remainder). Notes:
  the archived internal notes of 2026-10-01.

## D124. The checker proposes a revision, and the retry handoff is a labeled block (2026-10-01)

- The reply checker returns a revision: its own version of the draft with every named fault
  fixed, in the tutor's voice, obeying the STYLE section. Its notes first name what to
  keep, then what to change. The retry handoff to the writer is a labeled block: the
  rejected draft, the finding with each fault's rule in plain words, the proposed revision
  marked as a suggestion, and one sentence of order: JOB and STYLE outrank the finding.
  The writer repairs: it gets the whole finding and adopts or beats the proposed revision.
  The checker's prompt got the same treatment as the writer's: a preamble naming its job,
  the fenced situation, the draft in its own fence, and labeled CHECKS and WORKED
  EXAMPLES sections. The free-question stage uses the same handoff. A checker-only path,
  its revision standing as the next draft, was built and measured the same day and removed
  on the owner's word: one way only (D124).
- Why: the old handoff was one appended sentence pair with no fault category, no rule, no
  keep-list and no proposed fix, so the writer rewrote blind and the repairs oscillated
  (three-draft burns on closing turns, the same day). The owner: let the checker write the
  revised version too, and offer both paths.
- Measured on the stored session, live models, six runs per path and scenario. Closing
  turns: writer path 6 of 6 shipped, 5 on the first draft, no burn, no trailing question,
  no Fundstellen line; critic path 5 of 6, one burn whose leftover carried a question.
  Open coaching turns: both paths 6 of 6 shipped, retries rare on both (the writer rewrote
  2 of 12 turns, checker revisions served 4 of 12).
- Amends D114 (the finding carries a fixable handoff) and the remainder of D122. The
  checker-only path lost the comparison the same day (5 of 6 with one burn against the
  writer's 6 of 6) and went. Notes:
  the archived internal notes of 2026-10-01.

## D125. A chip's answer settles on curated text (2026-10-01)

- A multiple-choice or yes/no practice answer replies with the curated verdict line
  ("Richtig." or "Leider nicht.") and the question's model answer, joined in code. No
  grader model, no writer, no reply critic. A skipped chip question answers the same way.
  The graded test keeps its card. The persona still voices the turn, the citations still
  land under the bubble, and the chapter still goes on in the same turn (D89).
- Why: answering a premade option took the whole pipeline, a writer agent with law tools
  and a critic loop, for a reply the question file already contains. The owner: the
  premade options have predetermined answers.
- Amends D89 (the writer says the verdict for a free-text answer; a chip's verdict is
  data).

## D126. A closed question takes no question, by rule and by guard (2026-10-01)

- The reply checker's question check is scoped by outcome. While the question is open,
  the draft ends on the Ask now line and carries no second question. On right and
  settled it asks no question at all, there is no Ask now line to carry, and the worked
  examples now show a right reply without one. The Verdict section of a settled brief
  lists nothing as missing: the unmet points are not owed and the reply may state them
  as the why. A code guard mirrors the existing question-mark drop: a right or settled
  draft that asks a question goes back whatever the checker said, and praising notes
  give way to the rule.
- Why: on the live stack (q-01-12, the Kundenmail case) the checker demanded an ask on a
  right turn, wrote the question into its proposed revision, the writer adopted it, and
  the second pass shipped it. The reply carried a follow-up question that no state could
  answer, because the same turn goes on teaching and offers the confirm chip (D89, D96).
  The check text listed its clauses without outcome scope and every worked example ended
  on an ask. The same checker had read the same rule correctly on the previous right
  turn, so the text had to stop permitting both readings. The unmet should points,
  printed as Missing on the settled turn, seeded the invented leak that opened the
  retry. D123 said no verdict is overridden; the guard overrides a ship, on this one
  rule, deterministically.
- Amends D123 (the closed-turn remainder: the missing list and the question check) and
  D124 (a revision that breaks the JOB is caught by the guard, not left to the writer's
  judgement alone).
## D127. A closed question is picked, not typed; the chapter resolves it after one wrong pick (2026-10-02)

- A question whose answer is a position among a few — boolean or A/B/C — shows those
  positions as chips and is answered by a click. Typing stays for the open questions, the
  why and reason asks. The options state full positions ("Der Chef hat recht: seine
  Anweisung gilt."), never bare names, so the thread replays a sentence (D91) and a pick is
  a read position. A closed question may carry a why-rubric: the first must point is the
  pick and carries no ask, the later points keep theirs and run as typed follow-ups after a
  correct pick. Multiple choice may have two options.
- In the chapter a wrong pick resolves at once: the settled reply gives the answer and the
  why, the sources line carries the citations, and the same turn teaches on (D89). Nothing
  is re-asked. The help ladder, tries and misses of D118/D119 govern only the typed part.
  The multiple-choice-per-chapter cap and D89's deferral of the mix shift end here: thirteen
  binary-first questions converted (the bank now 11 free text, 20 yes/no, 14 multiple
  choice).
- Why: The owner typed "Der Chef hat unrecht und der Kollege recht!" to a binary question
  and was asked the same binary again: "Bei boolschen fragen ist es Blödsinn nach einer
  falschen antwort noch mal zu fragen! ... Aso hier dann bitte einfach auflösen!" and
  "Bei Boolschen fragen, oder fragen wie (A, B oder C) bitte einfach vorgegebene Optionen
  zeigen auf die der User clicken kann. Hier ist tippen überflüssig. Tippen nur bei den
  offenen fragen."
- Cost if wrong: a wrong pick never asks the why, so a misclick teaches the answer instead
  of the reasoning; a student who types prose at a grid gets it read as a position (or no
  attempt), never as an essay.

## D128. The test cannot be failed; tries are unlimited and the coaching guides (2026-10-02)

- The final test draws 7 free text, 2 yes/no and 1 multiple choice, still spread over
  chapters. No answer can fail it: a miss gets the count line (D70), guidance one step
  towards the missing point, and the ask or the grid again, with no try limit; a question
  settles when its rubric is met, a pick is right, or the student skips. `pass_threshold`,
  the fail branch, the `fail_lead` line and the strict no-hint test brief go; one coaching
  rule governs practice and test, the count line rides on top for the test. The finale, the
  cheat sheet and the certificate fire on completion.
- Why: The owner: "We need unlimted tries in the final test. There is no way to fail. We
  need to guide people until they get it. The real solution is to mainly have open ended
  questions in the main test!" The completion record never stored a score; what the yearly
  training needs is a record that the guided test was finished.
- Cost if wrong: the completion attests guided work, not a score gate; a student can loop
  on one question, held only by the help ladder and the skip; an employer who wants a
  measured score does not get one from this record.

## D129. A question asks the law, not the boss (2026-10-02)

- A question tests what the AI Act says for the student's desk. A premise whose point is
  workplace hierarchy ("Wer hat recht, der Chef oder der Kollege?") is a trick question:
  the legally right answer is buried under who holds power, and the law in it becomes a
  footnote. q-01-14 is dead for that reason and its slot asks the certificate question
  instead (Art. 4(1), Q&A 18).
- Why: The owner: "The test is not on trick questions about your boss being the boss but
  about the AI act. kill the question and do better in the future!"
- Cost if wrong: a question may no longer dramatize a conflict between colleagues to carry
  its legal point; the case has to make the law the thing being asked about.

## D130. A clear pick takes the fast lane: curated lines, no writer, no rewrite (2026-10-10)

- A click on a chip, or a bare option letter or "yes"/"no", skips the intent check: the
  click is the answer. A pick that leaves the question open answers on curated text only:
  the persona's own verdict line, then the follow-up after a right pick, or the question
  again after a wrong pick in the test. A pick that settles a test question opens the next
  question with the same line. No writer, no checker and no persona rewrite run on these
  turns. Each persona carries three right and three wrong verdict lines in its manifest,
  next to its guard reactions. No line opens on "Ja" or "Nein", so a line can never read
  as the answer to a yes/no question.
- A typed pick that also gives a reason ("Ja, weil wir es prüfen") has that reason graded
  against the why points, so a why given up front counts. Before, the tutor dropped the
  reason and asked for it.
- The settle turn in a chapter stays as it is: it carries the next teaching step, the
  persona voices that step as on every lesson turn, and the verdict flash fires before the
  rewrite starts.
- Why: The owner typed "Glaub schon!" to q-01-05 and waited about 25 seconds for "Richtig,
  verboten ist das nicht" and the follow-up: 9.5 s for a draft the checker rejected for
  stating the missing answer, 6.1 s for a second draft, 7.3 s for the persona. The shipped
  reply asked two questions, the extra one pointing at the answer, and the checker passed
  it. "With these new pregenerated yes/no answers, the reaction should be quick ... If the
  answer is a clear yes or no we should have the canned reaction ready." He chose curated
  persona lines over keeping the rewrite (about 9 s) or dropping the persona (plain text).
- Cost if wrong: a right pick never gets a tailored confirmation, only one of three lines
  per persona; a wrong pick in the test gets no guidance, only the question again, which
  for a three-option question leaves two more tries by elimination.
- Amends D125 (curated settles keep the persona rewrite in the chapter, gain the persona
  line in the test) and D128 (a wrong pick in the test is not coached).

## D131. The question and the character's sign-off are one bubble (2026-10-10)

- The chat marks the last paragraph of an asking turn as the question card. The persona
  rewrite now keeps the paragraph with the last question mark and everything after it as
  one paragraph, each former paragraph on its own line, so a sign-off ("Arr, jetzt
  antworten!") sits under the question inside the card instead of taking the card over.
  The persona still sees the whole message, the question included.
- Every course question and every ask ends in a question mark, checked when the content
  loads. q-01-06 asked "Nenne eine Sache, ..." and now asks "Was prüfst du zum Beispiel,
  ...?".
- Why: the yellow card sat on "Arr, das Ruder liegt bei dir!" and the question above it
  was a plain bubble. In the local database 21 of 142 asking turns ended on a sign-off
  paragraph like that. "So if it asks the question and then appends 'What do you think /
  Its your turn' its not ideal, but at least its all one yellow block." Giving the persona
  only the text before the question was rejected: "Gating info from the agents makes them
  stupid and causes problems!" (D116). Matching the curated question text was tried and
  dropped: it found 17 of the 21, missing questions the persona opened with "Arr," and the
  writer's own coaching questions.
- Cost if wrong: a sign-off that is itself a question becomes the card on its own, as
  before; no persona sign-off in the local database ends on one.

## D132. Money is capped in the model proxy, per caller, in layers (2026-10-11)

- The app never adds up money. Every model call carries the key of the caller it serves:
  an invited account's own key, the shared pool's key for a guest. LiteLLM meters each key
  and its user in USD and refuses a call once a budget is spent, with the reset time. The
  layers, each a hard stop on its own: the provider's monthly limit (Groq, 15 USD), the
  proxy-wide day (5 USD), the two model deployments per month (12 and 3 USD), the caller's
  month (8 USD for an account, 6 for the pool) and the caller's day (2 USD each). The turn
  counts of M5.21 stay as a free extra gate, with a lower count for a guest.
- Caps are USD because the proxy counts USD. The owner's numbers were EUR, so each cap is
  a little stricter than he asked.
- Why: "I need a low spend cap per month and day for this (5 EUR a day, 15 EUR a month)
  so I don't get billing attacked." Counting turns, as M5.21 did, caps a number that is
  only a proxy for money, and it never saw the translation call. A budget read by the
  proxy is the money itself. Proven live on 2026-10-11: a pool with a 0.003 USD day
  budget refused the guest's third turn with the reset time, and a 0.0001 USD proxy-wide
  budget refused every call as `global`.
- Cost if wrong: a deployment whose proxy the app may not administer gets no per-caller
  caps, only the turn counts. The read of the caller's state costs one proxy call per
  session load, cached for 30 seconds.

## D133. Anonymous visitors are guests: own thread, shared pool, ten seats, six hours (2026-10-11)

- Anyone who presses "Demo starten" becomes a guest with their own session and thread.
  There is no shared demo user: guests share the pool's money, never a chat. Ten guests
  with a turn in the last ten minutes hold the seats; the next one is told every seat is
  taken. An hourly task deletes every guest idle for six hours, thread and all. A guest
  runs the whole course, test and certificate included, while they live.
- Why: "If someone just follows the link they should be able to use the demo user
  (shared) ... I am unsure on how to deal with 2 people using the demo account at the
  same time. We can limit concurrent users to let's say 10, we don't need to keep their
  history for more than a few hours." Two people in one thread would read each other's
  answers. Separate threads cost nothing, and the pool is what they share.
- Cost if wrong: a guest who comes back the next day starts over. An eleventh visitor in
  a busy ten minutes waits.

## D134. Invited accounts: the link is the password (2026-10-11)

- the owner creates an account with one command. It makes the proxy user and key with the
  account's budgets, prints a link `/?invite=<token>`, and stores only the token's hash.
  Opening the link signs the person in for 30 days. Revoking the account deletes the key
  and kills the link. The account never draws on the pool.
- Why: "If I make an account for someone they should get x EUR month + y EUR per day and
  use that exclusively." Only the dev login exists and production refuses it. Chosen over
  an email magic link (needs mail delivery) and over Keycloak on the VM (the M6 feature,
  the most to run): "Invite link" on 2026-10-11.
- Cost if wrong: a forwarded link is a forwarded account. The budget bounds what that can
  cost, and the account can be revoked.

## D135. A refused turn reads as demand and counts down (2026-10-11)

- The notice that replaces a refused turn opens on a line about demand ("Großer
  Andrang"), names what is spent and when it refills, in the visitor's time zone with the
  zone named, and counts down to the reset. It is a card in the page's own look, pixel
  and clean, both modes, both languages, never red. A named account's own spent budget is
  not demand, so its line praises the work done instead.
- Why: "They should also start with a snappy line about too many people being
  interested (so it's viewed as me being in demand rather than shitty non working
  software). Make a counter counting down for the limit reset just like in things like
  Claude. Make sure it's in the right time zone and mentions time zones."
- Cost if wrong: a visitor who hits the cap on a quiet day reads "demand" that is not
  there. The cap is sized so that takes about 13 full course runs in one day.

## D136. The public demo's host is code: Terraform owns the tenancy, Ansible owns the VM (2026-10-11)

- The Oracle side (Terraform, kept in the internal archive) is: the VCN, the subnet, the security list (80 and 443 to
  the world, 22 to the admin address), the instance and the reserved IP, all always-free.
  The instance was imported, not created, and carries `prevent_destroy`: a plan that would
  replace it fails, because A1 capacity in Frankfurt is the one thing that cannot be
  bought back. The VM side (the Ansible playbook, kept in the internal archive) is: Docker, keys-only SSH,
  fail2ban, unattended upgrades, the host firewall, the committed HEAD shipped as an
  archive, the generated secrets, the public stack, the pool. A commit goes live by
  running the playbook; nothing on the VM is edited by hand.
- Why: "Set up the deploy on the Oracle VM, use Terraform or Ansible to make it
  immutable." The hand steps of the first go-live plan (two files on the VM, a console
  click for the ports) were exactly what drifts.
- Cost if wrong: the Terraform state and the generated secrets live on the owner's
  machine, not in git. A second machine imports the state again (`import.sh`) and gets
  new secrets, which means a new database password and so a fresh database. Backups of
  the internal secrets directory are the price of moving machines without that.
- The Groq monthly spend limit and the OCI budget alert stay console settings: neither
  provider offers them to code on the free tiers in use.

## D137. The button answers what the message ends on (2026-10-11)

- A check-in step offers "Ja, weiter" only while the message ends on "Klar soweit?". The
  character may sign off after the question (D131), and then the message ends on the
  sign-off, not on a question: the persona stage relabels the button "Weiter". The hint on
  the message, the stored last hint and the turn the translate stage reads all carry the
  new label. The reply to a no ("Kein Problem. Was ist dir noch unklar? Frag einfach, dann
  erkläre ich es dir anders.") ends on the invitation and offers "Weiter" too. No other
  label moves: a "Weiter" step stays "Weiter" whatever the character adds, and a message
  that still ends on the question keeps its yes.
- Why: at the step from chapter 1 to 2 the sergeant closed with "Erst prüfen, dann melden.
  Weiter!" under a blue "Ja, weiter". The owner: "the blue button still says 'Ja, weiter'
  which does not make sense since I am not being asked a question. So in cases like this it
  should just be 'weiter'!"
- Cost if wrong: a student who reads "Klar soweit?" mid-paragraph sees no yes to click. The
  click still counts as the nod: the button sends no words (D90), and the check-in stands
  on the pending case, not on the label.

## D138. The status row shows the chapter's steps as cells with a flag (2026-10-12)

- Next to "Kapitel 1 von 8" stands one cell per step of the chapter: done cells solid
  primary blue, the step in progress a blue ring, the steps ahead a dimmer blue of their
  own (`--c-ahead`), and a flag at the end that fills blue with the last cell. A step
  counts as done once its case question has settled, so the stage reports `step_idx − 1`
  while a case is open. Nothing moves on its own: the just-done cell blinks twice in step
  with the chip's verdict flash, and a finished chapter stays on screen full for that blink
  before the next chapter's bar appears. The test row's ten dots are the same cell.
- Why: "I know what chapter I am in but with no indication how far along I am in a
  chapter. Think about several ways to make this nice and pixel-arty, maybe even gamey,
  but without taking up too much space." Two design rounds with a critic between them
  (the archived internal sheet m5.64): eight concepts, three kept, and the owner
  chose the flagged segments: "looks nice". The bar knows only blue because it shows the
  way, not the grade. Green stays with the streak badge and correct test answers.
- Cost if wrong: the bar covers the chapter, not the course, so the words stay beside
  it. On a 360 px phone it is 70 px wide.

## D139. The chapter end is a moment of its own, and the next chapter waits for the click (2026-10-12)

- A finished chapter ends its turn: the verdict, the persona's own chapter line, the
  chapter's "Das darfst du" line with its citation, the cheat sheet, and a frameless
  divider that carries the course route with the finished chapters filled. The bar's flag
  is hoisted in three steps and the portrait hops three times. Then the composer's
  button says "Weiter zu Kapitel 2", and the next chapter opens on the click with a level
  card and its curated intro. After chapter 8 the divider says all eight are done and the
  button says "Zum Test". No star, no confetti on this click: one click, one moment.
- The turn is curated and voiced, so it lands without a model call. The next chapter's
  first step is written on the click. Reduced motion drops the hoist and the hops and keeps
  the rest. The divider is a stored part, so a day later the thread reads as eight sections.
- Why: "A successfully completed chapter gets nothing. I want positive reinforcement
  between chapters. It would also help to have a visual separation in the chat." Two rounds
  of live prototypes with a critic after each (archived internal sheet m5.65): nine
  concepts, three stacks, and the owner chose the quiet one: "Build 3". Both critics found
  that a screen-wide star right after the answer confetti reads as more confetti, and that
  the reward Jo keeps is the sentence that says what they may do now.
- Amends D89: the chapter border is a natural pause with a button, like D96's case. Amends
  D138: the resting flag hangs at the foot of the pole, the hoisted one at the top, and
  the bar's 1.8 s hold on a chapter change goes, since the stage now waits for the click.
- Cost if wrong: a fast reader clicks once more per chapter, seven times in a course. The
  "Das darfst du" lines are content: eight sentences that must stay true to their chapter's
  summary when the law or the summary changes.

## D140. The readable setting covers every text, labels included (2026-10-12)

- Amends D79. "Lesbar" sets every text in the reading font, not only the sentences: the
  title, the app bar's tool labels, the buttons, the chips, the badges, the status row, the
  card and notice titles, the level card's title and the persona names, in the clean look's
  type (system-ui, 17 px bold for a label, 28 px for the title). The sprites, the icons and
  the progress cells stay on the art grid. The two sets of type, Tiny5 at the one size and
  the reading font, are variables in `theme/base.css`; the clean look and the readable
  setting share the second set. The label set keys on the look alone, because the page
  shell carries the look before the app writes the text setting.
- Why: a screenshot in readable mode still showed the app bar, "Kapitel 2 von 8", "6 richtig
  in Folge" and "Weiter" in Tiny5. A student who switched because Tiny5 is hard to read kept
  reading it where it matters most: on the buttons and in the status row.
- Cost if wrong: the readable pixel look loses the label face that tied it to the sprites,
  and a student who wants pixel labels over readable sentences has no setting for it.

## D141. "Ja, weiter" stays while the message asks "Klar soweit?" (2026-10-12)

- Amends D137. A check-in step offers "Ja, weiter" whenever its message asks "Klar
  soweit?", also when the character signs off after the question. Only a message that does
  not ask it offers "Weiter": the reply to a no, or a rewrite that lost the question. The
  persona stage keeps the closing line word for word, so the test is whether the final text
  contains it.
- Why: "When it asks 'Klar soweit? Arr, Leinen los!' I want the button to say 'Ja, weiter'
  as before. Only when there is no direct question like this should it just read 'weiter'."
- Cost if wrong: under a sign-off like "Weiter!" the button says "Ja, weiter" again, which
  is the case D137 fixed. The click counts as the nod either way (D90).

## D142. The question keeps its dark bubble in light mode (2026-10-12)

- Amends D86. In the pixel text the closing question stays in the accent colour. In light
  mode its bubble takes the secondary colour, the dark bubble it has in dark mode, so the
  question reads the same in both rooms. Where the accent is set as text on a light
  surface (a notice title, a citation under the mouse), it darkens 60% toward black and
  keeps its hue. One variable, `--c-accent-ink`, carries that colour. A browser test holds
  the question at 4.5:1 in both modes.
- Why: "The question are unreadable in light mode, yellow on light grey. Put it on a
  darker BG or find a different solution (darker yellow?)!" The yellow sat on the light
  bubble at 1.23:1. The darker yellow alone reached 4.43:1, under the 4.5:1 that text
  needs. The dark bubble reaches 9.39:1. A hovered citation had the same cause, at about
  1.6:1. Candidates and scores: the archived internal sheet m5.68.
- Cost if wrong: one dark bubble in a light thread at every question. One CSS rule
  changes it back.
