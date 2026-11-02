"""What Valdrada's 3D view draws: sheds with a valid permit, unsafe façades, and scaffolding seen in the photo."""

from __future__ import annotations

import json

import pytest
from test_buildings import LAT, LON, at, footprint

from city_investigator.buildings import Buildings
from city_investigator.photo_input import field_of_view
from city_investigator.scene3d import Local, record_sheds, scene, seen_structures
from city_investigator.scene3d import moment as parse_moment

# A 20 m wide building whose south wall is 15 m north of the camera, and a small one 40 m east.
WIDE = footprint(*at(20, 0), 10, bin_="3000100", half_m=10) | {"base_bbl": "3009670010"}
SMALL = footprint(*at(0, 40), 10, bin_="3000200", half_m=3) | {"base_bbl": "3009670020"}


def moment(day):
    return {"utc": f"{day}T05:00:00+00:00", "local": f"{day} 00:00"}


def run(heading=0.0, size=(1000, 750), fov=90.0, boxes=None, flags=(), records=()):
    return {
        "topic": "sidewalk",
        "photo": {
            "location": {"lat": LAT, "lon": LON, "uncertainty_m": 5}, "heading_deg": heading, "size": list(size),
            "fov_deg": fov, "taken_at": "2026-02-10T15:00:00+00:00", "taken_local": "2026-02-10 10:00",
        },
        "observations": [{"id": "photo:scaffolding", "category": "seen_scaffolding", "boxes": boxes or []}],
        "flags": list(flags),
        "records": list(records),
    }


def wall_points(item):
    local = Local(LAT, LON)
    return [tuple(round(v, 1) for v in local.xy(*item[end])) for end in ("a", "b")]


def test_scaffolding_in_a_photo_lands_on_the_building_front_it_points_at():
    buildings = Buildings.from_rows([WIDE, SMALL])
    # a 90° lens facing north; the box spans columns 400 to 600, 11.3° either side of straight ahead
    [item] = seen_structures(run(boxes=[{"left": 400, "right": 600, "top": 100, "bottom": 500}]), buildings)
    (ax, ay), (bx, by) = sorted(wall_points(item))
    assert ay == by == pytest.approx(10, abs=0.2)  # on the south wall (10 m: the building's center less half its depth)
    assert (ax, bx) == (pytest.approx(-2.0, abs=0.2), pytest.approx(2.0, abs=0.2)) and item["distance_m"] == 10
    assert item["label"] == "Seen in the photo, 2026-02-10"


def test_a_panorama_turns_a_full_circle_and_a_narrow_box_still_makes_a_shed():
    buildings = Buildings.from_rows([WIDE, SMALL])
    # heading east; north is a quarter of the way across a 2:1 panorama
    [item] = seen_structures(run(heading=90, size=(2000, 1000), fov=None, boxes=[{"left": 499, "right": 501, "top": 0, "bottom": 9}]), buildings)
    (ax, _), (bx, _) = sorted(wall_points(item))
    assert bx - ax == pytest.approx(3.0, abs=0.1)  # Valdrada's shortest shed
    # pointing east the line of sight meets the small building's west wall at 37 m
    [east] = seen_structures(run(heading=90, size=(2000, 1000), fov=None, boxes=[{"left": 990, "right": 1010, "top": 0, "bottom": 9}]), buildings)
    assert east["distance_m"] == 37


def test_nothing_is_placed_without_a_heading_or_a_wall_in_sight():
    buildings = Buildings.from_rows([WIDE])
    box = [{"left": 400, "right": 600, "top": 100, "bottom": 500}]
    assert seen_structures(run(heading=None, boxes=box), buildings) == []
    assert seen_structures(run(heading=180, boxes=box), buildings) == []  # facing south: open street


