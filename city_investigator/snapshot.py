"""Download and save every record the prototype uses for Brooklyn Community District 6.

Each dataset is saved to data/snapshots/<name>.json with the query used and the time
it was retrieved, so investigations are reproducible and the demo works offline.
Owner names are dropped before saving.

The city's stormwater flood maps come from the ArcGIS layers its climate office
publishes: only the part inside the neighborhood is requested, then clipped and merged.

Usage:
  python -m city_investigator.snapshot
  python -m city_investigator.snapshot --only floodnet_sensors --only floodnet_events
  python -m city_investigator.snapshot --only stormwater
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import requests

from city_investigator import times
from city_investigator.config import (
    COMPLAINT_TYPES,
    DATASETS,
    DROPPED_FIELDS,
    FLOOD_COMPLAINT_TYPES,
    LEGACY_PERMIT_SUBTYPES,
    NEIGHBORHOOD,
    PERMIT_WORK_TYPES,
    RAIN_START_YEAR,
    RAIN_STATION,
    STORMWATER_DATASET,
    STORMWATER_PUBLISHER,
    STORMWATER_SCENARIOS,
)
from city_investigator.evidence import classify_complaint
from city_investigator.settings import SNAPSHOT_DIR, load_env
from city_investigator.socrata import Socrata, SocrataError

IEM_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
ARCGIS_PAGE = 1000
STORMWATER_SIMPLIFY_DEG = 0.000005  # about half a meter; the maps are drawn on a coarser grid
STORMWATER_GRID_DEG = 0.000001


def quoted(values: list[str]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


@dataclass
class Step:
    name: str
    dataset: str
    # SoQL where clauses to try in order; later ones are fallbacks for type differences.
    wheres: Callable[[dict[str, list[dict[str, Any]]]], list[str]]
    keep: Callable[[dict[str, Any]], bool] = lambda row: True


def plan() -> list[Step]:
    board, dob_board = NEIGHBORHOOD["board_311"], NEIGHBORHOOD["board_dob"]
    return [
        Step(
            "311_2020_on",
            DATASETS["311_2020_on"],
            lambda _: [
                f"community_board = '{board}' AND created_date >= '2020-01-01T00:00:00' "
                f"AND complaint_type IN ({quoted(COMPLAINT_TYPES)})"
            ],
            keep=lambda row: classify_complaint(row.get("complaint_type"), row.get("descriptor")) is not None,
        ),
        Step(
            "311_2010s",
            DATASETS["311_2010s"],
            lambda _: [f"community_board = '{board}' AND complaint_type IN ({quoted(FLOOD_COMPLAINT_TYPES)})"],
            keep=lambda row: classify_complaint(row.get("complaint_type"), row.get("descriptor")) is not None,
        ),
        Step(
            "dob_now_permits",
            DATASETS["dob_now_permits"],
            lambda _: [f"community_board = '{dob_board}' AND work_type IN ({quoted(sorted(PERMIT_WORK_TYPES))})"],
        ),
        Step(
            "dob_legacy_permits",
            DATASETS["dob_legacy_permits"],
            lambda _: [
                f"community_board = '{dob_board}' AND permit_subtype IN ({quoted(sorted(LEGACY_PERMIT_SUBTYPES))})"
            ],
        ),
        Step(
            "floodnet_sensors",
            DATASETS["floodnet_sensors"],
            # This column holds community district codes such as BK06, despite its name.
            lambda _: [f"council_district = '{NEIGHBORHOOD['district_floodnet']}'"],
        ),
        Step(
            "floodnet_events",
            DATASETS["floodnet_events"],
            lambda done: [
                "sensor_id IN ("
                + quoted(sorted({row["sensor_id"] for row in done.get("floodnet_sensors", []) if row.get("sensor_id")}))
                + ")"
            ],
        ),
        Step(
            "pluto",
            DATASETS["pluto"],
            lambda _: [f"cd = '{NEIGHBORHOOD['pluto_cd']}'", f"cd = {NEIGHBORHOOD['pluto_cd']}"],
        ),
    ]


def scrub(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in DROPPED_FIELDS}


def fetch_step(client: Socrata, step: Step, done: dict[str, list[dict[str, Any]]]) -> tuple[str, list[dict[str, Any]]]:
    wheres = step.wheres(done)
    if any("IN ()" in where for where in wheres):
        raise RuntimeError("nothing to query: an earlier step it depends on returned no rows")
    last_error: Exception | None = None
    for where in wheres:
        try:
            rows = client.rows(step.dataset, where)
            return where, [scrub(row) for row in rows if step.keep(row)]
        except SocrataError as error:
            last_error = error
            if error.status != 400:  # only a malformed query is worth retrying with a fallback
                raise
    raise last_error or RuntimeError("no query to run")


def fetch_rainfall(start_year: int, session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Hourly rain at the Central Park weather station, routine hourly reports only."""
    session = session or requests.Session()
    rows: list[dict[str, Any]] = []
    for year in range(start_year, date.today().year + 1):
        end = min(date(year, 12, 31), date.today())
        response = session.get(
            IEM_URL,
            params={
                "station": RAIN_STATION["id"],
                "data": "p01i",
                "year1": year, "month1": 1, "day1": 1,
                "year2": end.year, "month2": end.month, "day2": end.day,
                "tz": "Etc/UTC",
                "format": "onlycomma",
                "latlon": "no",
                "missing": "M",
                "trace": "T",
                "report_type": "3",
            },
            timeout=180,
        )
        response.raise_for_status()
        for row in csv.DictReader(io.StringIO(response.text)):
            value = row.get("p01i")
            if value in (None, "", "M"):
                continue
            rows.append({"valid_utc": row["valid"], "inches": 0.0 if value == "T" else float(value)})
    return rows


