"""Write the explanation: Muse Spark turns one investigation into short, labeled, cited claims.

Muse Spark gets the question, the blurred photo and every piece of evidence the
investigation gathered, each with an ID. It calls tools to check what matters: SAM 3.1
to verify what it thinks it sees in the photo, and lookups in the local snapshots. It
answers in claims labeled observation, record, model, hypothesis or no_coverage, each
citing evidence IDs.

Code then checks every claim. A claim that cites an ID that does not exist, or whose
label does not fit what it cites (an "observation" that cites a 311 complaint), is
dropped, and Muse Spark gets one chance to fix the problems. Flags come from rules
(checks.py), never from the model; the answer is checked for leaving any out.

Usage:
  python -m city_investigator.explain latest
  python -m city_investigator.explain 1306991370360816   # the newest run of this photo
  python -m city_investigator.explain data/private/investigations/<run>
  python -m city_investigator.explain latest --provider open   # Muse Spark Open on Baseten
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from city_investigator import times
from city_investigator.config import DROPPED_FIELDS, RAIN_STATION
from city_investigator.evidence import Evidence
from city_investigator.investigate import MIN_CONFIDENCE, OUTPUT
from city_investigator.meta import (
    PROVIDERS,
    SpendCapError,
    SpendGuard,
    chat_client,
    data_url,
    env_float,
    meta_client,
    muse_cost,
)
from city_investigator.segment import segment, summarize
from city_investigator.settings import load_env
from city_investigator.store import Coverage, Hit, Store

KINDS = ["observation", "record", "model", "hypothesis", "no_coverage"]
LABELS = {
    "observation": "OBSERVED",
    "record": "RECORD",
    "model": "MODEL",
    "hypothesis": "INFERRED",
    "no_coverage": "NO COVERAGE",
}
# Each label must cite at least one piece of evidence of these types.
NEEDS = {
    "observation": {"photo"},
    "record": {"record", "coverage"},
    "model": {"model"},
    "hypothesis": {"photo", "record", "model", "coverage", "flag"},
    "no_coverage": {"coverage"},
}
MAX_TOOL_TURNS = 5
MAX_PHOTO_CHECKS = 4
MAX_REPAIRS = 1
MAX_RECORDS = 80
MAX_TOOL_ITEMS = 40
MAX_TOOL_RADIUS_M = 400
# Words for each SAM concept, to spot Muse Spark reporting something SAM 3.1 did not find.
CONCEPT_WORDS = {
    "water": ("water", "flooded"),
    "puddle": ("puddle",),
    "catch basin": ("catch basin", "drain", "sewer grate", "storm grate"),
    "storm drain": ("catch basin", "drain", "sewer grate", "storm grate"),
    "scaffolding": ("scaffold", "sidewalk shed"),
    "construction fence": ("fence",),
    "construction barrier": ("barrier", "barricade"),
}
NEGATION = r"\b(no|not|without|never|nor)\b[^.]{0,40}"

SYSTEM = """You explain what a street photo and public records show about one place in Brooklyn, New York, \
to a resident who asked a question. You get the photo (faces and license plates are blurred), an evidence \
list in which every item has an id, a type and a summary, and flags that rules raised when comparing the \
photo with the records.

Answer in short claims, one fact or inference each, in plain words a neighbor would use. Label each claim:
- observation: what the photo shows. Cite only photo ids. You may read signs, building numbers and \
storefront names yourself and cite "photo".
- record: what a record, a count of records or a coverage note states. Cite those ids, never photo ids.
- model: what a model estimate states. Cite model ids.
- hypothesis: an inference that connects or explains evidence. Say "may" or "likely". Cite every id it rests on.
- no_coverage: what the data cannot tell here, because a source does not cover this place or time or \
cannot see it. Cite the coverage id.