def test_only_sheds_with_a_permit_valid_on_the_photo_date_are_drawn_once_per_building():
    buildings = Buildings.from_rows([WIDE, SMALL])
    when = run()["photo"]["taken_at"]
    records = [
        {"id": "dobnow:1", "category": "shed_permit", "bin": "3000100", "start": moment("2026-01-02"), "end": moment("2026-04-01"), "address": "1 A ST"},
        {"id": "dobnow:2", "category": "shed_permit", "bin": "3000100", "start": moment("2025-10-01"), "end": moment("2026-03-01")},
        {"id": "dobnow:3", "category": "scaffold_permit", "bin": "3000200", "start": moment("2025-01-02"), "end": moment("2025-04-01")},
        {"id": "dobnow:4", "category": "fence_permit", "bin": "3000200", "start": moment("2026-01-02"), "end": None},
    ]
    [shed] = record_sheds(records, buildings, parse_moment(when))
    assert shed["id"] == "dobnow:1" and shed["label"] == "Shed permit, 2026-01-02 to 2026-04-01" and shed["address"] == "1 A ST"
    assert len(shed["rings"][0]) == 5 and shed["height_m"] == pytest.approx(12.19, abs=0.01)


def test_the_scene_carries_unsafe_facades_from_the_flags_and_no_flood_for_other_topics():
    buildings = Buildings.from_rows([WIDE, SMALL])
    filing = {"id": "fisp:9", "category": "facade_filing", "bbl": "3009670020", "start": moment("2024-05-01")}
    flag = {"type": "facade_unsafe_unprotected", "severity": "conflict", "message": "", "evidence_ids": ["fisp:9"]}
    data = scene(run(flags=[flag], records=[filing]), buildings, None)
    [facade] = data["facades"]
    assert facade["label"] == "Façade filing UNSAFE, 2024-05-01" and data["flood"] is None and data["sheds"] == []
    assert data["center"] == {"lat": LAT, "lon": LON}


def test_mapillary_calibration_gives_the_field_of_view():
    assert field_of_view({"is_pano": True}, (2048, 1024)) == 360
    # focal length 0.5 of the longer side: a 90° lens across a landscape photo
    assert field_of_view({"camera_type": "perspective", "camera_parameters": [0.5, 0, 0]}, (2048, 1536)) == 90
    assert field_of_view({"camera_type": "fisheye", "camera_parameters": [0.5, 0, 0]}, (2048, 1536)) is None
    assert field_of_view({}, (2048, 1536)) is None


def test_the_list_shows_the_newest_run_of_each_photo_with_what_it_draws(tmp_path, monkeypatch, capsys):
    from city_investigator import investigate, scene3d
    from city_investigator.store import Store

    flag = {"type": "facade_unsafe_unprotected", "severity": "conflict", "message": "", "evidence_ids": ["fisp:9"]}
    filing = {"id": "fisp:9", "category": "facade_filing", "bbl": "3009670020", "start": moment("2024-05-01"), "address": "9 B ST"}
    newer = run(flags=[flag], records=[filing]) | {"topic_label": "Unsafe façades"}
    newer["photo"] |= {"ref": "77"}
    older = json.loads(json.dumps(newer))
    del older["photo"]["fov_deg"]  # from before the photo's objects could be placed
    for name, result in (("20261031-100000-77", older), ("20261102-100000-77", newer)):
        (tmp_path / name).mkdir()
        (tmp_path / name / "result.json").write_text(json.dumps(result))
    monkeypatch.setattr(investigate, "OUTPUT", tmp_path)
    monkeypatch.setattr(Store, "load", classmethod(lambda cls, *a, **k: type("S", (), {"buildings": Buildings.from_rows([WIDE, SMALL])})()))
    scene3d.main([])
    assert capsys.readouterr().out == (
        "Unsafe façades at 9 B ST: 0 record pin(s), 0 permitted shed(s), 0 seen in the photo, 1 unsafe façade(s), 0 proposal(s) for After\n"
        "    http://127.0.0.1:8000/#run=20261102-100000-77\n"
    )
    scene3d.main(["--all"])
    listed = capsys.readouterr().out
    assert listed.count("http://") == 2 and "photo: run again to place it" in listed  # the older run, listed too


