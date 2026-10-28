import re

from app.content.models import Question

_CHOICE_RE = re.compile(r"^\(?([a-f])[).:]?$", re.IGNORECASE)


def parse_yes_no(text: str) -> bool | None:
    """The key a yes/no chip sends. Anything typed is read by the fast model."""
    return {"yes": True, "no": False}.get(text.strip().lower())


def parse_choice(text: str, question: Question) -> str | None:
    """The option letter a chip sends or the student types alone. Anything else is read by
    the fast model."""
    match = _CHOICE_RE.match(text.strip())
    if match is None:
        return None
    key = match.group(1).upper()
    return key if key in {option.key for option in question.options} else None
