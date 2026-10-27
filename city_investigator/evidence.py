"""Evidence items: one public record with what it says, where, when, and a link to it.

Adapters turn raw rows from each dataset into Evidence. They read field names
defensively because the city renames and re-encodes fields over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from city_investigator import times
from city_investigator.config import COMPLAINTS, LEGACY_PERMIT_SUBTYPES, PERMIT_WORK_TYPES
from city_investigator.geo import point, to_float
from city_investigator.socrata import record_url

PERMIT_DEFAULT_DAYS = 90
# Placeholder building numbers the city uses when the real one is unknown.
PLACEHOLDER_BINS = {"1000000", "2000000", "3000000", "4000000", "5000000"}
OWNER_TYPES = {
    "C": "city-owned",
    "M": "mixed city and private ownership",
    "O": "other public ownership",
    "P": "privately owned",
    "X": "tax-exempt (public or institutional)",
}


@dataclass
class Evidence:
    id: str
    kind: str  # "record" or "model"
    topic: str  # "flooding", "sidewalk" or "context"
    category: str
    source: str
    dataset: str
    summary: str
    lat: float | None
    lon: float | None
    located_by: str  # how the location was set: address, intersection, sensor, lot, ...
    start: datetime | None  # UTC
    end: datetime | None  # UTC; None for one-moment records
    url: str
    address: str | None = None
    bbl: str | None = None
    bin: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self, distance_m: float | None = None) -> dict[str, Any]:
        def moment(value: datetime | None) -> dict[str, str] | None:
            if value is None:
                return None
            return {"utc": value.isoformat(), "local": times.to_local(value).strftime("%Y-%m-%d %H:%M")}

        return {
            "id": self.id,
            "kind": self.kind,
            "topic": self.topic,
            "category": self.category,
            "source": self.source,
            "dataset": self.dataset,
            "summary": self.summary,
            "address": self.address,
            "lat": self.lat,
            "lon": self.lon,
            "located_by": self.located_by,
            "distance_m": None if distance_m is None else round(distance_m),
            "start": moment(self.start),
            "end": moment(self.end),
            "bbl": self.bbl,
            "bin": self.bin,
            "url": self.url,
        }


@dataclass
class Sensor:
    id: str
    name: str
    lat: float | None
    lon: float | None
    installed: datetime | None
    removed: datetime | None
    tidal: bool


def first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def norm_bbl(value: Any) -> str | None:
    digits = str(value or "").split(".")[0].strip()
    return digits if digits.isdigit() and len(digits) == 10 and int(digits) > 0 else None


def norm_bin(value: Any) -> str | None:
    digits = str(value or "").split(".")[0].strip()
    return digits if digits.isdigit() and int(digits) > 0 and digits not in PLACEHOLDER_BINS else None


def join_address(*parts: Any) -> str | None:
    text = " ".join(str(part).strip() for part in parts if part not in (None, ""))
    return " ".join(text.split()) or None


def classify_complaint(complaint_type: Any, descriptor: Any) -> tuple[str, str] | None:
    ctype = str(complaint_type or "").strip()
    desc = str(descriptor or "").strip()
    return COMPLAINTS.get((ctype, desc)) or COMPLAINTS.get((ctype, None))


def day(value: datetime | None) -> str:
    return times.to_local(value).strftime("%Y-%m-%d") if value else "unknown date"


def from_311(row: dict[str, Any], dataset: str) -> Evidence | None:
    match = classify_complaint(row.get("complaint_type"), row.get("descriptor"))
    key = row.get("unique_key")
    if not match or not key:
        return None
    topic, category = match
    lat, lon = point(row, ("latitude", "longitude"))
    created = times.parse(row.get("created_date"))
    closed = times.parse(row.get("closed_date"))
    status = f"closed {day(closed)}" if closed else str(row.get("status") or "status unknown").lower()
    address = join_address(row.get("incident_address")) or join_address(
        row.get("intersection_street_1"), "and", row.get("intersection_street_2")
    )
    return Evidence(
        id=f"311:{key}",
        kind="record",
        topic=topic,
        category=category,
        source="NYC 311 service requests",
        dataset=dataset,
        summary=(
            f"311 complaint on {day(created)}: {row.get('complaint_type')} / {row.get('descriptor')}"
            f" ({status})"
        ),
        lat=lat,
        lon=lon,
        located_by=str(row.get("address_type") or "unknown").lower(),
        start=created,
        end=None,
        url=record_url(dataset, unique_key=str(key)),
        address=address,
        bbl=norm_bbl(row.get("bbl")),
        raw=row,
    )


def _permit(
    *,
    category: str,
    work_type: str,
    status: str,
    issued: datetime | None,
    expires: datetime | None,
    key: str,
    url: str,
    address: str | None,
    lat: float | None,
    lon: float | None,
    bbl: str | None,
    bin_: str | None,
    dataset: str,
    source: str,
    row: dict[str, Any],
) -> Evidence:
    if issued and not expires:
        expires = issued + timedelta(days=PERMIT_DEFAULT_DAYS)
    return Evidence(
        id=key,
        kind="record",
        topic="sidewalk",
        category=category,
        source=source,
        dataset=dataset,
        summary=f"DOB permit: {work_type}, valid {day(issued)} to {day(expires)} (status now: {status.lower()})",
        lat=lat,
        lon=lon,
        located_by="building",
        start=issued,
        end=expires,
        url=url,
        address=address,
        bbl=bbl,
        bin=bin_,
        raw=row,
    )


def from_dob_now(row: dict[str, Any], dataset: str) -> Evidence | None:
    work_type = str(row.get("work_type") or "").strip()
    category = PERMIT_WORK_TYPES.get(work_type)
    if not category:
        return None
    issued_text = first(row, "issued_date", "issuance_date")
    job = first(row, "job_filing_number", "job_filing_no")
    permit_no = first(row, "work_permit", "permit_number")
    bin_ = norm_bin(first(row, "bin", "bin__"))
    key = permit_no or f"{job}:{work_type}:{str(issued_text or '')[:10]}"
    lat, lon = point(row, ("latitude", "longitude"))
    return _permit(
        category=category,
        work_type=work_type,
        status=str(row.get("permit_status") or "status unknown"),
        issued=times.parse(issued_text),
        expires=times.parse(first(row, "expired_date", "expiration_date")),
        key=f"dobnow:{key}",
        url=record_url(dataset, job_filing_number=str(job)) if job else record_url(dataset, bin=str(bin_)),
        address=join_address(first(row, "house_no", "house_number", "house__"), row.get("street_name")),
        lat=lat,
        lon=lon,
        bbl=norm_bbl(row.get("bbl")),
        bin_=bin_,
        dataset=dataset,
        source="DOB NOW approved permits",
        row=row,
    )


def from_dob_legacy(row: dict[str, Any], dataset: str) -> Evidence | None:
    subtype = str(row.get("permit_subtype") or "").strip()
    category = LEGACY_PERMIT_SUBTYPES.get(subtype)
    if not category:
        return None
    issued_text = first(row, "issuance_date", "filing_date")
    job = first(row, "job__", "job_number")
    sequence = first(row, "permit_sequence__", "permit_sequence")
    bin_ = norm_bin(first(row, "bin__", "bin"))
    lat, lon = point(row, ("gis_latitude", "gis_longitude"), ("latitude", "longitude"))
    return _permit(
        category=category,
        work_type={"SH": "Sidewalk Shed", "SF": "Scaffold", "FN": "Construction Fence"}[subtype],
        status=str(row.get("permit_status") or "issued"),
        issued=times.parse(issued_text),
        expires=times.parse(row.get("expiration_date")),
        key=f"dobbis:{job}:{sequence or str(issued_text or '')[:10]}",
        url=record_url(dataset, job__=str(job)) if job else record_url(dataset, bin__=str(bin_)),
        address=join_address(first(row, "house__", "house_no"), row.get("street_name")),
        lat=lat,
        lon=lon,
        bbl=None,
        bin_=bin_,
        dataset=dataset,
        source="DOB permit issuance (before DOB NOW)",
        row=row,
    )


def sensor_from_row(row: dict[str, Any]) -> Sensor | None:
    sensor_id = row.get("sensor_id")
    if not sensor_id:
        return None
    lat, lon = point(row, ("latitude", "longitude"), ("lat", "lon"))
    tidal = str(row.get("tidally_influenced") or "").strip().lower() in {"true", "yes", "1", "y"}
    return Sensor(
        id=str(sensor_id),
        name=str(row.get("sensor_name") or sensor_id),
        lat=lat,
        lon=lon,
        installed=times.parse(first(row, "date_installed", "deployment_date")),
        removed=times.parse(first(row, "date_removed", "removal_date")),
        tidal=tidal,
    )


def from_floodnet_event(row: dict[str, Any], sensors: dict[str, Sensor], dataset: str) -> Evidence | None:
    sensor = sensors.get(str(row.get("sensor_id")))
    start_text = row.get("flood_start_time")
    start = times.parse(start_text, "utc")
    if sensor is None or start is None:
        return None
    end = times.parse(first(row, "flood_end_time", "flood_end"), "utc")
    depth = to_float(row.get("max_depth_inches"))
    depth_text = f", deepest {depth:.1f} in at the sensor" if depth is not None else ""
    return Evidence(
        id=f"floodnet:{sensor.id}:{start.strftime('%Y%m%dT%H%M%SZ')}",
        kind="record",
        topic="flooding",
        category="flood_event",
        source="FloodNet street flooding sensors (NYU and CUNY)",
        dataset=dataset,
        summary=f"FloodNet flood event at {sensor.name} starting {times.to_local(start):%Y-%m-%d %H:%M}{depth_text}",
        lat=sensor.lat,
        lon=sensor.lon,
        located_by="sensor",
        start=start,
        end=end,
        url=record_url(dataset, sensor_id=sensor.id, flood_start_time=str(start_text)),
        address=sensor.name,
        raw=row,
    )


def floors_text(value: Any) -> str | None:
    floors = to_float(value)
    if not floors:
        return None
    count = int(floors) if floors.is_integer() else floors
    return f"{count} floor" if count == 1 else f"{count} floors"


def from_pluto(row: dict[str, Any], dataset: str) -> Evidence | None:
    bbl = norm_bbl(row.get("bbl"))
    if not bbl:
        return None
    lat, lon = point(row, ("latitude", "longitude"))
    details = [
        f"building class {row['bldgclass']}" if row.get("bldgclass") else None,
        f"built {row['yearbuilt']}" if str(row.get("yearbuilt") or "0") not in {"0", ""} else None,
        floors_text(row.get("numfloors")),
        OWNER_TYPES.get(str(row.get("ownertype") or "").strip(), None),
        f"zoning {row['zonedist1']}" if row.get("zonedist1") else None,
    ]
    flood_zone = "inside the 2007 FEMA flood zone" if str(row.get("firm07_flag") or "") == "1" else None
    version = row.get("version")
    address = join_address(row.get("address"))
    return Evidence(
        id=f"pluto:{bbl}",
        kind="record",
        topic="context",
        category="lot",
        source=f"PLUTO property data{f' {version}' if version else ''}",
        dataset=dataset,
        summary=f"Property lot{f' at {address}' if address else ''}: " + ", ".join(part for part in [*details, flood_zone] if part),
        lat=lat,
        lon=lon,
        located_by="lot",
        start=None,
        end=None,
        url=record_url(dataset, bbl=str(row.get("bbl"))),
        address=address,
        bbl=bbl,
        raw=row,
    )
