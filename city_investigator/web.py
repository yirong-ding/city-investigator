"""The web page: bring a photo, confirm the pin, ask, and watch the investigation unfold.

The page streams each step as it happens (SAM 3.1 looking for scaffolding, Muse Spark
reading a complaint), then shows the answer, a map, a timeline and the sources. It
runs on this computer only (127.0.0.1), with the same snapshots, keys and spend cap as
the command line. Photos and results stay in data/private/.

Usage:
  python -m city_investigator.web            # opens http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import threading
import uuid
import webbrowser
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from city_investigator.explain import explain_run
from city_investigator.investigate import OUTPUT, USER_UNCERTAINTY_M, investigate_photo, parse_local
from city_investigator.photo_input import Photo, from_file, from_mapillary
from city_investigator.settings import ROOT, load_env
from city_investigator.shortlist import street_view
from city_investigator.sources import SOURCES, STATE_CATEGORIES
from city_investigator.store import Store
from city_investigator.topics import TOPICS

STATIC = Path(__file__).parent / "static"
UPLOADS = ROOT / "data" / "private" / "uploads"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
RUN_FILES = {"photo.jpg", "overlay.png"}
MAP_HALF_M = 400  # flood model shown within this distance of the pin
MAP_MAX_M = 1000  # records farther than this (the Central Park rain gauge) stay off the map
KEEPALIVE_S = 15

DEMOS = [
    {
        "label": "Sidewalk shed on Court St",
        "mapillary_id": "1306991370360816",
        "question": "What records relate to this blocked sidewalk?",
    },
    {
        "label": "Permit, but no shed: 230 Court St",
        "mapillary_id": "1332532847863656",
        "question": "What records relate to this blocked sidewalk?",
    },
    {
        "label": "Flooding at Carroll St and 4th Av",
        "mapillary_id": "1385498442151420",
        "question": "Is flooding a recurring problem here?",
        "when": "2026-08-23",
    },
]


@dataclass
class Job:
    """One investigation running in the background, with every step it has reported."""

    id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    condition: threading.Condition = field(default_factory=threading.Condition)

    def put(self, event: dict[str, Any]) -> None:
        with self.condition:
            # Numbered, so a page that reconnects can skip the steps it has already shown.
            self.events.append(event | {"n": len(self.events)})
            self.finished = self.finished or event["type"] in ("done", "error")
            self.condition.notify_all()

    def stream(self) -> Iterator[str]:
        """Server-sent events: every step so far, then each new one until the job ends."""
        index = 0
        while True:
            with self.condition:
                if index >= len(self.events) and not self.finished:
                    self.condition.wait(timeout=KEEPALIVE_S)
                batch, finished = self.events[index:], self.finished
            index += len(batch)
            for event in batch:
                yield f"data: {json.dumps(event)}\n\n"
            if finished:
                return
            if not batch:
                yield ": still working\n\n"


class State:
    def __init__(self, store: Store | None = None) -> None:
        self._store = store
        self.photos: dict[str, Photo] = {}
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    @property
    def store(self) -> Store:
        with self.lock:
            if self._store is None:
                self._store = Store.load()
            return self._store


class InvestigationRequest(BaseModel):
    photo: str
    lat: float
    lon: float
    question: str
    taken: str | None = None  # New York time, YYYY-MM-DD [HH:MM]
    when: str | None = None
    topic: str | None = None
    provider: Literal["meta", "open"] = "meta"
    explain: bool = True


def photo_info(token: str, photo: Photo) -> dict[str, Any]:
    described = photo.describe()
    return {
        "photo": token,
        "preview": f"/api/photos/{token}.jpg",
        "lat": photo.lat,
        "lon": photo.lon,
        "location_source": photo.location_source,
        "uncertainty_m": photo.uncertainty_m,
        "taken_local": described["taken_local"],
        "credit": photo.credit,
        "page_url": photo.page_url,
        "street_view": street_view(photo.lat, photo.lon) if photo.lat is not None and photo.lon is not None else None,
    }


def confirmed(photo: Photo, request: InvestigationRequest) -> Photo:
    """The photo with the pin and time the person confirmed: the confirmed pin is the record."""
    moved = photo.lat is None or photo.lon is None or abs(photo.lat - request.lat) + abs(photo.lon - request.lon) > 1e-6
    return replace(
        photo,
        lat=request.lat,
        lon=request.lon,
        location_source="user" if moved else photo.location_source,
        uncertainty_m=USER_UNCERTAINTY_M if moved else photo.uncertainty_m,
        taken_at=parse_local(request.taken) if request.taken else photo.taken_at,
    )


def group(record: dict[str, Any]) -> str:
    """How the page draws a record: complaint, permit, agency action, inventory, sensor, lot or rain."""
    rid, category = record["id"], record.get("category") or ""
    prefix = rid.split(":", 1)[0]
    if prefix == "311":
        return "complaint"
    if prefix == "rain":
        return "rain"
    if category.endswith(("_permit", "_license")) or category == "street_closure" or prefix in ("dobnow", "doblegacy"):
        return "permit"
    if category in STATE_CATEGORIES or prefix in ("tree_points", "ramps"):
        return "inventory"
    if category == "flood_event" or prefix == "floodnet":
        return "sensor"
    if category == "lot" or prefix == "pluto":
        return "lot"
    if prefix in SOURCES:
        return "agency"
    return "other"


def map_layers(result: dict[str, Any], explanation: dict[str, Any] | None, store: Store | None) -> dict[str, Any]:
    """GeoJSON for the page: records near the pin, and the city's flood model around it."""
    location = result["photo"]["location"]
    lat, lon = location["lat"], location["lon"]
    points: dict[str, dict[str, Any]] = {}
    found_by_muse = (explanation or {}).get("evidence", {}).values()
    for record in [*result["records"], *found_by_muse]:
        rid, rlat, rlon = record["id"], record.get("lat"), record.get("lon")
        if rid in points or rlat is None or rlon is None or record.get("kind", record.get("type")) == "model":
            continue
        if (record.get("distance_m") or 0) > MAP_MAX_M:
            continue
        start = record.get("start") or {}
        end = record.get("end") or {}
        points[rid] = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [rlon, rlat]},
            "properties": {
                "id": rid,
                "group": group(record),
                "category": record.get("category") or "",
                "summary": record["summary"],
                "address": record.get("address") or "",
                "date": start.get("local") or record.get("date") or "",
                "until": end.get("local") or record.get("until") or "",
                "url": record.get("url") or "",
            },
        }
    flood = []
    if store is not None and result["topic"] == "flooding":
        for flood_map in store.flood_maps:
            flood += flood_map.around(lat, lon, MAP_HALF_M)
    return {
        "pin": {"lat": lat, "lon": lon, "uncertainty_m": location["uncertainty_m"], "radius_m": result["radius_m"]},
        "records": {"type": "FeatureCollection", "features": list(points.values())},
        "flood": {"type": "FeatureCollection", "features": flood},
    }


