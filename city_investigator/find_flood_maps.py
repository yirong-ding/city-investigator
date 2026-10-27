"""Find a readable, official copy of the city's stormwater flood maps.

The collection on NYC Open Data (9i7c-xyvv) holds Esri compressed geodatabases, which
open-source GIS libraries cannot read. This lists what the older single-scenario
datasets offer, and every public ArcGIS layer of the maps with the organization that
publishes it, so the snapshot can use a copy the city publishes.

Usage:
  python -m city_investigator.find_flood_maps
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from city_investigator.config import STORMWATER_DATASET
from city_investigator.snapshot import OPEN_DATA

OLDER_DATASETS = {
    "7r5q-vr7p": "moderate storm, current sea levels",
    "5rzh-cyqd": "moderate storm, 2050 sea levels",
    "w8eg-8ha6": "extreme storm, 2080 sea levels",
    STORMWATER_DATASET: "the collection",
}
ARCGIS = "https://www.arcgis.com/sharing/rest"
SEEN_HOSTING = "https://services2.arcgis.com/IsDCghZ73NgoYoz5/ArcGIS/rest/services"


def get_json(session: requests.Session, url: str, **params: Any) -> dict[str, Any]:
    try:
        response = session.get(url, params=params or None, timeout=60)
        return response.json() if response.ok else {"error": f"HTTP {response.status_code}"}
    except (requests.RequestException, ValueError) as error:
        return {"error": f"{type(error).__name__}: {error}"[:200]}


def open_data(session: requests.Session) -> None:
    print("NYC Open Data")
    for dataset, label in OLDER_DATASETS.items():
        meta = get_json(session, f"{OPEN_DATA}/api/views/{dataset}.json")
        if "error" in meta:
            print(f"  {dataset} ({label}): {meta['error']}")
            continue
        stamp = meta.get("rowsUpdatedAt") or meta.get("viewLastModified")
        updated = datetime.fromtimestamp(stamp, timezone.utc).date() if stamp else "unknown"
        attachments = [a.get("filename") or a.get("name") for a in (meta.get("metadata") or {}).get("attachments") or []]
        print(
            f"  {dataset} ({label}): {meta.get('name')!r}; type {meta.get('viewType')}/{meta.get('assetType')}; "
            f"file {meta.get('blobFilename')}; attachments {attachments}; updated {updated}"
        )


def arcgis(session: requests.Session) -> None:
    found = get_json(session, f"{ARCGIS}/search", q='stormwater flood type:"Feature Service"', f="json", num=100)
    items = [item for item in found.get("results", []) if "storm" in str(item.get("title", "")).lower()]
    orgs: dict[str, str] = {}
    for org in {item.get("orgId") for item in items} | {"IsDCghZ73NgoYoz5"}:
        if org:
            orgs[org] = get_json(session, f"{ARCGIS}/portals/{org}", f="json").get("name") or "name not public"
    print(f"\nArcGIS Online: {len(items)} public stormwater layers ({found.get('error', 'ok')})")
    for item in sorted(items, key=lambda item: -(item.get("numViews") or 0))[:40]:
        print(
            f"  {item.get('title')} | {orgs.get(item.get('orgId'), 'unknown org')} ({item.get('owner')}) | "
            f"views {item.get('numViews')} | {item.get('url')}"
        )
    services = get_json(session, SEEN_HOSTING, f="json").get("services", [])
    print(f"\nLayers hosted by {orgs['IsDCghZ73NgoYoz5']} (the copy found by web search):")
    for service in services:
        if any(word in service.get("name", "").lower() for word in ("sea", "flood", "storm")):
            print(f"  {service['name']} ({service.get('type')}): {service.get('url') or SEEN_HOSTING + '/' + service['name']}")


def main() -> None:
    session = requests.Session()
    open_data(session)
    arcgis(session)


if __name__ == "__main__":
    main()