def arcgis_json(session: requests.Session, url: str, **params: Any) -> dict[str, Any]:
    response = session.get(url, params={"f": "json", **params}, timeout=600)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"{url}: {data['error']}")
    return data


def stormwater_layer(session: requests.Session, words: tuple[str, ...], services: list[dict[str, Any]]) -> str | None:
    """The URL of the publisher's map layer whose name has all the words, or None."""
    names = [
        service["name"]
        for service in services
        if service.get("type") == "FeatureServer" and all(word in service["name"].lower() for word in words)
    ]
    if not names:
        return None
    service = f"{STORMWATER_PUBLISHER['services']}/{min(names, key=len)}/FeatureServer"  # skip copies such as _view
    layers = arcgis_json(session, service).get("layers") or [{"id": 0}]
    return f"{service}/{layers[0]['id']}"


def flood_category(properties: dict[str, Any]) -> int | None:
    # "Flooding_Category", or "Flooding_C" where the layer came from a shapefile (10-character names).
    key = next((key for key in properties if "categ" in key.lower() or key.lower().startswith("flooding_c")), None)
    if key is None:
        raise RuntimeError(f"no flooding category field; fields: {sorted(properties)}")
    found = re.match(r"\s*(\d+)", str(properties[key]))
    return int(found.group(1)) if found else None


