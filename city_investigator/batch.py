"""Investigate many shortlisted places in one go and add up what the records and photos show.

Reads data/derived/shortlist.json (from `shortlist --photos`), investigates the best photo of
each site at the site itself, has Muse Spark explain it, and writes data/derived/batch.json,
batch.md and batch.geojson (one point per site with its flags, for the page's map). Sites
already in batch.json with the same photo are kept, not paid for again; the run stops cleanly
at the daily spend cap.

Usage:
  python -m city_investigator.batch --topic trees --limit 3
  python -m city_investigator.batch --limit 5          # up to 5 sites of every topic
  python -m city_investigator.batch --limit 3 --again  # investigate every site again (after the checks change)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

from city_investigator import times
from city_investigator.meta import PROVIDERS, SpendCapError
from city_investigator.photo_input import from_mapillary
from city_investigator.settings import DERIVED_DIR, load_env
from city_investigator.store import Store
from city_investigator.topics import TOPICS

SEVERITY_ORDER = ("conflict", "gap", "agreement")
SITE_RADIUS_M = 10.0  # the site's point stands for the place the photo faces


def facing(site: dict[str, Any]) -> dict[str, Any] | None:
    """The site's best photo that does not face away from it: one facing away cannot show it."""
    return next((photo for photo in site.get("photos") or [] if photo.get("faces_site") is not False), None)


def plan(shortlist: dict[str, Any], topics: list[str] | None, limit: int) -> list[dict[str, Any]]:
    """One job per shortlisted site with a photo that can show it: the topic, the site and that photo."""
    groups = {"sidewalk": shortlist.get("sheds", []), "flooding": shortlist.get("flood_corners", []), **shortlist.get("topics", {})}
    jobs = []
    for topic, sites in groups.items():
        if topics and topic not in topics:
            continue
        usable = [(site, photo) for site in sites if (photo := facing(site))]
        for site, photo in usable[:limit]:
            jobs.append({
                "topic": topic,
                "place": site.get("address") or site.get("sensor") or f"{site['lat']:.5f}, {site['lon']:.5f}",
                "lat": site["lat"],
                "lon": site["lon"],
                "photo_id": photo["id"],
            })
    return jobs


def key(job: dict[str, Any]) -> tuple[str, str, float, float]:
    return job["topic"], job["photo_id"], round(job["lat"], 5), round(job["lon"], 5)


async def run_job(job: dict[str, Any], store: Store, provider: str, explain: bool) -> dict[str, Any]:
    from city_investigator.explain import explain_run  # explain imports investigate
    from city_investigator.investigate import investigate_photo

    photo = from_mapillary(job["photo_id"], os.environ["MAPILLARY_TOKEN"])
    if photo.taken_at is None:
        raise ValueError("the photo has no date")
    photo.lat, photo.lon = job["lat"], job["lon"]
    photo.location_source, photo.uncertainty_m = "shortlist", SITE_RADIUS_M
    result, run_dir = await investigate_photo(photo, TOPICS[job["topic"]].example, job["topic"], store=store)
    entry = job | {
        "run": run_dir.name,
        "photo_date": result["photo"]["taken_local"][:10],
        "photo_credit": result["photo"].get("credit"),
        "records": len(result["records"]),
        "coverage": {note["source"]: note["state"] for note in result["coverage"]},
        "flags": [{"type": flag["type"], "severity": flag["severity"], "message": flag["message"]} for flag in result["flags"]],
    }
    if explain:
        explanation = explain_run(run_dir, provider, store)  # as the investigate command does; sites run one at a time
        entry["explanation"] = {
            "answer": explanation["claims"][0]["text"] if explanation["claims"] else None,
            "claims": len(explanation["claims"]),
            "dropped": len(explanation["dropped"]),
            "repairs": explanation["repairs"],
            "lookups": [call.get("tool") for call in explanation["tool_calls"]],
            "models_disagree": len(explanation["models_disagree"]),
            "seconds": explanation["seconds"],
            "cost_usd": explanation["estimated_cost_usd"],
        }
    return entry


def worst(entry: dict[str, Any]) -> str:
    found = {flag["severity"] for flag in entry.get("flags", [])}
    return next((severity for severity in SEVERITY_ORDER if severity in found), "none")


