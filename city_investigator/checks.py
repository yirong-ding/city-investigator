"""Rule-based checks that compare the photo with the records, and records with each other.

Flags come from explicit rules, not from the model, so they appear even if the model
overlooks them. Each flag has a type, because different kinds of disagreement mean
different things: a sensor flood that nobody reported is a reporting gap, not a
contradiction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from city_investigator import times
from city_investigator.evidence import Evidence, day
from city_investigator.sheds import ShedChain, days_between
from city_investigator.sources import yes
from city_investigator.topics import TOPICS, problem_categories

AGREEMENT, CONFLICT, GAP = "agreement", "conflict", "gap"
STRUCTURE_SEEN = {"seen_scaffolding", "seen_construction_fence", "seen_construction_barrier"}
WATER_SEEN = {"seen_water", "seen_puddle", "seen_standing_water"}
FLOOD_COMPLAINTS = {"street_flooding", "catch_basin", "sewer_backup", "manhole_overflow"}
DRY_RAIN_IN = 0.05
# A permit farther than this from the camera may simply be out of frame.
IN_VIEW_M = 20
INDOOR_COMPLAINTS = {"sewer_backup"}
MOMENT_TOLERANCE = timedelta(hours=12)
# Modeled flooding this close to the place counts as the model expecting flooding there.
MODEL_NEAR_M = 50
CURRENT_SCENARIO = "moderate_current"
DESIGN_STORM_IN_HR = 2.13  # the rain rate of the city's moderate design storm


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
    distances: dict[str, float] | None = None,
) -> list[Flag]:
    """distances maps evidence IDs to meters from the camera."""
    flags: list[Flag] = []
    distances = distances or {}
    seen = [item for item in observations if item.category in STRUCTURE_SEEN]
    sheds = [item for item in permits_at_photo if item.category in {"shed_permit", "scaffold_permit"}]
    close_sheds = [item for item in sheds if distances.get(item.id, 0) <= IN_VIEW_M]
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
    elif close_sheds:
        flags.append(Flag(
            "permit_without_structure", CONFLICT,
            f"Shed or scaffold permits were valid{when} at {addresses(close_sheds)}, within {IN_VIEW_M} m of the "
            "camera, but no scaffolding is visible. "
            "It may be on another side of the building, out of frame, or already taken down: a permit shows "
            "authorization, and DOB does not track whether a shed is physically up. The model can also miss it.",
            ids(close_sheds),
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
    model_coverage_state: str | None = None,
    rain_peak_in: float | None = None,
) -> list[Flag]:
    """moment_hits are records around the moment asked about, plus the flood model's estimates."""
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

        def lag(items: list[Evidence]) -> float | None:
            starts = [item.start for item in items if item.start]
            return (min(starts) - first_event).total_seconds() / 3600 if starts else None

        street_lag = lag([item for item in complaints if item.category not in INDOOR_COMPLAINTS])
        indoor_lag = lag([item for item in complaints if item.category in INDOOR_COMPLAINTS])
        parts = []
        if street_lag is not None:
            parts.append(f"the first street complaint came about {street_lag:.0f} hours after the sensor first recorded water")
        if indoor_lag is not None:
            parts.append(f"the first indoor sewer backup was reported about {indoor_lag:.0f} hours after")
        if max(value for value in (street_lag, indoor_lag) if value is not None) > 2:
            flags.append(Flag(
                "complaints_lag_sensor", AGREEMENT,
                "The sensor and the complaints agree that it flooded, but " + "; ".join(parts) + ".",
                ids(events) + ids(complaints),
            ))
    recorded = events + [item for item in complaints if item.category not in INDOOR_COMPLAINTS]
    modeled = next(
        (item for item in moment_hits if item.category == "modeled_flooding" and item.raw.get("scenario") == CURRENT_SCENARIO),
        None,
    )
    if recorded and modeled and min(modeled.raw["distances_m"].values()) <= MODEL_NEAR_M:
        flags.append(Flag(
            "model_expects_flooding", AGREEMENT,
            f"The city's stormwater flood model also maps flooding within {MODEL_NEAR_M} m of here in a moderate "
            "storm with today's sea levels: this is a place the city expects to flood.",
            ids(recorded) + [modeled.id],
        ))
        if rain_peak_in is not None and rain_peak_in < DESIGN_STORM_IN_HR:
            rain = [item for item in moment_hits if item.category == "rainfall"]
            flags.append(Flag(
                "flooded_in_lighter_rain", GAP,
                f"It flooded although the wettest hour measured at the Central Park weather station had "
                f"{rain_peak_in:.2f} in of rain, under the {DESIGN_STORM_IN_HR} in/hr of the moderate storm the "
                "city's model uses. Rain here, miles from Central Park, may have been heavier, or this spot may "
                "flood in smaller storms than the model's.",
                ids(recorded) + [modeled.id] + ids(rain),
            ))
    elif recorded and model_coverage_state in {"found", "nothing_found"}:
        flags.append(Flag(
            "model_misses_flooding", GAP,
            f"Flooding was recorded here, but the city's stormwater flood model for a moderate storm with today's "
            f"sea levels maps none within {MODEL_NEAR_M} m. The model maps only ponding at least 4 in deep over a "
            "quarter acre, so smaller, brief or very local flooding can be missing from it.",
            ids(recorded),
        ))
    return flags


