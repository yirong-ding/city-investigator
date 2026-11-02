"""What Valdrada's 3D view of a run draws: the run's records, and what its photo shows, placed in the city.

City Investigator's add-on to Valdrada (city_investigator/valdrada/cityInvestigator.js) fetches this for the place on
screen. Every item is a record or a SAM 3.1 detection and is labeled as one:
- flood: the city flood model's areas at their depth class, and a FloodNet sensor's deepest reading;
- sheds: buildings with a shed or scaffold permit valid on the photo's date (DOB does not record whether a shed is
  standing, so this is what was authorized, drawn with Valdrada's own shed model on the building's street side);
- facades: buildings whose latest façade filing before the photo is UNSAFE (from the run's flags);
- seen: scaffolding SAM 3.1 found in the photo, along the building front that its box points at from the camera;
- markers: the records the flags and the answer rest on (complaints, inspections, orders, inventory trees), as pins
  in the page's colors for their kind;
- after: the explanation's proposals, at the records they cite, with how the After view illustrates each action done
  (city_investigator.actions: rain gardens, the shed an unsafe façade must have, a young tree); an illustration, not a
  design or a prediction.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Callable

from city_investigator.actions import ACTIONS
from city_investigator.buildings import Building, Buildings
from city_investigator.geo import distance_m

SHED_LABELS = {"shed_permit": "Shed permit", "scaffold_permit": "Scaffold permit"}
UNSAFE_FLAGS = {"facade_unsafe_protected", "facade_unsafe_unprotected"}
SEEN_AS_SHED = {"seen_scaffolding"}
DEFAULT_FOV_DEG = 65.0  # a phone's main camera, when the photo does not say
SIGHT_M = 50.0  # a line of sight from the camera is followed this far to a building front
MIN_SPAN_M = 3.0  # Valdrada's shortest shed
MARKER_M, MAX_MARKERS = 150, 12  # pins for cited records this close to the pin, nearest first
PIN_GROUPS = {  # the page's names and colors for kinds of record (static/app.js GROUPS)
    "complaint": ("311 complaint", "#d9480f"),
    "permit": ("Permit or license", "#5f3dc4"),
    "agency": ("Agency inspection, order or filing", "#1971c2"),
    "inventory": ("City inventory", "#2b8a3e"),
    "sensor": ("FloodNet flood", "#0b7285"),
    "other": ("Record", "#495057"),
}
DRAWN_OTHERWISE = {"shed_permit", "scaffold_permit", "facade_filing", "ground_elevation"}


def moment(value: dict[str, str] | str | None) -> datetime | None:
    text = value.get("utc") if isinstance(value, dict) else value
    if not text:
        return None
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def day(value: dict[str, str] | None) -> str:
    return (value or {}).get("local", "")[:10]


def outline(building: Building) -> dict[str, Any]:
    return {"rings": [[list(point) for point in ring] for ring in building.rings], "height_m": building.height_m}


def record_sheds(records: list[dict[str, Any]], buildings: Buildings, when: datetime) -> list[dict[str, Any]]:
    """The buildings with a shed or scaffold permit valid on the photo's date, one entry per building."""
    found: dict[str, dict[str, Any]] = {}
    for record in records:
        label = SHED_LABELS.get(record.get("category") or "")
        start, end = moment(record.get("start")), moment(record.get("end"))
        if not label or start is None or start > when or (end is not None and end < when):
            continue
        building = buildings.find(record.get("bin"), record.get("bbl"), record.get("lat"), record.get("lon"))
        key = building and (building.bin or f"{building.lat:.6f},{building.lon:.6f}")
        if building is None or key in found:
            continue
        until = f" to {day(record.get('end'))}" if record.get("end") else ""
        found[key] = outline(building) | {
            "id": record["id"], "label": f"{label}, {day(record.get('start'))}{until}", "address": record.get("address") or "",
        }
    return list(found.values())


