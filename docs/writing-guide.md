# Writing guide

For everything a person reads in this repo: docs, commit messages, final reports, pull
request text, UI source strings and the neutral (pre-persona) course content. This guide
sets the rules: short sentences, everyday words, active voice, one idea per paragraph, no
em dashes, no semicolons, British spelling. Cut every word the sentence survives without.
What follows only adds what is specific to this project.

## Course content

The neutral lesson text, questions, model answers and cheat sheets follow the same spirit in
every language: short sentences, everyday words, active voice, one idea per paragraph. Legal
terms keep their official wording and cite the article. The persona layer adds flavour on top
of that text at runtime and must never make it harder to understand.

A chapter step teaches one concept in two short paragraphs and one example. Its question is a
neighbouring case: a situation the step did not answer, which the concept it just taught
decides. It is never the step's own sentence with a question mark behind it. It ends in a
question mark, never on an order like "Nenne ...": the chat finds the question by it (D131).
The answer's
explanation says why in two sentences. The content lint rejects a question that repeats a
sentence of its step (D76).

A question asks the law, not the people (D129): a premise whose point is workplace
hierarchy or who holds power is a trick, and the law in it becomes a footnote.

The interesting case is free text. A question asks one fact, the first must point's: "Was
sagst du ihr?", "Wer steht dafür gerade?", "Muss dabeistehen, dass das Video erzeugt ist?".
Never two things in one stem: no "und warum?", no "und wer?". The reason, the actor and the
second check come through the asks, one per must point (D119). A must point holds one fact:
one verdict, one actor, one reason, one check. "nennt, dass X, weil Y" is two points, or a
point and a should point. Two must points are the norm, three the ceiling; a reason is a
must point only when the reason is what the step teaches, otherwise it is a should point.
A closed question is picked, not typed (D127): the options state full positions, never
bare names, and none of them names a why point's content. A closed question may carry a
why-rubric whose first must point is the pick and carries no ask, so a correct pick opens
the typed follow-up. Yes/no fits only where the case is one. A rubric's must points are in
the student's words and never legal terms, a should point may name the article, and the
model answer is one or two sentences and leads with the verdict word (Ja, Nein or the
position).

Every must point of a typed question carries an `ask`: the one question the tutor puts
when that point is the next one missing (D118); the pick point of a closed question
carries none (D127). It is du-form, ends in a question mark, names what is wanted and
carries none of the point's content. It may extend the case ("Sie fragt zurück, ...") and
it may not name the concept the point names. The first point's ask restates what the
question asks for that point, since the tutor puts it after a miss instead of the whole
case. The asks eval pastes every ask back as an answer and lets the model grade it past the
product's echo guard. An ask that earns its own point and carries its content or names its
concept is a bug in the content. The eval also lists asks the grader credits by
implication alone. Those stay, since the echo guard makes a pasted ask no attempt.

German content and German model output use the generic masculine: Nutzer, Mitarbeiter,
Betreiber, Kollegen. No gender star, colon, underscore, middle dot or slash, no capital-I form
("NutzerInnen"), no paired form ("Nutzerinnen und Nutzer"), no participle substitute
("Mitarbeitende"). `backend/app/content/gender.py` enforces the rule in code: the content lint
rejects curated text that genders, and `plain_text` rewrites a model answer that slips one
through, the way D49 enforces the ban on Markdown.