Rules:
- Cite only ids from the evidence list or from tool results. Never invent ids, dates, numbers or addresses.
- Start with one or two claims that answer the question directly.
- Mention every flag, citing its flag id together with the evidence behind it.
- A permit shows authorization, not that a structure is physically up. Complaints show that someone \
reported (anyone can file one, so do not say who), not how bad a problem was. A sensor measures one spot. A flood model shows where water is expected \
to pond in a design storm, not what happened on any day.
- If the photo was taken at a different time than the question asks about, it shows the place, not that moment.
- Say nothing about who owns or runs a building, and do not assign blame. Do not describe people in the photo.
- Use the local dates given. Write 6 to 12 claims.

Use the tools to check what matters before you answer:
- Before saying the photo shows something specific that matters to the answer (a drain, a sign, a ramp, \
a barrier), check it with check_photo and cite the id it returns. If SAM 3.1 does not find it, say so. \
Do not re-check what SAM 3.1 already looked for in the evidence list.
- Read the complaints and permits that matter with get_record: a complaint's resolution_description \
says what the city did about it.
- Use search_records or building_records when a longer period or a whole building's history would \
change the answer."""

REWRITE = (
    "Now write your answer as labeled claims in the required format: one claim per fact or inference, "
    "citing only ids from the evidence list or tool results."
)

CHECK_PHOTO_TOOL = {
    "type": "function",
    "function": {
        "name": "check_photo",
        "description": (
            "Ask SAM 3.1 to find something in the photo, to verify what you think you see. Returns a photo "
            f"evidence id with what it found. At most {MAX_PHOTO_CHECKS} checks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "concept": {"type": "string", "description": "a short noun phrase, such as 'storm drain' or 'street sign'"},
            },
            "required": ["concept"],
            "additionalProperties": False,
        },
    },
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_records",
            "description": (
                "Search the local snapshots for records around the confirmed location in any period. "
                "Returns evidence items with ids you may cite, and coverage notes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "enum": ["flooding", "sidewalk"]},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, New York time"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, New York time"},
                    "radius_m": {"type": "number", "description": f"meters, at most {MAX_TOOL_RADIUS_M}"},
                },
                "required": ["topic", "start_date", "end_date", "radius_m"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "building_records",
            "description": "All flooding and sidewalk records filed under one building, from any date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "building_id": {
                        "type": "string",
                        "description": "a 7-digit BIN or a 10-digit BBL from the evidence",
                    },
                },
                "required": ["building_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_record",
            "description": "Every field of one record, for details its summary leaves out (such as a permit's job description).",
            "parameters": {
                "type": "object",
                "properties": {"evidence_id": {"type": "string"}},
                "required": ["evidence_id"],
                "additionalProperties": False,
            },
        },
    },
]

CLAIMS_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "claims",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "claims": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "kind": {"type": "string", "enum": KINDS},
                            "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["text", "kind", "evidence_ids"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["claims"],
            "additionalProperties": False,
        },
    },
}


# The evidence list


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def unique(base: str, taken: dict[str, Any]) -> str:
    candidate, number = base, 2
    while candidate in taken:
        candidate, number = f"{base}:{number}", number + 1
    return candidate


def evidence_item(record: dict[str, Any]) -> dict[str, Any]:
    """The parts of an evidence dict the model needs, plus its link for the sources list."""
    item: dict[str, Any] = {"id": record["id"], "type": record["kind"], "summary": record["summary"]}
    if record.get("start"):
        item["date"] = record["start"]["local"]
    if record.get("end"):
        item["until"] = record["end"]["local"]
    for key in ("address", "distance_m", "bin", "bbl", "url"):
        if record.get(key) not in (None, ""):
            item[key] = record[key]
    return item


def not_seen_item(concept: str) -> dict[str, Any]:
    return {
        "id": f"photo:not_seen:{slug(concept)}",
        "type": "photo",
        "summary": (
            f"SAM 3.1 found no {concept} in the photo at confidence {MIN_CONFIDENCE} or above. "
            "Segmentation can miss objects."
        ),
    }


def for_model(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "url"}


