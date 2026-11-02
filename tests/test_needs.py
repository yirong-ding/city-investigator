"""Gehl's quality criteria: every topic is tagged, and the district counts sites per theme."""

from __future__ import annotations

from city_investigator import needs
from city_investigator.topics import TOPICS


def test_every_topic_bears_on_at_least_one_of_gehls_criteria():
    assert set(needs.TOPIC_NEEDS) == set(TOPICS)
    assert len(needs.CRITERIA) == 12 and {c.theme for c in needs.CRITERIA.values()} == set(needs.THEMES)
    assert needs.for_topic("facades") == [
        {"theme": "Protection", "criterion": "Protection against traffic and accidents", "why": "debris falling from an unsafe façade"},
    ]
    assert needs.themes("street_construction") == ["Protection", "Comfort"]  # in Gehl's order
    assert needs.for_topic("unknown") == []


def test_the_district_counts_places_per_theme_and_where_records_and_photo_disagree():
    sites = [{"topic": "flooding", "worst": "conflict"}, {"topic": "curb_ramps", "worst": "agreement"}, {"topic": "potholes", "worst": "conflict"}]
    assert needs.district(sites) == {
        "Protection": {"sites": 2, "disagree": 2},  # flooding's standing water, the pothole
        "Comfort": {"sites": 2, "disagree": 1},  # flooding's crossings, the ramp
        "Enjoyment": {"sites": 0, "disagree": 0},
    }