def test_proposals_are_placed_at_what_they_cite_with_how_to_draw_them():
    buildings = Buildings.from_rows([WIDE, SMALL])
    filing = {"id": "fisp:9", "category": "facade_filing", "bbl": "3009670020", "lat": at(0, 40)[0], "lon": at(0, 40)[1]}
    flag = {"type": "facade_unsafe_unprotected", "severity": "conflict", "message": "", "evidence_ids": ["fisp:9"]}
    tree = {"id": "tree_points:5", "category": "tree_inventory", "lat": at(5, 5)[0], "lon": at(5, 5)[1]}
    complaint = {"id": "311:7", "category": "dead_tree", "lat": at(9, 9)[0], "lon": at(9, 9)[1]}
    explanation = {"evidence": {}, "claims": [
        {"kind": "proposal", "text": "A 311 report could ask DOB to inspect.", "evidence_ids": ["action:311_debris_falling_or", "flag:facade_unsafe_unprotected"]},
        {"kind": "proposal", "text": "Parks could inspect the tree.", "evidence_ids": ["action:311_dead_dying_tree", "311:7", "tree_points:5"]},
        {"kind": "proposal", "text": "Rain gardens could soak up runoff.", "evidence_ids": ["action:green_infrastructure", "311:7"]},
        {"kind": "proposal", "text": "The board could raise it.", "evidence_ids": ["action:community_board", "311:7"]},
        {"kind": "record", "text": "A complaint.", "evidence_ids": ["311:7"]},
    ]}
    data = scene(run(flags=[flag], records=[filing, tree, complaint]), buildings, None, explanation)
    shed, young, gardens, board = data["after"]
    assert shed["draw"] == "shed" and shed["height_m"] and len(shed["rings"][0]) == 5  # the unsafe building's outline
    assert young["draw"] == "young_tree" and young["at"] == [tree["lon"], tree["lat"]]  # the inventory tree, not the lot
    assert gardens["draw"] == "rain_gardens" and gardens["at"] == [LON, LAT]  # around the low spot the photo shows
    assert board["draw"] is None and board["at"] == [complaint["lon"], complaint["lat"]] and board["text"] == "The board could raise it."
    assert scene(run(), buildings, None, None)["after"] == []
    idea = {"evidence": {}, "claims": [{"kind": "proposal", "text": "Netting could replace the shed.", "evidence_ids": ["idea:facade_netting", "311:7"]}]}
    [netting] = scene(run(records=[complaint]), buildings, None, idea)["after"]
    assert netting["idea"] is True and netting["draw"] is None and netting["at"] == [complaint["lon"], complaint["lat"]]


def test_pins_mark_the_cited_records_near_the_place_nearest_first():
    from city_investigator.web import group

    near, far = at(8, 0), at(400, 0)
    records = [
        {"id": "311:1", "category": "pothole", "lat": near[0], "lon": near[1], "start": moment("2026-01-05"), "summary": "Pothole reported"},
        {"id": "pothole_orders:2", "category": "pothole_repair", "lat": at(3, 0)[0], "lon": at(3, 0)[1], "start": moment("2026-01-09"), "summary": "Repaired"},
        {"id": "311:3", "category": "pothole", "lat": far[0], "lon": far[1], "summary": "Far away"},
        {"id": "311:4", "category": "pothole", "lat": near[0], "lon": near[1], "summary": "Not cited"},
        {"id": "dobnow:5", "category": "shed_permit", "lat": near[0], "lon": near[1], "summary": "Drawn as a shed"},
    ]
    flag = {"type": "reported_and_seen", "severity": "agreement", "message": "", "evidence_ids": ["311:1", "311:3", "dobnow:5"]}
    explanation = {"evidence": {}, "claims": [{"kind": "record", "text": "", "evidence_ids": ["pothole_orders:2"]}]}
    pins = scene(run(flags=[flag], records=records), None, None, explanation, group)["markers"]
    assert [pin["id"] for pin in pins] == ["pothole_orders:2", "311:1"]
    assert pins[1]["title"] == "311 complaint, 2026-01-05" and pins[1]["color"] == "#d9480f" and pins[1]["distance_m"] == 8
    assert pins[0]["title"].startswith("Agency inspection, order or filing")
