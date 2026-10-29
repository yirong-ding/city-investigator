"""Offline tests for the seven newer topics: wording, sources, store, checks and a whole run.

Rows are made up but use the city's column names, as listed by city_investigator.probe.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from test_data_layer import SHED, store, write  # noqa: F401  (store is a fixture)
from test_investigate import BOX_LINE, photo_at, sam_result

from city_investigator import investigate as inv
from city_investigator import meta, snapshot, web
from city_investigator.checks import topic_checks
from city_investigator.evidence import Evidence, classify_complaint
from city_investigator.socrata import SocrataError
from city_investigator.geo import from_state_plane
from city_investigator.sources import SOURCES, address_key, street_key
from city_investigator.store import FOUND, NO_COVERAGE, PARTIAL, Store
from city_investigator.topics import TOPICS, detect_topic

LAT, LON = SHED
LOT = "3004560012"  # the made-up lot at SHED in the store fixture
WHEN = datetime(2025, 6, 1, 16, tzinfo=timezone.utc)


def at_lot(bbl):
    return (LAT, LON, "1 TEST STREET") if bbl == LOT else (None, None, None)


def to_evidence(name, row):
    return SOURCES[name].to_evidence(row, SOURCES[name].dataset, at_lot)


def seen(concept, topic):
    return Evidence(f"photo:{concept.replace(' ', '_')}", "observation", topic, f"seen_{concept.replace(' ', '_')}",
                    "SAM", "photo", concept, LAT, LON, "photo", WHEN, None, "")


def record(rid, category, topic, start=None, end=None, raw=None, address=None, bbl=None):
    return Evidence(rid, "record", topic, category, "test", "test", rid, LAT, LON, "test", start, end, "",
                    address=address, bbl=bbl, raw=raw or {})


def types(flags):
    return [flag.type for flag in flags]


def test_every_example_question_finds_its_topic():
    for topic in TOPICS.values():
        assert detect_topic(topic.example) == topic.key
    assert detect_topic("Has this broken sidewalk been reported?") == "sidewalk_damage"  # beats a bare "sidewalk"
    assert detect_topic("What records relate to this blocked sidewalk?") == "sidewalk"
    assert detect_topic("Why is the road closed on Broadway?") == "street_construction"  # "road" inside Broadway is ignored


def test_the_districts_own_311_wording_is_matched():
    assert classify_complaint("Damaged Tree", "Branch or Limb Has Fallen Down") == ("trees", "damaged_tree")
    assert classify_complaint("Outdoor Dining", "Sidewalk Zone Blocked") == ("outdoor_dining", "dining_sidewalk_blocked")
    assert classify_complaint("Outdoor Dining", "Barrier Condition") == ("outdoor_dining", "dining_complaint")
    assert classify_complaint("Street Condition", "Pothole") == ("potholes", "pothole")
    assert classify_complaint("Street Condition", "Plate Condition - Shifted") == ("street_construction", "road_plate")
    assert classify_complaint("Sidewalk Condition", "Pedestrian Ramp Defective") == ("curb_ramps", "ramp_defective")
    assert classify_complaint("General Construction/Plumbing", "Debris - Falling Or In Danger Of Falling") == ("facades", "falling_debris")
    assert classify_complaint("Curb Condition", "Defacement") is None
    assert "Damaged Tree" in snapshot.plan()[1].wheres({})[0]  # the 311 download asks for the new types


def test_each_source_reads_its_rows():
    point = {"type": "Point", "coordinates": [LON, LAT]}
    tree = to_evidence("tree_points", {"globalid": "{T1}", "genusspecies": "Platanus x acerifolia - London planetree",
                                       "dbh": "24", "tpcondition": "Fair", "tpstructure": "Full", "location": point,
                                       "updateddate": "2026-05-01T00:00:00.000"})
    assert tree.category == "tree_inventory" and tree.start is None and tree.lat == pytest.approx(LAT)
    assert "London planetree, trunk 24 in across, condition Fair" in tree.summary

    inspection = to_evidence("tree_inspections", {"globalid": "{I1}", "geometry": f"POINT ({LON} {LAT})",
                                                  "inspectiondate": "2025-05-02T00:00:00.000", "inspectiontpcondition": "Poor"})
    assert inspection.lat == pytest.approx(LAT) and "tree condition Poor" in inspection.summary

    order = to_evidence("tree_work_orders", {"globalid": "{W1}", "bbl": LOT, "createddate": "2025-01-05T00:00:00.000",
                                             "canceldate": "2025-02-01T00:00:00.000", "cancelreason": "Duplicate", "wotype": "Tree Removal"})
    assert order.located_by == "tree" and order.lat == LAT and "canceled 2025-02-01 (Duplicate)" in order.summary

    filing = to_evidence("facade_filings", {"tr6_no": "TR6-1", "block": "456", "lot": "12", "cycle": "9",
                                            "filing_date": "03/01/2024", "filing_status": "UNSAFE", "bin": "3000001"})
    assert filing.bbl == LOT and "UNSAFE (unsafe)" in filing.summary and filing.address == "1 TEST STREET"

    violation = to_evidence("sidewalk_violations", {"violationid": "V1", "lot_bbl": LOT, "vissuedate": "2024-04-01T00:00:00.000",
                                                    "trip_haz": "Y", "broken": "N", "vdismissdate": "2024-09-01T00:00:00.000"})
    assert "trip hazard; dismissed 2024-09-01" in violation.summary and violation.end is not None

    ramp = to_evidence("ramps", {"rampid": "R1", "the_geom": point, "stname1": "COURT ST", "stname2": "UNION ST", "ponding": "Yes"})
    assert ramp.category == "ramp_survey" and "at Court St and Union St" in ramp.summary and "ponding Yes" in ramp.summary

    complaint = to_evidence("ramp_complaints", {"complaint_id": "C1", "block": "456", "lot": "12", "complaint_date": "2025-03-01T00:00:00.000"})
    assert complaint.bbl == LOT

    pothole = to_evidence("pothole_orders", {"defnum": "D1", "rptdate": "2025-04-01T00:00:00.000", "rptclosed": "2025-04-03T00:00:00.000",
                                             "the_geom": {"type": "MultiLineString", "coordinates": [[[LON, LAT], [LON + 0.001, LAT]]]},
                                             "onprimname": "COURT STREET", "frmprimnam": "UNION STREET", "toprimname": "PRESIDENT STREET"})
    assert pothole.lon == pytest.approx(LON + 0.0005) and "on Court Street between Union Street and President Street" in pothole.summary

    permit = to_evidence("street_permits", {"permitnumber": "P1", "permittypedesc": "PLATES", "issuedworkstartdate": "2025-05-20T00:00:00.000",
                                            "issuedworkenddate": "2025-06-20T00:00:00.000", "latitude": str(LAT), "longitude": str(LON),
                                            "located_by": "house number"})
    assert permit.category == "street_permit" and "work allowed 2025-05-20 to 2025-06-20" in permit.summary
    assert permit.lat == LAT and permit.located_by == "house number"

    closure = to_evidence("street_closures", {"uniqueid": "U1", "work_start_date": "2025-05-01T00:00:00.000", "the_geom": point})
    license_ = to_evidence("dining_licenses", {"bbl": LOT, "license_type": "Roadway", "license_status": "Active",
                                               "license_issue_date": "2024-09-01T00:00:00.000", "license_expiration_date": "2026-09-01T00:00:00.000",
                                               "location": {"latitude": str(LAT), "longitude": str(LON)}})
    inspection_ = to_evidence("dining_inspections", {"restaurantinspectionid": "X1", "inspectedon": "2022-06-01T00:00:00.000",
                                                     "latitude": str(LAT), "longitude": str(LON), "issidewaycompliant": "No"})
    assert closure.category == "street_closure" and license_.address == "1 TEST STREET"
    assert "sidewalk seating compliant: No" in inspection_.summary
    assert to_evidence("pothole_orders", {"defnum": "D2"}) is None  # no date or place: skipped


class Dining:
    """A data portal where the district is written '06 BROOKLYN' and one form is a type error."""

    def __init__(self):
        self.asked = []

    def rows(self, dataset, where):
        self.asked.append(where)
        if "306 BROOKLYN" in where:
            raise SocrataError("type mismatch", 400)
        return [{"bbl": LOT, "community_board": "06 BROOKLYN"}] if "06 BROOKLYN" in where else []


def test_snapshot_tries_each_way_of_writing_the_district():
    step = next(step for step in snapshot.plan() if step.name == "dining_licenses")
    client = Dining()
    where, rows = snapshot.fetch_step(client, step, {})
    assert where == "community_board = '06 BROOKLYN'" and rows[0]["bbl"] == LOT
    assert len(client.asked) == 4  # '306' and 306 matched nothing, '306 BROOKLYN' was refused


# A 10 Street segment in State Plane feet, and where pyproj puts it (EPSG:2263 to EPSG:4326).
SEGMENT_FT = (989222.0208, 182026.3822)
SEGMENT_DEG = (40.666295666, -73.982077706)


def test_state_plane_feet_become_degrees():
    assert from_state_plane(*SEGMENT_FT) == pytest.approx(SEGMENT_DEG, abs=1e-7)
    assert from_state_plane(1_000_000, 200_000) == pytest.approx((40.715616479, -73.943185068), abs=1e-7)


def test_street_names_are_compared_in_one_spelling():
    assert street_key("7TH ST.") == street_key("7 STREET") == "7 STREET"
    assert street_key("E 53RD ST") == "EAST 53 STREET" and street_key("GOETHALS AVE.") == "GOETHALS AVENUE"
    assert street_key("AVENUE S") == "AVENUE S" and street_key("ST MARKS PL") == "SAINT MARKS PLACE"
    assert address_key(" 556 ", "henry st") == "556 HENRY STREET" and address_key("", "HENRY STREET") is None
    assert snapshot.house_and_street("253  4 AVENUE") == ("253", "4 AVENUE")
    assert snapshot.house_and_street("COURT STREET") is None


def district_lots(*extra):
    """Two lots on Court Street and two on Union Street, meeting at a corner."""
    lots = [
        (LOT, "1 COURT STREET", LAT, LON),
        ("3004560013", "3 COURT STREET", LAT + 0.0004, LON),
        ("3004560014", "5 UNION STREET", LAT + 0.0001, LON + 0.0003),
        ("3004560015", "7 UNION STREET", LAT + 0.0001, LON + 0.0008),
        *extra,
    ]
    return {"pluto": [{"bbl": bbl, "address": address, "latitude": str(lat), "longitude": str(lon)} for bbl, address, lat, lon in lots]}


class BoardNumber:
    """A portal that records the board number without a borough, as DOT's sidewalk datasets do."""

    def rows(self, dataset, where):
        if not where.startswith("cb = 6 "):
            return []
        return [
            {"violationid": "V1", "house_num": "1", "onstname": "COURT ST.", "frstname": "UNION ST", "tostname": "PRESIDENT ST"},
            {"violationid": "V2", "house_num": "3", "onstname": "COURT STREET", "frstname": "EAST 33 STREET"},  # another borough
            {"violationid": "V3", "house_num": "325", "onstname": "EAST 53 STREET"},  # not a district address
        ]


