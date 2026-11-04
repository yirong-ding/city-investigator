"""After the answer: the proposals drawn into the photo by Muse Image, and drafts to send written by Muse Spark."""

from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_data_layer import CORNER, store  # noqa: F401  (store is a fixture)

from city_investigator import after_photo, draft, meta, web
from city_investigator.actions import ACTIONS

STREET_311 = next(f"action:{a.key}" for a in ACTIONS["flooding"] if a.key.startswith("311_street"))
FACTS = [
    {"text": "The photo shows water at the corner.", "kind": "observation", "evidence_ids": ["photo:water"]},
    {"text": "There were 83 street-flood reports on 64 days from 2010 to 2026.", "kind": "record", "evidence_ids": ["recurrence:street_flooding"]},
]
PROPOSALS = [
    {"text": "You could ask about rain gardens.", "kind": "proposal", "evidence_ids": ["action:green_infrastructure", "photo:water"]},
    {"text": "You could file a 311 report.", "kind": "proposal", "evidence_ids": [STREET_311, "recurrence:street_flooding"]},
    {"text": "A cloudburst basin was tried in Queens.", "kind": "proposal", "evidence_ids": ["idea:cloudburst", "photo:water"]},
]
EVIDENCE = {"recurrence:street_flooding": {"id": "recurrence:street_flooding", "type": "record",
                                           "summary": "83 street-flood reports on 64 days, 2010 to 2026"}}


def webp() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 4), (90, 140, 90)).save(out, "WEBP")
    return out.getvalue()


def make_run(folder, observations=(), proposals=PROPOSALS):
    folder.mkdir(parents=True)
    folder.joinpath("result.json").write_text(json.dumps({
        "topic": "flooding", "question": "Is flooding a recurring problem here?", "radius_m": 150, "flags": [],
        "records": [{"id": "311:1", "summary": "A complaint", "address": "4 AVENUE", "category": "street_flooding"}],
        "observations": list(observations), "not_seen": [], "coverage": [],
        "photo": {"location": {"lat": CORNER[0], "lon": CORNER[1], "uncertainty_m": 10}, "credit": "Photo by someone, Mapillary, CC BY-SA 4.0"},
    }))
    folder.joinpath("explanation.json").write_text(json.dumps({"claims": FACTS + list(proposals), "evidence": EVIDENCE}))
    buffer = io.BytesIO()
    Image.new("RGB", (8, 4)).save(buffer, "JPEG")
    folder.joinpath("photo.jpg").write_bytes(buffer.getvalue())
    return folder


class FakeImages:
    def __init__(self):
        self.calls = []

    def edit(self, **request):
        self.calls.append(request | {"image": request["image"].read()})
        return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(webp()).decode())])


class FakeChat:
    """Answers each call with the next of `answers`."""

    def __init__(self, *answers):
        self.answers, self.messages = list(answers), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, model, messages, response_format):
        self.messages.append(messages)
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=200)
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.answers.pop(0))))])


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(meta, "LEDGER", tmp_path / "spend.json")


def test_muse_image_draws_the_proposals_with_a_picture_and_keeps_the_water(tmp_path):
    run = make_run(tmp_path / "run")
    fake = SimpleNamespace(images=FakeImages())
    info = after_photo.draw_after(run, fake)
    assert info["draws"] == ["rain_gardens"]  # the 311 report and the idea have no picture
    sent = fake.images.calls[0]
    assert sent["model"] == "muse-image-1.0" and sent["image"] == run.joinpath("photo.jpg").read_bytes()  # the blurred photo
    assert "rain gardens" in sent["prompt"] and "any water on the street" in sent["prompt"]
    assert run.joinpath("after.webp").read_bytes()[8:12] == b"WEBP"
    assert "not evidence" in info["note"] and info["credit"].endswith("Photo by someone, Mapillary, CC BY-SA 4.0")
    assert json.loads(run.joinpath("after.json").read_text())["draws"] == ["rain_gardens"]