# The newer topics (topics.py): the same comparisons for every topic, plus a few of their own.

REPORTED_BEFORE = timedelta(days=90)
REPAIR_LOOKBACK = timedelta(days=365)
# Agency records whose end date means the problem was closed out, with how to name them.
CLOSURES = {
    "pothole_repair": "a DOT pothole work order",
    "sidewalk_violation": "a DOT sidewalk violation (dismissed: repaired or withdrawn)",
    "tree_work_order": "a Parks tree work order",
    "ramp_complaint_dot": "a DOT ramp complaint (temporary repair)",
}
# Permissions that should be in force when the structure in the photo stands.
LICENSES = {
    "street_construction": ({"street_permit", "street_closure"}, "a street construction permit or closure"),
    "outdoor_dining": ({"dining_license"}, "a Dining Out NYC license"),
}
DINING_LICENSES_START = datetime(2024, 8, 1, tzinfo=timezone.utc)
TREE_MATCH_M = 8
REMOVED_TREE = {"retired", "stump"}  # inventory structures with no standing tree
RAMP_MATCH_M = 15


def topic_checks(
    topic: str,
    observations: list[Evidence],
    records: list[Evidence],
    when: datetime,
    distances: dict[str, float] | None = None,
) -> list[Flag]:
    """records are the topic's records around the pin; distances maps their IDs to meters from it."""
    spec = TOPICS[topic]
    distances = distances or {}
    flags: list[Flag] = []
    seen = [item for item in observations if item.category in problem_categories(topic)]
    what = " and ".join(sorted({item.category.removeprefix("seen_").replace("_", " ") for item in seen}))
    complaints = [item for item in records if item.id.startswith("311:") and item.topic == topic and item.start]
    around = [item for item in complaints if when - timedelta(days=180) <= item.start <= when + timedelta(days=30)]
    before = [item for item in complaints if when - REPORTED_BEFORE <= item.start <= when]
    days = sorted({day(item.start) for item in complaints})
    where = f"within {spec.radius_m:.0f} m"

    if not spec.problems:  # the photo cannot show this topic's problem, so it neither confirms nor contradicts reports
        seen, around, before = [], [], []
    if seen and around:
        flags.append(Flag(
            "reported_and_seen", AGREEMENT,
            f"The photo shows {what}, and {len(around)} 311 complaint(s) {where} describe a {spec.noun} problem "
            f"between {day(min(c.start for c in around))} and {day(max(c.start for c in around))}.",
            ids(seen) + ids(around),
        ))
    elif seen and not complaints:
        flags.append(Flag(
            "seen_not_reported", GAP,
            f"The photo shows {what}, but no 311 {spec.noun} complaint was filed {where} in the "
            f"{spec.lookback_days // 365 or 1} year(s) before the photo. That is a gap in reporting, not proof it does not matter.",
            ids(seen),
        ))
    still_open = [item for item in before if not item.end or item.end > when]
    if still_open and not seen:
        flags.append(Flag(
            "reported_not_seen", CONFLICT,
            f"{len(still_open)} 311 complaint(s) filed in the 90 days before the photo and still open on its date describe a "
            f"{spec.noun} problem {where}, but SAM 3.1 found none in the photo. It may have been fixed, be out of frame, "
            "or be missed by the model.",
            ids(still_open),
        ))
    elif before and not seen:
        flags.append(Flag(
            "closed_and_not_seen", AGREEMENT,
            f"{len(before)} 311 complaint(s) {where} in the 90 days before the photo were closed by its date, and SAM 3.1 "
            "finds no such problem in the photo: consistent with a repair, though it may also be out of frame.",
            ids(before),
        ))
    closed = [
        item for item in records
        if item.category in CLOSURES and item.end and when - REPAIR_LOOKBACK <= item.end <= when
        and distances.get(item.id, 0) <= IN_VIEW_M and not item.raw.get("canceldate")
    ]
    if seen and closed:
        latest = max(closed, key=lambda item: item.end)
        flags.append(Flag(
            "closed_but_still_seen", CONFLICT,
            f"{CLOSURES[latest.category].capitalize()} {distances.get(latest.id, 0):.0f} m away was closed on {day(latest.end)}, "
            f"before the photo on {day(when)}, but the photo still shows {what}. The repair may not have held, "
            "or the record may be about a different spot.",
            ids(seen) + [latest.id],
        ))
    if len(days) >= 3:
        flags.append(Flag(
            "repeat_reports", GAP,
            f"311 {spec.noun} complaints {where} were filed on {len(days)} separate days, {days[0]} to {days[-1]}.",
            ids(complaints),
        ))
    if topic in LICENSES:
        flags += license_checks(topic, seen, what, records, when, distances)
    if topic == "facades":
        flags += facade_checks(observations, records, when, distances)
    if topic == "trees":
        flags += tree_checks(observations, records, distances, when)
    if topic == "curb_ramps":
        flags += ramp_checks(seen, records, distances)
    return flags


