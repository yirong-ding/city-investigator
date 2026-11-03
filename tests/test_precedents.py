"""Precedents: how 311 reports with a site's wordings ended across the district."""

from __future__ import annotations

import json
from dataclasses import replace

from city_investigator import explain, precedents
from city_investigator.evidence import from_311

BASIN = ("Sewer", "Catch Basin Clogged/Flooding (Use Comments) (SC)")
STREET = ("Sewer", "Street Flooding (SJ)")
CLEANED = "The Department of Environmental Protection cleaned the catch basin on 03/02/2024. Thank you."
NOTHING = "The Department of Environmental Protection inspected and found no problem."


def report(n, wording, created, closed=None, outcome=None):
    return {"unique_key": str(n), "complaint_type": wording[0], "descriptor": wording[1], "created_date": created,
            "closed_date": closed, "resolution_description": outcome}


def snapshot(tmp_path, rows):
    tmp_path.joinpath("311_2020_on.json").write_text(json.dumps({"rows": rows}))
    precedents.rows.cache_clear()
    return tmp_path


def test_reports_like_the_sites_come_first_with_how_they_ended(tmp_path):
    rows = [report(n, BASIN, f"2024-03-0{1 + n % 3}T10:00:00", f"2024-03-0{2 + n % 3}T10:00:00", CLEANED.replace("03/02", f"0{1 + n % 3}/02"))
            for n in range(6)]
    rows += [report(10 + n, STREET, "2021-06-01T10:00:00", "2021-06-11T10:00:00" if n < 4 else None, NOTHING) for n in range(8)]
    rows += [report(30, BASIN, "2024-05-01T10:00:00")]  # still open
    folder = snapshot(tmp_path, rows + [{"unique_key": "99", "complaint_type": "Noise", "descriptor": "Loud Music"}])
    street, basin = precedents.for_site("flooding", set(), folder)  # by count: street flooding first
    assert (street.reports, basin.reports) == (8, 7)
    basin_first = precedents.for_site("flooding", {basin.category}, folder)
    assert [p.id for p in basin_first][0] == basin.id  # the wording filed at the site comes first
    assert basin.closed == 6 and basin.median_days == 1 and basin.since == 2024
    assert basin.outcomes == (("The Department of Environmental Protection cleaned the catch basin on #/#/#.", 6),)  # one outcome
    item = street.item()
    assert item["type"] == "precedent" and "8 311 reports of 'Sewer / Street Flooding (SJ)': 50% closed, half of those within 10 days" in item["summary"]
    assert '"The Department of Environmental Protection inspected and found no problem." (100%)' in item["summary"]
    assert precedents.for_site("trees", set(), folder) == []  # no tree reports
    precedents.rows.cache_clear()


def test_reports_closed_within_hours_read_within_a_day():
    hours = precedents.Precedent("Sewer", "Street Flooding (SJ)", "street_flooding", 9, 9, 0.3, 2020, ())
    assert "half of those within a day." in hours.item()["summary"]
    assert "half of those within 1 day." in replace(hours, median_days=0.62).item()["summary"]


def test_a_complaint_says_how_it_ended_and_precedents_reach_the_explanation(tmp_path, monkeypatch):
    evidence = from_311(report(7, BASIN, "2024-03-01T10:00:00", "2024-03-02T10:00:00", CLEANED) | {"latitude": "40.67", "longitude": "-73.98"}, "x")
    assert evidence.summary.endswith("(closed 2024-03-02); outcome: The Department of Environmental Protection cleaned the catch basin on 03/02/2024.")
    folder = snapshot(tmp_path, [report(n, BASIN, "2024-03-01T10:00:00", "2024-03-02T10:00:00", CLEANED) for n in range(5)])
    monkeypatch.setattr(precedents, "SNAPSHOT_DIR", folder)
    result = {"topic": "flooding", "photo": {"taken_local": "2024-04-01 10:00"}, "observations": [], "not_seen": [], "records": [],
              "coverage": [], "flags": [], "radius_m": 150}
    known = explain.evidence_list(result)
    assert known["precedent:catch_basin_clogged_flooding_use_comments_sc"]["type"] == "precedent"
    assert "precedent" in explain.NEEDS["record"] and "precedent" not in explain.FINDINGS
    precedents.rows.cache_clear()