def test_sidewalk_records_are_matched_to_district_lots_by_address():
    step = next(step for step in snapshot.plan() if step.name == "sidewalk_violations")
    where, rows = snapshot.fetch_step(BoardNumber(), step, district_lots())
    assert where == "cb = 6 AND vissuedate >= '2015-01-01T00:00:00'"
    assert [(row["violationid"], row["lot_bbl"]) for row in rows] == [("V1", LOT)]
    violation = to_evidence("sidewalk_violations", {**rows[0], "vissuedate": "2024-04-01T00:00:00.000"})
    assert violation.bbl == LOT and violation.lat == LAT
    damage = next(step for step in snapshot.plan() if step.name == "tree_sidewalk_damage")
    assert damage.select({"atdid": "A1", "house_num": "3", "onstname": "COURT ST."}, district_lots())["lot_bbl"] == "3004560013"


class Permits:
    """Street permits on the district's streets: a mapped segment, or only a house number or cross streets."""

    def __init__(self):
        self.asked = []

    def rows(self, dataset, where):
        self.asked.append(where)
        x, y = SEGMENT_FT
        return [
            {"permitnumber": "P1", "onstreetname": "10 STREET", "wkt": f"LINESTRING ({x} {y}, {x} {y})"},
            {"permitnumber": "P2", "onstreetname": "COURT STREET", "permithousenumber": "3"},
            {"permitnumber": "P3", "onstreetname": "COURT STREET", "fromstreetname": "UNION ST", "tostreetname": "SACKETT STREET"},
            {"permitnumber": "P4", "onstreetname": "5 AVENUE", "permithousenumber": "8000", "fromstreetname": "80 STREET"},
            {"permitnumber": "P5", "onstreetname": "COURT STREET"},  # nothing to place it by
        ]


