"""Offline checks for the smoke-test helpers: no API key or network needed."""

from __future__ import annotations

import io
import json

import pytest
from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format
from PIL import Image

from city_investigator import meta
from smoke import _common
from smoke._common import SpendCapError, SpendGuard, load_photo
from smoke.muse_spark import validate_claims
from smoke.sam import draw_overlay, summarize

# One SAM 3.1 image record (box plus mask, with confidence), in the documented wire format.
SAM_LINE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334;c=0.75|>"
    "<|mask;x=0;y=0;c=0.75;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>\n"
)


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "spend.json"
    monkeypatch.setattr(meta, "LEDGER", path)
    return path


def test_spend_guard_stops_at_call_cap(ledger):
    guard = SpendGuard(max_calls=2)
    guard.check()
    guard.check()
    with pytest.raises(SpendCapError):
        guard.check()


def test_spend_guard_stops_at_daily_cap(ledger, monkeypatch):
    monkeypatch.setenv("DAILY_SPEND_CAP_USD", "0.01")
    guard = SpendGuard(max_calls=10)
    guard.check()
    guard.record(0.02)
    assert json.loads(ledger.read_text())
    with pytest.raises(SpendCapError):
        guard.check()


def test_validate_claims_flags_unknown_evidence():
    answer = json.dumps(
        {"claims": [{"text": "Water covers the crosswalk.", "kind": "observation", "evidence_ids": ["photo", "311-999"]}]}
    )
    problems = validate_claims(answer, {"photo"})
    assert problems == ["claim 0: cites unknown evidence ['311-999']"]


def test_validate_claims_accepts_valid_answer():
    answer = json.dumps({"claims": [{"text": "A 311 complaint was filed.", "kind": "record", "evidence_ids": ["r1"]}]})
    assert validate_claims(answer, {"r1"}) == []


def test_validate_claims_rejects_unknown_kind():
    answer = json.dumps({"claims": [{"text": "x", "kind": "fact", "evidence_ids": []}]})
    assert "kind 'fact' not allowed" in validate_claims(answer, set())[0]


def parsed_sam_result():
    parser = image_segmentation_format().create_parser()
    parser.push(SAM_LINE)
    return parser.finish(CompletedOutcome()).result


def test_sam_summary_reads_box_mask_and_confidence():
    result = parsed_sam_result()
    summary = summarize(result, "duck", (320, 334))
    assert summary["outcome"] == "completed"
    assert summary["objects"] == 1
    box = summary["boxes"][0]
    assert (box["left"], box["top"], box["right"], box["bottom"]) == (211, 228, 271, 255)
    assert box["confidence"] == 0.75
    assert box["inside_photo"]
    mask = next(record for record in result.records if record.kind == "mask")
    assert len(decode_mask_to_raster(mask.mask)) == 60 * 27
    assert summary["mask_pixels"][0]["pixels"] > 0


def test_sam_overlay_draws_inside_the_box():
    buffer = io.BytesIO()
    Image.new("RGB", (320, 334), (255, 255, 255)).save(buffer, "JPEG")
    png = draw_overlay(buffer.getvalue(), [("duck", parsed_sam_result())])
    overlay = Image.open(io.BytesIO(png)).convert("RGB")
    assert overlay.size == (320, 334)
    inside = [overlay.getpixel((x, y)) for x in range(211, 271) for y in range(228, 255)]
    assert any(pixel != (255, 255, 255) for pixel in inside)
    assert overlay.getpixel((10, 10)) == (255, 255, 255)


def test_load_photo_applies_rotation_and_strips_metadata(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90 degrees to display
    path = tmp_path / "portrait.jpg"
    Image.new("RGB", (400, 300)).save(path, "JPEG", exif=exif.tobytes())
    jpeg, size = load_photo(path)
    assert size == (300, 400)
    assert not Image.open(io.BytesIO(jpeg)).getexif()


def test_open_client_requires_baseten_key(monkeypatch):
    monkeypatch.delenv("OPEN_MODEL_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="OPEN_MODEL_API_KEY"):
        _common.open_client()


def test_open_client_defaults_to_baseten(monkeypatch):
    monkeypatch.setenv("OPEN_MODEL_API_KEY", "test-key")
    monkeypatch.delenv("OPEN_MODEL_BASE_URL", raising=False)
    assert str(_common.open_client().base_url).startswith("https://inference.baseten.co/v1")


def test_cost_uses_provider_prices(monkeypatch):
    class Usage:
        prompt_tokens = 1_000_000
        completion_tokens = 0

    monkeypatch.setenv("OPEN_MODEL_INPUT_USD_PER_M", "0.5")
    assert _common.muse_cost(Usage(), "OPEN_MODEL") == 0.5
