"""Check where the records are placed, before trusting them in a demo.

First, for every agency source: how many rows were saved, how many the store could place,
and how many land inside the district's box, with an example of one that does not.

Then the records the snapshot placed itself.

DOT's sidewalk datasets record no borough, so their rows are matched to district lots by
address. DOT's own lot ID (bblid) is shared by both datasets: a tree damage record at a
violation's address but with a different bblid is on another borough's lot with the same
address. The lot IDs also run by borough, so a few far below the rest point to the same
problem. Street permits show how each was placed. Reads the snapshot only; no network.

Usage: python -m smoke.placements
"""

from __future__ import annotations

import json
from collections import Counter
from statistics import median
from typing import Any

from city_investigator.settings import SNAPSHOT_DIR
from city_investigator.snapshot import district_box
from city_investigator.sources import SOURCES, District, address_key
from city_investigator.store import Store


def rows(name: str) -> list[dict[str, Any]]:
    path = SNAPSHOT_DIR / f"{name}.json"
    return json.loads(path.read_text())["rows"] if path.is_file() else []


def lot_id(row: dict[str, Any]) -> int | None:
    text = str(row.get("bblid") or "").split(".")[0]
    return int(text) if text.isdigit() else None


def where(row: dict[str, Any]) -> str:
    return f"{row.get('house_num')} {row.get('onstname')} (DOT lot {row.get('bblid')})"


def skipped_example(source: Any, saved: list[dict[str, Any]], store: Store) -> str | None:
    """The fields of the first saved row the store could not turn into a record."""
    by_bbl = {lot.bbl: lot for lot in store.lots if lot.bbl}

    def at_lot(bbl: str | None) -> tuple[float | None, float | None, str | None]:
        lot = by_bbl.get(bbl) if bbl else None
        return (lot.lat, lot.lon, lot.address) if lot else (None, None, None)

    row = next((row for row in saved if source.to_evidence(row, source.dataset, at_lot) is None), None)
    if row is None:
        return None
    return "; ".join(f"{key}={str(value)[:60]}" for key, value in sorted(row.items()) if not key.startswith(":"))


def source_lines() -> list[str]:
    store = Store.load(SNAPSHOT_DIR)
    district = District(district_box({"pluto": rows("pluto")}))
    lines = []
    for source in SOURCES.values():
        saved = rows(source.name)
        placed = [item for item in store.evidence if item.id.startswith(f"{source.name}:")]
        outside = [item for item in placed if not district.contains(item.lat, item.lon)]
        line = f"{source.label}: {len(saved):,} saved, {len(placed):,} placed, {len(placed) - len(outside):,} inside the district"
        if len(placed) < len(saved) and (example := skipped_example(source, saved, store)):
            line += f"\n    not placed, e.g. {example}"
        if outside:
            item = outside[0]
            shapes = "; ".join(f"{key}={str(item.raw[key])[:70]}" for key in ("geometry", "location", "the_geom", "wkt") if item.raw.get(key))
            line += f"\n    outside, e.g. {item.lat}, {item.lon} from {shapes or 'no geometry column'}"
        lines.append(line)
    return lines


def main() -> None:
    print("\n".join(source_lines()) + "\n")
    violations, damage, permits = rows("sidewalk_violations"), rows("tree_sidewalk_damage"), rows("street_permits")

    known: dict[str | None, set[int | None]] = {}
    for row in violations:
        known.setdefault(address_key(row.get("house_num"), row.get("onstname")), set()).add(lot_id(row))
    same, different = 0, []
    for row in damage:
        ids = known.get(address_key(row.get("house_num"), row.get("onstname")))
        if ids is None:
            continue
        if lot_id(row) in ids:
            same += 1
        else:
            different.append(where(row))
    print(f"Tree damage records at a violation's address: {same} on the same DOT lot, {len(different)} on a different one")
    for line in different[:10]:
        print(f"    different: {line}")

    for name, data in (("sidewalk_violations", violations), ("tree_sidewalk_damage", damage)):
        placed = sorted((row for row in data if lot_id(row) is not None), key=lot_id)
        if not placed:
            print(f"\n{name}: no rows")
            continue
        ids = [lot_id(row) for row in placed]
        print(f"\n{name}: {len(data)} rows; DOT lot IDs {ids[0]} to {ids[-1]}, median {median(ids):.0f}")
        for row in placed[:5]:
            print(f"    lowest:  {where(row)}")
        for row in placed[-3:]:
            print(f"    highest: {where(row)}")

    ways = Counter(row.get("located_by") for row in permits)
    print(f"\nstreet_permits: {len(permits)} rows, placed by " + ", ".join(f"{way}: {n}" for way, n in ways.most_common()))


if __name__ == "__main__":
    main()
