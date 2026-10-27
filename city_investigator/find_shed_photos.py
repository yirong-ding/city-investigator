"""Find sidewalk sheds that a nearby street photo actually shows, using SAM 3.1 to check.

Scans every shed permit chain in the district for Mapillary photos taken while its
permits were valid, close to the building and facing it, ranks the newest and
closest, then runs SAM 3.1 on the top candidates to see whether scaffolding is
visible. The SAM step costs about $0.005 per photo.

Usage:
  python -m city_investigator.find_shed_photos
  python -m city_investigator.find_shed_photos --max-distance 20 --check 15
"""

from __future__ import annotations

import argparse
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from city_investigator import times
from city_investigator.evidence import day
from city_investigator.photo_check import check
from city_investigator.photos import photos_near
from city_investigator.settings import DERIVED_DIR, load_env
from city_investigator.sheds import ShedChain, build_chains
from city_investigator.store import Store

CONCEPTS = ["scaffolding", "sidewalk shed"]
MAPILLARY_START = datetime(2014, 1, 1, tzinfo=times.LOCAL)


def during_permits(photo: dict[str, Any], chain: ShedChain) -> bool:
    taken = times.parse(photo.get("captured_at"), "utc")
    return bool(taken) and any(start <= taken <= end for start, end in chain.runs)


def best_photo(chain: ShedChain, max_distance: float) -> dict[str, Any] | None:
    photos = photos_near(chain.lat, chain.lon, max_distance)  # type: ignore[arg-type]
    good = [p for p in photos if p["faces_site"] and during_permits(p, chain)]
    if not good:
        return None
    best = max(good, key=lambda p: (p["captured_at"] or "", -p["distance_m"]))
    return best | {"matching_photos": len(good)}


def candidates(store: Store, max_distance: float, workers: int = 6) -> list[tuple[ShedChain, dict[str, Any]]]:
    chains = [
        chain
        for chain in build_chains(store.evidence)
        if chain.lat is not None and any(end >= MAPILLARY_START for _, end in chain.runs)
    ]
    print(f"Searching photos for {len(chains)} sheds with permits since 2014...")
    found: list[tuple[ShedChain, dict[str, Any]]] = []

    def search(chain: ShedChain) -> tuple[ShedChain, dict[str, Any] | None]:
        try:
            return chain, best_photo(chain, max_distance)
        except Exception as error:  # keep searching the other sheds
            print(f"  photo search failed for {chain.address}: {type(error).__name__}")
            return chain, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (chain, photo) in enumerate(pool.map(search, chains), 1):
            if photo:
                found.append((chain, photo))
            if index % 50 == 0:
                print(f"  {index} of {len(chains)} searched, {len(found)} with a matching photo")
    found.sort(key=lambda item: (item[1]["captured_at"] or "", -item[1]["distance_m"]), reverse=True)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max-distance", type=float, default=15, help="meters from the building (default 15)")
    parser.add_argument("--check", type=int, default=10, help="how many top photos to check with SAM (default 10)")
    args = parser.parse_args()
    load_env()
    store = Store.load()
    at = times.now()
    found = candidates(store, args.max_distance)
    print(f"\n{len(found)} sheds have a facing photo within {args.max_distance:.0f} m taken while permits were valid.")
    top = found[: args.check]
    confidences = asyncio.run(check([photo["id"] for _, photo in top], CONCEPTS)) if top else {}

    rows = []
    for chain, photo in top:
        scores = confidences.get(photo["id"], {})
        rows.append(
            {
                "address": chain.address,
                "active_today": chain.active(at),
                "permitted": f"{day(chain.up_since)} to {day(chain.expires)}",
                "photo_date": (photo["captured_at"] or "")[:10],
                "distance_m": photo["distance_m"],
                "matching_photos": photo["matching_photos"],
                **{concept: scores.get(concept) for concept in CONCEPTS},
                "photo": photo["page_url"],
                "credit": photo["credit"],
            }
        )
    lines = [
        "# Sheds with a matching street photo",
        "",
        "| Address | Active today | Current permit run | Photo date | Distance | SAM: scaffolding | SAM: sidewalk shed | Photo |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        def score(value: float | None) -> str:
            return f"{value:.2f}" if value is not None else "-"

        lines.append(
            f"| {row['address']} | {'yes' if row['active_today'] else 'no'} | {row['permitted']} | {row['photo_date']} | "
            f"{row['distance_m']} m | {score(row['scaffolding'])} | {score(row['sidewalk shed'])} | [open]({row['photo']}) |"
        )
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    (DERIVED_DIR / "shed_photos.json").write_text(json.dumps(rows, indent=2))
    (DERIVED_DIR / "shed_photos.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\nSaved to {DERIVED_DIR / 'shed_photos.md'}; overlays in data\\private\\mapillary")


if __name__ == "__main__":
    main()
