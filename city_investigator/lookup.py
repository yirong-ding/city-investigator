"""Look up evidence near a point or for a building, with a coverage note per source.

Usage:
  python -m city_investigator.lookup --lat 40.6787 --lon -73.9830 --start 2026-08-22 --end 2026-08-26 --topic flooding
  python -m city_investigator.lookup --lat 40.6787 --lon -73.9830 --radius 50 --topic sidewalk
  python -m city_investigator.lookup --bin 3008123
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from city_investigator import times
from city_investigator.store import Store

STATE_LABELS = {"found": "FOUND", "nothing_found": "NOTHING FOUND", "no_coverage": "NO COVERAGE", "partial": "PARTIAL"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--radius", type=float, default=150, help="meters (default 150)")
    parser.add_argument("--start", type=date.fromisoformat, help="first local date, YYYY-MM-DD")
    parser.add_argument("--end", type=date.fromisoformat, help="last local date, YYYY-MM-DD")
    parser.add_argument("--topic", choices=["flooding", "sidewalk"])
    parser.add_argument("--bbl", help="10-digit tax lot number")
    parser.add_argument("--bin", help="building number")
    parser.add_argument("--limit", type=int, default=40, help="evidence lines to print")
    parser.add_argument("--json", type=Path, help="also save the full result here")
    args = parser.parse_args()

    store = Store.load()
    if args.bbl or args.bin:
        result = store.for_building(args.bbl, args.bin, args.topic)
    elif args.lat is not None and args.lon is not None:
        result = store.near(
            args.lat,
            args.lon,
            args.radius,
            times.local_day_start(args.start) if args.start else None,
            times.local_day_end(args.end) if args.end else None,
            args.topic,
        )
    else:
        parser.error("give --lat and --lon, or --bbl or --bin")

    print("Coverage")
    for item in result.coverage:
        print(f"  [{STATE_LABELS[item.state]}] {item.source}: {item.note}")
    print(f"\nEvidence ({len(result.hits)})")
    for hit in result.hits[: args.limit]:
        item = hit.evidence
        when = f"{times.to_local(item.start):%Y-%m-%d %H:%M}" if item.start else "undated         "
        distance = f"{hit.distance_m:5.0f} m" if hit.distance_m is not None else "      "
        print(f"  {when}  {distance}  {item.kind}/{item.category}: {item.summary}  [{item.id}]")
    if len(result.hits) > args.limit:
        print(f"  ... {len(result.hits) - args.limit} more (raise --limit or use --json)")
    if args.json:
        args.json.write_text(json.dumps(result.to_dict(), indent=2))
        print(f"\nSaved to {args.json}")


if __name__ == "__main__":
    main()
