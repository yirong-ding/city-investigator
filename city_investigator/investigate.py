"""Run one investigation: a photo and a question in; observations, records, coverage and flags out.

Steps:
  1. Bring in the photo (a Mapillary ID or a file) and confirm where and when it was taken.
  2. Blur faces and license plates. Mapillary photos arrive already blurred; for your own
     photos SAM 3.1 finds them, which sends the unblurred photo to Meta's API once.
  3. Look for what the question is about with SAM 3.1. Each find is an observation.
  4. Gather records and coverage notes for that place and time from the local snapshots.
  5. Run rule-based checks that compare the photo with the records.
  6. Save everything to data/private/investigations/<run>/ (never committed).
  7. With --explain, Muse Spark writes the labeled, cited explanation (see explain.py).

Usage:
  python -m city_investigator.investigate 1306991370360816 --question "What records relate to this blocked sidewalk?" --explain
  python -m city_investigator.investigate 1385498442151420 --question "Is flooding a recurring problem here?" --when 2026-08-23
  python -m city_investigator.investigate my_photo.jpg --question "Is this flooding recurring?" --lat 40.6763 --lon -73.9841
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from city_investigator import times
from city_investigator.buildings import SOURCE as GROUND_SOURCE
from city_investigator.checks import Flag, flood_checks, ground_checks, sidewalk_checks, topic_checks
from city_investigator.evidence import Evidence, day
from city_investigator.geo import distance_m
from city_investigator.meta import PROVIDERS, SpendGuard, data_url, env_float, meta_client
from city_investigator.photo_input import Photo, from_file, from_mapillary
from city_investigator.segment import blur_regions, draw_overlay, segment, summarize
from city_investigator.settings import ROOT, load_env
from city_investigator.sheds import ShedChain, build_chains
from city_investigator.shortlist import street_view
from city_investigator.store import FOUND, NO_COVERAGE, Coverage, Hit, LookupResult, Store, overlaps
from city_investigator.topics import TOPICS, detect_topic, window

OUTPUT = ROOT / "data" / "private" / "investigations"
# What SAM 3.1 looks for, per topic. For flooding, "storm drain" finds the street drains that
# "catch basin" missed on the Carroll St/4th Av photo.
CONCEPTS = {key: list(topic.concepts) for key, topic in TOPICS.items()}
PRIVACY_CONCEPTS = ["face", "license plate"]
RADIUS_M = {key: topic.radius_m for key, topic in TOPICS.items()}
MIN_CONFIDENCE = 0.4
RECURRING_DAYS = 3
USER_UNCERTAINTY_M = 10.0
STREET_FLOOD_COMPLAINTS = {"street_flooding", "catch_basin", "manhole_overflow"}

# Reports each step as it starts; the terminal prints it, the web page streams it.
Progress = Callable[[str], None]


def say(message: str) -> None:
    print(f"  {message}", flush=True)


def parse_local(text: str) -> datetime:
    """A New York date or date and time, as UTC; a bare date means noon."""
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            moment = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt == "%Y-%m-%d":
            moment = moment.replace(hour=12)
        return moment.replace(tzinfo=times.LOCAL).astimezone(timezone.utc)
    raise ValueError(f"not a date: {text!r} (use YYYY-MM-DD or YYYY-MM-DD HH:MM)")


def parse_point(text: str) -> tuple[float, float]:
    lat_text, lon_text = text.replace(" ", "").split(",")
    return float(lat_text), float(lon_text)


# 1. Photo, place and time


def load_input(source: str) -> Photo:
    path = Path(source)
    if path.is_file():
        return from_file(path)
    if source.isdigit():
        token = os.environ.get("MAPILLARY_TOKEN")
        if not token:
            raise SystemExit("MAPILLARY_TOKEN is not set.")
        return from_mapillary(source, token)
    raise SystemExit(f"{source} is neither a file nor a Mapillary photo ID.")


def confirm_place_and_time(photo: Photo, args: argparse.Namespace) -> None:
    """The confirmed pin, not the photo's metadata, is the record."""
    if args.lat is not None and args.lon is not None:
        photo.lat, photo.lon = args.lat, args.lon
        photo.location_source, photo.uncertainty_m = "user", USER_UNCERTAINTY_M
    if args.taken:
        photo.taken_at = parse_local(args.taken)
    if photo.lat is None or photo.lon is None:
        if args.yes:
            raise SystemExit("The photo has no location. Add --lat and --lon.")
        photo.lat, photo.lon = parse_point(input("The photo has no location. Type latitude,longitude: "))
        photo.location_source, photo.uncertainty_m = "user", USER_UNCERTAINTY_M
    elif not args.yes:
        print(f"Location: {photo.lat:.6f}, {photo.lon:.6f} (from {photo.location_source}, about {photo.uncertainty_m:.0f} m)")
        print(f"  Check it by eye: {street_view(photo.lat, photo.lon)}")
        answer = input("Use this location? [Y/n, or type latitude,longitude]: ").strip().lower()
        if answer not in ("", "y", "yes"):
            text = input("Type latitude,longitude: ") if answer in ("n", "no") else answer
            photo.lat, photo.lon = parse_point(text)
            photo.location_source, photo.uncertainty_m = "user", USER_UNCERTAINTY_M
    if photo.taken_at is None:
        if args.yes:
            raise SystemExit("The photo has no date. Add --taken YYYY-MM-DD.")
        photo.taken_at = parse_local(input("When was the photo taken? (YYYY-MM-DD or YYYY-MM-DD HH:MM): "))


