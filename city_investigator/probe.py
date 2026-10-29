"""Find the exact 311 wording and the city datasets for the seven new topics, before building them.

Prints, for Brooklyn Community District 6:
  1. every 311 complaint type and descriptor that could belong to a new topic, with counts,
     using the city's exact wording (it must match character for character);
  2. the NYC Open Data datasets that hold each topic's agency records, found by name, with
     their IDs, last update and column names.

Writes the full lists to data/derived/probe.json. Nothing is downloaded beyond counts and
the catalog.

With --look, it instead shows how a snapshot source's dataset writes the columns it is
selected and placed by: their types, three recent rows, the most common values of the
first, and for each where clause the snapshot would try, how many rows match and how many
of those land in the district. Nothing is saved.

Usage:
  python -m city_investigator.probe
  python -m city_investigator.probe --look street_permits --look sidewalk_violations
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

import requests

from city_investigator import snapshot
from city_investigator.config import DATASETS, NEIGHBORHOOD
from city_investigator.settings import DERIVED_DIR, SNAPSHOT_DIR, load_env
from city_investigator.socrata import BASE, Socrata, SocrataError
from city_investigator.sources import SOURCES, District

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

# The columns each source is selected and placed by; the first is grouped to show its values.
LOOK = {
    "sidewalk_violations": ("cb", "house_num", "onstname", "frstname", "tostname", "vissuedate"),
    "tree_sidewalk_damage": ("cb", "house_num", "onstname", "atdissuedate"),
    "street_permits": ("boroughname", "permithousenumber", "onstreetname", "fromstreetname", "tostreetname", "issuedworkenddate", "wkt"),
}
VIEWS = "https://data.cityofnewyork.us/api/views"


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


def describe(row: dict[str, Any], columns: tuple[str, ...]) -> str:
    return "; ".join(f"{column}={str(row.get(column))[:100]!r}" for column in columns)


def look(client: Socrata, name: str, district: District) -> list[str]:
    """Lines showing how a source's dataset writes its columns and what each where clause finds."""
    source = SOURCES[name]
    columns = LOOK.get(name, ())
    lines = [f"{name} ({source.dataset})"]
    try:
        response = client.session.get(f"{VIEWS}/{source.dataset}.json", timeout=60)
        types = {column.get("fieldName"): column.get("dataTypeName") for column in response.json().get("columns", [])}
        lines.append("  types: " + ", ".join(f"{column}={types.get(column, 'missing')}" for column in columns))
    except (requests.RequestException, ValueError, AttributeError) as error:
        lines.append(f"  types: unavailable ({error})")
    try:
        lines += [f"  recent: {describe(row, columns)}" for row in client.get(source.dataset, {"$limit": 3, "$order": ":id DESC"})]
        if columns:
            first = columns[0]
            common = client.get(source.dataset, {"$select": f"{first}, count(*) AS n", "$group": first, "$order": "n DESC", "$limit": 12})
            lines.append(f"  most common {first}: " + ", ".join(f"{row.get(first)!r} ({row.get('n')})" for row in common))
    except SocrataError as error:
        lines.append(f"  could not read rows: {error}")
    for where in source.where(district):
        label = f"  {snapshot.shorten(where, 90)}"
        try:
            count = int(client.get(source.dataset, {"$select": "count(*) AS n", "$where": where})[0]["n"])
            rows = client.get(source.dataset, {"$where": where, "$limit": 1000}) if count else []
        except SocrataError as error:
            lines.append(f"{label}: refused (HTTP {error.status})")
            continue
        kept = [row for row in rows if source.select(row, district) is not None]
        found = f"{label}: {count} rows" + (f"; of {len(rows)} read, {len(kept)} in the district" if rows else "")
        lines.append(found + (f"\n      e.g. {describe(rows[0], columns)}" if rows and not kept else ""))
    return lines


def look_main(names: list[str]) -> None:
    pluto = SNAPSHOT_DIR / "pluto.json"
    done = {"pluto": json.loads(pluto.read_text())["rows"]} if pluto.is_file() else {}
    district = snapshot.district(done)
    print(f"District: {len(district.lots)} lots, {len(district.streets)} streets, box {tuple(round(v, 4) for v in district.box)}")
    client = Socrata()
    for name in names:
        if name not in SOURCES:
            print(f"\n{name}: not a source; choose from {', '.join(SOURCES)}")
            continue
        print("\n" + "\n".join(look(client, name, district)))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--look", action="append", help="a snapshot source to inspect; repeatable")
    args = parser.parse_args(argv)
    load_env()
    if args.look:
        look_main(args.look)
        return
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
