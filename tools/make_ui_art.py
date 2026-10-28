"""Generate the pixel-skin PNGs under frontend/src/ui/art.

Run from the backend directory (Pillow lives in its dev group):

    cd backend && uv run python ../tools/make_ui_art.py

Art is baked from the given palette; a palette change means rerunning the
tool and committing the new PNGs. Icons are inline SVG (src/ui/Icon.tsx)
and deliberately not part of this output.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

GRID = 4  # every art pixel is a GRID x GRID block
NINE = 12  # nine-slice edge in art pixels -> 48px
SLICE_CELLS = 3  # nine-slice border band -> 12px
SMALL = 6  # chip/badge edge -> 24px
SMALL_SLICE = 1  # chip/badge border band -> 4px

Color = tuple[int, int, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", default="#2563eb")
    parser.add_argument("--secondary", default="#0f172a")
    parser.add_argument("--grid", type=int, default=4)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "frontend" / "src" / "ui" / "art",
    )
    return parser.parse_args()


def rgb(hex_value: str) -> Color:
    value = hex_value.removeprefix("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def mixed(a: Color, b: Color, t: float) -> Color:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


class Canvas:
    """An art-pixel canvas: (x, y) addresses art pixels, not device pixels."""

    def __init__(self, cells: int) -> None:
        self.cells = cells
        self.image = Image.new("RGBA", (cells * GRID, cells * GRID), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)

    def px(self, x: int, y: int, color: Color) -> None:
        self.draw.rectangle(
            [x * GRID, y * GRID, x * GRID + GRID - 1, y * GRID + GRID - 1],
            fill=(*color, 255),
        )

    def grid(self, rows: list[str], colors: dict[str, Color]) -> None:
        for y, row in enumerate(rows):
            for x, letter in enumerate(row):
                if letter in colors:
                    self.px(x, y, colors[letter])


def nine_slice(
    outline: Color,
    band: Color,
    fill: Color | None,
    cells: int = NINE,
    slice_cells: int = SLICE_CELLS,
    bevel_light: Color | None = None,
    bevel_dark: Color | None = None,
) -> Image.Image:
    canvas = Canvas(cells)
    last = cells - 1
    for y in range(cells):
        for x in range(cells):
            in_band = (
                x < slice_cells
                or x >= cells - slice_cells
                or y < slice_cells
                or y >= cells - slice_cells
            )
            if in_band:
                canvas.px(x, y, band)
    if bevel_light is not None:
        for i in range(1, last):
            canvas.px(i, 1, bevel_light)
            canvas.px(1, i, bevel_light)
    if bevel_dark is not None:
        for i in range(1, last):
            canvas.px(i, last - 1, bevel_dark)
            canvas.px(last - 1, i, bevel_dark)
    for i in range(cells):
        for x, y in ((i, 0), (i, last), (0, i), (last, i)):
            canvas.px(x, y, outline)
    if fill is not None:
        for y in range(slice_cells, cells - slice_cells):
            for x in range(slice_cells, cells - slice_cells):
                canvas.px(x, y, fill)
    return canvas.image


CURSOR = [
    "w.......",
    "wk......",
    "wkk.....",
    "wkkk....",
    "wkkkk...",
    "wkkkkk..",
    "wkkkkkk.",
    "wkkkkkkk",
]


def build_all(args: argparse.Namespace) -> dict[str, Image.Image]:
    primary = rgb(args.primary)
    secondary = rgb(args.secondary)
    white = (255, 255, 255)

    # No sprite carries a baked surface colour: every centre is transparent and the
    # CSS variables paint it. That is what lets one set serve dark and light (D42).
    ink = mixed(secondary, white, 0.35)  # outlines
    paper = mixed(secondary, white, 0.55)  # light band/bevel
    dim = mixed(secondary, white, 0.30)  # dark band/bevel
    card_band = mixed(paper, primary, 0.20)

    art: dict[str, Image.Image] = {
        "frame": nine_slice(outline=ink, band=paper, fill=None),
        "card": nine_slice(outline=ink, band=card_band, fill=None),
        "bubble": nine_slice(outline=dim, band=ink, fill=None),
        # The student's own bubble is outlined, never filled: a bright band reads
        # as a button and the thread must hold nothing pressable.
        "bubble-user": nine_slice(outline=primary, band=dim, fill=None),
        "button": nine_slice(outline=ink, band=paper, fill=None, bevel_light=white, bevel_dark=dim),
        "button-pressed": nine_slice(
            outline=ink, band=dim, fill=None, bevel_light=ink, bevel_dark=paper
        ),
        "button-disabled": nine_slice(outline=dim, band=dim, fill=None),
        "chip": nine_slice(
            outline=primary, band=primary, fill=None, cells=SMALL, slice_cells=SMALL_SLICE
        ),
        "chip-selected": nine_slice(
            outline=ink, band=ink, fill=primary, cells=SMALL, slice_cells=SMALL_SLICE
        ),
        # A citation pill is a link, not a control: the accent stays on the
        # things the student presses.
        "chip-dim": nine_slice(
            outline=dim, band=dim, fill=None, cells=SMALL, slice_cells=SMALL_SLICE
        ),
        "badge": nine_slice(outline=dim, band=dim, fill=None, cells=SMALL, slice_cells=SMALL_SLICE),
    }

    cursor = Canvas(8)
    cursor.grid(CURSOR, {"w": white, "k": ink})
    art["cursor"] = cursor.image

    return art


def main() -> None:
    args = parse_args()
    global GRID
    GRID = args.grid
    images = build_all(args)

    used: set[Color] = set()
    for image in images.values():
        for _, pixel in image.convert("RGB").getcolors(maxcolors=100_000) or []:
            used.add(pixel)
    if len(used) > 16:
        raise SystemExit(f"palette too large: {len(used)} distinct colors")

    args.out.mkdir(parents=True, exist_ok=True)
    for name, image in images.items():
        image.save(args.out / f"{name}.png")
    print(f"{len(images)} PNGs -> {args.out} ({len(used)} colors)")


if __name__ == "__main__":
    main()
