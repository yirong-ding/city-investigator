"""Offline tests for the explanation step, using made-up data and a scripted stand-in for Muse Spark."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from test_data_layer import SHED, store  # noqa: F401  (store is a fixture)
from test_investigate import BOX_LINE, photo_at, sam_result

from city_investigator import explain as ex
from city_investigator import investigate as inv
from city_investigator import meta, times


@pytest.fixture
def sidewalk_result(store, tmp_path, monkeypatch):  # noqa: F811
    """A whole offline investigation of the made-up shed, as saved in result.json."""
    taken = times.local_day_start(datetime(2026, 2, 10).date())

    async def fake_sam(photo, topic, guard):
        return photo.jpeg, 0, [("scaffolding", sam_result(BOX_LINE)), ("construction fence", sam_result())]

    monkeypatch.setattr(inv, "load_input", lambda source: photo_at(*SHED, taken))
    monkeypatch.setattr(inv, "run_sam", fake_sam)
    monkeypatch.setattr(inv.Store, "load", classmethod(lambda cls: store))
    monkeypatch.setattr(inv, "OUTPUT", tmp_path / "out")
    monkeypatch.setattr(meta, "LEDGER", tmp_path / "spend.json")
    args = inv.argparse.Namespace(
        source="123", question="What records relate to this blocked sidewalk?", topic=None, lat=None, lon=None,
        taken=None, when=None, radius=None, yes=True, explain=False, provider="meta",
    )
    return json.loads(json.dumps(inv.asyncio.run(inv.investigate(args))))


def reply(content=None, tool_calls=None):
    def dump(exclude_none=True):
        calls = [{"id": c.id, "type": "function", "function": vars(c.function)} for c in tool_calls or []]
        return {"role": "assistant", "content": content, "tool_calls": calls}

    message = SimpleNamespace(content=content, tool_calls=tool_calls, model_dump=dump)
    usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=100)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def tool_call(name, **arguments):
    return SimpleNamespace(id=f"call_{name}", function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


class FakeMuse:
    """Plays back scripted replies and keeps every request."""

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request):
        self.requests.append(json.loads(json.dumps(request, default=str)))
        return self.replies.pop(0)


def claims(*items):
    return json.dumps({"claims": [{"text": text, "kind": kind, "evidence_ids": ids} for text, kind, ids in items]})


def test_evidence_list_gives_everything_an_id(sidewalk_result):
    known = ex.evidence_list(sidewalk_result)
    assert known["photo"]["type"] == "photo"
    assert known["photo:scaffolding"]["type"] == "photo"
    assert "can miss" in known["photo:not_seen:construction_fence"]["summary"]
    assert known["shed_history:3000001"]["type"] == "record"
    assert known["coverage:311_sidewalk_complaints"]["type"] == "coverage"
    flag = known["flag:permit_matches_structure"]
    assert flag["severity"] == "agreement" and set(flag["rests_on"]) <= set(known)
    text = ex.question_text(sidewalk_result, known)
    assert "What records relate" in text and "https://" not in text  # links stay out of the prompt


def test_claims_must_cite_existing_evidence_of_the_right_type(sidewalk_result):
    known = ex.evidence_list(sidewalk_result)
    permit = next(eid for eid, item in known.items() if item.get("summary", "").startswith("DOB permit"))

    def problems(kind, ids):
        return ex.claim_problems({"text": "x", "kind": kind, "evidence_ids": ids}, known)

    assert problems("observation", ["photo:scaffolding"]) == []
    assert problems("record", [permit]) == []
    assert problems("hypothesis", ["photo:scaffolding", permit]) == []
    assert problems("no_coverage", ["coverage:311_sidewalk_complaints"]) == []
    assert "does not exist" in problems("record", ["311:999"])[0]
    assert "only the photo" in problems("observation", ["photo", permit])[0]
    assert "may not cite the photo" in problems("record", [permit, "photo"])[0]
    assert "must cite coverage" in problems("no_coverage", [permit])[0]
    assert "cites no evidence" in problems("hypothesis", [])[0]
    assert "not one of" in problems("fact", [permit])[0]


def test_claims_are_read_through_code_fences():
    answer = "```json\n" + claims(("A.", "record", ["r1"])) + "\n```"
    assert ex.parse_claims(answer) == [{"text": "A.", "kind": "record", "evidence_ids": ["r1"]}]
    assert ex.parse_claims("no JSON here") is None


def test_explanation_uses_tools_drops_bad_claims_and_repairs(sidewalk_result, store):  # noqa: F811
    permit = next(r["id"] for r in sidewalk_result["records"] if r["category"] == "shed_permit")
    tool_coverage = "coverage:311_sidewalk_complaints@2025-01-01..2026-10-27"
    first = claims(
        ("Scaffolding covers the sidewalk.", "observation", ["photo:scaffolding"]),
        ("A shed permit was valid.", "record", [permit, "flag:permit_matches_structure"]),
        ("A complaint shows the shed.", "observation", ["311:1002"]),  # wrong label
        ("Another complaint was filed.", "record", ["311:999"]),  # made-up ID
    )
    flags = [f"flag:{flag['type']}" for flag in sidewalk_result["flags"]]
    fixed = claims(
        ("Scaffolding covers the sidewalk.", "observation", ["photo:scaffolding"]),
        ("A shed permit was valid, consistent with the photo.", "hypothesis", [permit, "photo:scaffolding", *flags]),
        ("One complaint about the shed was filed in 2026.", "record", ["311:1002", tool_coverage]),
    )
    muse = FakeMuse([
        reply(tool_calls=[tool_call("search_records", topic="sidewalk", start_date="2025-01-01",
                                    end_date="2026-10-27", radius_m=50)]),
        reply(content="A shed is up and permitted."),
        reply(content=first),
        reply(content=fixed),
    ])
    explanation = ex.explain(sidewalk_result, b"jpeg", "meta", client=muse, store=store)

    tools_request, _, schema_request, repair_request = muse.requests
    assert tools_request["tools"] and "response_format" not in tools_request
    assert tools_request["messages"][1]["content"][1]["type"] == "image_url"
    assert schema_request["response_format"]["json_schema"]["strict"] and "tools" not in schema_request
    assert "does not exist" in repair_request["messages"][-1]["content"]
    assert explanation["tool_calls"][0]["tool"] == "search_records"
    assert explanation["repairs"] == 1 and explanation["dropped"] == [] and explanation["warnings"] == []
    assert [claim["kind"] for claim in explanation["claims"]] == ["observation", "hypothesis", "record"]
    assert tool_coverage in explanation["evidence"]

    report = ex.render(explanation)
    assert "**OBSERVED** Scaffolding covers the sidewalk." in report
    assert "Flags (from rules, not the model)" in report and "CC BY-SA 4.0" in report


def test_a_worse_repair_is_not_used(sidewalk_result, store):  # noqa: F811
    flags = [f"flag:{flag['type']}" for flag in sidewalk_result["flags"]]
    good = claims(("Scaffolding is visible.", "observation", ["photo:scaffolding"]),
                  ("Records agree.", "hypothesis", ["photo:scaffolding", *flags]),
                  ("Made up.", "record", ["311:999"]))
    worse = claims(("Made up.", "record", ["311:999"]))
    muse = FakeMuse([reply(content="Done."), reply(content=good), reply(content=worse)])
    explanation = ex.explain(sidewalk_result, None, "open", client=muse, store=store)
    assert len(explanation["claims"]) == 2 and len(explanation["dropped"]) == 1
    assert explanation["model"] == "meta-models/muse-spark-open-1026"


def test_tools_look_up_buildings_and_records_without_owner_names(sidewalk_result, store):  # noqa: F811
    known = ex.evidence_list(sidewalk_result)
    tools = ex.Toolbox(sidewalk_result, known, store)
    building = tools.run("building_records", json.dumps({"building_id": "3000001"}))
    assert len(building["evidence"]) == 4 and all(item["id"] in known for item in building["evidence"])
    record = tools.run("get_record", json.dumps({"evidence_id": "311:1002"}))
    assert record["fields"]["unique_key"] == "1002"
    assert "error" in tools.run("get_record", json.dumps({"evidence_id": "311:999"}))
    assert "error" in tools.run("search_records", json.dumps({"topic": "noise"}))
    assert "error" in tools.run("no_such_tool", "{}")
    assert [call["tool"] for call in tools.calls][-1] == "no_such_tool"
