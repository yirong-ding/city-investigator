"""Find the exact 311 wording and the city datasets for the seven new topics, before building them.

Prints, for Brooklyn Community District 6:
  1. every 311 complaint type and descriptor that could belong to a new topic, with counts,
     using the city's exact wording (it must match character for character);
  2. the NYC Open Data datasets that hold each topic's agency records, found by name, with
     their IDs, last update and column names.

Writes the full lists to data/derived/probe.json. Nothing is downloaded beyond counts and
the catalog.

Usage:
  python -m city_investigator.probe
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from city_investigator.config import DATASETS, NEIGHBORHOOD
from city_investigator.settings import DERIVED_DIR, load_env
from city_investigator.socrata import BASE

CATALOG = "https://api.us.socrata.com/api/catalog/v1"
# Words that mark a 311 complaint as possibly belonging to one of the new topics.
TOPIC_WORDS = (
    "tree", "branch", "limb", "root", "stump", "sidewalk", "curb", "ramp", "street condition", "pothole",
    "cave", "plate", "hardware", "dining", "restaurant", "cafe", "construction", "facade", "façade",
    "building", "debris", "unsafe", "scaffold", "shed", "obstruction", "highway",
)
# Catalog searches for each topic's agency records.
SEARCHES = {
    "street trees": ["Forestry Tree Points", "Forestry Inspections", "Forestry Work Orders", "Forestry Service Requests", "Forestry Risk Assessments"],
    "unsafe facades": ["DOB NOW: Safety Facades Compliance Filings", "DOB Complaints Received", "DOB ECB Violations"],
    "sidewalk damage": ["DOT sidewalk inspection", "sidewalk violations", "sidewalk management"],
    "curb ramps": ["Pedestrian Ramp Locations", "pedestrian ramp"],
    "potholes": ["Street Pothole Work Orders", "pothole"],
    "street construction": ["Street Construction Permits", "street closures construction"],
    "outdoor dining": ["Dining Out NYC", "Open Restaurant Applications", "sidewalk cafe"],
}


def complaint_counts(session: requests.Session) -> list[dict[str, Any]]:
    board = NEIGHBORHOOD["board_311"]
    response = session.get(
        f"{BASE}/{DATASETS['311_2020_on']}.json",
        params={
            "$select": "complaint_type, descriptor, agency, count(*) AS n",
            "$where": f"community_board = '{board}' AND created_date >= '2020-01-01T00:00:00'",
            "$group": "complaint_type, descriptor, agency",
            "$order": "n DESC",
            "$limit": 5000,
        },
        timeout=300,
    )
    response.raise_for_status()
    return [{**row, "n": int(row["n"])} for row in response.json()]


def find_datasets(session: requests.Session, query: str, limit: int = 3) -> list[dict[str, Any]]:
    response = session.get(
        CATALOG,
        params={"domains": "data.cityofnewyork.us", "search_context": "data.cityofnewyork.us", "q": query, "only": "dataset", "limit": limit},
        timeout=60,
    )
    response.raise_for_status()
    found = []
    for result in response.json().get("results", []):
        resource = result.get("resource", {})
        found.append({
            "id": resource.get("id"),
            "name": resource.get("name"),
            "updated": (resource.get("data_updated_at") or resource.get("updatedAt") or "")[:10],
            "columns": resource.get("columns_field_name", []),
        })
    return found


def relevant(row: dict[str, Any]) -> bool:
    text = f"{row.get('complaint_type', '')} {row.get('descriptor', '')}".lower()
    return any(word in text for word in TOPIC_WORDS)


def main() -> None:
    load_env()
    session = requests.Session()
    if os.environ.get("SOCRATA_APP_TOKEN"):
        session.headers["X-App-Token"] = os.environ["SOCRATA_APP_TOKEN"]

    counts = complaint_counts(session)
    matches = [row for row in counts if relevant(row)]
    print(f"311 complaints in {NEIGHBORHOOD['board_311']} since 2020 that may fit a new topic ({len(matches)} of {len(counts)} kinds):")
    for row in matches:
        print(f"  {row['n']:>6}  {row.get('agency', '')}  {row.get('complaint_type')} | {row.get('descriptor')}")

    datasets: dict[str, list[dict[str, Any]]] = {}
    for topic, queries in SEARCHES.items():
        print(f"\n{topic}:")
        seen = set()
        for query in queries:
            try:
                results = find_datasets(session, query)
            except requests.RequestException as error:
                print(f"  {query!r}: search failed ({error})")
                continue
            for item in results:
                if item["id"] in seen:
                    continue
                seen.add(item["id"])
                datasets.setdefault(topic, []).append(item)
                columns = ", ".join(item["columns"][:30]) + (" ..." if len(item["columns"]) > 30 else "")
                print(f"  {item['id']}  {item['name']}  (updated {item['updated']})\n      {columns}")

    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    path = DERIVED_DIR / "probe.json"
    path.write_text(json.dumps({"complaints": counts, "datasets": datasets}, indent=2))
    print(f"\nFull lists saved to {path}")


if __name__ == "__main__":
    main()