# 2 and 3. Privacy and observations


async def run_sam(
    photo: Photo, topic: str, guard: SpendGuard, progress: Progress = say
) -> tuple[bytes, int, list[tuple[str, Any]]]:
    """Blur faces and plates if needed, then segment the topic's concepts on the blurred photo."""
    price = env_float("SAM_USD_PER_IMAGE", 0.0025)
    jpeg = photo.jpeg
    blurred = 0
    async with meta_client(async_client=True) as api:

        async def call(image: bytes, concept: str) -> Any:
            guard.check()
            try:
                return await segment(api, data_url(image), concept)
            finally:
                guard.record(price)

        if not photo.already_blurred:
            progress("SAM 3.1 is finding faces and license plates to blur")
            boxes = []
            for concept in PRIVACY_CONCEPTS:
                result = await call(jpeg, concept)
                boxes += [(r.left, r.top, r.right, r.bottom) for r in result.records if r.kind == "box"]
            jpeg, blurred = blur_regions(jpeg, boxes), len(boxes)
        results = []
        for concept in CONCEPTS[topic]:
            progress(f"SAM 3.1 is looking for {concept}")
            results.append((concept, await call(jpeg, concept)))
    return jpeg, blurred, results


def observations_from(results: list[tuple[str, Any]], photo: Photo, topic: str) -> tuple[list[Evidence], list[str]]:
    observed: list[Evidence] = []
    not_seen: list[str] = []
    width, height = photo.size
    for concept, result in results:
        summary = summarize(result, concept, photo.size)
        boxes = [box for box in summary["boxes"] if box["confidence"] is None or box["confidence"] >= MIN_CONFIDENCE]
        if not boxes:
            not_seen.append(concept)
            continue
        kept = {box["object_id"] for box in boxes}
        share = sum(m["pixels"] for m in summary["mask_pixels"] if m["object_id"] in kept) / (width * height)
        best = max((box["confidence"] for box in boxes if box["confidence"] is not None), default=None)
        share_text = "under 1%" if share < 0.01 else f"about {share:.0%}"
        best_text = f", highest confidence {best:.2f}" if best is not None else ""
        observed.append(
            Evidence(
                id=f"photo:{concept.replace(' ', '_')}",
                kind="observation",
                topic=topic,
                category=f"seen_{concept.replace(' ', '_')}",
                source="SAM 3.1 segmentation of the photo",
                dataset="photo",
                summary=f"The photo shows {concept}: {len(boxes)} region(s){best_text}, {share_text} of the image",
                lat=photo.lat,
                lon=photo.lon,
                located_by="photo",
                start=photo.taken_at,
                end=None,
                url=photo.page_url or "",
                raw={"boxes": boxes, "share_of_image": round(share, 4)},
            )
        )
    return observed, not_seen


# 4. Records and coverage


