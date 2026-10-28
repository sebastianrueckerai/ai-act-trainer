"""Generate persona portrait PNGs under personas/<id>/images/ via Replicate.

Reads every persona manifest's image_prompt and emotions, calls the Replicate
REST API once per emotion with a seed fixed per persona, asks rd-plus for a
native 64x64 image with the background removed, and writes it straight to
<emotion>.png next to the manifest as RGBA, no resize (D53: one pixel grid
for the whole screen; scaling to display size is CSS's job).

    cd backend && uv run python ../tools/generate_avatars.py --dry-run
    cd backend && uv run python ../tools/generate_avatars.py --persona marvin

Needs REPLICATE_API_TOKEN in the environment (not for --dry-run), falling
back to the repo's .env.tools file. On an out-of-credit response, stops at once
with a non-zero exit; it never retries that and never substitutes an image.
The output is committed; regeneration is manual, like the content.
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import time
import zlib
from pathlib import Path

import httpx
import yaml
from PIL import Image

REPLICATE_BASE = "https://api.replicate.com/v1/models/{model}/predictions"
# Every persona is part machine: the course is about AI, so the tutor looks the part.
# This lives here and not in a manifest so a new persona cannot be drawn without it.
CYBORG_ANCHOR = (
    "cyborg: one eye replaced by a glowing circular optical implant, brushed chrome "
    "plating over one cheek and temple, a few exposed cables at the neck"
)
STYLE_ANCHOR = (
    "retro 16-bit pixel art, crisp pixels, strong flat colors, no anti-aliasing, "
    "bust portrait, plain flat single-color background, centered"
)
EMOTION_PHRASES = {
    "neutral": "calm neutral expression",
    "happy": "clearly happy, warm smile",
    "disappointed": "disappointed, faint frown",
    "surprised": "surprised, eyes wide, eyebrows raised high, mouth open",
}
# A reaction frame is the neutral frame with one feature changed: switching the two images
# is the whole animation, so the prompt pins everything else down (D101).
FROM_NEUTRAL_PHRASES = {
    "happy": "exactly the same drawing, nothing moved or restyled, only the mouth now shows "
    "a small warm smile",
    "disappointed": "exactly the same drawing, nothing moved or restyled, only the mouth now "
    "shows a faint frown",
}
FROM_NEUTRAL_OVERRIDES: dict[str, dict[str, str]] = {
    # Depressobot does not smile; its positive reaction is one faintly raised eyebrow.
    "marvin": {
        "happy": "exactly the same drawing, nothing moved or restyled, only one eyebrow is "
        "now slightly raised in faint interest"
    },
}
FROM_NEUTRAL_EMOTIONS = ("happy", "disappointed")
SIZE = 64  # rd-plus's floor; the whole screen keeps one art pixel = 4 CSS px (D53)
MAX_COLORS = 64  # Pillow's RGBA quantize keeps per-pixel alpha exactly; verified empirically
POLL_SECONDS = 2.0
POLL_TIMEOUT = 300.0
RATE_LIMIT_TRIES = 6
RATE_LIMIT_WAIT = 20.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="retro-diffusion/rd-plus")
    parser.add_argument("--persona", action="append", help="persona id; repeatable, default all")
    parser.add_argument("--dry-run", action="store_true", help="print prompts, call nothing")
    parser.add_argument("--missing", action="store_true", help="skip emotions already on disk")
    parser.add_argument(
        "--from-neutral",
        action="store_true",
        help="regenerate happy and disappointed as a minimal edit of the committed neutral "
        "frame via image-to-image, so switching frames reads as an animation",
    )
    parser.add_argument(
        "--strength",
        type=float,
        default=0.2,
        help="image-to-image strength for --from-neutral; lower stays closer to the neutral",
    )
    parser.add_argument(
        "--personas-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "personas",
    )
    return parser.parse_args()


def personas(personas_dir: Path) -> list[dict]:
    loaded = []
    for manifest_path in sorted(personas_dir.glob("*/manifest.yaml")):
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["dir"] = manifest_path.parent
        loaded.append(manifest)
    return loaded


def _body(manifest: dict) -> str:
    body = manifest["image_prompt"].strip().rstrip(".")
    # Every tutor but the clerk is part machine: the course is about AI, so it looks the
    # part. A persona says so in its manifest, and its own prompt carries the detail.
    if manifest.get("machine", True):
        body = f"{body} {CYBORG_ANCHOR}"
    return body


def build_prompt(manifest: dict, emotion: str) -> str:
    try:
        phrase = EMOTION_PHRASES[emotion]
    except KeyError as err:
        raise SystemExit(f"no emotion phrase for {emotion!r}; extend EMOTION_PHRASES") from err
    return f"{_body(manifest)}. {phrase}. {STYLE_ANCHOR}"


def build_from_neutral_prompt(manifest: dict, emotion: str) -> str:
    phrase = (
        FROM_NEUTRAL_OVERRIDES.get(manifest["id"], {}).get(emotion) or FROM_NEUTRAL_PHRASES[emotion]
    )
    return f"{_body(manifest)}. {phrase}. {STYLE_ANCHOR}"


def seed_for(persona_id: str) -> int:
    # Fixed per persona so the four emotions stay one character.
    return zlib.crc32(persona_id.encode()) % 2**31


def load_token(repo_root: Path) -> str:
    token = os.environ.get("REPLICATE_API_TOKEN", "")
    if token:
        return token
    env_path = repo_root / ".env.tools"
    if not env_path.exists():
        return ""
    for line in env_path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key == "REPLICATE_API_TOKEN":
            return value.strip().strip('"').strip("'")
    return ""


def _out_of_credit(response: httpx.Response) -> bool:
    if response.status_code == 402:
        return True
    if response.status_code >= 400:
        try:
            detail = str(response.json())
        except ValueError:
            detail = response.text
        return "credit" in detail.lower()
    return False


def create_prediction(
    client: httpx.Client, token: str, model: str, prompt: str, seed: int, **input_fields: object
) -> dict:
    defaults = {"width": SIZE, "height": SIZE, "remove_bg": True}
    for attempt in range(RATE_LIMIT_TRIES):
        response = client.post(
            REPLICATE_BASE.format(model=model),
            headers={"Authorization": f"Bearer {token}"},
            json={"input": {"prompt": prompt, "seed": seed, **defaults, **input_fields}},
        )
        if _out_of_credit(response):
            raise SystemExit(
                f"Replicate account is out of credit (HTTP {response.status_code}). "
                "Stopping now; not retrying, not substituting any image."
            )
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        wait = float(response.headers.get("retry-after", RATE_LIMIT_WAIT * (attempt + 1)))
        print(f"rate limited, waiting {wait:.0f}s")
        time.sleep(wait)
    raise SystemExit("Replicate kept rate limiting the request")


def wait_for_output(client: httpx.Client, token: str, prediction: dict) -> str:
    deadline = time.monotonic() + POLL_TIMEOUT
    poll_url = prediction["urls"]["get"]
    while time.monotonic() < deadline:
        got = client.get(poll_url, headers={"Authorization": f"Bearer {token}"})
        got.raise_for_status()
        body = got.json()
        if body["status"] == "succeeded":
            return body["output"]
        if body["status"] in ("failed", "canceled"):
            raise RuntimeError(f"prediction {body['status']}: {body.get('error')}")
        time.sleep(POLL_SECONDS)
    raise RuntimeError("prediction polling timed out")


def first_image_url(output: object) -> str:
    if isinstance(output, list):
        return str(output[0])
    return str(output)


def fetch_bytes(client: httpx.Client, url_or_data: str) -> bytes:
    if url_or_data.startswith("data:"):
        return base64.b64decode(url_or_data.split(",", 1)[1])
    response = client.get(url_or_data)
    response.raise_for_status()
    return response.content


def save_processed(raw: bytes, out_path: Path) -> None:
    image = Image.open(io.BytesIO(raw)).convert("RGBA")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.quantize(MAX_COLORS).convert("RGBA").save(out_path, format="PNG")


def main() -> None:
    args = parse_args()
    selected = personas(args.personas_dir)
    if args.persona:
        wanted = set(args.persona)
        selected = [m for m in selected if m["id"] in wanted]
        missing = wanted - {m["id"] for m in selected}
        if missing:
            raise SystemExit(f"unknown persona(s): {', '.join(sorted(missing))}")

    from_neutral = [
        (manifest, emotion, build_from_neutral_prompt(manifest, emotion))
        for manifest in selected
        for emotion in FROM_NEUTRAL_EMOTIONS
        if emotion in manifest["emotions"]
    ]
    jobs = (
        from_neutral
        if args.from_neutral
        else [
            (manifest, emotion, build_prompt(manifest, emotion))
            for manifest in selected
            for emotion in manifest["emotions"]
            if not (args.missing and (manifest["dir"] / "images" / f"{emotion}.png").exists())
        ]
    )
    for manifest, emotion, prompt in jobs:
        print(f"[{manifest['id']}/{emotion}] {prompt}")

    if args.dry_run:
        return

    token = load_token(Path(__file__).resolve().parents[1])
    if not token:
        raise SystemExit("REPLICATE_API_TOKEN is not set (checked the environment and .env.tools)")

    with httpx.Client(timeout=60) as client:
        for manifest, emotion, prompt in jobs:
            out_path = manifest["dir"] / "images" / f"{emotion}.png"
            input_fields = {}
            if args.from_neutral:
                neutral = (manifest["dir"] / "images" / "neutral.png").read_bytes()
                input_fields = {
                    "input_image": f"data:image/png;base64,{base64.b64encode(neutral).decode()}",
                    "strength": args.strength,
                }
            prediction = create_prediction(
                client, token, args.model, prompt, seed_for(manifest["id"]), **input_fields
            )
            output = first_image_url(wait_for_output(client, token, prediction))
            save_processed(fetch_bytes(client, output), out_path)
            print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
