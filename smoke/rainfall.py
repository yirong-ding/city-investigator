"""Day 1 smoke test: which rainfall source works for a storm date?

Tries two sources for the same window and reports hourly peaks and totals in inches:

  - Iowa Environmental Mesonet: airport and Central Park weather stations. These are
    measurements, so in City Investigator they are records.
  - Open-Meteo historical archive: reanalysis estimates for a grid cell. These come
    from a model, so in City Investigator they are model output.

Usage:
  python -m smoke.rainfall
  python -m smoke.rainfall --start 2026-08-22 --end 2026-08-24 --station LGA
"""

from __future__ import annotations

import argparse
import csv
import io
from datetime import date
from typing import Any

import requests

from smoke._common import write_result

GOWANUS = (40.6787, -73.9830)  # near Carroll St and 4th Ave


def iem_station(station: str, start: date, end: date) -> dict[str, Any]:
    response = requests.get(
        "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py",
        params={
            "station": station,
            "data": "p01i",
            "year1": start.year, "month1": start.month, "day1": start.day,
            "year2": end.year, "month2": end.month, "day2": end.day,
            "tz": "America/New_York",
            "format": "onlycomma",
            "latlon": "no",
            "missing": "M",
            "trace": "T",
            # Routine hourly reports only, so specials do not double count rain.
            "report_type": "3",
        },
        timeout=60,
    )
    response.raise_for_status()
    hourly = []
    for row in csv.DictReader(io.StringIO(response.text)):
        value = row.get("p01i")
        if value in (None, "", "M"):
            continue
        hourly.append((row["valid"], 0.0 if value == "T" else float(value)))
    if not hourly:
        raise RuntimeError("no precipitation rows returned")
    peak = max(hourly, key=lambda item: item[1])
    return {
        "label": "record",
        "station": station,
        "hours": len(hourly),
        "total_in": round(sum(value for _, value in hourly), 2),
        "peak_in_per_hr": peak[1],
        "peak_at_local": peak[0],
    }


def open_meteo(start: date, end: date) -> dict[str, Any]:
    response = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude": GOWANUS[0],
            "longitude": GOWANUS[1],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": "precipitation",
            "precipitation_unit": "inch",
            "timezone": "America/New_York",
        },
        timeout=60,
    )
    response.raise_for_status()
    hourly = response.json()["hourly"]
    pairs = [(t, v) for t, v in zip(hourly["time"], hourly["precipitation"]) if v is not None]
    if not pairs:
        raise RuntimeError("no precipitation values returned")
    peak = max(pairs, key=lambda item: item[1])
    return {
        "label": "model",
        "grid_point": GOWANUS,
        "hours": len(pairs),
        "total_in": round(sum(value for _, value in pairs), 2),
        "peak_in_per_hr": peak[1],
        "peak_at_local": peak[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # Default window: the most recent reviewed flood event at Carroll St and 4th Ave.
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 8, 22))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 8, 24))
    parser.add_argument("--station", default="NYC", help="NYC (Central Park), LGA or JFK")
    args = parser.parse_args()

    sources = {
        f"Iowa Environmental Mesonet, station {args.station}": lambda: iem_station(args.station, args.start, args.end),
        "Open-Meteo archive": lambda: open_meteo(args.start, args.end),
    }
    results: dict[str, Any] = {"window": [args.start, args.end]}
    for name, fetch in sources.items():
        try:
            outcome = {"ok": True, **fetch()}
            print(
                f"PASS  {name} ({outcome['label']}): {outcome['total_in']} in total, "
                f"peak {outcome['peak_in_per_hr']} in/hr at {outcome['peak_at_local']}"
            )
        except Exception as error:  # report and try the next source
            outcome = {"ok": False, "error": f"{type(error).__name__}: {error}"[:600]}
            print(f"FAIL  {name}: {outcome['error']}")
        results[name] = outcome
    path = write_result("rainfall", results)
    print(f"\nDetails: {path}")


if __name__ == "__main__":
    main()
