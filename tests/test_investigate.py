"""Offline tests for the investigate command, using made-up data and a stand-in for SAM."""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import pytest
from meta_sam_parser import CompletedOutcome, image_segmentation_format
from PIL import Image
from test_data_layer import CORNER, SHED, store  # noqa: F401  (store is a fixture)

from city_investigator import investigate as inv
from city_investigator import times
from city_investigator.checks import flood_checks, sidewalk_checks
from city_investigator.evidence import Evidence
from city_investigator.photo_input import Photo, _capture_time, dms_to_degrees, read_exif
from city_investigator.segment import blur_regions

BOX_LINE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334;c=0.75|>"
    "<|mask;x=0;y=0;c=0.75;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>\n"
)


def sam_result(line: str = ""):
    parser = image_segmentation_format().create_parser()
    if line:
        parser.push(line)
    return parser.finish(CompletedOutcome()).result


def white_jpeg(size=(320, 334)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (255, 255, 255)).save(buffer, "JPEG")
    return buffer.getvalue()


def photo_at(lat, lon, taken) -> Photo:
    return Photo("mapillary", "123", white_jpeg(), (320, 334), lat, lon, taken, "mapillary", 10.0,
                 credit="Photo by tester, Mapillary, CC BY-SA 4.0", already_blurred=True)


def evidence(eid, category, start=None, topic="sidewalk", address=None):
    return Evidence(eid, "record", topic, category, "test", "test", eid, None, None, "test", start, None, "", address=address)


def test_topic_is_guessed_from_the_question():
    assert inv.detect_topic("What records relate to this blocked sidewalk?") == "sidewalk"
    assert inv.detect_topic("Is this flooding a recurring problem?") == "flooding"
    assert inv.detect_topic("What has changed here?") is None


def test_local_dates_become_utc():
    assert inv.parse_local("2026-08-23") == datetime(2026, 8, 23, 16, tzinfo=timezone.utc)
    assert inv.parse_local("2026-08-23 06:45") == datetime(2026, 8, 23, 10, 45, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        inv.parse_local("yesterday")


def test_capture_time_uses_the_offset_when_present():
    assert _capture_time("2026:08:23 07:40:00", "-04:00") == datetime(2026, 8, 23, 11, 40, tzinfo=timezone.utc)
    assert _capture_time("2026:01:10 07:40:00", None) == datetime(2026, 1, 10, 12, 40, tzinfo=timezone.utc)
    assert dms_to_degrees((73, 59, 6.0), "W") == pytest.approx(-73.985)


def test_exif_location_and_time_are_read(tmp_path):
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (40.0, 40.0, 36.0), 3: "W", 4: (73.0, 59.0, 2.4), 31: 7.0}
    exif[0x8769] = {0x9003: "2026:08:23 07:40:00", 0x9011: "-04:00"}
    path = tmp_path / "phone.jpg"
    Image.new("RGB", (64, 48)).save(path, "JPEG", exif=exif.tobytes())
    lat, lon, error, taken = read_exif(path)
    assert lat == pytest.approx(40.67667, abs=1e-4) and lon == pytest.approx(-73.98400, abs=1e-4)
    assert error == 7.0 and taken == datetime(2026, 8, 23, 11, 40, tzinfo=timezone.utc)


def test_blur_changes_only_the_boxes():
    buffer = io.BytesIO()
    image = Image.new("RGB", (200, 100), (255, 255, 255))
    for x in range(0, 200, 2):
        for y in range(100):
            image.putpixel((x, y), (0, 0, 0))
    image.save(buffer, "PNG")
    blurred = Image.open(io.BytesIO(blur_regions(buffer.getvalue(), [(20, 20, 60, 60)]))).convert("L")
    assert 60 < blurred.getpixel((40, 40)) < 200  # stripes averaged to grey
    assert blurred.getpixel((150, 50)) < 60 or blurred.getpixel((151, 50)) > 200  # stripes kept


def test_observations_record_finds_and_misses():
    photo = photo_at(*SHED, datetime(2026, 2, 10, tzinfo=timezone.utc))
    observed, not_seen = inv.observations_from(
        [("scaffolding", sam_result(BOX_LINE)), ("construction fence", sam_result())], photo, "sidewalk"
    )
    assert [item.id for item in observed] == ["photo:scaffolding"]
    assert observed[0].kind == "observation" and "confidence 0.75" in observed[0].summary
    assert not_seen == ["construction fence"]


