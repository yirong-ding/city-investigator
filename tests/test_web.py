"""Offline tests for the web page's API, with made-up data and stand-ins for SAM 3.1 and Muse Spark."""

from __future__ import annotations

import io
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_data_layer import CORNER, SHED, store  # noqa: F401  (store is a fixture)
from test_investigate import BOX_LINE, photo_at, sam_result

from city_investigator import investigate as inv
from city_investigator import meta, times, web

QUESTION = "What records relate to this blocked sidewalk?"


@pytest.fixture
def client(store, tmp_path, monkeypatch):  # noqa: F811
    taken = times.local_day_start(datetime(2026, 2, 10).date())

    async def fake_sam(photo, topic, guard, progress=print):
        progress("SAM 3.1 is looking for scaffolding")
        return photo.jpeg, 0, [("scaffolding", sam_result(BOX_LINE)), ("construction fence", sam_result())]

    def fake_explain_run(run_dir, provider, store, progress):
        progress("Muse Spark reads record 311:1002")
        explanation = {
            "question": QUESTION, "provider": provider, "model": "test", "evidence": {}, "flags": [],
            "claims": [{"text": "Scaffolding is visible.", "kind": "observation", "evidence_ids": ["photo:scaffolding"]}],
            "dropped": [], "warnings": [], "models_disagree": [], "tool_calls": [], "repairs": 0,
            "photo_credit": None, "seconds": 1.0, "model_calls": 2, "estimated_cost_usd": 0.01,
        }
        (run_dir / "explanation.json").write_text(json.dumps(explanation))
        return explanation

    monkeypatch.setattr(inv, "run_sam", fake_sam)
    monkeypatch.setattr(inv, "OUTPUT", tmp_path / "runs")
    monkeypatch.setattr(web, "OUTPUT", tmp_path / "runs")
    monkeypatch.setattr(web, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(web, "explain_run", fake_explain_run)
    monkeypatch.setattr(web, "from_mapillary", lambda photo_id, token: photo_at(*SHED, taken))
    monkeypatch.setattr(meta, "LEDGER", tmp_path / "spend.json")
    monkeypatch.setenv("MAPILLARY_TOKEN", "test")
    return TestClient(web.create_app(web.State(store)))


def events_of(client, job):
    with client.stream("GET", f"/api/jobs/{job}/events") as stream:
        return [json.loads(line[6:]) for line in stream.iter_lines() if line.startswith("data: ")]


def jpeg_bytes(exif=None):
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 200, 200)).save(buffer, "JPEG", **({"exif": exif.tobytes()} if exif else {}))
    return buffer.getvalue()


def test_photo_to_answer_streams_every_step(client):
    assert "City Investigator" in client.get("/").text
    photo = client.post("/api/photos", data={"mapillary_id": "123"}).json()
    assert photo["lat"] == pytest.approx(SHED[0]) and photo["location_source"] == "mapillary"
    assert client.get(photo["preview"]).headers["content-type"] == "image/jpeg"

    job = client.post("/api/investigations", json={
        "photo": photo["photo"], "lat": SHED[0], "lon": SHED[1], "question": QUESTION,
    }).json()["job"]
    events = events_of(client, job)
    assert [event["n"] for event in events] == list(range(len(events)))
    assert events[-1]["type"] == "done" and "investigated" in [event["type"] for event in events]
    steps = [event["message"] for event in events if event["type"] == "progress"]
    assert steps[0] == "SAM 3.1 is looking for scaffolding" and "Muse Spark reads record 311:1002" in steps
    assert events_of(client, job) == events  # a page that reconnects gets the same steps again

    run = events[-1]["run"]
    assert [item["name"] for item in client.get("/api/runs").json()] == [run]
    data = client.get(f"/api/runs/{run}").json()
    assert data["explanation"]["claims"][0]["evidence_ids"] == ["photo:scaffolding"]
    assert {"permit", "complaint", "lot"} <= {f["properties"]["group"] for f in data["map"]["records"]["features"]}
    assert data["map"]["pin"]["radius_m"] == 50 and data["map"]["flood"]["features"] == []
    assert client.get(f"/api/runs/{run}/files/overlay.png").headers["content-type"] == "image/png"
    assert client.get(f"/api/runs/{run}/files/result.json").status_code == 404
    assert client.get("/api/runs/no-such-run").status_code == 404