def run_folder(name: str) -> Path:
    path = OUTPUT / name
    if not re.fullmatch(r"[\w.-]+", name) or not (path / "result.json").is_file():
        raise HTTPException(404, f"No investigation named {name!r}.")
    return path


def create_app(state: State | None = None) -> FastAPI:
    state = state or State()
    app = FastAPI(title="City Investigator")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/demos")
    def demos() -> list[dict[str, Any]]:
        return DEMOS

    @app.get("/api/topics")
    def topics() -> list[dict[str, str]]:
        return [{"key": topic.key, "label": topic.label, "example": topic.example} for topic in TOPICS.values()]

    @app.post("/api/photos")
    def add_photo(file: UploadFile | None = File(None), mapillary_id: str | None = Form(None)) -> dict[str, Any]:
        if file is not None and file.filename:
            suffix = Path(file.filename).suffix.lower()
            if suffix not in PHOTO_TYPES:
                raise HTTPException(400, f"Use a JPEG, PNG, WebP or HEIC photo, not {suffix or 'this file'}.")
            UPLOADS.mkdir(parents=True, exist_ok=True)
            path = UPLOADS / f"{uuid.uuid4().hex[:12]}{suffix}"  # never the person's file name
            path.write_bytes(file.file.read())
            photo = from_file(path)
        elif mapillary_id and mapillary_id.strip().isdigit():
            token = os.environ.get("MAPILLARY_TOKEN")
            if not token:
                raise HTTPException(400, "MAPILLARY_TOKEN is not set.")
            try:
                photo = from_mapillary(mapillary_id.strip(), token)
            except Exception as error:  # show the reason on the page
                raise HTTPException(502, f"Could not get Mapillary photo {mapillary_id}: {error}") from error
        else:
            raise HTTPException(400, "Upload a photo or give a Mapillary photo ID.")
        token = uuid.uuid4().hex[:12]
        state.photos[token] = photo
        return photo_info(token, photo)

    @app.get("/api/photos/{token}.jpg")
    def photo_preview(token: str) -> Response:
        photo = state.photos.get(token)
        if photo is None:
            raise HTTPException(404, "Unknown photo.")
        return Response(photo.jpeg, media_type="image/jpeg")

    @app.post("/api/investigations")
    def start(request: InvestigationRequest) -> dict[str, str]:
        photo = state.photos.get(request.photo)
        if photo is None:
            raise HTTPException(404, "Unknown photo; load it again.")
        try:
            photo = confirmed(photo, request)
            when = parse_local(request.when) if request.when else None
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        if photo.taken_at is None:
            raise HTTPException(400, "When was the photo taken?")
        if request.topic and request.topic not in TOPICS:
            raise HTTPException(400, f"Unknown topic {request.topic!r}.")
        job = Job(uuid.uuid4().hex[:12])
        state.jobs[job.id] = job

        def work() -> None:
            def progress(message: str) -> None:
                job.put({"type": "progress", "message": message})

            try:
                _, run_dir = asyncio.run(
                    investigate_photo(photo, request.question, request.topic, when, None, state.store, progress)
                )
                job.put({"type": "investigated", "run": run_dir.name})
                if request.explain:
                    explain_run(run_dir, request.provider, state.store, progress)
                job.put({"type": "done", "run": run_dir.name})
            except Exception as error:  # report it on the page instead of failing silently
                job.put({"type": "error", "message": f"{type(error).__name__}: {error}"[:500]})

        threading.Thread(target=work, daemon=True).start()
        return {"job": job.id}

    @app.get("/api/jobs/{job_id}/events")
    def events(job_id: str) -> StreamingResponse:
        job = state.jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown job.")
        return StreamingResponse(job.stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/api/runs")
    def runs() -> list[dict[str, Any]]:
        folders = sorted((p for p in OUTPUT.iterdir() if (p / "result.json").is_file()), reverse=True) if OUTPUT.is_dir() else []
        listed = []
        for folder in folders[:40]:
            result = json.loads((folder / "result.json").read_text())
            listed.append({
                "name": folder.name,
                "question": result["question"],
                "topic": result["topic"],
                "taken_local": result["photo"].get("taken_local"),
                "explained": (folder / "explanation.json").is_file(),
            })
        return listed

    @app.get("/api/runs/{name}")
    def run(name: str) -> dict[str, Any]:
        folder = run_folder(name)
        result = json.loads((folder / "result.json").read_text())
        path = folder / "explanation.json"
        explanation = json.loads(path.read_text()) if path.is_file() else None
        for record in [*result["records"], *((explanation or {}).get("evidence") or {}).values()]:
            record["group"] = group(record)
        result.setdefault("topic_label", TOPICS[result["topic"]].label if result["topic"] in TOPICS else result["topic"])
        return {"name": name, "result": result, "explanation": explanation, "map": map_layers(result, explanation, state.store)}

    @app.get("/api/runs/{name}/files/{file}")
    def run_file(name: str, file: str) -> FileResponse:
        if file not in RUN_FILES:
            raise HTTPException(404, "Unknown file.")
        return FileResponse(run_folder(name) / file)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="do not open the page")
    args = parser.parse_args()
    load_env()
    import uvicorn

    url = f"http://127.0.0.1:{args.port}"
    print(f"City Investigator is running at {url} (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
