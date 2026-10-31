"""Bring a photo into an investigation, from Mapillary or a local file.

Reads where and when the photo was taken (Mapillary's computed position and capture
time, or the file's GPS and timestamp), then prepares an upright JPEG without any
metadata. The location is only a hint until the person confirms it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from city_investigator import times
from city_investigator.meta import load_photo
from city_investigator.photo_check import fetch_image
from city_investigator.photos import LICENSE

MAPILLARY_UNCERTAINTY_M = 10.0
# Phone GPS in dense streets is often off by 6 to 15 m, with outliers far beyond.
GPS_MIN_UNCERTAINTY_M = 15.0
GPS_IFD, EXIF_IFD = 0x8825, 0x8769


@dataclass
class Photo:
    source: str  # "mapillary" or "file"
    ref: str  # Mapillary ID or file name
    jpeg: bytes  # upright, resized, metadata removed
    size: tuple[int, int]
    lat: float | None
    lon: float | None
    taken_at: datetime | None  # UTC
    location_source: str  # "mapillary", "photo_gps", "user" or "none"
    uncertainty_m: float | None
    credit: str | None = None
    license: str | None = None
    page_url: str | None = None
    already_blurred: bool = False
    heading_deg: float | None = None  # the camera's compass direction, when the source records it
    fov_deg: float | None = None  # the photo's horizontal field of view; 360 for a panorama

    def describe(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ref": self.ref,
            "size": list(self.size),
            "taken_at": self.taken_at.isoformat() if self.taken_at else None,
            "taken_local": times.to_local(self.taken_at).strftime("%Y-%m-%d %H:%M") if self.taken_at else None,
            "location": {
                "lat": self.lat,
                "lon": self.lon,
                "source": self.location_source,
                "uncertainty_m": self.uncertainty_m,
            },
            "credit": self.credit,
            "license": self.license,
            "page_url": self.page_url,
            "faces_and_plates": "blurred by Mapillary" if self.already_blurred else "blurred here",
            "heading_deg": self.heading_deg,
            "fov_deg": self.fov_deg,
        }


def field_of_view(meta: dict[str, Any], size: tuple[int, int]) -> float | None:
    """Horizontal field of view in degrees: 360 for a panorama; for a perspective camera, from Mapillary's
    calibration, whose focal length is a share of the photo's longer side."""
    kind = meta.get("camera_type") or "perspective"
    if meta.get("is_pano") or kind in ("spherical", "equirectangular"):
        return 360.0
    focal = (meta.get("camera_parameters") or [None])[0]
    if kind != "perspective" or not isinstance(focal, (int, float)) or focal <= 0:
        return None
    width, height = size
    return round(math.degrees(2 * math.atan(width / (2 * focal * max(width, height)))), 1)


def from_mapillary(photo_id: str, token: str) -> Photo:
    path, meta = fetch_image(photo_id, token)
    jpeg, size = load_photo(path)
    coordinates = (meta.get("computed_geometry") or {}).get("coordinates") or [None, None]
    captured = meta.get("captured_at")
    creator = (meta.get("creator") or {}).get("username") or "a Mapillary contributor"
    return Photo(
        source="mapillary",
        ref=str(photo_id),
        jpeg=jpeg,
        size=size,
        lat=coordinates[1],
        lon=coordinates[0],
        taken_at=datetime.fromtimestamp(captured / 1000, timezone.utc) if isinstance(captured, (int, float)) else None,
        location_source="mapillary",
        uncertainty_m=MAPILLARY_UNCERTAINTY_M,
        credit=f"Photo by {creator}, Mapillary, {LICENSE}",
        license=LICENSE,
        page_url=f"https://www.mapillary.com/app/?pKey={photo_id}",
        already_blurred=True,
        heading_deg=next((float(value) for value in (meta.get("computed_compass_angle"), meta.get("compass_angle"))
                          if isinstance(value, (int, float))), None),
        fov_deg=field_of_view(meta, size),
    )


def dms_to_degrees(values: Any, ref: Any) -> float | None:
    try:
        degrees, minutes, seconds = (float(value) for value in values)
    except (TypeError, ValueError):
        return None
    result = degrees + minutes / 60 + seconds / 3600
    return -result if str(ref).upper() in {"S", "W"} else result


def read_exif(path: Path) -> tuple[float | None, float | None, float | None, datetime | None]:
    """(lat, lon, GPS error in meters, capture time in UTC) from a photo's metadata."""
    from PIL import Image

    if path.suffix.lower() in {".heic", ".heif"}:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    with Image.open(path) as image:
        exif = image.getexif()
    gps = exif.get_ifd(GPS_IFD)
    lat = dms_to_degrees(gps.get(2), gps.get(1))
    lon = dms_to_degrees(gps.get(4), gps.get(3))
    error = gps.get(31)
    details = exif.get_ifd(EXIF_IFD)
    taken = _capture_time(details.get(0x9003), details.get(0x9011))
    return lat, lon, float(error) if error is not None else None, taken


def _capture_time(local_text: Any, offset_text: Any) -> datetime | None:
    if not local_text:
        return None
    try:
        moment = datetime.strptime(str(local_text).strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    if offset_text:
        sign = -1 if str(offset_text).startswith("-") else 1
        hours, _, minutes = str(offset_text).lstrip("+-").partition(":")
        offset = timezone(sign * timedelta(hours=int(hours), minutes=int(minutes or 0)))
        return moment.replace(tzinfo=offset).astimezone(timezone.utc)
    # Without an offset, assume the camera clock was on New York time.
    return moment.replace(tzinfo=times.LOCAL).astimezone(timezone.utc)


def from_file(path: Path) -> Photo:
    lat, lon, error, taken = read_exif(path)
    jpeg, size = load_photo(path)
    has_gps = lat is not None and lon is not None
    return Photo(
        source="file",
        ref=path.name,
        jpeg=jpeg,
        size=size,
        lat=lat,
        lon=lon,
        taken_at=taken,
        location_source="photo_gps" if has_gps else "none",
        uncertainty_m=max(GPS_MIN_UNCERTAINTY_M, error or 0) if has_gps else None,
    )
