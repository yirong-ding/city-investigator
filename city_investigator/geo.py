"""Distances in meters and simple bounding boxes."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass bearing from the first point to the second, 0 to 360 degrees."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lon2 - lon1)
    x = math.sin(dlmb) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return math.degrees(math.atan2(x, y)) % 360


def angle_between(a: float, b: float) -> float:
    """Smallest difference between two compass directions, 0 to 180 degrees."""
    return abs((a - b + 180) % 360 - 180)


def bbox(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat) around a point."""
    dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    dlon = math.degrees(radius_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat


def to_float(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _coordinate(lat: object, lon: object) -> tuple[float, float] | None:
    lat_f, lon_f = to_float(lat), to_float(lon)
    # The city writes 0 for missing coordinates.
    if lat_f is None or lon_f is None or lat_f == 0 or lon_f == 0:
        return None
    return lat_f, lon_f


def point(row: dict, *pairs: tuple[str, str]) -> tuple[float | None, float | None]:
    """Read a coordinate from the first (lat field, lon field) pair present, or a GeoJSON point."""
    for lat_key, lon_key in pairs:
        found = _coordinate(row.get(lat_key), row.get(lon_key))
        if found:
            return found
    for value in row.values():
        if isinstance(value, dict) and value.get("type") == "Point":
            lon, lat = (list(value.get("coordinates") or []) + [None, None])[:2]
            found = _coordinate(lat, lon)
            if found:
                return found
    return None, None
