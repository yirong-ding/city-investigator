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
import io
import os
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import aclosing
from pathlib import Path
from typing import Any

from meta_sam_parser import (
    ImageSegmentationResult,
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
)

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
COLORS = [(230, 60, 60), (60, 120, 230), (240, 170, 30), (60, 180, 90), (170, 80, 200)]


async def lane_events(stream: AsyncIterable[Any]) -> AsyncIterator[dict[str, Any]]:
    """Pass Responses events to the parser as plain dicts.

    The SAM API finishes its text with `response.content_part.done` only; the parser
    also accepts `response.output_text.done`, so one is added from the content part
    in case a parser version needs it. The parser ignores a matching duplicate.
    """
    finished: set[tuple[Any, Any, Any]] = set()
    async for event in stream:
        data = event.model_dump() if hasattr(event, "model_dump") else dict(event)
        lane = (data.get("item_id"), data.get("output_index"), data.get("content_index"))
        if data.get("type") == "response.output_text.done":
            if lane in finished:
                continue
            finished.add(lane)
        yield data
        part = data.get("part")
        if (
            data.get("type") == "response.content_part.done"
            and lane not in finished
            and isinstance(part, dict)
            and part.get("type") == "output_text"
            and isinstance(part.get("text"), str)
        ):
            finished.add(lane)
            yield {
                "type": "response.output_text.done",
                "item_id": lane[0],
                "output_index": lane[1],
                "content_index": lane[2],
                "text": part["text"],
            }


async def segment(api: Any, image_url: str, concept: str) -> ImageSegmentationResult:
    stream = await api.responses.create(
        model=os.environ.get("SAM_MODEL") or "sam-3.1",
        stream=True,
        # A request carries either one noun phrase or object prompts, never both.
        input=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": concept},
                    {"type": "input_image", "image_url": image_url},
                ],
            }
        ],
        # Confidence scores are returned only when asked for.
        metadata={"include_confidence": "true"},
    )
    async with stream, aclosing(lane_events(stream)) as events:
        return await parse_responses_stream(events, image_segmentation_format()).final_result()


def summarize(result: Any, concept: str, size: tuple[int, int]) -> dict[str, Any]:
    width, height = size
    boxes = [record for record in result.records if record.kind == "box"]
    masks = [record for record in result.records if record.kind == "mask"]
    errors = [item for item in result.diagnostics if item.severity == "error"]
    return {
        "concept": concept,
        "outcome": result.outcome.status,
        "objects": len(boxes),
        "boxes": [
            {
                "object_id": box.object_id,
                "left": box.left,
                "top": box.top,
                "right": box.right,
                "bottom": box.bottom,
                "confidence": box.confidence,
                # Boxes outside the photo would mean an orientation mismatch.
                "inside_photo": 0 <= box.left < box.right <= width and 0 <= box.top < box.bottom <= height,
            }
            for box in boxes
        ],
        "mask_pixels": [
            {"object_id": mask.object_id, "pixels": sum(decode_mask_to_raster(mask.mask))}
            for mask in masks
        ],
        "parser_errors": [f"line {item.line}: {item.message}" for item in errors],
    }


def draw_overlay(jpeg: bytes, results: list[tuple[str, Any]]) -> bytes:
    """Draw every mask on the photo, one color per concept, and return PNG bytes."""
    from PIL import Image

    base = Image.open(io.BytesIO(jpeg)).convert("RGBA")
    for index, (_, result) in enumerate(results):
        color = COLORS[index % len(COLORS)]
        boxes = {record.object_id: record for record in result.records if record.kind == "box"}
        for record in result.records:
            if record.kind != "mask":
                continue
            mask = record.mask
            raster = bytes(255 if value else 0 for value in decode_mask_to_raster(mask))
            alpha = Image.frombytes("L", (mask.width, mask.height), raster).point(lambda v: v * 120 // 255)
            layer = Image.new("RGBA", (mask.width, mask.height), color + (0,))
            layer.putalpha(alpha)
            anchor = boxes.get(record.object_id, record)
            base.alpha_composite(layer, (anchor.left, anchor.top))
    output = io.BytesIO()
    base.convert("RGB").save(output, "PNG")
    return output.getvalue()


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
