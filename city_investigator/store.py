"""Look up evidence near a place and time, and say what the data could not have seen.

Every lookup returns the records found plus one coverage note per source. The notes
keep three kinds of "nothing" apart: data that exists but holds nothing relevant,
data that could not exist (no sensor yet, outside a dataset's years), and records of
a negative finding, so an empty result is never read as "nothing happened".
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from city_investigator import times
from city_investigator.config import RAIN_STATION
from city_investigator.evidence import (
    Evidence,
    Sensor,
    day,
    from_311,
    from_dob_legacy,
    from_dob_now,
    from_floodnet_event,
    from_pluto,
    sensor_from_row,
)
from city_investigator.floodmap import MODEL_NOTE, FloodMap
from city_investigator.geo import distance_m
from city_investigator.settings import SNAPSHOT_DIR

FOUND, NOTHING_FOUND, NO_COVERAGE, PARTIAL = "found", "nothing_found", "no_coverage", "partial"
TOPICS = ("flooding", "sidewalk")
RAIN_WINDOW_LIMIT = timedelta(days=14)
FLOODNET_REVIEW_LAG = timedelta(days=14)
LOT_MATCH_M = 60
UTC = timezone.utc


@dataclass
class Coverage:
    source: str
    state: str
    note: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class Hit:
    evidence: Evidence
    distance_m: float | None


@dataclass
class LookupResult:
    query: dict[str, Any]
    hits: list[Hit]
    coverage: list[Coverage]

    def categories(self) -> Counter[str]:
        return Counter(hit.evidence.category for hit in self.hits)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "coverage": [item.to_dict() for item in self.coverage],
            "evidence": [hit.evidence.to_dict(hit.distance_m) for hit in self.hits],
        }


def overlaps(evidence: Evidence, start: datetime | None, end: datetime | None) -> bool:
    if evidence.start is None:
        return start is None and end is None
    finish = evidence.end or evidence.start
    if start and finish < start:
        return False
    if end and evidence.start > end:
        return False
    return True


def window_text(start: datetime | None, end: datetime | None) -> str:
    if start and end:
        return f" between {day(start)} and {day(end)}"
    if start:
        return f" since {day(start)}"
    if end:
        return f" before {day(end)}"
    return ""


def local_midnight(year: int, month: int, day_: int) -> datetime:
    return datetime(year, month, day_, tzinfo=times.LOCAL).astimezone(UTC)


class Store:
    def __init__(
        self,
        evidence: list[Evidence],
        lots: list[Evidence],
        sensors: list[Sensor],
        rain: list[tuple[datetime, float]],
        periods_311: dict[str, list[tuple[datetime, datetime]]],
        loaded: set[str],
        floodnet_retrieved: datetime | None = None,
        flood_maps: list[FloodMap] | None = None,
    ) -> None:
        self.evidence = evidence
        self.lots = lots
        self.lot_by_bbl = {lot.bbl: lot for lot in lots if lot.bbl}
        self.sensors = sensors
        self.rain = sorted(rain)
        self.periods_311 = periods_311
        self.loaded = loaded
        self.floodnet_retrieved = floodnet_retrieved
        self.flood_maps = flood_maps or []

    @classmethod
    def load(cls, folder: Path = SNAPSHOT_DIR) -> Store:
        def read(name: str) -> dict[str, Any] | None:
            path = folder / f"{name}.json"
            return json.loads(path.read_text()) if path.is_file() else None

        loaded: set[str] = set()
        evidence: list[Evidence] = []
        periods: dict[str, list[tuple[datetime, datetime]]] = {topic: [] for topic in TOPICS}

        recent = read("311_2020_on")
        if recent:
            loaded.add("311_2020_on")
            evidence += [e for row in recent["rows"] if (e := from_311(row, recent["dataset"]))]
            span = (local_midnight(2020, 1, 1), times.parse(recent["retrieved_at"], "utc") or times.now())
            periods["flooding"].append(span)
            periods["sidewalk"].append(span)
        older = read("311_2010s")
        if older:
            loaded.add("311_2010s")
            evidence += [e for row in older["rows"] if (e := from_311(row, older["dataset"]))]
            # Only flooding types were downloaded from the 2010s dataset.
            periods["flooding"].append((local_midnight(2010, 1, 1), local_midnight(2020, 1, 1)))

        for name, adapter in (("dob_now_permits", from_dob_now), ("dob_legacy_permits", from_dob_legacy)):
            snapshot = read(name)
            if snapshot:
                loaded.add(name)
                evidence += [e for row in snapshot["rows"] if (e := adapter(row, snapshot["dataset"]))]

        sensors: list[Sensor] = []
        sensor_snapshot = read("floodnet_sensors")
        if sensor_snapshot:
            loaded.add("floodnet_sensors")
            sensors = [s for row in sensor_snapshot["rows"] if (s := sensor_from_row(row))]
        events = read("floodnet_events")
        floodnet_retrieved = None
        if events:
            loaded.add("floodnet_events")
            floodnet_retrieved = times.parse(events["retrieved_at"], "utc")
            by_id = {sensor.id: sensor for sensor in sensors}
            evidence += [e for row in events["rows"] if (e := from_floodnet_event(row, by_id, events["dataset"]))]

        lots: list[Evidence] = []
        pluto = read("pluto")
        if pluto:
            loaded.add("pluto")
            lots = [e for row in pluto["rows"] if (e := from_pluto(row, pluto["dataset"]))]

        rain: list[tuple[datetime, float]] = []
        rainfall = read("rainfall")
        if rainfall:
            loaded.add("rainfall")
            for row in rainfall["rows"]:
                moment = times.parse(row["valid_utc"], "utc")
                if moment:
                    rain.append((moment, float(row["inches"])))

        flood_maps: list[FloodMap] = []
        stormwater = read("stormwater")
        if stormwater:
            loaded.add("stormwater")
            flood_maps = [FloodMap.from_dict(scenario) for scenario in stormwater["scenarios"]]

        return cls(evidence, lots, sensors, rain, periods, loaded, floodnet_retrieved, flood_maps)

    # Lookups

    def near(
        self,
        lat: float,
        lon: float,
        radius_m: float,
        start: datetime | None = None,
        end: datetime | None = None,
        topic: str | None = None,
    ) -> LookupResult:
        topics = (topic,) if topic else TOPICS
        hits: list[Hit] = []
        for item in self.evidence:
            if item.topic not in topics or item.lat is None or item.lon is None:
                continue
            distance = distance_m(lat, lon, item.lat, item.lon)
            if distance <= radius_m and overlaps(item, start, end):
                hits.append(Hit(item, distance))

        coverage: list[Coverage] = []
        if "flooding" in topics:
            coverage.append(self._complaint_coverage("flooding", hits, radius_m, start, end))
            coverage.append(self._floodnet_coverage(lat, lon, radius_m, start, end, hits))
            rain_hit, rain_coverage = self._rain(lat, lon, start, end)
            if rain_hit:
                hits.append(rain_hit)
            if rain_coverage:
                coverage.append(rain_coverage)
            model_hits, model_coverage = self._stormwater(lat, lon, radius_m)
            hits += model_hits
            coverage.append(model_coverage)
        if "sidewalk" in topics:
            coverage.append(self._complaint_coverage("sidewalk", hits, radius_m, start, end))
            coverage.append(self._permit_coverage(hits, radius_m, start, end))

        lot = self.nearest_lot(lat, lon, min(radius_m, LOT_MATCH_M))
        if lot:
            hits.append(lot)
        hits.sort(key=sort_key)
        query = {
            "lat": lat,
            "lon": lon,
            "radius_m": radius_m,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "topic": topic,
        }
        return LookupResult(query, hits, coverage)

    def for_building(self, bbl: str | None = None, bin_: str | None = None, topic: str | None = None) -> LookupResult:
        topics = (topic,) if topic else TOPICS
        hits = [
            Hit(item, None)
            for item in self.evidence
            if item.topic in topics and ((bbl and item.bbl == bbl) or (bin_ and item.bin == bin_))
        ]
        if bbl and bbl in self.lot_by_bbl:
            hits.append(Hit(self.lot_by_bbl[bbl], None))
        hits.sort(key=sort_key)
        coverage = [
            Coverage(
                "Matching by building",
                PARTIAL,
                "Only records that carry this tax lot or building number are matched. Complaints "
                "located at the street or an intersection are missed, so also search by distance.",
            )
        ]
        return LookupResult({"bbl": bbl, "bin": bin_, "topic": topic}, hits, coverage)

    def nearest_lot(self, lat: float, lon: float, max_m: float) -> Hit | None:
        best: Hit | None = None
        for lot in self.lots:
            if lot.lat is None or lot.lon is None:
                continue
            distance = distance_m(lat, lon, lot.lat, lot.lon)
            if distance <= max_m and (best is None or distance < (best.distance_m or 0)):
                best = Hit(lot, distance)
        return best

    def rain_total(self, start: datetime, end: datetime) -> float | None:
        """Inches measured between start and end, or None if there are no readings."""
        readings = [inches for moment, inches in self.rain if start <= moment <= end]
        return round(sum(readings), 2) if readings else None

    def rain_peak(self, start: datetime, end: datetime) -> tuple[datetime, float] | None:
        """The wettest hourly reading between start and end: (end of that hour, inches)."""
        readings = [(moment, inches) for moment, inches in self.rain if start <= moment <= end]
        return max(readings, key=lambda item: item[1]) if readings else None

    def rain_summary(self, start: datetime, end: datetime) -> Evidence | None:
        readings = [(moment, inches) for moment, inches in self.rain if start <= moment <= end]
        if not readings:
            return None
        total = sum(inches for _, inches in readings)
        peak_time, peak = max(readings, key=lambda item: item[1])
        url = str(
            requests.Request(
                "GET",
                "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py",
                params={
                    "station": RAIN_STATION["id"], "data": "p01i", "tz": "Etc/UTC", "format": "onlycomma",
                    "year1": start.year, "month1": start.month, "day1": start.day,
                    "year2": end.year, "month2": end.month, "day2": end.day, "report_type": "3",
                },
            ).prepare().url
        )
        return Evidence(
            id=f"rain:{RAIN_STATION['id']}:{start:%Y%m%dT%H%MZ}-{end:%Y%m%dT%H%MZ}",
            kind="record",
            topic="flooding",
            category="rainfall",
            source=f"{RAIN_STATION['name']} (Iowa Environmental Mesonet)",
            dataset=f"IEM ASOS {RAIN_STATION['id']}",
            summary=(
                f"Rain measured at the {RAIN_STATION['name']}: {total:.2f} in{window_text(start, end)}; "
                f"heaviest hour {peak:.2f} in, ending {times.to_local(peak_time):%Y-%m-%d %H:%M}"
            ),
            lat=RAIN_STATION["lat"],
            lon=RAIN_STATION["lon"],
            located_by="weather station",
            start=start,
            end=end,
            url=url,
        )

    # Coverage notes

    def _complaint_coverage(
        self, topic: str, hits: list[Hit], radius_m: float, start: datetime | None, end: datetime | None
    ) -> Coverage:
        label = f"311 {topic} complaints"
        periods = self.periods_311.get(topic, [])
        if not periods:
            return Coverage(label, NO_COVERAGE, "311 data is not loaded; run the snapshot.")
        loaded_text = " and ".join(f"{day(a)} to {day(b)}" for a, b in sorted(periods))
        window_start = start or min(a for a, _ in periods)
        window_end = end or times.now()
        if not any(a <= window_end and b >= window_start for a, b in periods):
            return Coverage(label, NO_COVERAGE, f"311 data loaded covers {loaded_text}; the window falls outside it.")
        fully_covered = any(a <= window_start and b >= window_end for a, b in periods)
        found = [hit for hit in hits if hit.evidence.topic == topic and hit.evidence.id.startswith("311:")]
        days = {day(hit.evidence.start) for hit in found}
        where = f"within {radius_m:.0f} m{window_text(start, end)}"
        if found:
            state = FOUND
            note = (
                f"{plural(len(found), 'complaint')} on {plural(len(days), 'separate day')} {where}. Repeat complaints "
                "about one incident are corroboration, not separate incidents."
            )
        else:
            state = NOTHING_FOUND if fully_covered else PARTIAL
            note = (
                f"No {topic} complaints {where}. Complaints show who reports as well as what "
                "happens: fewer complaints does not mean fewer problems."
            )
        if not fully_covered:
            note += f" Only {loaded_text} is loaded."
        return Coverage(label, state, note)

    def _floodnet_coverage(
        self, lat: float, lon: float, radius_m: float, start: datetime | None, end: datetime | None, hits: list[Hit]
    ) -> Coverage:
        label = "FloodNet flood sensors"
        located = [(s, distance_m(lat, lon, s.lat, s.lon)) for s in self.sensors if s.lat is not None and s.lon is not None]
        if not located:
            return Coverage(label, NO_COVERAGE, "FloodNet data is not loaded; run the snapshot.")
        inside = [(sensor, distance) for sensor, distance in located if distance <= radius_m]
        if not inside:
            nearest, distance = min(located, key=lambda item: item[1])
            return Coverage(
                label,
                NO_COVERAGE,
                f"No FloodNet sensor within {radius_m:.0f} m; the nearest is {nearest.name}, "
                f"{distance:.0f} m away. No sensor events here does not mean no flooding.",
            )
        names = ", ".join(sorted({sensor.name for sensor, _ in inside}))
        window_end = end or times.now()
        deployed = [
            sensor
            for sensor, _ in inside
            if (sensor.installed is None or sensor.installed <= window_end)
            and (sensor.removed is None or start is None or sensor.removed >= start)
        ]
        if not deployed:
            installed = min((s.installed for s, _ in inside if s.installed), default=None)
            return Coverage(
                label,
                NO_COVERAGE,
                f"The sensor at {names} was installed {day(installed)}, after this window, so floods "
                "then are unobserved, not absent.",
            )
        notes = []
        earliest = min((s.installed for s in deployed if s.installed), default=None)
        starts_late = bool(earliest and start and start < earliest)
        if starts_late:
            notes.append(f"Sensor coverage here starts {day(earliest)}; earlier floods are unobserved, not absent.")
        if self.floodnet_retrieved and window_end > self.floodnet_retrieved - FLOODNET_REVIEW_LAG:
            notes.append(
                "FloodNet publishes events after review, about every two weeks; this snapshot was "
                f"downloaded {day(self.floodnet_retrieved)}, so floods after about "
                f"{day(self.floodnet_retrieved - FLOODNET_REVIEW_LAG)} may still be pending review."
            )
        found = [hit for hit in hits if hit.evidence.category == "flood_event"]
        if found:
            state = FOUND
            at = sorted({hit.evidence.address or "a sensor" for hit in found})
            base = f"{plural(len(found), 'flood event')} at {', '.join(at)}{window_text(start, end)}."
            quiet = sorted({sensor.name for sensor in deployed} - set(at))
            if quiet:
                base += f" No events at {', '.join(quiet)}."
        else:
            state = PARTIAL if starts_late else NOTHING_FOUND
            base = (
                f"No flood events at {names}{window_text(start, end)}. These sensors may not register "
                "street water until it tops the curb (about 15 cm)."
            )
        return Coverage(label, state, " ".join([base, *notes]))

    def _permit_coverage(self, hits: list[Hit], radius_m: float, start: datetime | None, end: datetime | None) -> Coverage:
        label = "DOB shed, scaffold and fence permits"
        if not self.loaded & {"dob_now_permits", "dob_legacy_permits"}:
            return Coverage(label, NO_COVERAGE, "Permit data is not loaded; run the snapshot.")
        found = [hit for hit in hits if hit.evidence.category.endswith("_permit")]
        where = f"within {radius_m:.0f} m{window_text(start, end)}"
        if found:
            return Coverage(
                label,
                FOUND,
                f"{plural(len(found), 'permit')} {where}. A permit shows the work was authorized, not that it is "
                "standing: DOB does not track whether a shed is physically up.",
            )
        return Coverage(
            label,
            NOTHING_FOUND,
            f"No shed, scaffold or fence permit {where}. The work may be unpermitted, or its permit "
            "may be filed under another address.",
        )

    def _rain(
        self, lat: float, lon: float, start: datetime | None, end: datetime | None
    ) -> tuple[Hit | None, Coverage | None]:
        label = "Rainfall"
        if not (start and end) or end - start > RAIN_WINDOW_LIMIT:
            return None, None
        if "rainfall" not in self.loaded:
            return None, Coverage(label, NO_COVERAGE, "Rainfall data is not loaded; run the snapshot.")
        summary = self.rain_summary(start, end)
        if summary is None:
            return None, Coverage(label, NO_COVERAGE, f"No weather station readings{window_text(start, end)}.")
        station_km = distance_m(lat, lon, RAIN_STATION["lat"], RAIN_STATION["lon"]) / 1000
        note = (
            f"Measured at the {RAIN_STATION['name']}, {station_km:.1f} km away; rain can differ "
            "a lot over that distance."
        )
        return Hit(summary, station_km * 1000), Coverage(label, FOUND, note)


    def _stormwater(self, lat: float, lon: float, radius_m: float) -> tuple[list[Hit], Coverage]:
        label = "City stormwater flood maps"
        if "stormwater" not in self.loaded:
            return [], Coverage(
                label, NO_COVERAGE, "The city's stormwater flood maps are not loaded; run the snapshot with --only stormwater."
            )
        hits = [
            Hit(item, distance_m(lat, lon, item.lat, item.lon))
            for flood_map in self.flood_maps
            if (item := flood_map.evidence(lat, lon, radius_m)) and item.lat is not None and item.lon is not None
        ]
        if hits:
            return hits, Coverage(label, FOUND, MODEL_NOTE)
        return [], Coverage(
            label,
            NOTHING_FOUND,
            f"No modeled flooding within {radius_m:.0f} m in any of the {plural(len(self.flood_maps), 'scenario')}. "
            + MODEL_NOTE,
        )


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def sort_key(hit: Hit) -> tuple[int, float]:
    started = hit.evidence.start.timestamp() if hit.evidence.start else 0.0
    # Lots and models have no date; list them first so a cap on records never drops them.
    return (0 if hit.evidence.topic == "context" or hit.evidence.kind == "model" else 1, -started)