def unsafe_facades(result: dict[str, Any], buildings: Buildings) -> list[dict[str, Any]]:
    """The buildings whose latest façade filing before the photo is UNSAFE."""
    cited = {eid for flag in result.get("flags", []) if flag.get("type") in UNSAFE_FLAGS for eid in flag.get("evidence_ids", [])}
    facades = []
    for record in result["records"]:
        if record["id"] not in cited:
            continue
        building = buildings.find(record.get("bin"), record.get("bbl"), record.get("lat"), record.get("lon"))
        if building is not None:
            facades.append(outline(building) | {
                "id": record["id"], "label": f"Façade filing UNSAFE, {day(record.get('start'))}", "address": record.get("address") or "",
            })
    return facades


class Local:
    """Meters east (x) and north (y) of a point, for distances under a kilometer."""

    def __init__(self, lat: float, lon: float) -> None:
        self.lat, self.lon = lat, lon
        self.kx, self.ky = 111_320 * math.cos(math.radians(lat)), 110_574

    def xy(self, lon: float, lat: float) -> tuple[float, float]:
        return (lon - self.lon) * self.kx, (lat - self.lat) * self.ky

    def lonlat(self, x: float, y: float) -> list[float]:
        return [round(self.lon + x / self.kx, 7), round(self.lat + y / self.ky, 7)]