def license_checks(
    topic: str, seen: list[Evidence], what: str, records: list[Evidence], when: datetime, distances: dict[str, float]
) -> list[Flag]:
    categories, kind = LICENSES[topic]
    if not seen or (topic == "outdoor_dining" and when < DINING_LICENSES_START):
        return []  # nothing to explain, or the license records start after the photo
    valid = [
        item for item in records
        if item.category in categories and item.start and item.start <= when <= (item.end or item.start)
    ]
    if valid:
        return [Flag(
            "licensed_and_seen", AGREEMENT,
            f"The {what} in the photo is consistent with {kind} valid on {day(when)} "
            f"({addresses(valid) if any(item.address for item in valid) else 'nearby'}).",
            ids(seen) + ids(valid),
        )]
    return [Flag(
        "seen_without_license", GAP,
        f"The photo shows {what}, but no {kind.removeprefix('a ')} was valid on {day(when)} within "
        f"{TOPICS[topic].radius_m:.0f} m. It may be filed under another address, unlicensed, or (for street work) emergency work.",
        ids(seen),
    )]


def facade_checks(
    observations: list[Evidence], records: list[Evidence], when: datetime, distances: dict[str, float]
) -> list[Flag]:
    protection = [item for item in observations if item.category in {"seen_scaffolding", "seen_safety_netting"}]
    latest: dict[str, Evidence] = {}
    for item in records:
        if item.category == "facade_filing" and item.start and item.start <= when:
            key = item.bbl or item.id
            if key not in latest or item.start > latest[key].start:
                latest[key] = item
    flags = []
    for filing in latest.values():
        if str(filing.raw.get("filing_status") or "").strip().upper() != "UNSAFE":
            continue
        place = filing.address or "a building nearby"
        rule = "An unsafe façade must have public protection, such as a sidewalk shed, until it is repaired"
        if protection:
            flags.append(Flag(
                "facade_unsafe_protected", AGREEMENT,
                f"The latest façade filing for {place} ({day(filing.start)}) is UNSAFE. {rule}, "
                "consistent with what the photo shows.",
                ids(protection) + [filing.id],
            ))
        elif distances.get(filing.id, IN_VIEW_M + 1) <= IN_VIEW_M:  # farther away, the building may be out of frame
            flags.append(Flag(
                "facade_unsafe_unprotected", CONFLICT,
                f"The latest façade filing for {place} ({day(filing.start)}) is UNSAFE. {rule}, but none is visible. "
                "It may have been repaired since, or be out of frame.",
                [filing.id],
            ))
    return flags