def test_no_shed_is_drawn_where_the_photo_shows_scaffolding(tmp_path):
    shed = {"text": "You could file a 311 report.", "kind": "proposal", "evidence_ids": ["action:311_debris_falling_or", "photo:water"]}
    result = {"observations": [{"category": "seen_scaffolding"}]}
    assert after_photo.drawable(result, {"claims": [shed]}) == []
    assert after_photo.drawable({"observations": []}, {"claims": [shed]}) == ["shed"]
    with pytest.raises(ValueError, match="no proposal|No proposal"):
        after_photo.draw_after(make_run(tmp_path / "run", [{"category": "seen_scaffolding"}], [shed]), SimpleNamespace(images=FakeImages()))


def test_a_draft_uses_only_numbers_from_the_checked_claims(tmp_path):
    run = make_run(tmp_path / "run")
    invented = {"subject": "Street Flooding (SJ)", "body": "There were 120 floods here.", "claims_used": [2]}
    fixed = {"subject": "Street Flooding (SJ)", "body": "There were 83 street-flood reports on 64 days. Please inspect.", "claims_used": [2]}
    fake = FakeChat(invented, fixed)
    saved = draft.write_draft(run, 3, fake)  # claim 3 is the 311 proposal
    assert saved["kind"] == "311" and saved["body"] == fixed["body"] and saved["problems"] == [] and saved["repairs"] == 1
    assert "120" in fake.messages[1][-1]["content"]  # the repair names the invented number
    assert saved["claims_used"] == [FACTS[1]["text"]]
    request = fake.messages[0][1]["content"]
    assert "1. [observation] The photo shows water" in request and "You could ask about rain gardens" not in request
    assert json.loads(run.joinpath("drafts.json").read_text())["3"]["body"] == fixed["body"]
    with pytest.raises(ValueError, match="idea from elsewhere"):
        draft.write_draft(run, 4, FakeChat())
    with pytest.raises(ValueError, match="not a proposal"):
        draft.write_draft(run, 0, FakeChat())


def test_a_draft_may_not_promise_a_result():
    problems = draft.draft_problems({"subject": "s", "body": "A rain garden will fix the flooding.", "claims_used": [1]}, 1, "")
    assert problems == ["the draft may ask for something, not promise a result"]
    assert draft.draft_problems({"subject": "s", "body": "Please look.", "claims_used": []}, 1, "")


def test_the_page_draws_the_photo_and_writes_drafts(store, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(web, "OUTPUT", tmp_path / "runs")
    monkeypatch.setattr("city_investigator.explain.OUTPUT", tmp_path / "runs")
    run = make_run(tmp_path / "runs" / "20261104-100000-1385498442151420")
    images = SimpleNamespace(images=FakeImages())
    monkeypatch.setattr(after_photo, "meta_client", lambda: images)
    chat = FakeChat({"subject": "Rain gardens", "body": "Could DEP look at this corner? [your name]", "claims_used": [1]})
    monkeypatch.setattr(draft, "chat_client", lambda provider: (chat, "muse-spark-1.3", "MUSE"))
    client = TestClient(web.create_app(web.State(store)))
    data = client.get(f"/api/runs/{run.name}").json()
    assert data["after_photo"] is None and data["after_photo_draws"] == ["rain_gardens"] and data["drafts"] == {}
    assert client.post(f"/api/runs/{run.name}/after-photo").json()["draws"] == ["rain_gardens"]
    assert client.get(f"/api/runs/{run.name}/files/after.webp").headers["content-type"] == "image/webp"
    assert client.post(f"/api/runs/{run.name}/drafts/2").json()["kind"] == "letter"
    data = client.get(f"/api/runs/{run.name}").json()
    assert data["after_photo"]["file"] == "after.webp" and data["drafts"]["2"]["subject"] == "Rain gardens"
    assert client.post(f"/api/runs/{run.name}/drafts/0").status_code == 400
    assert client.get("/api/demo").json()["flood"] == run.name
