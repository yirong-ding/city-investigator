"""What a resident or the community board can do about each topic's problem: channels that exist.

Muse Spark may propose next steps only from this list, and each proposal must also cite the
evidence it answers, so a proposal never invents a program, a phone number or an outcome.
The 311 entries use the complaint wording the city's own records for this district use
(config.COMPLAINTS); the agency is the one those complaints go to.
"""

from __future__ import annotations

from dataclasses import dataclass

from city_investigator.config import COMPLAINTS
from city_investigator.topics import slug


@dataclass(frozen=True)
class Action:
    key: str
    summary: str


def report(complaint_type: str, descriptor: str | None, agency: str, use: str) -> Action:
    """A 311 report, named the way the city's records name it."""
    assert (complaint_type, descriptor) in COMPLAINTS, (complaint_type, descriptor)
    wording = f"'{complaint_type}'" + (f", '{descriptor}'" if descriptor else "")
    return Action(
        "311_" + "_".join(slug(descriptor or complaint_type).split("_")[:3]),
        f"A 311 report under {wording} (the wording in the city's own records), which goes to {agency}: {use}.",
    )


COMMUNITY_BOARD = Action(
    "community_board",
    "Brooklyn Community Board 6 takes up local service problems, especially ones that keep coming back or that "
    "311 has not resolved, and raises them with the city agencies; its district office and public meetings are "
    "open to residents.",
)
GREEN_INFRASTRUCTURE = Action(
    "green_infrastructure",
    "The NYC Department of Environmental Protection's Green Infrastructure Program builds curbside rain gardens "
    "and similar features that soak up stormwater before it reaches the sewers.",
)
GENERAL = "General Construction/Plumbing"

ACTIONS: dict[str, tuple[Action, ...]] = {
    "flooding": (
        report("Sewer", "Catch Basin Clogged/Flooding (Use Comments) (SC)", "the Department of Environmental Protection",
               "a street drain that is blocked, so it is inspected and cleaned"),
        report("Sewer", "Street Flooding (SJ)", "the Department of Environmental Protection",
               "water standing in the street, best filed while it is happening"),
        GREEN_INFRASTRUCTURE,
        COMMUNITY_BOARD,
    ),
    "sidewalk": (
        report(GENERAL, "Sidewalk Shed/Pipe Scafford - Inadequate Defective/None", "the Department of Buildings",
               "a sidewalk shed or scaffold that looks unsafe or seems to lack a permit, so it is inspected"),
        COMMUNITY_BOARD,
    ),
    "trees": (
        report("Dead/Dying Tree", None, "NYC Parks", "a street tree that looks dead or dying, so it is inspected"),
        report("Damaged Tree", None, "NYC Parks", "a cracked or hanging branch or a damaged tree"),
        report("Root/Sewer/Sidewalk Condition", None, "NYC Parks",
               "a sidewalk lifted by a street tree's roots, which Parks' Trees and Sidewalks Program repairs"),
        COMMUNITY_BOARD,
    ),
    "facades": (
        report(GENERAL, "Debris - Falling Or In Danger Of Falling", "the Department of Buildings",
               "material falling or about to fall from a building; for immediate danger, call 911"),
        COMMUNITY_BOARD,
    ),
    "sidewalk_damage": (
        report("Sidewalk Condition", "Broken Sidewalk", "the Department of Transportation",
               "a broken or uneven sidewalk, so it is inspected"),
        report("Root/Sewer/Sidewalk Condition", None, "NYC Parks",
               "a sidewalk lifted by a street tree's roots, which Parks' Trees and Sidewalks Program repairs"),
        COMMUNITY_BOARD,
    ),
    "curb_ramps": (
        report("Sidewalk Condition", "Pedestrian Ramp Defective", "the Department of Transportation",
               "a curb ramp that is broken, blocked or holds water"),
        report("Curb Condition", "Broken Curb", "the Department of Transportation", "a broken curb"),
        COMMUNITY_BOARD,
    ),
    "potholes": (
        report("Street Condition", "Pothole", "the Department of Transportation", "a pothole, so it is repaired"),
        report("Street Condition", "Failed Street Repair", "the Department of Transportation",
               "a repair that did not hold"),
        COMMUNITY_BOARD,
    ),
    "street_construction": (
        report("Street Condition", "Plate Condition - Shifted", "the Department of Transportation",
               "a steel road plate that has shifted"),
        report("Sidewalk Condition", "Blocked - Construction", "the Department of Transportation",
               "a sidewalk blocked by construction"),
        COMMUNITY_BOARD,
    ),
    "outdoor_dining": (
        report("Outdoor Dining", "Sidewalk Zone Blocked", "the Department of Transportation",
               "an outdoor dining setup that blocks the sidewalk's walking path"),
        COMMUNITY_BOARD,
    ),
}


def action_items(topic: str) -> list[dict[str, str]]:
    """The topic's actions as evidence items the explanation can cite."""
    return [{"id": f"action:{action.key}", "type": "action", "summary": action.summary} for action in ACTIONS.get(topic, ())]