def sites_with(done: list[dict[str, Any]], test: Any) -> int:
    return sum(1 for entry in done if any(test(flag) for flag in entry["flags"]))


def summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    done = [entry for entry in entries if "error" not in entry]
    explained = [entry["explanation"] for entry in done if entry.get("explanation")]
    flags = [flag for entry in done for flag in entry["flags"]]
    claims = sum(item["claims"] for item in explained)
    dropped = sum(item["dropped"] for item in explained)
    return {
        "sites": len(done),
        "failed": len(entries) - len(done),
        "records_considered": sum(entry["records"] for entry in done),
        "flags_by_severity": dict(Counter(flag["severity"] for flag in flags)),
        "flags_by_type": dict(Counter(f"{flag['severity']}: {flag['type']}" for flag in flags).most_common()),
        # Places, counted once each, by what their flags say.
        "sites_records_and_photo_disagree": sites_with(done, lambda flag: flag["severity"] == "conflict"),
        "sites_reported_again_and_again": sites_with(done, lambda flag: flag["type"] == "repeat_reports"),
        "sites_with_another_gap": sites_with(done, lambda flag: flag["severity"] == "gap" and flag["type"] != "repeat_reports"),
        "sites_records_and_photo_agree": sites_with(done, lambda flag: flag["severity"] == "agreement"),
        "explained": len(explained),
        "claims_kept": claims,
        "claims_removed": dropped,
        "claims_kept_share": round(claims / (claims + dropped), 3) if claims + dropped else None,
        "repair_rounds": sum(item["repairs"] for item in explained),
        "lookups": dict(Counter(tool for item in explained for tool in item["lookups"])),
        "model_vision_disagreements": sum(item["models_disagree"] for item in explained),
        "cost_usd": round(sum(item["cost_usd"] for item in explained), 3),
    }


def geojson(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [entry["lon"], entry["lat"]]},
                "properties": {
                    "topic": entry["topic"],
                    "label": TOPICS[entry["topic"]].label,
                    "place": entry["place"],
                    "worst": worst(entry),
                    "flags": [flag["type"] for flag in entry["flags"]],
                    "answer": (entry.get("explanation") or {}).get("answer"),
                    "run": entry["run"],
                },
            }
            for entry in entries if "error" not in entry
        ],
    }


def to_markdown(entries: list[dict[str, Any]], totals: dict[str, Any]) -> str:
    share = totals["claims_kept_share"]
    lines = [
        "# Batch investigation",
        "",
        f"Generated {times.to_local(times.now()):%Y-%m-%d %H:%M} New York time. Each site's best Mapillary photo, investigated at the site.",
        "",
        f"- Sites investigated: {totals['sites']} ({totals['failed']} failed); records considered: {totals['records_considered']}",
        f"- Places where the records and the photo (or the flood model) disagree: {totals['sites_records_and_photo_disagree']}",
        f"- Places where a problem was reported on 3 or more separate days: {totals['sites_reported_again_and_again']}",
        f"- Places with another gap in the records: {totals['sites_with_another_gap']}",
        f"- Places where the records and the photo agree: {totals['sites_records_and_photo_agree']}",
        "- Flags: " + (", ".join(f"{severity} {n}" for severity, n in totals["flags_by_severity"].items()) or "none"),
        f"- Claims kept after checking: {totals['claims_kept']} of {totals['claims_kept'] + totals['claims_removed']}"
        + (f" ({share:.0%})" if share is not None else "") + f"; repair rounds: {totals['repair_rounds']}",
        "- Muse Spark's lookups: " + (", ".join(f"{tool} {n}" for tool, n in totals["lookups"].items()) or "none")
        + f"; model and SAM 3.1 disagreed {totals['model_vision_disagreements']} times",
        f"- Cost of the explanations: about ${totals['cost_usd']:.2f}",
        "",
        "## Flags by type",
        "",
        *[f"- {name}: {n}" for name, n in totals["flags_by_type"].items()],
        "",
        "## Sites",
        "",
        "| Topic | Place | Photo | Records | Flags | Claims kept | Answer |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in entries:
        if "error" in entry:
            lines.append(f"| {entry['topic']} | {entry['place']} | {entry['photo_id']} | - | failed: {entry['error'][:80]} | - | - |")
            continue
        explanation = entry.get("explanation") or {}
        flags = ", ".join(f"{flag['severity']}: {flag['type']}" for flag in entry["flags"]) or "none"
        kept = f"{explanation['claims']} of {explanation['claims'] + explanation['dropped']}" if explanation else "-"
        answer = (explanation.get("answer") or "-").replace("|", "/")
        lines.append(f"| {entry['topic']} | {entry['place']} | {entry['photo_date']} | {entry['records']} | {flags} | {kept} | {answer} |")
    mismatches = [(entry, flag) for entry in entries if "error" not in entry for flag in entry["flags"] if flag["severity"] in ("conflict", "gap")]
    if mismatches:
        lines += ["", "## Conflicts and gaps", ""]
        lines += [f"- **{entry['place']}** ({entry['topic']}, {flag['severity']}): {flag['message']}" for entry, flag in mismatches]
    return "\n".join(lines) + "\n"


def save(entries: list[dict[str, Any]], folder: Path) -> dict[str, Any]:
    totals = summary(entries)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "batch.json").write_text(json.dumps({"summary": totals, "sites": entries}, indent=2))
    (folder / "batch.geojson").write_text(json.dumps(geojson(entries)))
    (folder / "batch.md").write_text(to_markdown(entries, totals), encoding="utf-8")
    return totals