def cross(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


def bearing_of(u: float, width: int, heading: float, fov: float) -> float:
    """The compass bearing of a pixel column: across a panorama's full turn, or through a perspective lens."""
    if fov >= 359:
        return (heading + (u / width - 0.5) * 360) % 360
    focal = (width / 2) / math.tan(math.radians(fov / 2))
    return (heading + math.degrees(math.atan((u - width / 2) / focal))) % 360


def first_wall(walls: list[tuple[tuple[float, float], tuple[float, float]]], bearing: float):
    """The nearest wall a line of sight from the camera (at 0, 0) meets: (meters, wall)."""
    d = (math.sin(math.radians(bearing)), math.cos(math.radians(bearing)))
    best = None
    for p, q in walls:
        e = (q[0] - p[0], q[1] - p[1])
        denom = cross(d, e)
        if abs(denom) < 1e-9:
            continue
        t, s = cross(p, e) / denom, cross(p, d) / denom
        if 0.5 < t <= SIGHT_M and 0 <= s <= 1 and (best is None or t < best[0]):
            best = (t, (p, q))
    return best


def along(wall, bearing: float) -> float | None:
    """Where a line of sight crosses a wall's line, as meters along the wall from its start."""
    (p, q), d = wall, (math.sin(math.radians(bearing)), math.cos(math.radians(bearing)))
    e = (q[0] - p[0], q[1] - p[1])
    denom = cross(d, e)
    if abs(denom) < 1e-9 or cross(p, e) / denom <= 0:
        return None
    return cross(p, d) / denom * math.hypot(*e)


def seen_structures(result: dict[str, Any], buildings: Buildings) -> list[dict[str, Any]]:
    """Scaffolding in the photo, along the building front the middle of its box points at: from that front's point
    under the box's left edge to the one under its right edge."""
    photo = result["photo"]
    location, heading = photo.get("location") or {}, photo.get("heading_deg")
    if heading is None or location.get("lat") is None or not photo.get("size"):
        return []
    width, height = photo["size"]
    fov = photo.get("fov_deg") or (360.0 if width == 2 * height else DEFAULT_FOV_DEG)
    local = Local(location["lat"], location["lon"])
    walls = [
        (local.xy(*ring[k]), local.xy(*ring[k + 1]))
        for building, _ in buildings.around(location["lat"], location["lon"], SIGHT_M + 30)
        for ring in building.rings for k in range(len(ring) - 1)
    ]
    seen = []
    for observation in result.get("observations", []):
        if observation.get("category") not in SEEN_AS_SHED:
            continue
        for box in observation.get("boxes", []):
            middle = bearing_of((box["left"] + box["right"]) / 2, width, heading, fov)
            hit = first_wall(walls, middle)
            if hit is None:
                continue
            meters, wall = hit
            length = math.dist(*wall)
            ends = [along(wall, bearing_of(box[side], width, heading, fov)) for side in ("left", "right")]
            centre = along(wall, middle)
            ends = sorted(min(max(end if end is not None else centre, 0), length) for end in ends)
            if ends[1] - ends[0] < MIN_SPAN_M:  # at least a shed's length, centered where the box points
                mid = min(max(centre, MIN_SPAN_M / 2), max(length - MIN_SPAN_M / 2, MIN_SPAN_M / 2))
                ends = [mid - MIN_SPAN_M / 2, mid + MIN_SPAN_M / 2]
            (px, py), (qx, qy) = wall
            point = lambda s: local.lonlat(px + (qx - px) * s / length, py + (qy - py) * s / length)
            seen.append({
                "id": observation["id"], "a": point(ends[0]), "b": point(ends[1]),
                "camera": [location["lon"], location["lat"]], "distance_m": round(meters),
                "label": f"Seen in the photo, {(photo.get('taken_local') or '')[:10]}",
            })
    return seen


def markers(
    result: dict[str, Any], explanation: dict[str, Any] | None, group_of: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    """The records the flags and the answer cite, as pins at their places, nearest first. Sheds and façades are drawn
    as such; rain gauges and lots describe areas; a flood's sensor has its marker pole."""
    cited = {eid for flag in result.get("flags", []) for eid in flag.get("evidence_ids", [])}
    cited |= {eid for claim in (explanation or {}).get("claims", []) for eid in claim.get("evidence_ids", [])}
    location = result["photo"]["location"]
    pins: dict[str, dict[str, Any]] = {}
    for record in [*result["records"], *((explanation or {}).get("evidence") or {}).values()]:
        rid, lat, lon = record.get("id"), record.get("lat"), record.get("lon")
        if rid not in cited or rid in pins or lat is None or lon is None or record.get("category") in DRAWN_OTHERWISE:
            continue
        group = group_of(record)
        if record.get("kind", record.get("type")) in ("observation", "model", "photo") or group in ("rain", "lot") \
                or (group == "sensor" and result["topic"] == "flooding"):
            continue
        meters = distance_m(location["lat"], location["lon"], lat, lon)
        if meters > MARKER_M:
            continue
        name, color = PIN_GROUPS.get(group, PIN_GROUPS["other"])
        when = day(record.get("start")) or record.get("date") or ""
        pins[rid] = {
            "id": rid, "at": [lon, lat], "title": f"{name}, {when}" if when else name, "text": record.get("summary") or "",
            "color": color, "distance_m": round(meters),
        }
    return sorted(pins.values(), key=lambda pin: pin["distance_m"])[:MAX_MARKERS]


def after_view(result: dict[str, Any], explanation: dict[str, Any] | None, buildings: Buildings) -> list[dict[str, Any]]:
    """The proposals that passed the explanation's checks, each where the findings it cites are."""
    if not explanation:
        return []
    by_id = {item["id"]: item for item in [*result["records"], *(explanation.get("evidence") or {}).values()]}
    flags = {f"flag:{flag['type']}": flag for flag in result.get("flags", [])}
    actions = {f"action:{action.key}": action for listed in ACTIONS.values() for action in listed}
    location = result["photo"]["location"]
    items = []
    for claim in explanation.get("claims", []):
        cited = claim.get("evidence_ids", [])
        action = next((actions[eid] for eid in cited if eid in actions), None)
        if claim.get("kind") != "proposal" or action is None:
            continue
        records = [by_id[eid] for eid in cited if eid in by_id]
        records += [by_id[rid] for eid in cited if eid in flags for rid in flags[eid].get("evidence_ids", []) if rid in by_id]
        located = [item for item in records if item.get("lat") is not None and item.get("lon") is not None]
        if action.after == "young_tree":  # the tree itself, from the inventory, before an address's lot
            located.sort(key=lambda item: item.get("category") != "tree_inventory")
        at = located[0] if located and action.after != "rain_gardens" else location  # rain gardens: around the low spot
        item = {"action": action.key, "draw": action.after, "text": claim["text"], "at": [at["lon"], at["lat"]]}
        if action.after == "shed":
            building = next((found for record in records if (found := buildings.find(
                record.get("bin"), record.get("bbl"), record.get("lat"), record.get("lon")))), None)
            item |= outline(building) if building else {"draw": None}
        items.append(item)
    return items


def scene(
    result: dict[str, Any], buildings: Buildings | None, flood: dict[str, Any] | None,
    explanation: dict[str, Any] | None = None, group_of: Callable[[dict[str, Any]], str] = lambda record: "other",
) -> dict[str, Any]:
    location = result["photo"]["location"]
    when = moment(result["photo"].get("taken_at")) or datetime.now(timezone.utc)
    buildings = buildings or Buildings([])
    return {
        "center": {"lat": location["lat"], "lon": location["lon"]},
        "note": "records and what the photo shows; Valdrada's own randomly placed sheds are hidden",
        "flood": flood,
        "sheds": record_sheds(result["records"], buildings, when),
        "facades": unsafe_facades(result, buildings),
        "seen": seen_structures(result, buildings),
        "markers": markers(result, explanation, group_of),
        "after": after_view(result, explanation, buildings),
    }


def main(argv: list[str] | None = None) -> None:
    """The investigations with something for Valdrada to draw, most first, with a link that opens each: the newest
    run of each photo and topic, unless --all."""
    import argparse

    from city_investigator.investigate import OUTPUT
    from city_investigator.store import Store
    from city_investigator.web import group

    parser = argparse.ArgumentParser(description="Investigations with something to draw in Valdrada")
    parser.add_argument("--all", action="store_true", help="every run, not only the newest of each photo and topic")
    every = parser.parse_args(argv).all
    runs: dict[Any, tuple[Any, dict[str, Any]]] = {}
    for path in sorted(OUTPUT.glob("*/result.json")):  # folder names start with the time: a later run replaces
        result = json.loads(path.read_text())
        runs[path if every else (result["photo"].get("ref"), result["topic"])] = (path, result)
    store = Store.load()
    rows = []
    for path, result in runs.values():
        explained = path.parent / "explanation.json"
        drawn = scene(result, store.buildings, None, json.loads(explained.read_text()) if explained.is_file() else None, group)
        placed = "fov_deg" in result["photo"]  # runs from before Nov 1 kept no SAM boxes to place the photo's objects
        counts = [len(drawn[kind]) for kind in ("markers", "sheds", "seen", "facades", "after")]
        where = next((item["address"] for kind in ("sheds", "facades") for item in drawn[kind] if item.get("address")), "")
        rows.append((sum(counts) + (result["topic"] == "flooding"), path.parent.name, result, counts, placed, where))
    rows.sort(key=lambda row: (-row[0], row[1]))
    for _, name, result, (pins, sheds, seen, facades, after), placed, where in rows:
        parts = [f"{pins} record pin(s)", f"{sheds} permitted shed(s)", f"{seen} seen in the photo" if placed else "photo: run again to place it",
                 f"{facades} unsafe façade(s)"] + (["flood water"] if result["topic"] == "flooding" else []) + [f"{after} proposal(s) for After"]
        label = result.get("topic_label") or result["topic"]
        print(f"{label}{f' at {where}' if where else ''}: {', '.join(parts)}\n    http://127.0.0.1:8000/#run={name}")
    if not rows:
        print(f"No investigations in {OUTPUT}.")


if __name__ == "__main__":
    main()