def gather_sidewalk(
    store: Store, lat: float, lon: float, radius: float, when: datetime
) -> tuple[list[Hit], list[Coverage], list[ShedChain], list[Evidence]]:
    at_photo = store.near(lat, lon, radius, when - timedelta(days=7), when + timedelta(days=7), "sidewalk")
    around = store.near(lat, lon, radius, when - timedelta(days=90), when + timedelta(days=30), "sidewalk")
    permits = [hit for hit in at_photo.hits if hit.evidence.category.endswith("_permit")]
    permit_bbls = {hit.evidence.bbl for hit in permits if hit.evidence.bbl}
    lots = [Hit(store.lot_by_bbl[bbl], None) for bbl in sorted(permit_bbls) if bbl in store.lot_by_bbl]
    if not lots:  # no permits: fall back to the lot nearest the photo
        lots = [hit for hit in at_photo.hits if hit.evidence.category == "lot"]
    complaints = [hit for hit in around.hits if hit.evidence.id.startswith("311:")]
    coverage = [c for c in around.coverage if c.source.startswith("311")] + [
        c for c in at_photo.coverage if "permit" in c.source
    ]
    bins = {hit.evidence.bin for hit in permits if hit.evidence.bin}
    chains = build_chains(item for item in store.evidence if item.bin in bins)
    # Records show permits from the week around the photo; checks use only those valid on its day.
    photo_day = times.to_local(when).date()
    valid = [
        hit.evidence
        for hit in permits
        if overlaps(hit.evidence, times.local_day_start(photo_day), times.local_day_end(photo_day))
    ]
    return lots + permits + complaints, coverage, chains, valid


def gather_topic(
    store: Store, lat: float, lon: float, radius: float, when: datetime, topic: str
) -> tuple[list[Hit], list[Coverage]]:
    """For the newer topics: complaints and agency records from the topic's lookback until a month after."""
    found = store.near(lat, lon, radius, *window(topic, when), topic)
    return found.hits, found.coverage


def recurrence(store: Store, history: LookupResult, lat: float, lon: float, radius: float) -> dict[str, Any]:
    events = [hit.evidence for hit in history.hits if hit.evidence.category == "flood_event"]
    street = [hit.evidence for hit in history.hits if hit.evidence.category in STREET_FLOOD_COMPLAINTS]
    indoor = [hit.evidence for hit in history.hits if hit.evidence.category == "sewer_backup"]

    def days(items: list[Evidence]) -> list[str]:
        return sorted({day(item.start) for item in items if item.start})

    sensors = sorted(
        {
            (sensor.name, day(sensor.installed))
            for sensor in store.sensors
            if sensor.lat is not None and sensor.lon is not None and distance_m(lat, lon, sensor.lat, sensor.lon) <= radius
        }
    )
    depths = [float(item.raw["max_depth_inches"]) for item in events if item.raw.get("max_depth_inches")]
    sensor_days, street_days = days(events), days(street)
    return {
        "definition": (
            f"Recurring means flood evidence on at least {RECURRING_DAYS} separate days within {radius:.0f} m, "
            "counted separately for each source within the years that source covers."
        ),
        "floodnet": {
            "sensors": [{"name": name, "installed": installed} for name, installed in sensors],
            "events": len(events),
            "days": len(sensor_days),
            "deepest_in": max(depths, default=None),
            "first": sensor_days[0] if sensor_days else None,
            "last": sensor_days[-1] if sensor_days else None,
            "recurring": len(sensor_days) >= RECURRING_DAYS,
        },
        "street_flood_complaints": {
            "complaints": len(street),
            "days": len(street_days),
            "first": street_days[0] if street_days else None,
            "last": street_days[-1] if street_days else None,
            "covers": "2010 onward",
            "recurring": len(street_days) >= RECURRING_DAYS,
        },
        "indoor_sewer_backup_complaints": {"complaints": len(indoor), "days": len(days(indoor))},
    }


def gather_flooding(
    store: Store, lat: float, lon: float, radius: float, when: datetime
) -> tuple[list[Hit], list[Coverage], dict[str, Any], float | None, str | None]:
    moment = store.near(lat, lon, radius, when - timedelta(hours=24), when + timedelta(hours=72), "flooding")
    history = store.near(lat, lon, radius, None, None, "flooding")
    sensor_state = next((c.state for c in moment.coverage if c.source == "FloodNet flood sensors"), None)
    # Include the hourly reading that covers the moment itself.
    rain_before = store.rain_total(when - timedelta(hours=24), when + timedelta(hours=1))
    rec = recurrence(store, history, lat, lon, radius) | {
        "evidence_ids": [hit.evidence.id for hit in history.hits if hit.evidence.topic == "flooding"]
    }
    return moment.hits, moment.coverage, rec, rain_before, sensor_state


# 5 and 6. Checks, report, files