def chain_summary(chain: dict[str, Any]) -> str:
    text = (
        f"Shed and scaffold permits at {chain['address'] or 'this building'}: permitted without a break since "
        f"{chain['up_since']}, valid until {chain['permit_valid_until']}, "
        f"{chain['permits_in_current_run']} permit(s) in a row"
    )
    if chain["gaps_over_bridge"]:
        text += "; paperwork gaps: " + ", ".join(
            f"{gap['from']} to {gap['to']} ({gap['days']} days)" for gap in chain["gaps_over_bridge"]
        )
    if chain["earlier_sheds"]:
        text += "; earlier sheds: " + ", ".join(f"{shed['from']} to {shed['to']}" for shed in chain["earlier_sheds"])
    return text + ". DOB tracks permits, not whether a shed is physically up."


def recurrence_items(rec: dict[str, Any], radius: float) -> list[dict[str, Any]]:
    def verdict(source: dict[str, Any]) -> str:
        return "recurring by the definition" if source["recurring"] else "not recurring by the definition"

    def span(source: dict[str, Any]) -> str:
        return f", {source['first']} to {source['last']}" if source.get("first") else ""

    sensor, street = rec["floodnet"], rec["street_flood_complaints"]
    indoor = rec["indoor_sewer_backup_complaints"]
    names = ", ".join(f"{s['name']} (installed {s['installed']})" for s in sensor["sensors"]) or "none"
    deepest = f", deepest {sensor['deepest_in']} in" if sensor["deepest_in"] is not None else ""
    return [
        {
            "id": "recurrence:floodnet",
            "type": "record",
            "summary": (
                f"FloodNet sensors within {radius:.0f} m: {names}. {sensor['events']} flood events on "
                f"{sensor['days']} days{span(sensor)}{deepest}: {verdict(sensor)}. {rec['definition']}"
            ),
        },
        {
            "id": "recurrence:street_flood_complaints",
            "type": "record",
            "summary": (
                f"311 street flooding, catch basin and manhole complaints within {radius:.0f} m, records from "
                f"{street['covers']}: {street['complaints']} on {street['days']} days{span(street)}: {verdict(street)}."
            ),
        },
        {
            "id": "recurrence:indoor_sewer_backups",
            "type": "record",
            "summary": (
                f"311 sewer backup complaints (usually inside buildings) within {radius:.0f} m: "
                f"{indoor['complaints']} on {indoor['days']} days."
            ),
        },
    ]


