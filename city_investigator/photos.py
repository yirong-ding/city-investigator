"""Find Mapillary street photos near a place, with date, location and credit.

Mapillary photos are licensed CC BY-SA 4.0: credit the photographer and Mapillary,
and share edited versions (such as mask overlays) under the same license.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

from city_investigator.geo import angle_between, bbox, bearing_deg, distance_m

API = "https://graph.mapillary.com/images"
FIELDS = "id,captured_at,computed_geometry,geometry,compass_angle,computed_compass_angle,is_pano,thumb_1024_url,creator"
# A camera pointing within this many degrees of the site counts as facing it.
FACING_TOLERANCE_DEG = 45
LICENSE = "CC BY-SA 4.0"


def parse_photo(item: dict[str, Any], lat: float, lon: float) -> dict[str, Any] | None:
    geometry = item.get("computed_geometry") or item.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    if len(coordinates) < 2 or not item.get("id"):
        return None
    photo_lon, photo_lat = float(coordinates[0]), float(coordinates[1])
    captured = item.get("captured_at")
    captured_at = (
        datetime.fromtimestamp(captured / 1000, timezone.utc).isoformat() if isinstance(captured, (int, float)) else None
    )
    creator = (item.get("creator") or {}).get("username") or "a Mapillary contributor"
    heading = item.get("computed_compass_angle", item.get("compass_angle"))
    is_pano = bool(item.get("is_pano"))
    distance = distance_m(lat, lon, photo_lat, photo_lon)
    if is_pano or distance < 3:
        faces_site = True
    elif isinstance(heading, (int, float)):
        faces_site = angle_between(heading, bearing_deg(photo_lat, photo_lon, lat, lon)) <= FACING_TOLERANCE_DEG
    else:
        faces_site = None  # unknown direction
    return {
        "id": str(item["id"]),
        "captured_at": captured_at,
        "lat": photo_lat,
        "lon": photo_lon,
        "distance_m": round(distance),
        "compass_angle": heading,
        "is_pano": is_pano,
        "faces_site": faces_site,
        "image_url": item.get("thumb_1024_url"),
        "page_url": f"https://www.mapillary.com/app/?pKey={item['id']}",
        "credit": f"Photo by {creator}, Mapillary, {LICENSE}",
        "license": LICENSE,
    }


def photos_near(
    lat: float,
    lon: float,
    radius_m: float = 40,
    limit: int = 2000,
    token: str | None = None,
    session: requests.Session | None = None,
    retries: int = 1,
) -> list[dict[str, Any]]:
    """Photos within radius_m, newest first. Image URLs expire; page URLs do not.

    A small limit makes Mapillary return an arbitrary subset of the photos in the box,
    so ask for many. An empty answer is retried once, since searches sometimes time out
    quietly.
    """
    token = token or os.environ.get("MAPILLARY_TOKEN")
    if not token:
        raise RuntimeError("MAPILLARY_TOKEN is not set")
    session = session or requests.Session()
    min_lon, min_lat, max_lon, max_lat = bbox(lat, lon, radius_m)
    params = {
        "access_token": token,
        "fields": FIELDS,
        "bbox": f"{min_lon:.6f},{min_lat:.6f},{max_lon:.6f},{max_lat:.6f}",
        "limit": limit,
    }
    for attempt in range(retries + 1):
        response = session.get(API, params=params, timeout=60)
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            raise RuntimeError(f"Mapillary error: {str(body['error'])[:200]}")
        items = body.get("data", [])
        if items or attempt == retries:
            break
        time.sleep(1)
    photos = [photo for item in items if (photo := parse_photo(item, lat, lon))]
    photos = [photo for photo in photos if photo["distance_m"] <= radius_m]
    return sorted(photos, key=lambda photo: photo["captured_at"] or "", reverse=True)