def print_report(result: dict[str, Any]) -> None:
    photo = result["photo"]
    print(f"\nInvestigation: {result['question']!r} (topic: {result['topic']})")
    print(f"Photo: {photo['source']} {photo['ref']}, taken {photo['taken_local']}" + (f"; {photo['credit']}" if photo["credit"] else ""))
    location = photo["location"]
    uncertainty = f"about {location['uncertainty_m']:.0f} m" if location["uncertainty_m"] else "accuracy unknown"
    print(f"Place: {location['lat']:.6f}, {location['lon']:.6f} (from {location['source']}, {uncertainty})")
    if result["question_moment"] != photo["taken_local"]:
        print(f"Question is about: {result['question_moment']}")
    print("\nObserved in the photo")
    for item in result["observations"]:
        print(f"  - {item['summary']}  [{item['id']}]")
    if result["not_seen"]:
        print(f"  - Not seen: {', '.join(result['not_seen'])}")
    print(f"\nRecords ({len(result['records'])})")
    for item in result["records"][:25]:
        when = (item["start"] or {}).get("local", "undated")[:10]
        distance = f"{item['distance_m']} m" if item["distance_m"] is not None else ""
        print(f"  {when:10}  {distance:>6}  {item['category']}: {item['summary']}  [{item['id']}]")
    if result.get("shed_chains"):
        print("\nShed history (by building)")
    for chain in result.get("shed_chains", []):
        earlier = ", ".join(f"{e['from'][:4]} to {e['to'][:4]}" for e in chain["earlier_sheds"])
        print(
            f"  {chain['address']}: permitted without a break since {chain['up_since']}, valid until "
            f"{chain['permit_valid_until']}, {chain['permits_in_current_run']} permit(s)"
            + (f"; {len(chain['gaps_over_bridge'])} paperwork gap(s) of 1 to 6 months" if chain["gaps_over_bridge"] else "")
            + (f"; earlier sheds: {earlier}" if earlier else "")
        )
    if "recurrence" in result:
        rec = result["recurrence"]
        print(f"\nRecurrence ({rec['definition']})")
        sensor = rec["floodnet"]
        names = ", ".join(f"{s['name']} (since {s['installed']})" for s in sensor["sensors"]) or "no sensor in range"
        def verdict(source: dict[str, Any]) -> str:
            return "recurring by this definition" if source["recurring"] else "not recurring by this definition"

        print(f"  FloodNet: {sensor['events']} events on {sensor['days']} days, deepest {sensor['deepest_in']} in: {verdict(sensor)}; sensors: {names}")
        street = rec["street_flood_complaints"]
        print(
            f"  311 street flooding and catch basins: {street['complaints']} complaints on {street['days']} days "
            f"({street['first']} to {street['last']}): {verdict(street)}"
        )
        print(f"  311 indoor sewer backups: {rec['indoor_sewer_backup_complaints']['complaints']} complaints")
    print("\nCoverage")
    for item in result["coverage"]:
        print(f"  [{item['state'].upper()}] {item['source']}: {item['note']}")
    print("\nFlags")
    for flag in result["flags"] or [{"severity": "none", "type": "-", "message": "No flags raised."}]:
        print(f"  [{flag['severity'].upper()}] {flag['type']}: {flag['message']}")


