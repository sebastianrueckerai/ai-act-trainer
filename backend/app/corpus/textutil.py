import re

from lxml import etree

NUMBER = r"\d{1,3}[a-z]?"
LABEL = re.compile(
    rf"^[\s‘“„]*"
    rf"(?:\(?(?P<paren>[a-z]{{1,3}}|[ivx]{{1,5}}|{NUMBER})\)|(?P<num>{NUMBER})\.)"
    rf"\s*(?P<rest>.*)$",
    re.S,
)
DROP_CLASSES = {"modref", "superscript"}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _drop(element: etree._Element) -> bool:
    classes = (element.get("class") or "").split()
    if any(cls in DROP_CLASSES for cls in classes):
        return True
    return element.tag == "a" and (element.get("id") or "").startswith("src.")


def text_of(element: etree._Element) -> str:
    parts: list[str] = []

    def walk(node: etree._Element) -> None:
        if _drop(node):
            if node.tail:
                parts.append(node.tail)
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
        if node.tail and node is not element:
            parts.append(node.tail)

    walk(element)
    return normalize("".join(parts))


def split_label(text: str) -> tuple[str, str]:
    match = LABEL.match(text.replace("\xa0", " "))
    if not match:
        return "", normalize(text)
    label = match.group("paren") or match.group("num")
    return label, normalize(match.group("rest"))
