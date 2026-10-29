"""Shortlist demo sites: the longest-standing sheds, the most-flooded sensor corners, and
for each newer topic the places where the most sources have something to say.

Writes data/derived/shortlist.md and shortlist.json. Every site has a Street View
link for scouting by eye and, with --photos and MAPILLARY_TOKEN set, the newest
Mapillary photos nearby, which the app may use with credit, and the command that
investigates the best one.

Usage:
  python -m city_investigator.shortlist
  python -m city_investigator.shortlist --photos --topic trees --top 5
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from city_investigator import times
from city_investigator.evidence import Evidence, Sensor, day
from city_investigator.geo import distance_m, to_float
from city_investigator.photos import photos_near
from city_investigator.settings import DERIVED_DIR, load_env
from city_investigator.sheds import build_chains
from city_investigator.sources import STATE_CATEGORIES
from city_investigator.store import Store
from city_investigator.topics import TOPICS, in_topic, window

SHED_COMPLAINT_RADIUS_M = 50
FLOOD_COMPLAINT_RADIUS_M = 150
PHOTO_RADIUS_M = 40
SITE_YEARS = 3  # a topic site is built from records of the last few years (and standing ones)
NEW_TOPICS = [key for key in TOPICS if key not in ("flooding", "sidewalk")]


def street_view(lat: float, lon: float) -> str:
    """Opens Google Street View in the browser for a person to look; never used as evidence."""
    return f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat:.6f},{lon:.6f}"


def shed_sites(store: Store, at: datetime, top: int) -> list[dict[str, Any]]:
    chains = [chain for chain in build_chains(store.evidence) if chain.active(at) and chain.lat is not None]
    chains.sort(key=lambda chain: chain.days_up(at), reverse=True)
    sites = []
    for chain in chains[:top]:
        assert chain.lat is not None and chain.lon is not None
        nearby = store.near(chain.lat, chain.lon, SHED_COMPLAINT_RADIUS_M, start=chain.up_since, topic="sidewalk")
        complaints = Counter(hit.evidence.category for hit in nearby.hits if hit.evidence.id.startswith("311:"))
        sites.append(
            chain.to_dict(at)
            | {"complaints_nearby_since": dict(complaints), "street_view": street_view(chain.lat, chain.lon)}
        )
    return sites


def flood_sites(store: Store, top: int) -> list[dict[str, Any]]:
    # A replaced sensor gets a new ID but keeps its name, so group by name.
    by_name: dict[str, list[Sensor]] = defaultdict(list)
    for sensor in store.sensors:
        by_name[sensor.name].append(sensor)
    events = [item for item in store.evidence if item.category == "flood_event"]
    sites = []
    for name, sensors in by_name.items():
        located = next((s for s in sensors if s.lat is not None and s.lon is not None), None)
        if located is None:
            continue
        assert located.lat is not None and located.lon is not None
        site_events = [item for item in events if item.address == name]
        depths = [d for item in site_events if (d := to_float(item.raw.get("max_depth_inches"))) is not None]
        installed = min((s.installed for s in sensors if s.installed), default=None)
        nearby = store.near(located.lat, located.lon, FLOOD_COMPLAINT_RADIUS_M, start=installed, topic="flooding")
        complaints = [hit for hit in nearby.hits if hit.evidence.id.startswith("311:")]
        sites.append(
            {
                "sensor": name,
                "sensor_ids": sorted(s.id for s in sensors),
                "tidal": any(s.tidal for s in sensors),
                "events": len(site_events),
                "max_depth_in": max(depths, default=None),
                "latest_event": day(max((item.start for item in site_events if item.start), default=None)),
                "first_installed": day(installed),
                "flood_complaints_nearby_since_install": len(complaints),
                "event_ids": [item.id for item in site_events],
                "lat": located.lat,
                "lon": located.lon,
                "street_view": street_view(located.lat, located.lon),
            }
        )
    sites.sort(key=lambda site: site["events"], reverse=True)
    return sites[:top]


def topic_sites(store: Store, topic: str, at: datetime, top: int) -> list[dict[str, Any]]:
    """Places where the most sources have recent records of the topic within its radius.

    Every recent record (not a standing one such as a tree in the inventory) is a
    candidate center; centers are ranked by how many sources, then 311 complaints, then
    records surround them, and kept only if they are well apart.
    """
    radius = TOPICS[topic].radius_m
    since = at - timedelta(days=365 * SITE_YEARS)
    items = [
        item for item in store.evidence
        if item.lat is not None and item.lon is not None and in_topic(topic, item.topic, item.category)
        and (item.category in STATE_CATEGORIES or (item.start is not None and item.start >= since))
    ]
    if not items:
        return []
    # A grid of cells one radius wide, so each center only measures its neighbors.
    lat_cell = radius / 111_320
    lon_cell = lat_cell / math.cos(math.radians(items[0].lat or 0))
    grid: dict[tuple[int, int], list[Evidence]] = defaultdict(list)
    for item in items:
        grid[int(item.lat // lat_cell), int(item.lon // lon_cell)].append(item)  # type: ignore[operator]

    def around(center: Evidence) -> list[Evidence]:
        row, column = int(center.lat // lat_cell), int(center.lon // lon_cell)  # type: ignore[operator]
        return [
            item for d_row in (-1, 0, 1) for d_column in (-1, 0, 1) for item in grid.get((row + d_row, column + d_column), ())
            if distance_m(center.lat, center.lon, item.lat, item.lon) <= radius  # type: ignore[arg-type]
        ]

    ranked = []
    measured: set[tuple[float, float]] = set()
    for center in items:
        spot = (round(center.lat, 5), round(center.lon, 5))  # type: ignore[arg-type]
        if center.category in STATE_CATEGORIES or spot in measured:  # many permits share one segment
            continue
        measured.add(spot)
        nearby = around(center)
        complaints = sum(1 for item in nearby if item.id.startswith("311:"))
        ranked.append(((len({item.source for item in nearby}), complaints, len(nearby)), center, nearby))
    ranked.sort(key=lambda entry: entry[0], reverse=True)

    sites: list[dict[str, Any]] = []
    for _, center, nearby in ranked:
        if len(sites) == top:
            break
        if any(distance_m(center.lat, center.lon, site["lat"], site["lon"]) < 2 * radius for site in sites):  # type: ignore[arg-type]
            continue
        dated = sorted((item for item in nearby if item.start), key=lambda item: item.start)  # type: ignore[arg-type, return-value]
        sites.append({
            "topic": topic,
            "address": center.address or next((item.address for item in nearby if item.address), None),
            "lat": center.lat,
            "lon": center.lon,
            "sources": sorted({item.source for item in nearby}),
            "records": dict(Counter(item.category for item in nearby).most_common()),
            "first": day(dated[0].start) if dated else None,
            "latest": day(dated[-1].start) if dated else None,
            "newest": [item.summary[:160] for item in reversed(dated[-3:])],
            "record_ids": [item.id for item in nearby],
            "street_view": street_view(center.lat, center.lon),  # type: ignore[arg-type]
        })
    return sites


def topic_sources(store: Store, topic: str) -> list[str]:
    """How many records each source holds for the topic, and its latest date: a source that
    stops early cannot speak about recent photos."""
    counts: Counter[str] = Counter()
    latest: dict[str, datetime] = {}
    for item in store.evidence:
        if item.topic != topic:
            continue
        counts[item.source] += 1
        if item.start and (item.source not in latest or item.start > latest[item.source]):
            latest[item.source] = item.start
    return [f"{source}: {n:,} records" + (f", latest {day(latest[source])}" if source in latest else "") for source, n in counts.most_common()]


def count_window_records(store: Store, site: dict[str, Any], photos: list[dict[str, Any]]) -> None:
    """How many of the topic's records an investigation of each photo would see, for its date."""
    counts: dict[str, int] = {}
    for photo in photos:
        taken = times.parse(photo.get("captured_at"), "utc")
        if taken is None:
            photo["records_in_window"] = 0
            continue
        key = taken.date().isoformat()
        if key not in counts:
            found = store.near(site["lat"], site["lon"], TOPICS[site["topic"]].radius_m, *window(site["topic"], taken), site["topic"])
            counts[key] = sum(
                1 for hit in found.hits
                if in_topic(site["topic"], hit.evidence.topic, hit.evidence.category) and hit.evidence.category not in STATE_CATEGORIES
            )
        photo["records_in_window"] = counts[key]


