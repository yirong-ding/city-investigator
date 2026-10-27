"""Day 1 smoke test: hosted SAM 3.1 on one photo, one request per concept, with confidence.

Writes smoke/results/sam.json and smoke/results/sam_overlay.png (masks drawn on the
photo, one color per concept). An empty result for a concept is a valid answer.

Usage:
  python -m smoke.sam path/to/photo.jpg
  python -m smoke.sam path/to/photo.jpg --concept "standing water" --concept scaffolding
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

from city_investigator.segment import draw_overlay, segment, summarize
from smoke._common import (
    RESULTS,
    SpendGuard,
    data_url,
    env_float,
    load_env,
    load_photo,
    meta_client,
    write_result,
)

DEFAULT_CONCEPTS = ["standing water", "scaffolding", "catch basin", "car"]


async def run(photo: Path, concepts: list[str]) -> None:
    jpeg, size = load_photo(photo)
    image_url = data_url(jpeg)
    guard = SpendGuard(max_calls=len(concepts))
    results: list[tuple[str, Any]] = []
    summaries = []
    async with meta_client(async_client=True) as api:
        for concept in concepts:
            guard.check()
            try:
                result = await segment(api, image_url, concept)
            except Exception as error:  # report the failure and try the next concept
                status = getattr(error, "status_code", None)
                print(f"FAIL  {concept!r}: {type(error).__name__} {status or ''}: {error}"[:600])
                summaries.append({"concept": concept, "error": str(error)[:600]})
                continue
            finally:
                guard.record(env_float("SAM_USD_PER_IMAGE", 0.0025))
            summary = summarize(result, concept, size)
            summaries.append(summary)
            results.append((concept, result))
            scores = [box["confidence"] for box in summary["boxes"]]
            ok = summary["outcome"] == "completed" and not summary["parser_errors"]
            print(f"{'PASS' if ok else 'FAIL'}  {concept!r}: {summary['objects']} object(s), confidence {scores}")
            if not all(box["inside_photo"] for box in summary["boxes"]):
                print("      - a box falls outside the photo: check EXIF orientation")
    path = write_result("sam", {"photo_size": size, "concepts": summaries})
    if results:
        overlay = RESULTS / "sam_overlay.png"
        overlay.write_bytes(draw_overlay(jpeg, results))
        print(f"\nOverlay: {overlay}")
    print(f"Details: {path}  (estimated spend today: ${guard.spent_today():.4f})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("photo", type=Path)
    parser.add_argument("--concept", action="append", help="short noun phrase; repeatable")
    args = parser.parse_args()
    load_env()
    asyncio.run(run(args.photo, args.concept or DEFAULT_CONCEPTS))


if __name__ == "__main__":
    main()