def test_street_permits_are_placed_by_segment_house_number_or_cross_streets():
    step = next(step for step in snapshot.plan() if step.name == "street_permits")
    done = district_lots(("3010000001", "400 10 STREET", *SEGMENT_DEG))
    assert "onstreetname IN ('COURT STREET', 'UNION STREET')" in step.wheres(done)[0]  # a street on one lot only is left out
    client = Permits()
    where, rows = snapshot.fetch_step(client, step, done)
    assert "onstreetname IN" in where and len(client.asked) == 1
    placed = {row["permitnumber"]: (float(row["latitude"]), float(row["longitude"]), row["located_by"]) for row in rows}
    assert set(placed) == {"P1", "P2", "P3"}
    assert placed["P1"] == pytest.approx((*SEGMENT_DEG, "street segment"))
    assert placed["P2"] == (pytest.approx(LAT + 0.0004), pytest.approx(LON), "house number")
    assert placed["P3"] == (pytest.approx(LAT + 0.00005), pytest.approx(LON + 0.00015), "cross streets")  # the Union Street corner


def test_borough_wide_filings_keep_only_the_districts_lots():
    step = next(step for step in snapshot.plan() if step.name == "facade_filings")
    done = {"pluto": [{"bbl": "3004560012.00000000", "latitude": str(LAT), "longitude": str(LON)}]}
    assert step.select({"block": "456", "lot": "12"}, done)
    assert step.select({"block": "999", "lot": "1"}, done) is None
    assert "intersects" in next(s for s in snapshot.plan() if s.name == "pothole_orders").wheres(done)[0]
    box = snapshot.district_box(done)
    assert box[0] < LAT < box[2] and box[1] < LON < box[3]