def tree_checks(
    observations: list[Evidence], records: list[Evidence], distances: dict[str, float], when: datetime | None = None
) -> list[Flag]:
    """Match a tree in the photo to the inventory: the nearest tree standing on the photo's date, within a few meters.

    The inventory holds each tree's latest state. A record marked removed (structure Retired or
    Stump) after the photo was a standing tree when the photo was taken; one marked removed
    before it is named, so it is not taken for the tree in the photo.
    """
    trees = [item for item in observations if item.category.startswith("seen_") and "tree" in item.category]
    inventory = sorted(
        (item for item in records if item.category == "tree_inventory" and distances.get(item.id, TREE_MATCH_M + 1) <= TREE_MATCH_M),
        key=lambda item: distances[item.id],
    )
    if not trees or not inventory:
        return []
    def removed(item: Evidence) -> bool:
        return str(item.raw.get("tpstructure") or "").strip().lower() in REMOVED_TREE

    def updated(item: Evidence) -> datetime | None:
        return times.parse(item.raw.get("updateddate") or item.raw.get("createddate"))

    def removed_by_photo(item: Evidence) -> bool:
        changed = updated(item)
        return removed(item) and (when is None or changed is None or changed <= when)

    standing = [item for item in inventory if not removed_by_photo(item)]
    gone = [item for item in inventory if item not in standing and (not standing or distances[item.id] < distances[standing[0].id])]

    def described(item: Evidence) -> str:
        return f"{distances[item.id]:.0f} m away: {item.summary.removeprefix('Street tree in the Parks inventory: ')}"

    if not standing:
        return [Flag(
            "removed_tree_listed", CONFLICT,
            f"A tree is seen, but the only Parks inventory records within {TREE_MATCH_M} m are of trees removed before the photo "
            f"(nearest {described(gone[0])}). The tree in the photo may be a newer planting the inventory does not "
            "list, or one farther away.",
            ids(trees) + [gone[0].id],
        )]
    nearest = standing[0]
    closer = f" A removed tree's record is closer, {described(gone[0])}." if gone else ""
    since = (
        f" Parks has since recorded it as removed ({day(updated(nearest))}), so it may have come down after the photo."
        if removed(nearest) else ""
    )
    return [Flag(
        "inventory_tree_nearby", AGREEMENT,
        f"The Parks inventory lists a tree standing on the photo's date {described(nearest)}. It is likely the tree in "
        f"the photo; the photo's direction was not checked.{since}{closer}",
        ids(trees) + [nearest.id] + ([gone[0].id] if gone else []),
    )]


def ramp_checks(seen: list[Evidence], records: list[Evidence], distances: dict[str, float]) -> list[Flag]:
    puddles = [item for item in seen if item.category == "seen_puddle"]
    surveyed = [
        item for item in records
        if item.category == "ramp_survey" and distances.get(item.id, RAMP_MATCH_M + 1) <= RAMP_MATCH_M
        and yes(item.raw.get("ponding"))
    ]
    if not (puddles and surveyed):
        return []
    return [Flag(
        "ramp_ponding_recorded", AGREEMENT,
        "Water stands at the ramp in the photo, and DOT's ramp survey also recorded ponding at a ramp within "
        f"{RAMP_MATCH_M} m.",
        ids(puddles) + ids(surveyed),
    )]