def best_window(site: dict[str, Any]) -> int:
    return max((photo.get("records_in_window", 0) for photo in site.get("photos") or []), default=0)


def best_photos(photos: list[dict[str, Any]], site: dict[str, Any], keep: int = 5) -> list[dict[str, Any]]:
    """Photos most likely to show the site: facing it and close.

    For a shed: the closest taken while the permits were valid, plus the closest from
    before (a "what has changed" pair). For a topic site: those whose date puts the most
    records in the investigation's window, closest first. For a flood corner: the newest,
    closest first.
    """
    photos = [photo | {"when": photo_period(photo, site)} for photo in photos]
    facing = [photo for photo in photos if photo["faces_site"]]
    pool = facing or photos
    if site.get("up_since"):
        during = sorted((p for p in pool if p["when"] == "while shed permits were valid"), key=lambda p: p["distance_m"])
        before = sorted((p for p in pool if p["when"] == "before the current shed permits"), key=lambda p: p["distance_m"])
        return during[: keep - 1] + before[:1] if during else before[:keep]
    if site.get("topic"):
        return sorted(pool, key=lambda p: (-p.get("records_in_window", 0), p["distance_m"]))[:keep]
    return sorted(pool, key=lambda p: ((p["captured_at"] or "")[:10], -p["distance_m"]), reverse=True)[:keep]