def write_sources(folder):
    point = {"type": "Point", "coordinates": [LON, LAT]}
    write(folder, "tree_points", [{"globalid": "{T1}", "genusspecies": "Acer - maple", "tpcondition": "Poor", "location": point}], "hn5i-inap")
    write(folder, "pothole_orders", [
        {"defnum": "D1", "rptdate": "2025-04-01T00:00:00.000", "rptclosed": "2025-04-03T00:00:00.000", "the_geom": point},
    ], "x9wy-ing4")
    write(folder, "facade_filings", [
        {"tr6_no": "TR6-1", "block": "456", "lot": "12", "filing_date": "03/01/2024", "filing_status": "UNSAFE"},
    ], "xubg-57si")


def test_store_finds_the_new_records_and_says_what_is_missing(store, tmp_path):  # noqa: F811
    write_sources(tmp_path)
    loaded = Store.load(tmp_path)
    result = loaded.near(LAT, LON, 30, WHEN - timedelta(days=365), WHEN, "trees")
    assert [hit.evidence.category for hit in result.hits if hit.evidence.topic == "trees"] == ["tree_inventory"]
    notes = {note.source: note for note in result.coverage}
    assert notes["Parks street tree inventory"].state == FOUND
    assert notes["Parks tree inspections"].state == NO_COVERAGE and "--only tree_inspections" in notes["Parks tree inspections"].note
    assert "311 street tree complaints" in notes
    facades = {note.source: note for note in loaded.near(40.70, -73.99, 40, None, None, "facades").coverage}
    assert facades["Façade inspection filings (Local Law 11)"].state == PARTIAL  # low buildings never file
    assert "six stories" in facades["Façade inspection filings (Local Law 11)"].note


