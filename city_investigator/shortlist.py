"""Shortlist demo sites: the longest-standing sheds and the most-flooded sensor corners.

Writes data/derived/shortlist.md and shortlist.json. Every site has a Street View
link for scouting by eye and, with --photos and MAPILLARY_TOKEN set, the newest
Mapillary photos nearby, which the app may use with credit.

Usage:
  python -m city_investigator.shortlist
  python -m city_investigator.shortlist --photos
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from city_investigator import times
from city_investigator.evidence import Sensor, day
from city_investigator.geo import to_float
from city_investigator.photos import photos_near
from city_investigator.settings import DERIVED_DIR, load_env
from city_investigator.sheds import build_chains
from city_investigator.store import Store

SHED_COMPLAINT_RADIUS_M = 50
FLOOD_COMPLAINT_RADIUS_M = 150
PHOTO_RADIUS_M = 40


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


def add_photos(sites: list[dict[str, Any]], keep: int = 5) -> None:
    for site in sites:
        try:
            site["photos"] = photos_near(site["lat"], site["lon"], PHOTO_RADIUS_M)[:keep]
        except Exception as error:  # one failed search should not stop the shortlist
            site["photos_error"] = f"{type(error).__name__}: {error}"[:300]


def photo_lines(site: dict[str, Any]) -> list[str]:
    if "photos_error" in site:
        return [f"  - Photo search failed: {site['photos_error']}"]
    if "photos" not in site:
        return []
    if not site["photos"]:
        return [f"  - No Mapillary photos within {PHOTO_RADIUS_M} m."]
    return [
        f"  - [{(photo['captured_at'] or 'undated')[:10]}, {photo['distance_m']} m away]({photo['page_url']}): {photo['credit']}"
        for photo in site["photos"]
    ]


def to_markdown(sheds: list[dict[str, Any]], floods: list[dict[str, Any]], generated: datetime) -> str:
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
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--photos", action="store_true", help="add nearby Mapillary photos (needs MAPILLARY_TOKEN)")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    load_env()
    store = Store.load()
    at = times.now()
    sheds = shed_sites(store, at, args.top)
    floods = flood_sites(store, args.top)
    if args.photos:
        add_photos(sheds)
        add_photos(floods)
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    (DERIVED_DIR / "shortlist.json").write_text(json.dumps({"sheds": sheds, "flood_corners": floods}, indent=2))
    markdown = to_markdown(sheds, floods, at)
    (DERIVED_DIR / "shortlist.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"Saved to {DERIVED_DIR / 'shortlist.md'}")


if __name__ == "__main__":
    main()
