"""Offline tests for the data layer, using small made-up snapshots (not real records)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from city_investigator import snapshot, times
from city_investigator.evidence import classify_complaint, norm_bbl, norm_bin
from city_investigator.geo import distance_m
from city_investigator.photos import parse_photo
from city_investigator.sheds import build_chains
from city_investigator.shortlist import flood_sites, shed_sites
from city_investigator.socrata import SocrataError
from city_investigator.store import FOUND, NO_COVERAGE, Store

CORNER = (40.6787, -73.9830)  # made-up "Test St/Example Av" corner
SHED = (40.6800, -73.9850)
NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def write(folder, name, rows, dataset="test-set"):
    payload = {"name": name, "dataset": dataset, "retrieved_at": "2026-10-27T12:00:00+00:00", "rows": rows}
    (folder / f"{name}.json").write_text(json.dumps(payload))


def permit(start, end, bin_="3000001", work_type="Sidewalk Shed"):
    return {
        "work_type": work_type,
        "permit_status": "Permit Issued",
        "issued_date": f"{start}T00:00:00.000",
        "expired_date": f"{end}T00:00:00.000",
        "job_filing_number": f"B0000{start.replace('-', '')}-I1",
        "bin": bin_,
        "bbl": "3004560012",
        "house_no": "1",
        "street_name": "TEST STREET",
        "latitude": str(SHED[0]),
        "longitude": str(SHED[1]),
    }


@pytest.fixture
def store(tmp_path):
    write(tmp_path, "floodnet_sensors", [
        {"sensor_id": "s1", "sensor_name": "Test St/Example Av", "latitude": str(CORNER[0]), "longitude": str(CORNER[1]),
         "date_installed": "2023-05-01T00:00:00.000"},
        {"sensor_id": "s0", "sensor_name": "Test St/Example Av", "latitude": "40.67875", "longitude": "-73.98305",
         "date_installed": "2021-06-01T00:00:00.000", "date_removed": "2022-06-01T00:00:00.000"},
        {"sensor_id": "s2", "sensor_name": "Far St/Away Av", "latitude": "40.7000", "longitude": "-73.9500",
         "date_installed": "2024-01-01T00:00:00.000"},
    ])
    write(tmp_path, "floodnet_events", [
        {"sensor_id": "s1", "flood_start_time": "2026-08-23T11:32:24.000", "max_depth_inches": "35.94"},
        {"sensor_id": "s0", "flood_start_time": "2021-09-02T00:11:58.000", "max_depth_inches": "27.76"},
    ])
    write(tmp_path, "311_2020_on", [
        {"unique_key": "1001", "created_date": "2026-08-23T07:40:00.000", "closed_date": "2026-08-25T10:00:00.000",
         "complaint_type": "Sewer", "descriptor": "Street Flooding (SJ)", "status": "Closed",
         "latitude": "40.6790", "longitude": "-73.9832", "address_type": "INTERSECTION"},
        {"unique_key": "1002", "created_date": "2026-02-10T09:00:00.000",
         "complaint_type": "General Construction/Plumbing",
         "descriptor": "Sidewalk Shed/Pipe Scafford - Inadequate Defective/None", "status": "Open",
         "latitude": "40.68005", "longitude": "-73.98505", "address_type": "ADDRESS", "bbl": "3004560012"},
        {"unique_key": "1003", "created_date": "2026-03-01T09:00:00.000", "complaint_type": "Noise - Residential",
         "descriptor": "Loud Music/Party", "latitude": "40.6790", "longitude": "-73.9832"},
    ])
    write(tmp_path, "dob_now_permits", [
        permit("2025-01-01", "2025-03-31"),
        permit("2025-04-15", "2025-07-14"),  # 15-day gap: paperwork delay
        permit("2025-09-01", "2025-11-30"),  # 49-day gap: a new run
        permit("2025-12-10", "2026-12-31"),
    ])
    write(tmp_path, "dob_legacy_permits", [
        {"permit_subtype": "SH", "issuance_date": "03/01/2015", "expiration_date": "05/30/2015", "bin__": "3000002",
         "job__": "300000001", "house__": "9", "street_name": "OLD STREET", "gis_latitude": "40.6810",
         "gis_longitude": "-73.9860"},
    ])
    write(tmp_path, "pluto", [
        {"bbl": "3004560012.00000000", "address": "1 TEST STREET", "bldgclass": "C1", "yearbuilt": "1910",
         "numfloors": "4", "ownertype": "P", "latitude": str(SHED[0]), "longitude": str(SHED[1]), "version": "25v4"},
    ])
    write(tmp_path, "rainfall", [
        {"valid_utc": "2026-08-23 10:51", "inches": 0.30},
        {"valid_utc": "2026-08-23 11:51", "inches": 0.49},
    ])
    return Store.load(tmp_path)


def window(first, last):
    return times.local_day_start(date.fromisoformat(first)), times.local_day_end(date.fromisoformat(last))


def by_source(result):
    return {item.source: item for item in result.coverage}


def test_times_convert_local_and_utc_correctly():
    assert times.parse("2026-08-23T07:40:00.000") == datetime(2026, 8, 23, 11, 40, tzinfo=timezone.utc)
    assert times.parse("2026-08-23T11:32:24.000", "utc") == datetime(2026, 8, 23, 11, 32, 24, tzinfo=timezone.utc)
    assert times.parse("03/01/2015") == datetime(2015, 3, 1, 5, tzinfo=timezone.utc)
    assert times.parse("") is None


def test_distance_is_in_meters():
    assert distance_m(40.0, -74.0, 40.001, -74.0) == pytest.approx(111.2, abs=0.5)


def test_complaint_strings_match_exactly():
    assert classify_complaint(
        "General Construction/Plumbing", "Sidewalk Shed/Pipe Scafford - Inadequate Defective/None"
    ) == ("sidewalk", "shed_complaint")
    assert classify_complaint("Obstruction", "Anything") == ("sidewalk", "obstruction")
    assert classify_complaint("Sewer Maintenance", "Backup") == ("flooding", "sewer_backup")
    assert classify_complaint("Noise - Residential", "Loud Music/Party") is None


def test_identifiers_are_normalized():
    assert norm_bbl("3004560012.00000000") == "3004560012"
    assert norm_bbl("0") is None
    assert norm_bin("3000000") is None  # placeholder
    assert norm_bin("3000001") == "3000001"


def test_flood_lookup_finds_records_and_rain(store):
    start, end = window("2026-08-22", "2026-08-26")
    result = store.near(*CORNER, 150, start, end, "flooding")
    categories = result.categories()
    assert categories["flood_event"] == 1
    assert categories["street_flooding"] == 1
    assert categories["rainfall"] == 1
    coverage = by_source(result)
    assert coverage["311 flooding complaints"].state == FOUND
    assert coverage["FloodNet flood sensors"].state == FOUND
    assert coverage["Rainfall"].state == FOUND
    rain = next(hit.evidence for hit in result.hits if hit.evidence.category == "rainfall")
    assert "0.79 in" in rain.summary


def test_no_sensor_nearby_is_no_coverage(store):
    result = store.near(40.6600, -74.0200, 150, topic="flooding")
    note = by_source(result)["FloodNet flood sensors"]
    assert note.state == NO_COVERAGE
    assert "nearest is" in note.note


def test_window_before_installation_is_no_coverage(store):
    start, end = window("2020-06-01", "2020-06-30")
    note = by_source(store.near(*CORNER, 150, start, end, "flooding"))["FloodNet flood sensors"]
    assert note.state == NO_COVERAGE
    assert "unobserved, not absent" in note.note


def test_recent_window_warns_about_review_lag(store):
    start, end = window("2026-10-01", "2026-10-26")
    note = by_source(store.near(*CORNER, 150, start, end, "flooding"))["FloodNet flood sensors"]
    assert "pending review" in note.note


def test_replaced_sensor_history_is_kept(store):
    result = store.near(*CORNER, 150, topic="flooding")
    starts = sorted(hit.evidence.start.year for hit in result.hits if hit.evidence.category == "flood_event")
    assert starts == [2021, 2026]


def test_311_outside_loaded_years_is_no_coverage(store):
    start, end = window("2015-01-01", "2015-12-31")
    note = by_source(store.near(*SHED, 50, start, end, "sidewalk"))["311 sidewalk complaints"]
    assert note.state == NO_COVERAGE


def test_shed_chain_bridges_short_gaps_only(store):
    chains = {chain.bin: chain for chain in build_chains(store.evidence)}
    chain = chains["3000001"]
    assert times.to_local(chain.up_since).date() == date(2025, 9, 1)
    assert len(chain.runs) == 2 and len(chain.gaps) == 1
    assert (chain.gaps[0][1] - chain.gaps[0][0]).days == 49
    assert chain.active(NOW)
    assert len(chain.permits_in_current_run()) == 2
    assert not chains["3000002"].active(NOW)  # the 2015 legacy permit, parsed from MM/DD/YYYY


def test_shortlist_ranks_active_sheds_and_flood_corners(store):
    sheds = shed_sites(store, NOW, 5)
    assert [site["bin"] for site in sheds] == ["3000001"]
    assert sheds[0]["complaints_nearby_since"] == {"shed_complaint": 1}
    floods = flood_sites(store, 5)
    assert floods[0]["sensor"] == "Test St/Example Av"
    assert floods[0]["events"] == 2 and floods[0]["max_depth_in"] == 35.94


def test_building_lookup_matches_permits_and_lot(store):
    result = store.for_building(bin_="3000001")
    assert result.categories()["shed_permit"] == 4
    result = store.for_building(bbl="3004560012", topic="sidewalk")
    assert result.categories()["lot"] == 1


class FakeClient:
    def __init__(self, rows, fail_first_with=None):
        self.rows_to_return = rows
        self.fail_first_with = fail_first_with
        self.wheres = []

    def rows(self, dataset, where):
        self.wheres.append(where)
        if self.fail_first_with and len(self.wheres) == 1:
            raise SocrataError("bad query", self.fail_first_with)
        return self.rows_to_return


def test_snapshot_drops_owner_names_and_falls_back_on_bad_query():
    step = next(step for step in snapshot.plan() if step.name == "pluto")
    client = FakeClient([{"bbl": "3004560012", "ownername": "A PERSON"}], fail_first_with=400)
    where, rows = snapshot.fetch_step(client, step, {})
    assert where == "cd = 306" and rows == [{"bbl": "3004560012"}]


def test_snapshot_keeps_only_known_complaints():
    step = next(step for step in snapshot.plan() if step.name == "311_2020_on")
    client = FakeClient([
        {"complaint_type": "Sewer", "descriptor": "Street Flooding (SJ)"},
        {"complaint_type": "Sewer", "descriptor": "Sewer Odor (SA2)"},
    ])
    _, rows = snapshot.fetch_step(client, step, {})
    assert len(rows) == 1


def test_mapillary_photo_is_parsed_with_credit():
    item = {"id": "123", "captured_at": 1755936000000, "computed_geometry": {"type": "Point", "coordinates": [-73.983, 40.6787]},
            "creator": {"username": "tester"}, "thumb_1024_url": "https://example.test/img.jpg"}
    photo = parse_photo(item, *CORNER)
    assert photo["credit"] == "Photo by tester, Mapillary, CC BY-SA 4.0"
    assert photo["distance_m"] == 0 and photo["captured_at"].startswith("2025-08-23")


def test_old_window_has_no_review_warning(store):
    start, end = window("2026-08-22", "2026-08-26")
    note = by_source(store.near(*CORNER, 150, start, end, "flooding"))["FloodNet flood sensors"]
    assert "pending review" not in note.note
    assert note.note.startswith("1 flood event at")


def test_install_dates_are_new_york_calendar_dates(store):
    sensor = next(s for s in store.sensors if s.id == "s0")
    assert times.to_local(sensor.installed).date() == date(2021, 6, 1)


def test_photo_period_relative_to_shed_permits():
    from city_investigator.shortlist import photo_period

    site = {"up_since": "2022-07-14", "permit_valid_until": "2026-12-31"}
    assert photo_period({"captured_at": "2025-03-30T10:00:00+00:00"}, site) == "while shed permits were valid"
    assert photo_period({"captured_at": "2020-02-12T10:00:00+00:00"}, site) == "before the current shed permits"
    assert photo_period({"captured_at": "2020-02-12T10:00:00+00:00"}, {}) is None


def test_floors_are_whole_numbers():
    from city_investigator.evidence import floors_text

    assert floors_text("1.0000000") == "1 floor"
    assert floors_text("4.5") == "4.5 floors"
    assert floors_text("0") is None


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.params = []

    def get(self, url, params, timeout):
        self.params.append(params)
        return FakeResponse(self.bodies.pop(0))


def test_photo_search_asks_for_many_and_retries_empty_answers(monkeypatch):
    from city_investigator import photos

    monkeypatch.setattr(photos.time, "sleep", lambda seconds: None)
    item = {"id": "1", "captured_at": 1755936000000, "computed_geometry": {"coordinates": [-73.983, 40.6787]}}
    session = FakeSession([{"data": []}, {"data": [item]}])
    found = photos.photos_near(*CORNER, token="t", session=session)
    assert len(found) == 1 and len(session.params) == 2
    assert session.params[0]["limit"] >= 1000


def test_photo_search_reports_errors_instead_of_no_photos():
    from city_investigator import photos

    session = FakeSession([{"error": {"message": "rate limit"}}])
    with pytest.raises(RuntimeError, match="Mapillary error"):
        photos.photos_near(*CORNER, token="t", session=session)


def test_photo_facing_uses_camera_direction():
    north_of_site = {"id": "a", "computed_geometry": {"coordinates": [CORNER[1], CORNER[0] + 0.0002]}}
    looking_south = parse_photo(north_of_site | {"compass_angle": 180}, *CORNER)
    looking_north = parse_photo(north_of_site | {"compass_angle": 0}, *CORNER)
    panorama = parse_photo(north_of_site | {"compass_angle": 0, "is_pano": True}, *CORNER)
    assert looking_south["faces_site"] is True
    assert looking_north["faces_site"] is False
    assert panorama["faces_site"] is True


def test_best_photos_prefers_close_facing_photos_during_permits():
    from city_investigator.shortlist import best_photos

    site = {"up_since": "2022-07-14", "permit_valid_until": "2026-12-31"}

    def photo(pid, taken, distance, faces):
        return {"id": pid, "captured_at": f"{taken}T12:00:00+00:00", "distance_m": distance, "faces_site": faces}

    chosen = best_photos(
        [
            photo("far-during", "2025-03-30", 35, True),
            photo("near-during", "2025-03-30", 8, True),
            photo("away-during", "2025-03-30", 5, False),
            photo("before", "2018-08-26", 20, True),
        ],
        site,
    )
    assert [p["id"] for p in chosen] == ["near-during", "far-during", "before"]


class FakeBinaryResponse(FakeResponse):
    def __init__(self, body=None, content=b""):
        super().__init__(body)
        self.content = content


def test_photo_check_downloads_image_and_metadata(tmp_path, monkeypatch):
    from city_investigator import photo_check

    monkeypatch.setattr(photo_check, "OUTPUT", tmp_path)

    class Session:
        def get(self, url, params=None, timeout=None):
            if "graph.mapillary.com" in url:
                return FakeBinaryResponse({"id": "42", "thumb_2048_url": "https://images.test/42.jpg"})
            return FakeBinaryResponse(content=b"jpeg-bytes")

    path, meta = photo_check.fetch_image("42", "token", Session())
    assert path == tmp_path / "42.jpg" and path.read_bytes() == b"jpeg-bytes"
    assert meta["thumb_2048_url"].endswith("42.jpg")


def test_photo_check_reports_missing_image(tmp_path, monkeypatch):
    from city_investigator import photo_check

    monkeypatch.setattr(photo_check, "OUTPUT", tmp_path)

    class Session:
        def get(self, url, params=None, timeout=None):
            return FakeBinaryResponse({"error": {"message": "not found"}})

    with pytest.raises(RuntimeError, match="no image for 7"):
        photo_check.fetch_image("7", "token", Session())