def test_uploaded_photo_without_location_or_date_needs_both(client):
    photo = client.post("/api/photos", files={"file": ("my street.jpg", jpeg_bytes(), "image/jpeg")}).json()
    assert photo["lat"] is None and photo["taken_local"] is None
    request = {"photo": photo["photo"], "lat": SHED[0], "lon": SHED[1], "question": QUESTION}
    answer = client.post("/api/investigations", json=request)
    assert answer.status_code == 400 and "When was the photo taken" in answer.json()["detail"]
    job = client.post("/api/investigations", json=request | {"taken": "2026-02-10 09:30"}).json()["job"]
    events = events_of(client, job)
    assert events[-1]["type"] == "done"
    result = client.get(f"/api/runs/{events[-1]['run']}").json()["result"]
    assert result["photo"]["location"]["source"] == "user" and result["photo"]["taken_local"] == "2026-02-10 09:30"
    assert "my street" not in events[-1]["run"]  # the person's file name is not kept


def test_uploaded_photo_gps_is_read(client):
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (40.0, 40.0, 48.0), 3: "W", 4: (73.0, 59.0, 6.0)}
    photo = client.post("/api/photos", files={"file": ("phone.jpg", jpeg_bytes(exif), "image/jpeg")}).json()
    assert photo["lat"] == pytest.approx(40.68, abs=1e-4) and photo["location_source"] == "photo_gps"
    assert photo["street_view"].startswith("https://www.google.com/maps")
    refused = client.post("/api/photos", files={"file": ("notes.pdf", b"%PDF", "application/pdf")})
    assert refused.status_code == 400 and ".pdf" in refused.json()["detail"]
    assert client.post("/api/photos", data={"mapillary_id": "not a number"}).status_code == 400


def test_moving_the_pin_makes_it_the_record():
    photo = photo_at(*SHED, None)
    request = web.InvestigationRequest(photo="x", lat=SHED[0] + 0.0002, lon=SHED[1], question=QUESTION, taken="2026-02-10")
    moved = web.confirmed(photo, request)
    assert (moved.lat, moved.location_source, moved.uncertainty_m) == (SHED[0] + 0.0002, "user", inv.USER_UNCERTAINTY_M)
    assert moved.taken_at == inv.parse_local("2026-02-10") and photo.lat == SHED[0]  # the original is unchanged
    kept = web.confirmed(photo, request.model_copy(update={"lat": SHED[0]}))
    assert kept.location_source == "mapillary"


def test_a_failing_investigation_reports_why(client):
    photo = client.post("/api/photos", data={"mapillary_id": "123"}).json()
    job = client.post("/api/investigations", json={
        "photo": photo["photo"], "lat": SHED[0], "lon": SHED[1], "question": "What has changed here?",
    }).json()["job"]
    events = events_of(client, job)
    assert events[-1]["type"] == "error" and "Could not tell" in events[-1]["message"]
    assert client.post("/api/investigations", json={"photo": "gone", "lat": 0, "lon": 0, "question": "q"}).status_code == 404
    assert client.get("/api/jobs/unknown/events").status_code == 404


def test_flood_map_layers_show_the_model_and_skip_far_records(store):  # noqa: F811
    result = {
        "topic": "flooding", "radius_m": 150,
        "photo": {"location": {"lat": CORNER[0], "lon": CORNER[1], "uncertainty_m": 10}},
        "records": [
            {"id": "floodnet:s1:x", "kind": "record", "category": "flood_event", "summary": "event", "lat": CORNER[0],
             "lon": CORNER[1], "distance_m": 0, "start": {"local": "2026-08-23 07:32"}},
            {"id": "rain:NYC:x", "kind": "record", "category": "rainfall", "summary": "rain", "lat": 40.779,
             "lon": -73.9692, "distance_m": 11499},
            {"id": "stormwater:moderate_current", "kind": "model", "category": "modeled_flooding", "summary": "m",
             "lat": CORNER[0], "lon": CORNER[1], "distance_m": 0},
        ],
    }
    layers = web.map_layers(result, None, store)
    assert [f["properties"]["id"] for f in layers["records"]["features"]] == ["floodnet:s1:x"]
    flood = layers["flood"]["features"]
    assert {(f["properties"]["scenario"], f["properties"]["category"]) for f in flood} == {("moderate_current", 1), ("moderate_current", 2)}
    assert all(f["properties"]["id"] == "stormwater:moderate_current" for f in flood)