def test_new_topic_checks():
    fixed = record("pothole_orders:D1", "pothole_repair", "potholes", WHEN - timedelta(days=60), WHEN - timedelta(days=58))
    pothole = seen("pothole", "potholes")
    flags = topic_checks("potholes", [pothole], [fixed], WHEN, {fixed.id: 5})
    assert types(flags) == ["seen_not_reported", "closed_but_still_seen"]
    assert "closed on 2025-04-04" in flags[1].message

    complaints = [record(f"311:{n}", "pothole", "potholes", WHEN - timedelta(days=10 * n)) for n in (1, 2, 3)]
    assert types(topic_checks("potholes", [], complaints, WHEN)) == ["reported_not_seen", "repeat_reports"]
    assert types(topic_checks("potholes", [pothole], complaints, WHEN))[0] == "reported_and_seen"

    structure = seen("outdoor dining structure", "outdoor_dining")
    license_ = record("dining_licenses:L1", "dining_license", "outdoor_dining", WHEN - timedelta(days=200), WHEN + timedelta(days=200))
    assert "licensed_and_seen" in types(topic_checks("outdoor_dining", [structure], [license_], WHEN))
    assert "seen_without_license" in types(topic_checks("outdoor_dining", [structure], [], WHEN))
    before_program = datetime(2023, 6, 1, tzinfo=timezone.utc)
    assert "seen_without_license" not in types(topic_checks("outdoor_dining", [structure], [], before_program))

    unsafe = record("facade_filings:1", "facade_filing", "facades", WHEN - timedelta(days=400), raw={"filing_status": "UNSAFE"},
                    address="1 TEST STREET", bbl=LOT)
    assert types(topic_checks("facades", [seen("scaffolding", "facades")], [unsafe], WHEN))[-1] == "facade_unsafe_protected"
    assert types(topic_checks("facades", [], [unsafe], WHEN)) == ["facade_unsafe_unprotected"]
    safe_later = record("facade_filings:2", "facade_filing", "facades", WHEN - timedelta(days=30), raw={"filing_status": "SAFE"}, bbl=LOT)
    assert topic_checks("facades", [], [unsafe, safe_later], WHEN) == []  # the latest filing counts

    tree = record("tree_points:T1", "tree_inventory", "trees")
    assert types(topic_checks("trees", [seen("tree", "trees")], [tree], WHEN, {tree.id: 5})) == ["inventory_tree_nearby"]
    assert topic_checks("trees", [seen("tree", "trees")], [tree], WHEN, {tree.id: 20}) == []

    ramp = record("ramps:R1", "ramp_survey", "curb_ramps", raw={"ponding": "Yes"})
    assert "ramp_ponding_recorded" in types(topic_checks("curb_ramps", [seen("puddle", "curb_ramps")], [ramp], WHEN, {ramp.id: 4}))


