"""Building footprints: heights for the 3D map, ground elevations for the flood checks."""

from __future__ import annotations

import math

import pytest
from test_data_layer import write

from city_investigator import snapshot
from city_investigator.buildings import Buildings, from_row, slim
from city_investigator.checks import ground_checks
from city_investigator.store import Store

LAT, LON = 40.6762, -73.9841  # Carroll St and 4th Av


def footprint(lat, lon, ground_ft, height_ft=40, bin_="3000001", half_m=4):
    dlat, dlon = half_m / 110_574, half_m / (111_320 * math.cos(math.radians(lat)))
    ring = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat], [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]
    return {"bin": bin_, "base_bbl": "3009670001", "height_roof": str(height_ft), "ground_elevation": str(ground_ft),
            "the_geom": {"type": "MultiPolygon", "coordinates": [[ring]]}, "shape_area": "100", "name": "dropped"}


def at(meters_north, meters_east):
    return LAT + meters_north / 110_574, LON + meters_east / (111_320 * math.cos(math.radians(LAT)))


def district(near_ft=10.0, around_ft=16.0):
    """Three buildings at the corner and twelve on the blocks around it."""
    rows = [footprint(*at(dy, dx), near_ft, bin_=f"30000{n}") for n, (dy, dx) in enumerate([(10, 0), (-15, 5), (0, -20)])]
    rows += [footprint(*at(150 * math.sin(a), 150 * math.cos(a)), around_ft, bin_=f"31000{n}")
             for n, a in enumerate(i * math.pi / 6 for i in range(12))]
    return rows


def test_a_footprint_keeps_only_what_is_used_and_reads_heights_in_meters():
    row = slim(footprint(LAT, LON, 12.345, height_ft=100) | {"the_geom": {"type": "MultiPolygon", "coordinates": [[[[LON + 1e-9, LAT], [LON, LAT + 1e-4], [LON - 1e-4, LAT], [LON + 1e-9, LAT]]]]}})
    assert set(row) == {"bin", "base_bbl", "height_roof", "ground_elevation", "the_geom"}  # shape_area and name dropped
    assert row["the_geom"]["coordinates"][0][0][0] == [round(LON, 6), LAT]
    building = from_row(footprint(LAT, LON, 0, height_ft=100))
    assert building.height_m == pytest.approx(30.48) and building.ground_ft is None  # 0 marks a missing elevation
    assert building.bbl == "3009670001" and len(building.rings) == 1


def test_a_corner_lower_than_its_blocks_is_measured_and_flagged_when_flooding_recurs():
    buildings = Buildings.from_rows(district())
    ground = buildings.ground_here(LAT, LON)
    assert ground.raw["difference_ft"] == -6.0 and ground.raw["share_higher"] == 0.8  # 12 of 15 stand higher
    assert "6.0 ft lower than its surroundings" in ground.summary
    [flag] = ground_checks(ground, ["recurrence:floodnet"])
    assert flag.type == "low_ground" and flag.severity == "agreement" and flag.evidence_ids == ["elevation:ground", "recurrence:floodnet"]
    assert ground_checks(ground, []) == []  # no recurring flooding: nothing to explain

    high = Buildings.from_rows(district(near_ft=20.0)).ground_here(LAT, LON)
    assert ground_checks(high, ["recurrence:street_flood_complaints"])[0].type == "flooding_on_higher_ground"
    assert ground_checks(Buildings.from_rows(district(near_ft=15.0)).ground_here(LAT, LON), ["recurrence:floodnet"]) == []
    assert Buildings.from_rows(district()[:3]).ground_here(LAT, LON) is None  # too few buildings around to compare


def test_buildings_become_map_polygons_with_the_cited_one_marked():
    buildings = Buildings.from_rows(district())
    features = buildings.features(LAT, LON, 100, {"300000"})["features"]
    assert len(features) == 3 and sum(f["properties"]["cited"] for f in features) == 1
    assert features[0]["properties"]["height"] == pytest.approx(12.2)


def test_footprints_are_downloaded_around_the_district_and_loaded(tmp_path):
    step = next(step for step in snapshot.plan() if step.name == "building_footprints")
    done = {"pluto": [{"bbl": "3009670001", "latitude": str(LAT), "longitude": str(LON)}]}
    assert step.wheres(done)[0].startswith("intersects(the_geom, 'POLYGON((")
    assert "name" not in step.select(footprint(LAT, LON, 10), done)
    write(tmp_path, "building_footprints", [slim(row) for row in district()], "5zhs-2jue")
    store = Store.load(tmp_path)
    assert "building_footprints" in store.loaded and len(store.buildings.items) == 15