def evidence_list(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Everything the model may cite, by ID: the photo, records, summaries, coverage notes and flags."""
    known: dict[str, dict[str, Any]] = {}

    def add(item: dict[str, Any]) -> None:
        item["id"] = unique(item["id"], known)
        known[item["id"]] = item

    photo = result["photo"]
    add({
        "id": "photo",
        "type": "photo",
        "summary": f"The photo itself, taken {photo['taken_local']} New York time.",
        "url": photo.get("page_url") or "",
    })
    for observation in result["observations"]:
        add(evidence_item(observation) | {"type": "photo"})
    for concept in result["not_seen"]:
        add(not_seen_item(concept))
    for record in result["records"][:MAX_RECORDS]:
        add(evidence_item(record))
    for chain in result.get("shed_chains", []):
        add({
            "id": f"shed_history:{chain['bin'] or slug(chain['address'] or 'building')}",
            "type": "record",
            "summary": chain_summary(chain),
        })
    if "recurrence" in result:
        for item in recurrence_items(result["recurrence"], result["radius_m"]):
            add(item)
    if result.get("rain_in_24h_before") is not None:
        add({
            "id": "rain:24h_before",
            "type": "record",
            "summary": (
                f"Rain measured at the {RAIN_STATION['name']} in the 24 hours up to about "
                f"{result['question_moment']}: {result['rain_in_24h_before']:.2f} in."
            ),
        })
    for note in result["coverage"]:
        add({
            "id": f"coverage:{slug(note['source'])}",
            "type": "coverage",
            "state": note["state"],
            "summary": f"{note['source']}: {note['note']}",
        })
    for flag in result["flags"]:
        add({
            "id": f"flag:{flag['type']}",
            "type": "flag",
            "severity": flag["severity"],
            "summary": flag["message"],
            "rests_on": [eid for eid in flag["evidence_ids"] if eid in known],
        })
    return known


def question_text(result: dict[str, Any], known: dict[str, dict[str, Any]]) -> str:
    photo, location = result["photo"], result["photo"]["location"]
    lines = [
        f"Question: {result['question']}",
        (
            f"Topic: {result['topic']}. Confirmed location: {location['lat']:.6f}, {location['lon']:.6f}. "
            f"Records were searched within {result['radius_m']:.0f} m; distance_m is meters from this location."
        ),
        f"Photo taken {photo['taken_local']} New York time. The question is about {result['question_moment']}.",
    ]
    if len(result["records"]) > MAX_RECORDS:
        lines.append(
            f"Only the newest {MAX_RECORDS} of {len(result['records'])} records are listed; "
            "use search_records for the rest."
        )
    lines.append("Evidence:\n" + json.dumps([for_model(item) for item in known.values()], indent=1))
    return "\n".join(lines)


# Tools


async def _segment_once(jpeg: bytes, concept: str) -> Any:
    async with meta_client(async_client=True) as api:
        return await segment(api, data_url(jpeg), concept)


def segment_now(jpeg: bytes, concept: str) -> Any:
    """One SAM 3.1 request from synchronous code, even when called inside a running event loop."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _segment_once(jpeg, concept)).result()


def outcome(output: dict[str, Any]) -> str:
    """A few words on what a tool returned, for the report."""
    if output.get("error"):
        return output["error"]
    if "fields" in output:
        return f"read {len(output['fields'])} fields"
    if "evidence" in output:
        return f"{len(output['evidence'])} records, {len(output['coverage'])} coverage notes"
    return output.get("summary", "")


class Toolbox:
    """Tools Muse Spark may call: SAM 3.1 on the blurred photo, and lookups in the local snapshots."""

    def __init__(
        self,
        result: dict[str, Any],
        known: dict[str, dict[str, Any]],
        store: Store | None = None,
        jpeg: bytes | None = None,
        guard: SpendGuard | None = None,
        segmenter: Callable[[bytes, str], Any] | None = None,
    ) -> None:
        location = result["photo"]["location"]
        self.lat, self.lon = location["lat"], location["lon"]
        self.known = known
        self._store = store
        self._index: dict[str, Evidence] | None = None
        self.jpeg, self.guard, self.segmenter = jpeg, guard, segmenter or segment_now
        self.not_seen: list[str] = []
        self.photo_checks = 0
        self.calls: list[dict[str, Any]] = []

    @property
    def tools(self) -> list[dict[str, Any]]:
        return [CHECK_PHOTO_TOOL, *TOOLS] if self.jpeg else TOOLS

    @property
    def store(self) -> Store:
        if self._store is None:
            self._store = Store.load()
        return self._store

    def run(self, name: str, arguments: str) -> dict[str, Any]:
        handlers = {
            "check_photo": self.check_photo,
            "search_records": self.search_records,
            "building_records": self.building_records,
            "get_record": self.get_record,
        }
        try:
            args: Any = json.loads(arguments or "{}")
            output = handlers[name](**args)
        except (KeyError, TypeError, ValueError, SpendCapError) as error:
            args, output = arguments, {"error": f"Could not run {name}: {error}"}
        self.calls.append({"tool": name, "arguments": args, "outcome": outcome(output)})
        return output

    def remember(self, item: dict[str, Any]) -> dict[str, Any]:
        self.known.setdefault(item["id"], item)
        return for_model(item)

    def reply(self, hits: list[Hit], coverage: list[Coverage], suffix: str) -> dict[str, Any]:
        evidence = [self.remember(evidence_item(hit.evidence.to_dict(hit.distance_m))) for hit in hits[:MAX_TOOL_ITEMS]]
        notes = [
            self.remember({
                "id": unique(f"coverage:{slug(note.source)}@{suffix}", self.known),
                "type": "coverage",
                "state": note.state,
                "summary": f"{note.source}: {note.note}",
            })
            for note in coverage
        ]
        answer: dict[str, Any] = {"evidence": evidence, "coverage": notes}
        if len(hits) > MAX_TOOL_ITEMS:
            answer["not_shown"] = f"{len(hits) - MAX_TOOL_ITEMS} older items; narrow the dates to see them"
        return answer

    def check_photo(self, concept: str) -> dict[str, Any]:
        concept = " ".join(str(concept).split())[:60]
        if not self.jpeg or not concept:
            raise ValueError("needs a photo and a concept")
        if self.photo_checks >= MAX_PHOTO_CHECKS:
            raise ValueError(f"at most {MAX_PHOTO_CHECKS} photo checks per explanation")
        self.photo_checks += 1
        if self.guard:
            self.guard.check()
        try:
            found = self.segmenter(self.jpeg, concept)
        finally:
            if self.guard:
                self.guard.record(env_float("SAM_USD_PER_IMAGE", 0.0025))
        from PIL import Image

        size = Image.open(io.BytesIO(self.jpeg)).size
        boxes = [
            box for box in summarize(found, concept, size)["boxes"]
            if box["confidence"] is None or box["confidence"] >= MIN_CONFIDENCE
        ]
        if not boxes:
            self.not_seen.append(concept)
            item = not_seen_item(concept)
        else:
            best = max((box["confidence"] for box in boxes if box["confidence"] is not None), default=None)
            best_text = f", highest confidence {best:.2f}" if best is not None else ""
            item = {
                "id": f"photo:{slug(concept)}",
                "type": "photo",
                "summary": f"SAM 3.1 found {concept} in the photo: {len(boxes)} region(s){best_text}",
            }
        item["id"] = unique(item["id"], self.known)
        return self.remember(item)

    def search_records(self, topic: str, start_date: str, end_date: str, radius_m: float) -> dict[str, Any]:
        if topic not in ("flooding", "sidewalk"):
            raise ValueError(f"topic must be flooding or sidewalk, not {topic!r}")
        radius = min(float(radius_m), MAX_TOOL_RADIUS_M)
        start = times.local_day_start(date.fromisoformat(start_date))
        end = times.local_day_end(date.fromisoformat(end_date))
        found = self.store.near(self.lat, self.lon, radius, start, end, topic)
        return self.reply(found.hits, found.coverage, f"{start_date}..{end_date}") | {"radius_m": radius}

    def building_records(self, building_id: str) -> dict[str, Any]:
        digits = re.sub(r"\D", "", str(building_id))
        if len(digits) == 10:
            found = self.store.for_building(bbl=digits)
        elif len(digits) == 7:
            found = self.store.for_building(bin_=digits)
        else:
            raise ValueError("building_id must be a 7-digit BIN or a 10-digit BBL")
        return self.reply(found.hits, found.coverage, digits)

    def get_record(self, evidence_id: str) -> dict[str, Any]:
        if self._index is None:
            self._index = {item.id: item for item in self.store.evidence + self.store.lots}
        item = self._index.get(evidence_id)
        if item is None:
            return {"error": f"No record {evidence_id!r} in the snapshots. Totals and counts have no further fields."}
        fields = {key: value for key, value in item.raw.items() if value not in (None, "") and key not in DROPPED_FIELDS}
        return self.remember(evidence_item(item.to_dict())) | {"fields": fields}


# Checks


def parse_claims(text: str) -> list[Any] | None:
    """The claims list from an answer, tolerating text or code fences around the JSON."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    claims = data.get("claims") if isinstance(data, dict) else None
    return claims if isinstance(claims, list) else None


def claim_problems(claim: Any, known: dict[str, dict[str, Any]]) -> list[str]:
    """Why a claim cannot be shown; an empty list means it passes."""
    if not isinstance(claim, dict) or not str(claim.get("text") or "").strip():
        return ["has no text"]
    kind, ids = claim.get("kind"), claim.get("evidence_ids")
    if kind not in KINDS:
        return [f"label {kind!r} is not one of {', '.join(KINDS)}"]
    if not isinstance(ids, list) or not ids:
        return ["cites no evidence"]
    unknown = [str(eid) for eid in ids if str(eid) not in known]
    if unknown:
        return [f"cites evidence that does not exist: {unknown}"]
    types = {known[str(eid)]["type"] for eid in ids}
    problems = []
    if not types & NEEDS[kind]:
        problems.append(f"a {kind} claim must cite {' or '.join(sorted(NEEDS[kind]))} evidence")
    if kind == "observation" and types - {"photo"}:
        problems.append("an observation may cite only the photo; a claim that combines photo and records is a hypothesis")
    if kind == "record" and "photo" in types:
        problems.append("a record claim may not cite the photo; a claim that combines photo and records is a hypothesis")
    return problems


def check_claims(
    answer: str, known: dict[str, dict[str, Any]], required: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """(claims that pass, claims dropped with reasons, warnings about the answer as a whole)."""
    claims = parse_claims(answer)
    if claims is None:
        return [], [], [f"The answer was not a claims list; it starts {answer[:80]!r}."]
    kept, dropped = [], []
    for claim in claims:
        problems = claim_problems(claim, known)
        if problems:
            dropped.append({"claim": claim, "problems": problems})
        else:
            kept.append({
                "text": claim["text"].strip(),
                "kind": claim["kind"],
                "evidence_ids": [str(eid) for eid in claim["evidence_ids"]],
            })
    cited = {eid for claim in kept for eid in claim["evidence_ids"]}
    warnings = [f"No claim mentions {eid}." for eid in required if eid not in cited]
    if not kept:
        warnings.append("No claim passed the checks.")
    return kept, dropped, warnings


def vision_disagreements(claims: list[dict[str, Any]], not_seen: list[str]) -> list[str]:
    """Observations where Muse Spark reports something SAM 3.1 did not find. Either model can be wrong."""
    notes = []
    for claim in claims:
        sam_finds = [eid for eid in claim["evidence_ids"] if eid.startswith("photo:") and ":not_seen:" not in eid]
        if claim["kind"] != "observation" or sam_finds:
            continue  # only claims that rest on Muse Spark's own reading of the photo
        text = claim["text"].lower()
        for concept in not_seen:
            if f"photo:not_seen:{slug(concept)}" in claim["evidence_ids"]:
                continue  # the claim reports the absence
            for word in CONCEPT_WORDS.get(concept, (concept,)):
                pattern = rf"\b{re.escape(word)}"
                if re.search(pattern, text) and not re.search(NEGATION + pattern, text):
                    notes.append(
                        f'Muse Spark reads "{claim["text"]}", but SAM 3.1 found no {concept}. '
                        "One of the two models is wrong; check the photo."
                    )
                    break
    return notes


def repair_prompt(dropped: list[dict[str, Any]], warnings: list[str]) -> str:
    lines = ["The evidence checks found these problems:"]
    lines += [f"- Removed {json.dumps(item['claim'])}: {'; '.join(item['problems'])}" for item in dropped]
    lines += [f"- {warning}" for warning in warnings]
    lines.append(
        "Write the full list of claims again, fixing these problems and keeping the claims that passed. "
        "Cite only ids from the evidence list or tool results."
    )
    return "\n".join(lines)


# Muse Spark


def explain(
    result: dict[str, Any],
    jpeg: bytes | None,
    provider: str = "meta",
    client: Any = None,
    store: Store | None = None,
    segmenter: Callable[[bytes, str], Any] | None = None,
) -> dict[str, Any]:
    if client is None:
        client, model, price_prefix = chat_client(provider)
    else:
        _, model, price_prefix = PROVIDERS[provider]
    guard = SpendGuard(max_calls=MAX_TOOL_TURNS + 1 + MAX_REPAIRS + MAX_PHOTO_CHECKS)
    known = evidence_list(result)
    # Every flag, and every source with no coverage, should be mentioned.
    required = [eid for eid, item in known.items() if item["type"] == "flag" or item.get("state") == "no_coverage"]
    toolbox = Toolbox(result, known, store, jpeg, guard, segmenter)
    started = time.monotonic()
    cost = 0.0

    def call(messages: list[dict[str, Any]], **options: Any) -> Any:
        nonlocal cost
        guard.check()
        response = client.chat.completions.create(model=model, messages=messages, **options)
        spent = muse_cost(response.usage, price_prefix)
        cost += spent
        guard.record(spent)
        return response.choices[0].message

    content: list[dict[str, Any]] = [{"type": "text", "text": question_text(result, known)}]
    if jpeg:  # images are accepted only in user messages
        content.append({"type": "image_url", "image_url": {"url": data_url(jpeg)}})
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]

    # 1. Tools without the schema: Muse Spark Open ignores the schema when tools are in the request.
    for _ in range(MAX_TOOL_TURNS):
        message = call(messages, tools=toolbox.tools, tool_choice="auto")
        if not message.tool_calls:
            messages.append({"role": "assistant", "content": message.content or ""})
            break
        messages.append(message.model_dump(exclude_none=True))
        for tool_call in message.tool_calls:
            print(f"  Muse Spark looked up {tool_call.function.name} {tool_call.function.arguments}")
            output = toolbox.run(tool_call.function.name, tool_call.function.arguments)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(output, default=str)})

    # 2. The same answer as claims under the strict schema, in a call without tools.
    messages.append({"role": "user", "content": REWRITE})
    answer = call(messages, response_format=CLAIMS_FORMAT).content or ""
    kept, dropped, warnings = check_claims(answer, known, required)

    # 3. One chance to fix what the checks found.
    repairs = 0
    while (dropped or warnings) and repairs < MAX_REPAIRS:
        repairs += 1
        messages += [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": repair_prompt(dropped, warnings)},
        ]
        try:
            retry = call(messages, response_format=CLAIMS_FORMAT).content or ""
        except SpendCapError as error:
            warnings.append(f"Repair skipped: {error}")
            break
        retried = check_claims(retry, known, required)
        if (len(retried[1]) + len(retried[2]), -len(retried[0])) < (len(dropped) + len(warnings), -len(kept)):
            answer, (kept, dropped, warnings) = retry, retried

    cited = sorted({eid for claim in kept for eid in claim["evidence_ids"]})
    return {
        "question": result["question"],
        "provider": provider,
        "model": model,
        "claims": kept,
        "dropped": dropped,
        "warnings": warnings,
        "flags": result["flags"],
        "evidence": {eid: known[eid] for eid in cited},
        "models_disagree": vision_disagreements(kept, result["not_seen"] + toolbox.not_seen),
        "tool_calls": toolbox.calls,
        "repairs": repairs,
        "photo_credit": result["photo"].get("credit"),
        "seconds": round(time.monotonic() - started, 1),
        "model_calls": guard.calls,
        "estimated_cost_usd": round(cost, 4),
        "estimated_spend_today_usd": round(guard.spent_today(), 4),
    }


# Report and files


def claim_text(claim: Any) -> str:
    return str(claim.get("text") if isinstance(claim, dict) else claim)


def render(explanation: dict[str, Any]) -> str:
    lines = [
        f"# {explanation['question']}",
        "",
        f"Written by Muse Spark ({explanation['model']}). Every claim is labeled and checked against the evidence it cites.",
        "",
    ]
    lines += [
        f"- **{LABELS[claim['kind']]}** {claim['text']} `{', '.join(claim['evidence_ids'])}`"
        for claim in explanation["claims"]
    ]
    if explanation["flags"]:
        lines += ["", "## Flags (from rules, not the model)", ""]
        lines += [f"- **{flag['severity'].upper()}** {flag['message']}" for flag in explanation["flags"]]
    if explanation["models_disagree"]:
        lines += ["", "## Muse Spark and SAM 3.1 disagree", ""]
        lines += [f"- {note}" for note in explanation["models_disagree"]]
    if explanation["dropped"] or explanation["warnings"]:
        lines += ["", "## Removed or missing (evidence checks)", ""]
        lines += [f"- Removed: {claim_text(item['claim'])} ({'; '.join(item['problems'])})" for item in explanation["dropped"]]
        lines += [f"- {warning}" for warning in explanation["warnings"]]
    if explanation["tool_calls"]:
        lines += ["", "## What Muse Spark checked", ""]
        for call in explanation["tool_calls"]:
            args = call["arguments"]
            shown = ", ".join(f"{key}={value}" for key, value in args.items()) if isinstance(args, dict) else args
            lines.append(f"- {call['tool']}({shown}): {call['outcome']}")
    lines += ["", "## Sources", ""]
    for eid, item in explanation["evidence"].items():
        if item["type"] == "flag":  # listed above
            continue
        place = ", ".join(
            part for part in (item.get("address"), f"{item['distance_m']} m away" if item.get("distance_m") is not None else None) if part
        )
        link = f" {item['url']}" if item.get("url") else ""
        lines.append(f"- `{eid}`{f' ({place})' if place else ''}: {item['summary']}{link}")
    if explanation["photo_credit"]:
        lines += ["", f"Photo: {explanation['photo_credit']}"]
    kept, removed = len(explanation["claims"]), len(explanation["dropped"])
    lines += [
        "",
        f"Checks: {kept} of {kept + removed} claims passed, {explanation['repairs']} repair round(s), "
        f"{len(explanation['tool_calls'])} lookup(s), {explanation['model_calls']} model calls, "
        f"about ${explanation['estimated_cost_usd']:.3f}.",
    ]
    return "\n".join(lines) + "\n"


def find_run(target: str) -> Path:
    """'latest', a photo ID or file name (its newest run), or a run folder."""
    path = Path(target)
    if path.is_dir() or path.is_file():
        path = path.parent if path.is_file() else path
        if not (path / "result.json").is_file():
            raise SystemExit(f"No result.json in {path}.")
        return path
    runs = sorted(path for path in OUTPUT.iterdir() if (path / "result.json").is_file()) if OUTPUT.is_dir() else []
    if target != "latest":
        runs = [run for run in runs if run.name.endswith("-" + target.replace(".", "_"))]
    if not runs:
        raise SystemExit(f"No investigation of {target!r} in {OUTPUT}. Run city_investigator.investigate first.")
    return runs[-1]


def explain_run(run_dir: Path, provider: str = "meta", store: Store | None = None) -> dict[str, Any]:
    result = json.loads((run_dir / "result.json").read_text())
    photo = run_dir / "photo.jpg"
    print(f"\nAsking Muse Spark ({provider}) to explain {run_dir.name} ...")
    explanation = explain(result, photo.read_bytes() if photo.is_file() else None, provider, store=store)
    report = render(explanation)
    (run_dir / "explanation.json").write_text(json.dumps(explanation, indent=2))
    (run_dir / "explanation.md").write_text(report, encoding="utf-8")
    print("\n" + report)
    print(
        f"Saved to {run_dir / 'explanation.md'} ({explanation['seconds']}s; "
        f"estimated spend today ${explanation['estimated_spend_today_usd']:.2f})"
    )
    return explanation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="'latest', a photo ID or file name, or an investigation folder")
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDERS),
        default="meta",
        help="meta: Meta Model API; open: Muse Spark Open on Baseten",
    )
    args = parser.parse_args()
    load_env()
    try:
        explain_run(find_run(args.run), args.provider)
    except SpendCapError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
