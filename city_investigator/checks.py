"""Rule-based checks that compare the photo with the records, and records with each other.

Flags come from explicit rules, not from the model, so they appear even if the model
overlooks them. Each flag has a type, because different kinds of disagreement mean
different things: a sensor flood that nobody reported is a reporting gap, not a
contradiction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from city_investigator.evidence import Evidence, day
from city_investigator.sheds import ShedChain, days_between

AGREEMENT, CONFLICT, GAP = "agreement", "conflict", "gap"
STRUCTURE_SEEN = {"seen_scaffolding", "seen_construction_fence", "seen_construction_barrier"}
WATER_SEEN = {"seen_water", "seen_puddle", "seen_standing_water"}
FLOOD_COMPLAINTS = {"street_flooding", "catch_basin", "sewer_backup", "manhole_overflow"}
DRY_RAIN_IN = 0.05
MOMENT_TOLERANCE = timedelta(hours=12)


@dataclass
class Flag:
    type: str
    severity: str  # "agreement", "conflict" or "gap"
    message: str
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def ids(items: list[Evidence]) -> list[str]:
    return [item.id for item in items]


def addresses(items: list[Evidence]) -> str:
    return ", ".join(sorted({item.address for item in items if item.address})) or "nearby buildings"


def sidewalk_checks(
    observations: list[Evidence],
    permits_at_photo: list[Evidence],
    chains: list[ShedChain],
    photo_time: datetime | None,
) -> list[Flag]:
    flags: list[Flag] = []
    seen = [item for item in observations if item.category in STRUCTURE_SEEN]
    sheds = [item for item in permits_at_photo if item.category in {"shed_permit", "scaffold_permit"}]
    when = f" on {day(photo_time)}" if photo_time else ""
    if seen and sheds:
        flags.append(Flag(
            "permit_matches_structure", AGREEMENT,
            f"The scaffolding in the photo is consistent with shed or scaffold permits valid{when} at "
            f"{addresses(sheds)}. The photo alone does not show which building's permit covers it.",
            ids(seen) + ids(sheds),
        ))
    elif seen:
        flags.append(Flag(
            "structure_without_permit", CONFLICT,
            f"A structure is visible, but no shed, scaffold or fence permit was valid{when} nearby. "
            "It may be unpermitted, or its permit may be filed under another address.",
            ids(seen),
        ))
    elif sheds:
        flags.append(Flag(
            "permit_without_structure", CONFLICT,
            f"Shed or scaffold permits were valid{when} at {addresses(sheds)}, but no scaffolding is visible. "
            "It may be on another side of the building, out of frame, or already taken down: a permit shows "
            "authorization, and DOB does not track whether a shed is physically up. The model can also miss it.",
            ids(sheds),
        ))
    for chain in chains:
        if chain.short_gaps:
            gaps = "; ".join(f"{day(a)} to {day(b)} ({days_between(a, b)} days)" for a, b in chain.short_gaps)
            flags.append(Flag(
                "permit_chain_gap", GAP,
                f"The shed permits at {chain.address} have gaps longer than 30 days: {gaps}.",
                [permit.id for permit in chain.permits],
            ))
    return flags


def flood_checks(
    observations: list[Evidence],
    moment_hits: list[Evidence],
    rain_in: float | None,
    sensor_coverage_state: str | None,
    photo_time: datetime | None,
    when: datetime | None,
) -> list[Flag]:
    flags: list[Flag] = []
    water = [item for item in observations if item.category in WATER_SEEN]
    events = [item for item in moment_hits if item.category == "flood_event"]
    complaints = [item for item in moment_hits if item.category in FLOOD_COMPLAINTS]
    sensor_covers = sensor_coverage_state in {"found", "nothing_found"}
    if photo_time and when and abs(photo_time - when) > MOMENT_TOLERANCE:
        flags.append(Flag(
            "different_moments", GAP,
            f"The photo was taken {day(photo_time)}, but the question is about {day(when)}. "
            "The photo shows the place, not the moment.",
        ))
    if water and not events and (rain_in is not None and rain_in < DRY_RAIN_IN) and sensor_covers:
        flags.append(Flag(
            "water_without_rain", CONFLICT,
            "Water is visible, but almost no rain was measured and the nearby sensor recorded no flooding. "
            "A water main break, an open hydrant or a high tide are possible causes.",
            ids(water),
        ))
    if water and not sensor_covers:
        flags.append(Flag(
            "no_sensor_coverage", GAP,
            "Water is visible, but no flood sensor covers this spot and time, so its depth and duration were not measured.",
            ids(water),
        ))
    if events and not complaints:
        flags.append(Flag(
            "reporting_gap", GAP,
            "The sensor recorded flooding, but nobody filed a flood complaint nearby. "
            "That is a gap in reporting, not evidence that the flooding did not matter.",
            ids(events),
        ))
    if complaints and not events and sensor_covers:
        flags.append(Flag(
            "report_without_sensor", CONFLICT,
            "People reported flooding, but the nearby sensor recorded none. The water may have stayed below "
            "the curb, where these sensors often cannot see it, or collected away from the sensor.",
            ids(complaints),
        ))
    if events and complaints:
        first_event = min(item.start for item in events if item.start)
        first_complaint = min(item.start for item in complaints if item.start)
        lag_hours = (first_complaint - first_event).total_seconds() / 3600
        if lag_hours > 2:
            flags.append(Flag(
                "complaints_lag_sensor", AGREEMENT,
                f"The sensor and the complaints agree that it flooded, but the first complaint came about "
                f"{lag_hours:.0f} hours after the sensor first recorded water.",
                ids(events) + ids(complaints),
            ))
    return flags
