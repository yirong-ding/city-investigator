"""Which of people's needs in a street an investigation bears on, in Jan Gehl's twelve quality criteria.

Gehl's criteria for public space (Cities for People, 2010; the Gehl Institute's public life tools) group what a
street must offer people under three themes: Protection, Comfort and Enjoyment. Each topic is tagged with the
criteria its conditions touch, and why. The tags say which needs a site's records and photo bear on; they do not
rate the place, which Gehl's method does by observing it on site.

The tagging is this project's reading of the criteria. Alternatives considered: Alfonzo's hierarchy of walking
needs (2005), whose safety level is safety from crime only, so falling debris and trip hazards have no level of
their own; and Mehta's public space index (2014), made for plazas rather than sidewalk conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

THEMES = ("Protection", "Comfort", "Enjoyment")
SOURCE = "Jan Gehl's 12 quality criteria for public space (Cities for People, 2010)"


@dataclass(frozen=True)
class Criterion:
    key: str
    theme: str
    name: str


CRITERIA = {
    criterion.key: criterion
    for criterion in (
        Criterion("accidents", "Protection", "Protection against traffic and accidents"),
        Criterion("crime", "Protection", "Protection against crime and violence"),
        Criterion("senses", "Protection", "Protection against unpleasant sensory experiences"),
        Criterion("walk", "Comfort", "Opportunities to walk"),
        Criterion("stay", "Comfort", "Opportunities to stand and stay"),
        Criterion("sit", "Comfort", "Opportunities to sit"),
        Criterion("see", "Comfort", "Opportunities to see"),
        Criterion("talk", "Comfort", "Opportunities to talk and listen"),
        Criterion("play", "Comfort", "Opportunities for play and exercise"),
        Criterion("scale", "Enjoyment", "Scale"),
        Criterion("climate", "Enjoyment", "Opportunities to enjoy the positive aspects of climate"),
        Criterion("senses_good", "Enjoyment", "Positive sensory experiences"),
    )
}

# topic -> the criteria its conditions touch, each with why, most direct first
TOPIC_NEEDS: dict[str, tuple[tuple[str, str], ...]] = {
    "flooding": (("walk", "flooded crossings and sidewalks"), ("senses", "standing water and spray from passing cars")),
    "sidewalk": (("walk", "sheds, scaffolding and fences narrow the sidewalk"),),
    "trees": (("accidents", "falling limbs from dead or damaged trees"), ("climate", "shade from street trees"),
              ("senses_good", "trees and greenery")),
    "facades": (("accidents", "debris falling from an unsafe façade"),),
    "sidewalk_damage": (("accidents", "trip hazards"), ("walk", "uneven surfaces, hard going with a wheelchair or stroller")),
    "curb_ramps": (("walk", "a way across for wheelchairs, strollers and walkers"),),
    "potholes": (("accidents", "potholes in the roadway"),),
    "street_construction": (("walk", "sidewalks blocked by work"), ("accidents", "shifted steel road plates")),
    "outdoor_dining": (("walk", "room to walk past dining setups"),),
}


def for_topic(topic: str) -> list[dict[str, str]]:
    """A topic's needs, for the page: theme, criterion and why."""
    return [
        {"theme": CRITERIA[key].theme, "criterion": CRITERIA[key].name, "why": why}
        for key, why in TOPIC_NEEDS.get(topic, ())
    ]


def themes(topic: str) -> list[str]:
    return sorted({CRITERIA[key].theme for key, _ in TOPIC_NEEDS.get(topic, ())}, key=THEMES.index)


def district(sites: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per theme: how many sites bear on it, and at how many the records and the photo disagree."""
    totals = {theme: {"sites": 0, "disagree": 0} for theme in THEMES}
    for site in sites:
        for theme in themes(site["topic"]):
            totals[theme]["sites"] += 1
            totals[theme]["disagree"] += site.get("worst") == "conflict"
    return totals