def add_photos(sites: list[dict[str, Any]], keep: int = 5, store: Store | None = None) -> None:
    for site in sites:
        try:
            photos = photos_near(site["lat"], site["lon"], PHOTO_RADIUS_M)
        except Exception as error:  # one failed search should not stop the shortlist
            site["photos_error"] = f"{type(error).__name__}: {error}"[:300]
            continue
        years = sorted({(photo["captured_at"] or "")[:4] for photo in photos if photo["captured_at"]})
        site["photo_count"] = len(photos)
        site["facing_count"] = sum(1 for photo in photos if photo["faces_site"])
        site["photo_years"] = f"{years[0]} to {years[-1]}" if years else None
        if store is not None and site.get("topic"):
            count_window_records(store, site, photos)
        site["photos"] = best_photos(photos, site, keep)
        if site.get("topic") and site["photos"]:
            # The site, not the camera, is what the question is about: the photo faces it from up to 40 m away.
            question = TOPICS[site["topic"]].example.replace('"', "'")
            site["command"] = (
                f'python -m city_investigator.investigate {site["photos"][0]["id"]} --question "{question}" '
                f'--topic {site["topic"]} --lat {site["lat"]:.6f} --lon {site["lon"]:.6f} --yes --explain'
            )


def photo_period(photo: dict[str, Any], site: dict[str, Any]) -> str | None:
    """For a shed site: was the photo taken before the permits or while they were valid?"""
    taken = (photo.get("captured_at") or "")[:10]
    since, until = site.get("up_since"), site.get("permit_valid_until")
    if not taken or not since:
        return None
    if taken < since:
        return "before the current shed permits"
    if until and taken <= until:
        return "while shed permits were valid"
    return "after the permits"


def photo_lines(site: dict[str, Any]) -> list[str]:
    if "photos_error" in site:
        return [f"  - Photo search failed: {site['photos_error']}"]
    if "photos" not in site:
        return []
    if not site["photos"]:
        return [f"  - No Mapillary photos within {PHOTO_RADIUS_M} m."]
    lines = [
        f"  - {site['photo_count']} photos within {PHOTO_RADIUS_M} m ({site['facing_count']} facing the site), "
        f"taken {site['photo_years']}; best candidates:"
    ]
    for photo in site["photos"]:
        facing = {True: ", facing the site", False: ", facing away", None: ""}[photo.get("faces_site")]
        when = (f", {photo['when']}" if photo.get("when") else "") + facing
        if "records_in_window" in photo:
            when += f", {photo['records_in_window']} records in its window"
        lines.append(
            f"  - [{(photo['captured_at'] or 'undated')[:10]}, {photo['distance_m']} m away{when}]({photo['page_url']}): {photo['credit']}"
        )
    return lines


def topic_markdown(topic: str, sites: list[dict[str, Any]], sources: list[str] | None = None) -> list[str]:
    spec = TOPICS[topic]
    days = spec.lookback_days or 365
    back = f"{days // 365} year{'s' if days >= 730 else ''}" if days >= 365 else f"{days} days"
    lines = [
        "",
        f"## {spec.label}",
        "",
        *[f"- {line}" for line in sources or []],
        "",
        f"Within {spec.radius_m:.0f} m, records from the last {SITE_YEARS} years (and standing records such as inventories). "
        f"A photo's window is what an investigation of its date looks at: {back} before to a month after.",
        "",
        "| # | Address | Sources | Records | First | Latest | Best photo: date, records in its window | Street View |",
        "|---|---|---|---|---|---|---|---|",
    ]
    if not sites:
        return [*lines, "| - | No records of this topic in the snapshot | | | | | | |"]
    for index, site in enumerate(sites, 1):
        records = ", ".join(f"{category} {n}" for category, n in site["records"].items())
        place = site["address"] or f"{site['lat']:.5f}, {site['lon']:.5f}"
        best = site.get("photos") or []
        photo = f"{(best[0]['captured_at'] or 'undated')[:10]}, {best[0].get('records_in_window', '-')}" if best else "-"
        lines.append(
            f"| {index} | {place} | {len(site['sources'])} | {records} | "
            f"{site['first'] or '-'} | {site['latest'] or '-'} | {photo} | [view]({site['street_view']}) |"
        )
    for index, site in enumerate(sites, 1):
        extra = photo_lines(site)
        lines += ["", f"{spec.label} site {index} ({site['address'] or 'no address'}): newest records:"]
        lines += [f"  - {summary}" for summary in site["newest"]]
        lines += extra
        if site.get("command"):
            lines.append(f"  - Investigate the best photo: `{site['command']}`")
    return lines


