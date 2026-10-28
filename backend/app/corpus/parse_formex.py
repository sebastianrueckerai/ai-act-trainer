import zipfile
from pathlib import Path

from lxml import etree

from app.corpus.model import Recital
from app.corpus.textutil import normalize, split_label


def parse_recitals(zip_path: Path) -> list[Recital]:
    with zipfile.ZipFile(zip_path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".fmx.xml")]
        body_name = max(names, key=lambda n: archive.getinfo(n).file_size)
        root = etree.fromstring(archive.read(body_name))
    recitals: list[Recital] = []
    for index, consid in enumerate(root.iter("CONSID"), start=1):
        etree.strip_elements(consid, "NOTE", with_tail=False)
        raw = normalize("".join(consid.itertext()))
        _, text = split_label(raw)
        recitals.append(Recital(id=f"rct_{index}", number=index, text=text or raw))
    return recitals
