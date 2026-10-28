"""Generate the persona scene PNGs under personas/<id>/images/scene.png via Replicate.

Reads every persona manifest's scene_prompt, calls the Replicate REST API once per
persona with a seed fixed per persona, and asks rd-plus for a native 320x240 room on
the office scene's own palette, so every scene sits in one colour world with the UI
art (D53: one pixel grid for the whole screen; scaling is CSS's job).

    uv run --project backend python tools/generate_scenes.py --dry-run
    uv run --project backend python tools/generate_scenes.py --only pirate,marvin

Needs REPLICATE_API_TOKEN in the environment (not for --dry-run), falling back to the
repo's .env.tools file. On an out-of-credit response, stops at once with a non-zero exit; it
never retries that and never substitutes an image. The output is committed;
regeneration is manual, like the content.
"""

from __future__ import annotations

import argparse
import base64
import io
import zlib
from pathlib import Path

import httpx
from generate_avatars import (
    create_prediction,
    fetch_bytes,
    first_image_url,
    load_token,
    personas,
    wait_for_output,
)
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
# The room every persona stands in: the course is about AI, so the room is part machine.
ANCHOR = (
    "retro 16-bit pixel art, environment, wide interior, night, muted dark palette with cool "
    "blues and warm lamp light, robot and cyber details tie it together: glowing panels, cables, "
    "a small robotic arm, a holographic screen; empty of people, calm, no text"
)
# The light look draws its own rooms rather than washing the dark ones out (D98): daylight
# from the start, and the outer edge feathered to white so the page has no seam.
LIGHT_ANCHOR = (
    "retro 16-bit pixel art, environment, wide interior, bright daylight, airy high-key palette "
    "of soft whites, pale greys and light blues, sunlight through large windows, robot and cyber "
    "details tie it together: glowing panels, cables, a small robotic arm, a holographic screen; "
    "empty of people, calm, no text"
)
LIGHT_FEATHER = 0.22  # the fraction of the width and height that fades into white

# The office scene the picker keeps behind it; every persona scene shares its colours.
PALETTE_SOURCE = REPO_ROOT / "frontend" / "src" / "ui" / "art" / "scene.png"
WIDTH = 320
HEIGHT = 240
SWATCH = 8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="retro-diffusion/rd-plus")
    parser.add_argument("--only", help="comma-separated persona ids, default all")
    parser.add_argument("--dry-run", action="store_true", help="print prompts, call nothing")
    parser.add_argument("--missing", action="store_true", help="skip scenes already on disk")
    parser.add_argument("--light", action="store_true", help="draw scene-light.png instead")
    parser.add_argument("--personas-dir", type=Path, default=REPO_ROOT / "personas")
    return parser.parse_args()


def palette_uri(source: Path) -> str:
    """The source image's own colours as a strip, the way rd-plus takes a palette."""
    image = Image.open(source).convert("RGB")
    colours = [colour for _, colour in sorted(image.getcolors(1 << 20), reverse=True)]
    strip = Image.new("RGB", (len(colours) * SWATCH, SWATCH))
    for i, colour in enumerate(colours):
        strip.paste(colour, (i * SWATCH, 0, (i + 1) * SWATCH, SWATCH))
    buffer = io.BytesIO()
    strip.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def build_prompt(manifest: dict, light: bool = False) -> str:
    prompt = manifest.get("scene_prompt", "").strip()
    if not prompt:
        raise SystemExit(f"persona {manifest['id']} has no scene_prompt in its manifest")
    if light:
        prompt = prompt.replace("moonlit", "sunlit").replace("night", "day")
    return f"{prompt}. {LIGHT_ANCHOR if light else ANCHOR}"


def feathered(image: Image.Image) -> Image.Image:
    """The room fading into white at every edge, so the page needs no veil over it."""
    white = Image.new("RGB", image.size, (255, 255, 255))
    mask = Image.new("L", image.size, 255)
    pixels = mask.load()
    fade_x = max(1, round(image.width * LIGHT_FEATHER))
    fade_y = max(1, round(image.height * LIGHT_FEATHER))
    for x in range(image.width):
        for y in range(image.height):
            edge = min(x, image.width - 1 - x) / fade_x, min(y, image.height - 1 - y) / fade_y
            pixels[x, y] = round(255 * min(1.0, min(edge)))
    return Image.composite(image, white, mask)


def seed_for(persona_id: str, light: bool = False) -> int:
    # Fixed per persona and per mode, so a rerun redraws the same room.
    return (
        zlib.crc32(
            f"scene-light:{persona_id}".encode() if light else f"scene:{persona_id}".encode()
        )
        % 2**31
    )


def main() -> None:
    args = parse_args()
    selected = personas(args.personas_dir)
    if args.only:
        wanted = {name.strip() for name in args.only.split(",") if name.strip()}
        selected = [manifest for manifest in selected if manifest["id"] in wanted]
        missing = wanted - {manifest["id"] for manifest in selected}
        if missing:
            raise SystemExit(f"unknown persona(s): {', '.join(sorted(missing))}")

    name = "scene-light" if args.light else "scene"
    jobs = [
        (manifest, build_prompt(manifest, args.light))
        for manifest in selected
        if not (args.missing and (manifest["dir"] / "images" / f"{name}.png").exists())
    ]
    for manifest, prompt in jobs:
        print(f"[{manifest['id']}/{name}] {prompt}")

    if args.dry_run:
        return

    token = load_token(REPO_ROOT)
    if not token:
        raise SystemExit("REPLICATE_API_TOKEN is not set (checked the environment and .env.tools)")
    palette = None if args.light else palette_uri(PALETTE_SOURCE)

    with httpx.Client(timeout=60) as client:
        for manifest, prompt in jobs:
            out_path = manifest["dir"] / "images" / f"{name}.png"
            prediction = create_prediction(
                client,
                token,
                args.model,
                prompt,
                seed_for(manifest["id"], args.light),
                width=WIDTH,
                height=HEIGHT,
                remove_bg=False,
                style="environment",
                **({} if palette is None else {"input_palette": palette}),
            )
            output = first_image_url(wait_for_output(client, token, prediction))
            image = Image.open(io.BytesIO(fetch_bytes(client, output))).convert("RGB")
            if args.light:
                image = feathered(image)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(out_path, format="PNG")
            print(f"wrote {out_path} {image.size}")


if __name__ == "__main__":
    main()
