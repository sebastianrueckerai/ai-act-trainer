import random

from app.content.models import Question

TEST_MIX: dict[str, int] = {"free_text": 7, "yes_no": 2, "multiple_choice": 1}


def draw_questions(questions: dict[str, Question], rng: random.Random) -> list[str]:
    drawn: list[str] = []
    for question_type, count in TEST_MIX.items():
        by_chapter: dict[str, list[str]] = {}
        for question in sorted(questions.values(), key=lambda item: item.id):
            if question.type == question_type:
                by_chapter.setdefault(question.chapter, []).append(question.id)
        chapters = sorted(by_chapter)
        rng.shuffle(chapters)
        # One id per chapter per pass over the shuffled chapters: passes spread the
        # draw across chapters before taking a second id from any one of them.
        passes = max((len(ids) for ids in by_chapter.values()), default=0)
        picks: list[str] = []
        for pass_index in range(passes):
            for chapter in chapters:
                ids = by_chapter[chapter]
                if pass_index < len(ids):
                    picks.append(ids[pass_index])
        drawn.extend(picks[:count])
    rng.shuffle(drawn)
    return drawn