def to_markdown(
    sheds: list[dict[str, Any]], floods: list[dict[str, Any]], generated: datetime,
    topics: dict[str, list[dict[str, Any]]] | None = None, sources: dict[str, list[str]] | None = None,
) -> str:
    lines = [
        "# Demo site shortlist",
        "",
        f"Generated {times.to_local(generated):%Y-%m-%d %H:%M} New York time from the local snapshots.",
        "Street View links are for looking with your own eyes; the app's evidence comes from records and Mapillary photos.",
        "",
        "## Longest-standing sidewalk sheds (permits active today)",
        "",
        "| # | Address | Permitted since | Years | Permits in current run | Gaps over 30 days | 311 complaints within 50 m since then | Street View |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for index, site in enumerate(sheds, 1):
        complaints = ", ".join(f"{name} {n}" for name, n in site["complaints_nearby_since"].items()) or "none"
        lines.append(
            f"| {index} | {site['address'] or site['bin']} | {site['up_since']} | {site['days_up'] / 365.25:.1f} | "
            f"{site['permits_in_current_run']} | {len(site['gaps_over_bridge'])} | {complaints} | [view]({site['street_view']}) |"
        )
    for index, site in enumerate(sheds, 1):
        extra = photo_lines(site)
        if extra:
            lines += ["", f"Photos near shed {index} ({site['address']}):", *extra]
    lines += [
        "",
        "## Flood sensor corners",
        "",
        "| # | Sensor | Events | Deepest (in) | Latest event | Sensor since | 311 flood complaints within 150 m since then | Tidal | Street View |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for index, site in enumerate(floods, 1):
        lines.append(
            f"| {index} | {site['sensor']} | {site['events']} | {site['max_depth_in'] or '-'} | "
            f"{site['latest_event'] if site['events'] else '-'} | "
            f"{site['first_installed']} | {site['flood_complaints_nearby_since_install']} | {'yes' if site['tidal'] else 'no'} | "
            f"[view]({site['street_view']}) |"
        )
    for index, site in enumerate(floods, 1):
        extra = photo_lines(site)
        if extra:
            lines += ["", f"Photos near flood corner {index} ({site['sensor']}):", *extra]
    for topic, sites in (topics or {}).items():
        lines += topic_markdown(topic, sites, (sources or {}).get(topic))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--photos", action="store_true", help="add nearby Mapillary photos (needs MAPILLARY_TOKEN)")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--topic", action="append", choices=NEW_TOPICS, help="only these newer topics (repeatable); default all")
    args = parser.parse_args()
    load_env()
    store = Store.load()
    at = times.now()
    sheds = shed_sites(store, at, args.top)
    floods = flood_sites(store, args.top)
    chosen = args.topic or NEW_TOPICS
    sources = {topic: topic_sources(store, topic) for topic in chosen}
    topics = {topic: topic_sites(store, topic, at, args.top) for topic in chosen}
    if args.photos:
        add_photos(sheds)
        add_photos(floods)
        # Mapillary photos are years old: rank topic sites again by the records their best photo's date can see.
        for topic in chosen:
            candidates = topic_sites(store, topic, at, args.top * 3)
            add_photos(candidates, store=store)
            topics[topic] = sorted(candidates, key=lambda site: -best_window(site))[: args.top]
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    (DERIVED_DIR / "shortlist.json").write_text(json.dumps({"sheds": sheds, "flood_corners": floods, "topics": topics}, indent=2))
    markdown = to_markdown(sheds, floods, at, topics, sources)
    (DERIVED_DIR / "shortlist.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"Saved to {DERIVED_DIR / 'shortlist.md'}")


if __name__ == "__main__":
    main()
