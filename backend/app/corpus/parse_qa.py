from pathlib import Path

from lxml import html

from app.corpus.manifest import ActSource
from app.corpus.model import Act, Article, Block, Paragraph
from app.corpus.textutil import normalize, text_of


def parse_qa(html_path: Path, source: ActSource) -> Act:
    root = html.parse(str(html_path)).getroot()
    articles: list[Article] = []
    items = root.xpath('//details[contains(@class,"ecl-accordion__item")]')
    for index, item in enumerate(items, start=1):
        summary = item.xpath(".//summary")
        content = item.xpath('.//div[contains(@class,"ecl-accordion__content")]')
        question = normalize(" ".join(summary[0].xpath(".//text()"))) if summary else ""
        blocks = content[0].xpath(".//p | .//li") if content else []
        answer = "\n\n".join(text_of(block) for block in blocks if text_of(block))
        articles.append(
            Article(
                id=f"item_{index}",
                number=str(index),
                title=question,
                paragraphs=[
                    Paragraph(
                        id=f"item_{index}.1",
                        number=None,
                        blocks=[Block(text=answer)] if answer else [],
                    )
                ],
            )
        )
    return source.act(articles=articles)
