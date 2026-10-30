"""Building footprints with roof heights and ground elevations (NYC Open Data 5zhs-2jue).

Two uses. The map's 3D view raises each building to its measured roof height. The flood
investigation compares the ground under the buildings at a spot with the ground under the
buildings around it, because water runs to low ground: a corner that sits lower than its
blocks collects their runoff in storms smaller than the drains were built for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Any

from shapely.errors import GEOSException
from shapely.geometry import shape

from city_investigator.evidence import Evidence, first, norm_bbl, norm_bin
from city_investigator.geo import distance_m, to_float

FOOTPRINTS_DATASET = "5zhs-2jue"
SOURCE = "NYC building footprints (ground elevation)"
PAGE = f"https://data.cityofnewyork.us/d/{FOOTPRINTS_DATASET}"
FT = 0.3048
NEAR_M, AROUND_M = 40, 200  # the spot, and the blocks around it
MIN_NEAR, MIN_AROUND = 2, 10
DEFAULT_HEIGHT_M = 6.0  # for the map only, when a footprint has no roof height
KEEP = ("bin", "base_bbl", "mappluto_bbl", "height_roof", "heightroof", "ground_elevation", "groundelev",
        "construction_year", "cnstrct_yr")


@dataclass(frozen=True)
class Building:
    bin: str | None
    bbl: str | None
    height_m: float | None
    ground_ft: float | None  # above sea level (NAVD88), at the building
    rings: tuple[tuple[tuple[float, float], ...], ...]  # outer rings, lon/lat
    lat: float
    lon: float


def slim(row: dict[str, Any]) -> dict[str, Any] | None:
    """A footprint row with only what is used, coordinates rounded to about 10 cm."""
    geometry = row.get("the_geom")
    if not isinstance(geometry, dict) or "coordinates" not in geometry:
        return None

    def rounded(value: Any) -> Any:
        return [rounded(item) for item in value] if isinstance(value, list) and value and isinstance(value[0], list) \
            else [round(float(number), 6) for number in value]

    return {key: row[key] for key in KEEP if row.get(key) not in (None, "")} | {
        "the_geom": {"type": geometry.get("type"), "coordinates": rounded(geometry["coordinates"])},
    }


def from_row(row: dict[str, Any]) -> Building | None:
    try:
        geometry = shape(row["the_geom"])
    except (KeyError, TypeError, ValueError, GEOSException):
        return None
    if geometry.is_empty:
        return None
    polygons = list(geometry.geoms) if hasattr(geometry, "geoms") else [geometry]
    middle = geometry.centroid
    height = to_float(first(row, "height_roof", "heightroof"))
    ground = to_float(first(row, "ground_elevation", "groundelev"))
    return Building(
        bin=norm_bin(row.get("bin")),
        bbl=norm_bbl(first(row, "mappluto_bbl", "base_bbl")),
        height_m=height * FT if height and height > 0 else None,
        ground_ft=ground if ground and ground > 0 else None,  # 0 marks a missing value
        rings=tuple(tuple((x, y) for x, y, *_ in polygon.exterior.coords) for polygon in polygons if not polygon.is_empty),
        lat=middle.y,
        lon=middle.x,
    )


class Buildings:
    def __init__(self, items: list[Building]) -> None:
        self.items = items

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> Buildings:
        return cls([building for row in rows if (building := from_row(row))])

    def around(self, lat: float, lon: float, radius_m: float) -> list[tuple[Building, float]]:
        dlat = radius_m / 110_000
        dlon = dlat / max(math.cos(math.radians(lat)), 0.1)
        found = []
        for building in self.items:
            if abs(building.lat - lat) <= dlat and abs(building.lon - lon) <= dlon:
                meters = distance_m(lat, lon, building.lat, building.lon)
                if meters <= radius_m:
                    found.append((building, meters))
        return sorted(found, key=lambda pair: pair[1])

    def features(self, lat: float, lon: float, half_m: float, highlight: set[str] | None = None) -> dict[str, Any]:
        """The buildings around a point as map polygons, with heights in meters."""
        highlight = highlight or set()
        features = []
        for building, _ in self.around(lat, lon, half_m):
            marked = bool({building.bin, building.bbl} & highlight - {None})
            for ring in building.rings:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [[list(point) for point in ring]]},
                    "properties": {
                        "height": round(building.height_m or DEFAULT_HEIGHT_M, 1),
                        "measured": building.height_m is not None,
                        "cited": marked,
                        "bin": building.bin or "",
                    },
                })
        return {"type": "FeatureCollection", "features": features}

    def ground_here(self, lat: float, lon: float) -> Evidence | None:
        """How the ground under the buildings at a spot compares with the ground around it."""
        around = [(b, d) for b, d in self.around(lat, lon, AROUND_M) if b.ground_ft is not None]
        near = [b.ground_ft for b, d in around if d <= NEAR_M]
        wider = [b.ground_ft for b, _ in around]
        if len(near) < MIN_NEAR or len(wider) < MIN_AROUND:
            return None
        here, there = median(near), median(wider)
        difference = here - there
        higher = sum(1 for value in wider if value > here) / len(wider)
        side = "lower" if difference < 0 else "higher"
        return Evidence(
            id="elevation:ground",
            kind="record",
            topic="flooding",
            category="ground_elevation",
            source=SOURCE,
            dataset=FOOTPRINTS_DATASET,
            summary=(
                f"The {len(near)} buildings within {NEAR_M} m stand on ground about {here:.1f} ft above sea level; "
                f"the {len(wider)} within {AROUND_M} m, about {there:.1f} ft (medians). This spot is {abs(difference):.1f} ft "
                f"{side} than its surroundings, and {higher:.0%} of those buildings stand higher. Measured at the "
                "buildings, not in the street."
            ),
            lat=lat,
            lon=lon,
            located_by="buildings around the pin",
            start=None,
            end=None,
            url=PAGE,
            raw={
                "near_ft": round(here, 2), "around_ft": round(there, 2), "difference_ft": round(difference, 2),
                "share_higher": round(higher, 3), "near_buildings": len(near), "around_buildings": len(wider),
            },
        )