async def investigate_photo(
    photo: Photo,
    question: str,
    topic: str | None = None,
    when: datetime | None = None,
    radius: float | None = None,
    store: Store | None = None,
    progress: Progress = say,
) -> tuple[dict[str, Any], Path]:
    """Steps 2 to 6 for a photo whose place and time are confirmed: (result, run folder)."""
    assert photo.lat is not None and photo.lon is not None and photo.taken_at is not None
    topic = topic or detect_topic(question)
    if topic is None:
        raise ValueError("Could not tell which kind of problem the question is about; choose a topic.")
    when = when or photo.taken_at
    radius = radius or RADIUS_M[topic]

    guard = SpendGuard(max_calls=len(PRIVACY_CONCEPTS) + len(CONCEPTS[topic]))
    jpeg, blurred, results = await run_sam(photo, topic, guard, progress)
    observations, not_seen = observations_from(results, photo, topic)

    progress(f"Gathering public records within {radius:.0f} m, with what each source can and cannot see")
    store = store or Store.load()
    extra: dict[str, Any] = {}
    if topic == "sidewalk":
        hits, coverage, chains, permits_at_photo = gather_sidewalk(store, photo.lat, photo.lon, radius, when)
        distances = {hit.evidence.id: hit.distance_m for hit in hits if hit.distance_m is not None}
        progress("Comparing the photo with the permits and complaints")
        flags: list[Flag] = sidewalk_checks(observations, permits_at_photo, chains, when, distances)
        extra["shed_chains"] = [chain.to_dict(times.now()) for chain in chains]
    elif topic != "flooding":
        hits, coverage = gather_topic(store, photo.lat, photo.lon, radius, when, topic)
        distances = {hit.evidence.id: hit.distance_m for hit in hits if hit.distance_m is not None}
        progress("Comparing the photo with the complaints and the agency's own records")
        flags = topic_checks(topic, observations, [hit.evidence for hit in hits], when, distances)
    else:
        hits, coverage, rec, rain_before, sensor_state = gather_flooding(store, photo.lat, photo.lon, radius, when)
        model_state = next((c.state for c in coverage if c.source == "City stormwater flood maps"), None)
        peak = store.rain_peak(when - timedelta(hours=24), when + timedelta(hours=72))
        progress("Comparing the photo, sensors, complaints, rain and the city's flood model")
        flags = flood_checks(
            observations, [hit.evidence for hit in hits], rain_before, sensor_state, photo.taken_at, when, model_state,
            peak[1] if peak else None,
        )
        ground = store.buildings.ground_here(photo.lat, photo.lon)
        if ground:
            hits.append(Hit(ground, 0.0))
            coverage.append(Coverage(GROUND_SOURCE, FOUND, ground.summary))
        else:
            coverage.append(Coverage(
                GROUND_SOURCE, NO_COVERAGE,
                "Not downloaded: run python -m city_investigator.snapshot --only building_footprints."
                if "building_footprints" not in store.loaded else "Too few buildings with a ground elevation around the pin.",
            ))
        recurring = [f"recurrence:{key}" for key in ("floodnet", "street_flood_complaints") if rec[key]["recurring"]]
        flags += ground_checks(ground, recurring)
        extra["recurrence"] = rec
        extra["rain_in_24h_before"] = rain_before
        if peak:
            extra["rain_wettest_hour"] = {"inches": peak[1], "ending": times.to_local(peak[0]).strftime("%Y-%m-%d %H:%M")}

    run_dir = OUTPUT / f"{times.now():%Y%m%d-%H%M%S}-{photo.ref.replace('.', '_')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "photo.jpg").write_bytes(jpeg)
    (run_dir / "overlay.png").write_bytes(draw_overlay(jpeg, results))
    result = {
        "question": question,
        "topic": topic,
        "topic_label": TOPICS[topic].label,
        "question_moment": times.to_local(when).strftime("%Y-%m-%d %H:%M"),
        "radius_m": radius,
        "photo": photo.describe() | {"faces_and_plates_blurred_here": blurred},
        "observations": [item.to_dict() for item in observations],
        "not_seen": not_seen,
        "records": [hit.evidence.to_dict(hit.distance_m) for hit in hits],
        "coverage": [item.to_dict() for item in coverage],
        "flags": [flag.to_dict() for flag in flags],
        **extra,
        "files": {"photo": str(run_dir / "photo.jpg"), "overlay": str(run_dir / "overlay.png")},
        "estimated_spend_today_usd": round(guard.spent_today(), 4),
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result, run_dir


async def investigate(args: argparse.Namespace) -> dict[str, Any]:
    photo = load_input(args.source)
    confirm_place_and_time(photo, args)
    store = Store.load()
    when = parse_local(args.when) if args.when else None
    try:
        result, run_dir = await investigate_photo(photo, args.question, args.topic, when, args.radius, store)
    except ValueError as error:
        raise SystemExit(f"{error} Add --topic.") from error
    print_report(result)
    print(f"\nSaved to {run_dir}")
    if args.explain:
        from city_investigator.explain import explain_run, print_explanation  # explain imports this module

        print(f"\nAsking Muse Spark ({args.provider}) to explain {run_dir.name} ...")
        print_explanation(explain_run(run_dir, args.provider, store), run_dir)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", help="a Mapillary photo ID or a photo file")
    parser.add_argument("--question", required=True)
    parser.add_argument("--topic", choices=sorted(TOPICS), help="the kind of problem (guessed from the question)")
    parser.add_argument("--lat", type=float, help="set the location instead of the photo's")
    parser.add_argument("--lon", type=float)
    parser.add_argument("--taken", help="when the photo was taken, if it has no date (YYYY-MM-DD [HH:MM])")
    parser.add_argument("--when", help="the moment the question is about, if not the photo's (YYYY-MM-DD [HH:MM])")
    parser.add_argument("--radius", type=float, help="meters (each topic has its own default, from 25 to 150)")
    parser.add_argument("--yes", action="store_true", help="accept the photo's location without asking")
    parser.add_argument("--explain", action="store_true", help="have Muse Spark write the labeled explanation")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="meta", help="for --explain: meta or open (Baseten)")
    args = parser.parse_args()
    load_env()
    asyncio.run(investigate(args))


if __name__ == "__main__":
    main()