def test_sidewalk_checks_cover_agreement_and_both_conflicts():
    seen = [evidence("photo:scaffolding", "seen_scaffolding")]
    permit = [evidence("dobnow:1", "shed_permit", address="218 COURT STREET")]
    when = datetime(2025, 3, 30, tzinfo=timezone.utc)
    assert [f.type for f in sidewalk_checks(seen, permit, [], when)] == ["permit_matches_structure"]
    assert [f.type for f in sidewalk_checks(seen, [], [], when)] == ["structure_without_permit"]
    flags = sidewalk_checks([], permit, [], when)
    assert flags[0].type == "permit_without_structure" and "authorization" in flags[0].message


def test_flood_checks_types_each_disagreement():
    when = datetime(2026, 8, 23, 11, tzinfo=timezone.utc)
    event = evidence("floodnet:1", "flood_event", when - timedelta(hours=1), "flooding")
    complaint = evidence("311:1", "catch_basin", when + timedelta(hours=13), "flooding")
    water = [evidence("photo:water", "seen_water", topic="flooding")]

    def types(observations, hits, rain, state, photo_time=when):
        return {f.type for f in flood_checks(observations, hits, rain, state, photo_time, when)}

    assert "reporting_gap" in types([], [event], 1.0, "found")
    assert "report_without_sensor" in types([], [complaint], 1.0, "nothing_found")
    assert "complaints_lag_sensor" in types([], [event, complaint], 1.0, "found")
    assert "water_without_rain" in types(water, [], 0.0, "nothing_found")
    assert "no_sensor_coverage" in types(water, [], 0.5, "no_coverage")
    assert "different_moments" in types([], [], None, "found", photo_time=when - timedelta(days=500))


def test_sidewalk_records_and_shed_history(store):  # noqa: F811
    when = times.local_day_start(datetime(2026, 2, 10).date())
    hits, coverage, chains, permits = inv.gather_sidewalk(store, *SHED, 50, when)
    categories = {hit.evidence.category for hit in hits}
    assert {"lot", "shed_permit", "shed_complaint"} <= categories
    assert [p.id for p in permits] and chains[0].bin == "3000001"
    assert {c.source for c in coverage} == {"311 sidewalk complaints", "DOB shed, scaffold and fence permits"}


def test_flood_recurrence_counts_each_source(store):  # noqa: F811
    when = datetime(2026, 8, 23, 11, 32, tzinfo=timezone.utc)
    hits, coverage, rec, rain, state = inv.gather_flooding(store, *CORNER, 150, when)
    assert rec["floodnet"]["events"] == 2 and rec["floodnet"]["days"] == 2
    assert rec["floodnet"]["recurring"] is False  # 2 days is below the 3-day definition
    assert rec["street_flood_complaints"]["complaints"] == 1
    assert rain == pytest.approx(0.79) and state == "found"
    assert "floodnet:s0:20210902T001158Z" in rec["evidence_ids"]


def test_whole_investigation_runs_offline(store, tmp_path, monkeypatch):  # noqa: F811
    taken = times.local_day_start(datetime(2026, 2, 10).date())

    async def fake_sam(photo, topic, guard):
        return photo.jpeg, 0, [("scaffolding", sam_result(BOX_LINE)), ("construction fence", sam_result())]

    monkeypatch.setattr(inv, "load_input", lambda source: photo_at(*SHED, taken))
    monkeypatch.setattr(inv, "run_sam", fake_sam)
    monkeypatch.setattr(inv.Store, "load", classmethod(lambda cls: store))
    monkeypatch.setattr(inv, "OUTPUT", tmp_path / "out")
    args = inv.argparse.Namespace(
        source="123", question="What records relate to this blocked sidewalk?", topic=None, lat=None, lon=None,
        taken=None, when=None, radius=None, yes=True,
    )
    result = inv.asyncio.run(inv.investigate(args))
    assert result["topic"] == "sidewalk"
    assert result["flags"][0]["type"] == "permit_matches_structure"
    assert result["shed_chains"][0]["up_since"] == "2025-09-01"
    run_dir = next((tmp_path / "out").iterdir())
    assert {path.name for path in run_dir.iterdir()} == {"photo.jpg", "overlay.png", "result.json"}
