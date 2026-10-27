"""The city's stormwater flood maps: where its models expect rain to pond in design storms.

The maps are models, not observations. They show ponding at least 4 in deep over at
least a quarter acre in a design storm, so smaller or shallower flooding is not mapped,
and they say nothing about what happened on any particular day.

The snapshot step clips each citywide layer to the neighborhood and saves it in
longitude and latitude. Here each layer is moved onto a flat local grid in meters, which
is accurate to well under a meter across one community district.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import shapely
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

from city_investigator.config import STORMWATER_CATEGORIES
from city_investigator.evidence import Evidence

LAT0, LON0 = 40.675, -73.995  # center of the local grid
M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(LAT0))
SPOT_M = 1.0  # closer than this counts as "at this spot"
MODEL_NOTE = (
    "These are models of design storms, not observations: they map ponding at least 4 in deep over at "
    "least a quarter acre, so smaller or shallower flooding is not shown, and they say nothing about any "
    "particular day."
)


def to_meters(geometry: Any) -> Any:
    return shapely.transform(
        geometry,
        lambda xy: np.column_stack(((xy[:, 0] - LON0) * M_PER_DEG_LON, (xy[:, 1] - LAT0) * M_PER_DEG_LAT)),
    )


def to_degrees(geometry: Any) -> Any:
    return shapely.transform(
        geometry,
        lambda xy: np.column_stack((xy[:, 0] / M_PER_DEG_LON + LON0, xy[:, 1] / M_PER_DEG_LAT + LAT0)),
    )


@dataclass
class FloodMap:
    key: str
    dataset: str
    title: str
    layers: dict[int, Any]  # flooding category -> geometry on the local grid

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FloodMap:
        layers: dict[int, Any] = {}
        for feature in data["features"]:
            category, geometry = int(feature["category"]), to_meters(shape(feature["geometry"]))
            layers[category] = shapely.union(layers[category], geometry) if category in layers else geometry
        return cls(data["key"], data["dataset"], data["title"], layers)

    def distances(self, lat: float, lon: float) -> dict[int, float]:
        """Meters from the point to each flooding category (0 inside it)."""
        point = to_meters(Point(lon, lat))
        return {category: float(shapely.distance(geometry, point)) for category, geometry in self.layers.items()}

    def evidence(self, lat: float, lon: float, radius_m: float) -> Evidence | None:
        near = {category: distance for category, distance in self.distances(lat, lon).items() if distance <= radius_m}
        if not near:
            return None
        parts = [
            f"{STORMWATER_CATEGORIES.get(category, f'flooding category {category}')} "
            + ("at this spot" if distance < SPOT_M else f"{distance:.0f} m away")
            for category, distance in sorted(near.items(), key=lambda item: item[1])
        ]
        closest = min(near, key=near.__getitem__)
        nearest = to_degrees(nearest_points(self.layers[closest], to_meters(Point(lon, lat)))[0])
        return Evidence(
            id=f"stormwater:{self.key}",
            kind="model",
            topic="flooding",
            category="modeled_flooding",
            source="NYC Stormwater Flood Maps (City of New York)",
            dataset=self.dataset,
            summary=f"The city's stormwater flood model for {self.title} maps " + "; ".join(parts),
            lat=nearest.y,
            lon=nearest.x,
            located_by="model",
            start=None,
            end=None,
            url=f"https://data.cityofnewyork.us/d/{self.dataset}",
            raw={"scenario": self.key, "distances_m": {str(category): round(d, 1) for category, d in near.items()}},
        )
