"""Check whether Mapillary photos show a sidewalk shed, using hosted SAM 3.1.

Downloads each photo to data/private/mapillary/ (never committed), segments shed-like
concepts, and writes an overlay image per photo. Costs one SAM request per photo and
concept (about $0.0025 each at the reported price).

Usage:
  python -m city_investigator.photo_check 1621408108523341 955892331835596
  python -m city_investigator.photo_check 1621408108523341 --concept scaffolding
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any

import requests

from city_investigator.meta import SpendGuard, data_url, env_float, load_photo, meta_client
from city_investigator.segment import draw_overlay, segment, summarize
from city_investigator.settings import ROOT, load_env

OUTPUT = ROOT / "data" / "private" / "mapillary"
DEFAULT_CONCEPTS = ["scaffolding", "sidewalk shed", "covered walkway"]
IMAGE_FIELDS = "id,thumb_2048_url,captured_at,creator,computed_geometry,compass_angle,computed_compass_angle"


def fetch_image(photo_id: str, token: str, session: requests.Session | None = None) -> tuple[Path, dict[str, Any]]:
    """Download one Mapillary photo; return its local path and metadata."""
    session = session or requests.Session()
    response = session.get(
        f"https://graph.mapillary.com/{photo_id}",
        params={"access_token": token, "fields": IMAGE_FIELDS},
        timeout=60,
    )
    response.raise_for_status()
    meta = response.json()
    if "error" in meta or not meta.get("thumb_2048_url"):
        raise RuntimeError(f"no image for {photo_id}: {str(meta.get('error', meta))[:200]}")
    image = session.get(meta["thumb_2048_url"], timeout=120)
    image.raise_for_status()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f"{photo_id}.jpg"
    path.write_bytes(image.content)
    return path, meta


async def check(photo_ids: list[str], concepts: list[str]) -> dict[str, dict[str, float | None]]:
    """Segment each photo; return the best confidence per concept (None: nothing found)."""

    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        raise SystemExit("MAPILLARY_TOKEN is not set.")
    guard = SpendGuard(max_calls=len(photo_ids) * len(concepts))
    found: dict[str, dict[str, float | None]] = {}
    async with meta_client(async_client=True) as api:
        for photo_id in photo_ids:
            try:
                path, meta = fetch_image(photo_id, token)
            except Exception as error:  # keep checking the other photos
                print(f"FAIL  {photo_id}: {type(error).__name__}: {error}"[:300])
                continue
            jpeg, size = load_photo(path)
            creator = (meta.get("creator") or {}).get("username", "a Mapillary contributor")
            print(f"\nPhoto {photo_id} by {creator} ({size[0]}x{size[1]}), saved to {path}")
            results = []
            for concept in concepts:
                guard.check()
                try:
                    result = await segment(api, data_url(jpeg), concept)
                finally:
                    guard.record(env_float("SAM_USD_PER_IMAGE", 0.0025))
                summary = summarize(result, concept, size)
                scores = sorted((box["confidence"] or 0 for box in summary["boxes"]), reverse=True)
                best = f", best confidence {scores[0]:.2f}" if scores else ""
                print(f"  {concept!r}: {summary['objects']} found{best}")
                results.append((concept, result))
                found.setdefault(photo_id, {})[concept] = scores[0] if scores else None
            overlay = OUTPUT / f"{photo_id}_overlay.png"
            overlay.write_bytes(draw_overlay(jpeg, results))
            print(f"  Overlay: {overlay}")
    print(f"\nEstimated spend today: ${guard.spent_today():.4f}")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("photo_ids", nargs="+", help="Mapillary photo IDs (the pKey in a Mapillary link)")
    parser.add_argument("--concept", action="append", help="noun phrase to look for; repeatable")
    args = parser.parse_args()
    load_env()
    asyncio.run(check(args.photo_ids, args.concept or DEFAULT_CONCEPTS))


if __name__ == "__main__":
    main()
