"""Check the records the snapshot placed itself, before trusting them in a demo.

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
from city_investigator.sources import address_key


def rows(name: str) -> list[dict[str, Any]]:
    path = SNAPSHOT_DIR / f"{name}.json"
    return json.loads(path.read_text())["rows"] if path.is_file() else []


def lot_id(row: dict[str, Any]) -> int | None:
    text = str(row.get("bblid") or "").split(".")[0]
    return int(text) if text.isdigit() else None


def where(row: dict[str, Any]) -> str:
    return f"{row.get('house_num')} {row.get('onstname')} (DOT lot {row.get('bblid')})"


def main() -> None:
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