def stormwater_features(session: requests.Session, layer: str, bounds: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Flood polygons in bounds (south, west, north, east), clipped and merged by flooding category."""
    import shapely
    from shapely.geometry import shape

    south, west, north, east = bounds
    parts: dict[int, list[Any]] = {}
    offset = 0
    while True:
        page = arcgis_json(
            session, f"{layer}/query", f="geojson", where="1=1", outFields="*", returnGeometry="true",
            geometry=f"{west},{south},{east},{north}", geometryType="esriGeometryEnvelope", inSR=4326,
            spatialRel="esriSpatialRelIntersects", outSR=4326, geometryPrecision=6,
            maxAllowableOffset=STORMWATER_SIMPLIFY_DEG, resultOffset=offset, resultRecordCount=ARCGIS_PAGE,
        )
        features = page.get("features") or []
        for feature in features:
            category = flood_category(feature.get("properties") or {})
            if category is None or not feature.get("geometry"):
                continue
            # City polygons can cross themselves; repair the clipped piece before merging.
            clipped = shapely.make_valid(shapely.clip_by_rect(shape(feature["geometry"]), west, south, east, north))
            polygons = [part for part in shapely.get_parts(clipped) if part.geom_type in ("Polygon", "MultiPolygon")]
            parts.setdefault(category, []).extend(polygons)
        more = page.get("exceededTransferLimit") or (page.get("properties") or {}).get("exceededTransferLimit")
        if not features or not more:
            break
        offset += len(features)
    # Merging on a fixed grid (1e-6 degrees, about 10 cm) is robust to near-coincident edges.
    merged = {
        category: shapely.make_valid(shapely.union_all(pieces, grid_size=STORMWATER_GRID_DEG))
        for category, pieces in parts.items()
        if pieces
    }
    return [{"category": category, "geometry": json.loads(shapely.to_geojson(geometry))} for category, geometry in sorted(merged.items())]


def fetch_stormwater(folder: Path, session: requests.Session | None = None) -> dict[str, Any]:
    session = session or requests.Session()
    services = arcgis_json(session, STORMWATER_PUBLISHER["services"]).get("services") or []
    scenarios = []
    for scenario in STORMWATER_SCENARIOS:
        layer = stormwater_layer(session, scenario["match"], services)
        if layer is None:
            print(f"      stormwater {scenario['key']}: not published by {STORMWATER_PUBLISHER['account']}")
            continue
        features = stormwater_features(session, layer, NEIGHBORHOOD["bounds"])
        scenarios.append(
            {key: value for key, value in scenario.items() if key != "match"}
            | {"dataset": STORMWATER_DATASET, "layer": layer, "features": features}
        )
        print(f"      stormwater {scenario['key']}: {len(features)} flooding categories in the neighborhood ({layer})")
    if not scenarios:
        names = ", ".join(service.get("name", "?") for service in services) or "none"
        raise RuntimeError(f"no flood map scenario found; {STORMWATER_PUBLISHER['account']} publishes: {names}"[:450])
    return {
        "name": "stormwater",
        "dataset": STORMWATER_DATASET,
        "publisher": STORMWATER_PUBLISHER,
        "bounds": NEIGHBORHOOD["bounds"],
        "retrieved_at": times.now().isoformat(),
        "scenarios": scenarios,
    }


def save(folder: Path, name: str, payload: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps(payload))


def update_manifest(folder: Path, entries: dict[str, dict[str, Any]]) -> None:
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text()) if path.is_file() else {}
    manifest.update(entries)
    path.write_text(json.dumps(manifest, indent=2))


def run(only: list[str] | None, folder: Path = SNAPSHOT_DIR, client: Socrata | None = None) -> dict[str, dict[str, Any]]:
    client = client or Socrata()
    done: dict[str, list[dict[str, Any]]] = {}
    # Dependent steps need their inputs even when only part of the plan is refreshed.
    for name in ("floodnet_sensors",):
        path = folder / f"{name}.json"
        if path.is_file():
            done[name] = json.loads(path.read_text())["rows"]
    entries: dict[str, dict[str, Any]] = {}
    for step in plan():
        if only and step.name not in only:
            continue
        started = time.monotonic()
        try:
            where, rows = fetch_step(client, step, done)
        except Exception as error:  # report and continue with the other datasets
            entries[step.name] = {"ok": False, "error": f"{type(error).__name__}: {error}"[:500]}
            print(f"FAIL  {step.name}: {entries[step.name]['error']}")
            continue
        done[step.name] = rows
        retrieved = times.now().isoformat()
        save(folder, step.name, {"name": step.name, "dataset": step.dataset, "where": where, "retrieved_at": retrieved, "rows": rows})
        entries[step.name] = {"ok": True, "dataset": step.dataset, "rows": len(rows), "retrieved_at": retrieved}
        print(f"OK    {step.name}: {len(rows)} rows ({time.monotonic() - started:.0f}s)")
    if not only or "rainfall" in only:
        try:
            rows = fetch_rainfall(RAIN_START_YEAR)
            retrieved = times.now().isoformat()
            save(folder, "rainfall", {"name": "rainfall", "dataset": "IEM ASOS " + RAIN_STATION["id"], "station": RAIN_STATION, "retrieved_at": retrieved, "rows": rows})
            entries["rainfall"] = {"ok": True, "dataset": "IEM ASOS " + RAIN_STATION["id"], "rows": len(rows), "retrieved_at": retrieved}
            print(f"OK    rainfall: {len(rows)} hourly readings")
        except Exception as error:
            entries["rainfall"] = {"ok": False, "error": f"{type(error).__name__}: {error}"[:500]}
            print(f"FAIL  rainfall: {entries['rainfall']['error']}")
    if not only or "stormwater" in only:
        try:
            payload = fetch_stormwater(folder)
            save(folder, "stormwater", payload)
            entries["stormwater"] = {"ok": True, "dataset": payload["dataset"], "scenarios": len(payload["scenarios"]), "retrieved_at": payload["retrieved_at"]}
            print(f"OK    stormwater: {len(payload['scenarios'])} flood map scenarios")
        except Exception as error:
            entries["stormwater"] = {"ok": False, "error": f"{type(error).__name__}: {error}"[:500]}
            print(f"FAIL  stormwater: {entries['stormwater']['error']}")
    update_manifest(folder, entries)
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", help="dataset name to refresh; repeatable")
    args = parser.parse_args()
    load_env()
    entries = run(args.only)
    failed = [name for name, entry in entries.items() if not entry["ok"]]
    print(f"\nSaved to {SNAPSHOT_DIR}" + (f"  ({len(failed)} failed: {', '.join(failed)})" if failed else ""))


if __name__ == "__main__":
    main()
