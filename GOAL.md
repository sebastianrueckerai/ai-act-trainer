## The one thing this app is for

Jo works a desk job. Jo has no interest in law and none in regulation, and Jo did not
ask for this. Jo spends 25 minutes learning the AI Act and 10 minutes on the test, and
walks away thinking:

> "Oh wow, now I feel safer using AI. Turns out I am allowed to do a lot."

And remembers it as the coolest compliance training of their life, or at the very least
the least shitty one.

Every screen, every string and every affordance bends to that. If something serves
completeness, correctness of form or compliance theatre instead of Jo, it is wrong.
Bureaucracy on screen is a bug.

One exception, and only one: the company lawyer who hates fun picks Der Sachbearbeiter
and switches to the clean look. That turns the course dull for them alone. It is the
only place where dullness is a feature, and it is never the default, never the
fallback, and never a reason to tone anything down for everyone else.

This repo is empty; we are going to populate it. I built something similar for my last job, so this will be a better version of that, from scratch.
German firms using AI must train their employees in the AI Act yearly and record the results for compliance (so everyone must pass, like fire safety and the other compliance shit).

I want a chat interface with an agent trainer that: 1. teaches you the AI Act in an approachable format (gives you lessons, answers questions, etc.) 2. Tests your knowledge: whenever you are ready it will do a 10-question test where it asks some multiple-choice questions (or simply yes/no), but a good amount of the questions should be free text where it asks "why..." and the student must answer. We want to be fair here: implied correct answers of "they meant the right thing" are OK, we are not rules lawyers.

The teaching part should be like a chat with documents, where the tool has the complete, up-to-date AI Act and any other helpful info, as well as the conversation history (which may need to be compacted at some point).

You can also ask questions back and get coaching along the way, but the tool will never just give you the answer. It will give you context, point you to the relevant part of the law... basically help you to understand the answer in a Socratic fashion.

Correct answers should be rewarded with some cool visual effects: confetti and the like. The whole thing should be gamified. Not so much that it makes the process tedious and longer than it needs to be, but enough that we make it as fun as possible and reward success.

Also, each correct answer should yield a card with a predetermined, fully correct answer and the fully correct explanation. So if the student correctly said "Yes, because of paragraph 7" - that may be correct, but we still want to give them a "Musterlösung" (model answer) for each question.

Also, after the teaching part of the experience, we want to give them a cheat sheet summarizing the relevant stuff from the AI Act. We may also give smaller versions of that if we manage to break the material into clear chapters.

BTW: this teaching should focus on application. We don't want dry facts. We want: how is this relevant to me, what do I need to do, and then link that to the law.

We want multiple personas the student can choose (all with a cool cyborg-like avatar): a sad robot like Marvin from The Hitchhiker's Guide, a drill sergeant, a jester and a bureaucrat. The bureaucrat is the boring choice where you get the usual dry compliance experience. The others inject some fun and idiosyncratic stuff. Not a ton, never so much that it makes the content harder to understand - but enough for flavour.

Persona images will be AI-generated, of course.

For this we can apply the persona last... get the content we want to serve and then apply some spice as the last step.

We also need to gracefully handle humor, insults, cheating attempts and derailing the conversation.
In all cases, we acknowledge, make a funny comment and re-route to the task at hand.
We never lecture; if someone wants to throw profanity - fine!
For us these things are just an opportunity to show some spice with the characters.

This should be a container-native app that can live within a cloud-native setup where we easily deploy it in an AI stack with something like LiteLLM. It should have an API to persist results and especially remember who finished the course when (we need to train once a year) in a DB. We can either spin up our own DB or use the customer's. We also need to handle identity providers so users can sign in via SSO.

FE should be React. We want a cool, modern design, special effects and pictures for the different personas (game-like, maybe even give them expressions and emotions reacting to things). BE can be Node or Python - I don't care. However, I want to use LangChain. Last time I coded this I just rolled the agent framework by hand. It was a multi-stage setup where we had guards (cheating, humor, etc.) and then a series of stages for the right answer, with its own branch to make sure that a helping answer never gave away the test answer in a way that the student could just copy and paste it and have a free answer.

So part of the project goal is for me to understand LangChain and how it is used. Last time I looked at it, it seemed too wordy and had lots of boilerplate; maybe it has gotten better. But even if not: I am applying for jobs that want the skill, so this project needs to help me acquire it!

We are working on an open-source collection of AI tools (Open WebUI, LiteLLM, etc.) to kickstart small companies with self-hosting their AI needs. This is part of the puzzle. All of it should be cloud-native, containerized and friendly for bare-metal hosting.
