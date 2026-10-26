"""Day 1 smoke test: confirm NYC dataset fields, complaint strings and neighborhood counts.

Each check runs on its own, so one wrong field name does not hide the others:

  1. 311 problem types in Brooklyn Community Board 6 (finds the sidewalk and shed strings)
  2. 311 flood complaints per year in three candidate districts (confirms the site choice)
  3. DOB NOW work types and how community boards are written (finds the shed fields)
  4. FloodNet sensors and flood events in Brooklyn Community District 6

Usage: python -m smoke.nyc_data
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Any

import requests

from smoke._common import load_env, write_result

BASE = "https://data.cityofnewyork.us/resource"
SERVICE_REQUESTS = "erm2-nwe9"  # 2020 to present; 2010 to 2019 is 76ig-c548
DOB_NOW_PERMITS = "rbx6-tga4"
FLOODNET_EVENTS = "aq7i-eu5q"
FLOODNET_SENSORS = "kb2e-tjy3"

FLOOD_DESCRIPTORS = [
    "Street Flooding (SJ)",
    "Catch Basin Clogged/Flooding (Use Comments) (SC)",
    "Sewer Backup (Use Comments) (SA)",
]
DISTRICTS = ["06 BROOKLYN", "12 QUEENS", "13 QUEENS"]
INTERESTING = re.compile(r"sidewalk|scaffold|shed|obstruct|block|curb|flood|sewer|catch basin", re.I)


def query(dataset: str, **params: str) -> list[dict[str, Any]]:
    headers = {}
    if os.environ.get("SOCRATA_APP_TOKEN"):
        headers["X-App-Token"] = os.environ["SOCRATA_APP_TOKEN"]
    response = requests.get(
        f"{BASE}/{dataset}.json",
        params={f"${key}": value for key, value in params.items()},
        headers=headers,
        timeout=60,
    )
    if response.status_code == 403:
        raise RuntimeError("HTTP 403: throttled (add SOCRATA_APP_TOKEN) or blocked by the network")
    response.raise_for_status()
    return response.json()


def columns(dataset: str) -> list[str]:
    rows = query(dataset, limit="1")
    return sorted(rows[0]) if rows else []


def quoted(values: list[str]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def check_311_types() -> dict[str, Any]:
    rows = query(
        SERVICE_REQUESTS,
        select="complaint_type, descriptor, count(*) AS n",
        where=f"community_board = '06 BROOKLYN' AND created_date >= '{date.today().year - 2}-01-01'",
        group="complaint_type, descriptor",
        order="n DESC",
        limit="500",
    )
    relevant = [row for row in rows if INTERESTING.search(f"{row.get('complaint_type')} {row.get('descriptor')}")]
    print(f"  {len(rows)} type/descriptor pairs; {len(relevant)} look relevant:")
    for row in relevant[:40]:
        print(f"    {row['n']:>6}  {row.get('complaint_type')} | {row.get('descriptor')}")
    return {"columns": columns(SERVICE_REQUESTS), "relevant": relevant, "all": rows}


def check_flood_counts() -> dict[str, Any]:
    rows = query(
        SERVICE_REQUESTS,
        select="community_board, date_extract_y(created_date) AS year, descriptor, count(*) AS n",
        where=(
            f"complaint_type = 'Sewer' AND community_board IN ({quoted(DISTRICTS)}) "
            f"AND descriptor IN ({quoted(FLOOD_DESCRIPTORS)})"
        ),
        group="community_board, year, descriptor",
        order="community_board, year",
        limit="1000",
    )
    totals: dict[str, dict[str, int]] = {}
    for row in rows:
        by_type = totals.setdefault(row["community_board"], {})
        by_type[row["descriptor"]] = by_type.get(row["descriptor"], 0) + int(row["n"])
    for district, by_type in totals.items():
        print(f"  {district}: " + ", ".join(f"{name.split(' (')[0]} {n}" for name, n in by_type.items()))
    return {"since": "2020 (erm2-nwe9)", "totals": totals, "by_year": rows}


def check_dob_permits() -> dict[str, Any]:
    cols = columns(DOB_NOW_PERMITS)
    work_types = query(DOB_NOW_PERMITS, select="work_type, count(*) AS n", group="work_type", order="n DESC", limit="100")
    print("  work types: " + ", ".join(f"{row.get('work_type')} ({row['n']})" for row in work_types[:25]))
    board_field = next((name for name in cols if "community" in name), None)
    boards: list[dict[str, Any]] = []
    if board_field:
        boards = query(
            DOB_NOW_PERMITS,
            select=f"{board_field}, count(*) AS n",
            where="work_type = 'Sidewalk Shed'",
            group=board_field,
            order="n DESC",
            limit="10",
        )
        print(f"  shed permits by {board_field} (top 10): " + ", ".join(f"{row.get(board_field)} ({row['n']})" for row in boards))
    return {"columns": cols, "work_types": work_types, "community_board_field": board_field, "shed_boards": boards}


def check_floodnet() -> dict[str, Any]:
    sensor_cols = columns(FLOODNET_SENSORS)
    event_cols = columns(FLOODNET_EVENTS)
    # The column named council_district holds community district codes such as BK06.
    sensors = query(FLOODNET_SENSORS, where="council_district = 'BK06'", limit="200")
    ids = sorted({row["sensor_id"] for row in sensors if row.get("sensor_id")})
    print(f"  {len(sensors)} sensor record(s) in BK06")
    events: list[dict[str, Any]] = []
    if ids:
        events = query(
            FLOODNET_EVENTS,
            select="sensor_id, count(*) AS events, max(max_depth_inches) AS max_depth_in, max(flood_start_time) AS latest",
            where=f"sensor_id IN ({quoted(ids)})",
            group="sensor_id",
            order="events DESC",
            limit="200",
        )
        names = {row["sensor_id"]: row.get("sensor_name", row["sensor_id"]) for row in sensors}
        for row in events:
            print(f"    {row['events']:>4} events, max {row.get('max_depth_in')} in, latest {row.get('latest')} UTC  {names.get(row['sensor_id'])}")
    return {"sensor_columns": sensor_cols, "event_columns": event_cols, "sensors": sensors, "events_by_sensor": events}


def main() -> None:
    load_env()
    checks = {
        "1 311 types, Brooklyn CB 6": check_311_types,
        "2 311 flood counts by district": check_flood_counts,
        "3 DOB NOW permits": check_dob_permits,
        "4 FloodNet in BK06": check_floodnet,
    }
    results: dict[str, Any] = {}
    for name, check in checks.items():
        print(name)
        try:
            results[name] = {"ok": True, **check()}
            print("  PASS")
        except Exception as error:  # report and continue with the next check
            results[name] = {"ok": False, "error": f"{type(error).__name__}: {error}"[:600]}
            print(f"  FAIL  {results[name]['error']}")
    path = write_result("nyc_data", results)
    print(f"\nDetails: {path}")


if __name__ == "__main__":
    main()
