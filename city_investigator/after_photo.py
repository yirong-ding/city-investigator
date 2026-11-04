"""After, in the photo itself: Muse Image redraws the run's photo with its proposals done.

The 3D After view (scene3d) draws each proposal in Valdrada; this draws the same proposals into the resident's own
photo with Muse Image's editing (`muse-image-1.0`), so the place they know shows what the action could look like.
It is an illustration, not evidence, not a design and not a prediction: the page and the saved file say so, the
photo's other content is kept as it is, and flood water stays (rain gardens hold a small share of it; see the 3D
label). Only proposals with a picture are drawn (actions.py `after`); a shed is not drawn where the photo already
shows scaffolding or netting. Muse Image gets the photo the run kept, with faces and license plates blurred.

Usage:
  python -m city_investigator.after_photo latest          # or a photo ID, or a run folder; saves after.webp
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import time
from pathlib import Path
from typing import Any

from city_investigator.actions import ACTIONS
from city_investigator.meta import SpendGuard, env_float, meta_client

FILE = "after.webp"
INFO = "after.json"
SEEN_SHED = {"seen_scaffolding", "seen_safety_netting"}  # protection the photo shows already (checks.py): no shed drawn
# What each picture adds, in words Muse Image can draw without inventing a place: no names, no signs, no text.
EDITS = {
    "rain_gardens": "two or three small curbside rain gardens in the sidewalk strip along the curb, each a long, "
                    "narrow planted bed of low native plants and grasses with a low stone edge, like the ones the "
                    "NYC Department of Environmental Protection builds",
    "shed": "a sidewalk shed along the building fronts on the sidewalk: a covered walkway of a dark green plywood "
            "deck on a steel pipe frame, as New York City requires in front of an unsafe façade",
    "young_tree": "a young street tree, staked and freshly planted, in a tree pit on the sidewalk",
}
KEEP = (
    "Keep everything else exactly as it is: the buildings, the street, the vehicles, the light, the weather, the "
    "camera angle and lens, and any water on the street or sidewalk. Change nothing else. Do not add people, text, "
    "signs, logos or license plates."
)


def drawable(result: dict[str, Any], explanation: dict[str, Any] | None) -> list[str]:
    """The pictures of the run's checked proposals, once each, in the order of the proposals."""
    pictures = {f"action:{action.key}": action.after for listed in ACTIONS.values() for action in listed if action.after}
    seen = {item.get("category") for item in result.get("observations", [])}
    found = []
    for claim in (explanation or {}).get("claims", []):
        if claim.get("kind") != "proposal":
            continue
        for eid in claim.get("evidence_ids", []):
            draw = pictures.get(eid)
            if draw and draw not in found and not (draw == "shed" and seen & SEEN_SHED):
                found.append(draw)
    return found


def prompt(draws: list[str]) -> str:
    added = "; and ".join(EDITS[draw] for draw in draws)
    return f"Edit this street photo to add {added}. {KEEP}"


def as_webp(data: bytes) -> bytes:
    """Muse Image answers in WebP; anything else is converted, so the file is always what its name says."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return data
    from PIL import Image

    out = io.BytesIO()
    Image.open(io.BytesIO(data)).convert("RGB").save(out, "WEBP", quality=85)
    return out.getvalue()


def draw_after(run_dir: Path, client: Any = None) -> dict[str, Any]:
    """Draw the run's proposals into its photo; save after.webp and after.json next to it, and return the info."""
    result = json.loads((run_dir / "result.json").read_text())
    path = run_dir / "explanation.json"
    explanation = json.loads(path.read_text()) if path.is_file() else None
    draws = drawable(result, explanation)
    if not draws:
        raise ValueError("No proposal of this run has a picture to draw in the photo"
                         + (" (or the photo already shows the protection)." if explanation else " (it has no explanation yet)."))
    model = os.environ.get("MUSE_IMAGE_MODEL") or "muse-image-1.0"
    guard = SpendGuard(max_calls=1)
    guard.check()
    started = time.monotonic()
    text = prompt(draws)
    client = client or meta_client()
    with open(run_dir / "photo.jpg", "rb") as photo:
        response = client.images.edit(model=model, prompt=text, image=photo, n=1)
    cost = env_float("MUSE_IMAGE_USD_PER_IMAGE", 0.01)
    guard.record(cost)
    (run_dir / FILE).write_bytes(as_webp(base64.b64decode(response.data[0].b64_json)))
    info = {
        "file": FILE,
        "model": model,
        "draws": draws,
        "prompt": text,
        "note": "AI illustration of the proposals done, drawn by Muse Image into the photo: not evidence, not a design "
                "and not a prediction. Flood water is kept.",
        "credit": f"Edited by Muse Image ({model}) from: {result['photo'].get('credit') or 'the photo'}",
        "seconds": round(time.monotonic() - started, 1),
        "estimated_cost_usd": cost,
    }
    (run_dir / INFO).write_text(json.dumps(info, indent=2))
    return info


def main() -> None:
    from city_investigator.explain import find_run
    from city_investigator.settings import load_env

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="'latest', a photo ID or file name, or an investigation folder")
    load_env()
    run_dir = find_run(parser.parse_args().run)
    info = draw_after(run_dir)
    print(f"Muse Image drew {', '.join(info['draws'])} into the photo in {info['seconds']} s: {run_dir / FILE}")


if __name__ == "__main__":
    main()