async def run(
    jobs: list[dict[str, Any]], store: Store, provider: str, explain: bool, folder: Path = DERIVED_DIR, again: bool = False,
) -> list[dict[str, Any]]:
    path = folder / "batch.json"
    previous = {key(entry): entry for entry in json.loads(path.read_text())["sites"]} if path.is_file() and not again else {}
    entries = [entry for entry in previous.values() if "error" not in entry]
    have = {key(entry) for entry in entries}
    todo = [job for job in jobs if key(job) not in have]
    print(f"{len(jobs)} sites planned, {len(jobs) - len(todo)} already done, {len(todo)} to investigate.")
    for number, job in enumerate(todo, 1):
        started = time.monotonic()
        print(f"\n[{number}/{len(todo)}] {TOPICS[job['topic']].label}: {job['place']} (photo {job['photo_id']})")
        try:
            entry = await run_job(job, store, provider, explain)
        except SpendCapError as error:
            print(f"Stopped at the daily spend cap: {error}. Raise DAILY_SPEND_CAP_USD or run again tomorrow; done sites are kept.")
            break
        except Exception as error:  # one failed site should not stop the batch
            entry = job | {"error": f"{type(error).__name__}: {error}"[:300]}
            print(f"  failed: {entry['error']}")
        entries.append(entry)
        save(entries, folder)  # after every site, so a stopped run keeps its work
        flags = ", ".join(flag["type"] for flag in entry.get("flags", [])) or "no flags"
        print(f"  done in {time.monotonic() - started:.0f}s: {flags}")
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--topic", action="append", choices=sorted(TOPICS), help="only these topics (repeatable); default all")
    parser.add_argument("--limit", type=int, default=5, help="sites per topic, in shortlist order")
    parser.add_argument("--no-explain", action="store_true", help="skip Muse Spark's explanation (SAM 3.1 and records only)")
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="meta")
    parser.add_argument("--again", action="store_true", help="investigate every planned site again instead of keeping earlier results")
    args = parser.parse_args()
    load_env()
    if not os.environ.get("MAPILLARY_TOKEN"):
        raise SystemExit("MAPILLARY_TOKEN is not set.")
    path = DERIVED_DIR / "shortlist.json"
    if not path.is_file():
        raise SystemExit("No shortlist yet: run python -m city_investigator.shortlist --photos first.")
    jobs = plan(json.loads(path.read_text()), args.topic, args.limit)
    entries = asyncio.run(run(jobs, Store.load(), args.provider, not args.no_explain, again=args.again))
    totals = save(entries, DERIVED_DIR)
    print("\n" + to_markdown(entries, totals).split("## Flags by type")[0])
    print(f"Saved to {DERIVED_DIR / 'batch.md'}")


if __name__ == "__main__":
    main()