def test_a_whole_pothole_investigation_runs_offline(store, tmp_path, monkeypatch):  # noqa: F811
    write_sources(tmp_path)
    loaded = Store.load(tmp_path)

    async def fake_sam(photo, topic, guard, progress=print):
        assert topic == "potholes"
        return photo.jpeg, 0, [("pothole", sam_result(BOX_LINE)), ("cracked asphalt", sam_result()), ("manhole cover", sam_result())]

    monkeypatch.setattr(inv, "run_sam", fake_sam)
    monkeypatch.setattr(inv, "OUTPUT", tmp_path / "runs")
    monkeypatch.setattr(meta, "LEDGER", tmp_path / "spend.json")
    photo = photo_at(LAT, LON, WHEN)
    result, run_dir = inv.asyncio.run(inv.investigate_photo(photo, "Was this pothole ever fixed?", store=loaded, progress=lambda m: None))
    assert result["topic"] == "potholes" and result["topic_label"] == "Potholes and road damage" and result["radius_m"] == 40
    assert "closed_but_still_seen" in [flag["type"] for flag in result["flags"]]
    assert any(note["source"] == "DOT pothole work orders (closed)" and note["state"] == FOUND for note in result["coverage"])
    saved = json.loads((run_dir / "result.json").read_text())
    assert saved["records"][0]["id"].startswith(("pothole_orders:", "pluto:"))


def test_the_page_lists_topics_and_groups_new_records():
    client = TestClient(web.create_app(web.State(store=None)))
    listed = client.get("/api/topics").json()
    assert len(listed) == 9 and listed[2] == {"key": "trees", "label": "Street trees", "example": "Has this tree been reported before?"}
    assert web.group({"id": "pothole_orders:D1", "category": "pothole_repair"}) == "agency"
    assert web.group({"id": "street_permits:P1", "category": "street_permit"}) == "permit"
    assert web.group({"id": "dining_licenses:x", "category": "dining_license"}) == "permit"
    assert web.group({"id": "tree_points:T1", "category": "tree_inventory"}) == "inventory"
    assert web.group({"id": "311:1", "category": "pothole"}) == "complaint"


def test_a_snapshot_that_finds_nothing_says_what_each_query_matched():
    step = next(step for step in snapshot.plan() if step.name == "sidewalk_violations")
    tried = []

    class Elsewhere:
        def rows(self, dataset, where):
            if where.startswith("cb = 6 "):
                raise SocrataError("type mismatch", 400)
            return [{"violationid": "V3", "house_num": "325", "onstname": "EAST 53 STREET"}]

    where, rows = snapshot.fetch_step(Elsewhere(), step, district_lots(), tried)
    assert rows == [] and "refused (HTTP 400)" in tried[0] and "1 matched, 0 kept" in tried[1]


class Portal:
    """Answers the probe's questions about the sidewalk violations dataset."""

    def __init__(self):
        self.session = self

    def json(self):
        return {"columns": [{"fieldName": "cb", "dataTypeName": "number"}, {"fieldName": "house_num", "dataTypeName": "text"}]}

    def get(self, dataset, params=None, timeout=None):
        if params is None:  # the column types
            return self
        where = params.get("$where", "")
        if "$group" in params:
            return [{"cb": "6", "n": "900"}, {"cb": "1", "n": "800"}]
        if where.startswith("cb = '6'"):
            raise SocrataError("type mismatch", 400)
        matching = [{"cb": "6", "house_num": "325", "onstname": "EAST 53 STREET"}] if where.startswith("cb = 6 ") else []
        if params.get("$select") == "count(*) AS n":
            return [{"n": str(len(matching))}]
        return matching if where else [{"cb": "6", "house_num": "1", "onstname": "COURT ST", "vissuedate": "2024-01-01"}]


def test_probe_look_shows_types_values_and_what_each_query_keeps():
    from city_investigator import probe

    district = snapshot.district(district_lots())
    text = "\n".join(probe.look(Portal(), "sidewalk_violations", district))
    assert "cb=number" in text and "house_num=text" in text and "'6' (900)" in text
    assert "refused (HTTP 400)" in text
    assert "cb = 6 AND vissuedate >= '2015-01-01T00:00:00': 1 rows; of 1 read, 0 in the district" in text
    assert "e.g. cb='6'; house_num='325'; onstname='EAST 53 STREET'" in text
