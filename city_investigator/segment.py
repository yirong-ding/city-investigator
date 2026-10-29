"""Segment photos with hosted SAM 3.1: requests, parsing, overlays and blurring."""

from __future__ import annotations

import io
import os
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import aclosing
from typing import Any

from meta_sam_parser import (
    ImageSegmentationResult,
    decode_mask_to_raster,
    image_segmentation_format,
    parse_responses_stream,
)

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
        result = await parse_responses_stream(events, image_segmentation_format()).final_result()
        # Read the stream to its end, so no half-read generator is left for the garbage collector
        # to close later from another thread's event loop.
        async for _ in events:
            pass
        return result


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


def blur_regions(jpeg: bytes, boxes: list[tuple[int, int, int, int]], pad: float = 0.2) -> bytes:
    """Blur each (left, top, right, bottom) box, padded, and return JPEG bytes."""
    from PIL import Image, ImageFilter

    image = Image.open(io.BytesIO(jpeg)).convert("RGB")
    width, height = image.size
    for left, top, right, bottom in boxes:
        pad_x, pad_y = int((right - left) * pad), int((bottom - top) * pad)
        box = (max(0, left - pad_x), max(0, top - pad_y), min(width, right + pad_x), min(height, bottom + pad_y))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        radius = max(6, (box[2] - box[0] + box[3] - box[1]) // 6)
        image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(radius)), box)
    output = io.BytesIO()
    image.save(output, "JPEG", quality=90)
    return output.getvalue()
