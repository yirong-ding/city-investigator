"""Day 1 smoke test: can Muse Spark take an image, tools and a strict JSON schema together?

Four requests on one photo, each adding one feature, so a failure points at the
feature that broke:

  1. image
  2. image + tools
  3. image + strict JSON schema
  4. image + tools + strict JSON schema (one tool loop, then a schema-valid answer)

Step 4 feeds back a fixed tool result that is labeled as a fixture, so it tests the
API mechanics, not real data. It also checks that every cited evidence ID exists.

Usage: python -m smoke.muse_spark path/to/street-photo.jpg
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from smoke._common import (
    SpendCapError,
    SpendGuard,
    data_url,
    load_env,
    load_photo,
    meta_client,
    muse_cost,
    write_result,
)

KINDS = ["observation", "record", "model", "hypothesis", "no_coverage"]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_311",
            "description": "Search NYC 311 complaints within a radius of a point and a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "radius_m": {"type": "number"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["lat", "lon", "radius_m", "start_date", "end_date"],
                "additionalProperties": False,
            },
        },
    }
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

FIXTURE_RECORD_ID = "fixture-311-1"
FIXTURE_RESULT = {
    "note": "Smoke-test fixture, not real data.",
    "records": [
        {
            "id": FIXTURE_RECORD_ID,
            "created_date": "2026-08-23T07:40:00",
            "complaint_type": "Sewer",
            "descriptor": "Street Flooding (SJ)",
            "distance_m": 42,
            "status": "Closed",
        }
    ],
    "coverage": {"dataset": "erm2-nwe9", "window": "2026-08-22 to 2026-08-26"},
}

QUESTION = (
    "This photo was taken near Carroll St and 4th Ave in Brooklyn (about 40.6787, -73.9830) "
    "on 2026-08-23. Is there flooding, and are there 311 complaints about it nearby?"
)


def validate_claims(text: str, known_ids: set[str]) -> list[str]:
    """Return problems with a claims answer; an empty list means it is valid."""
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as error:
        return [f"not JSON: {error}"]
    claims = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(claims, list) or not claims:
        return ["missing or empty 'claims' list"]
    problems = []
    for index, claim in enumerate(claims):
        if set(claim) != {"text", "kind", "evidence_ids"}:
            problems.append(f"claim {index}: unexpected keys {sorted(claim)}")
        if claim.get("kind") not in KINDS:
            problems.append(f"claim {index}: kind {claim.get('kind')!r} not allowed")
        unknown = set(claim.get("evidence_ids", [])) - known_ids
        if unknown:
            problems.append(f"claim {index}: cites unknown evidence {sorted(unknown)}")
    return problems


class Runner:
    def __init__(self, image_url: str) -> None:
        self.client = meta_client()
        self.model = os.environ.get("MUSE_MODEL") or "muse-spark-1.3"
        self.guard = SpendGuard(max_calls=10)
        self.image_part = {"type": "image_url", "image_url": {"url": image_url}}

    def call(self, messages: list[dict[str, Any]], **options: Any) -> Any:
        self.guard.check()
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, **options
        )
        self.guard.record(muse_cost(response.usage))
        return response

    def user_message(self, text: str) -> dict[str, Any]:
        # Images are accepted only in user messages.
        return {"role": "user", "content": [{"type": "text", "text": text}, self.image_part]}

    def step_image(self) -> dict[str, Any]:
        response = self.call([self.user_message("Describe the street in this photo in one sentence.")])
        content = response.choices[0].message.content
        return {"ok": bool(content), "answer": content}

    def step_tools(self) -> dict[str, Any]:
        response = self.call([self.user_message(QUESTION)], tools=TOOLS, tool_choice="auto")
        choice = response.choices[0]
        calls = choice.message.tool_calls or []
        arguments = [json.loads(call.function.arguments) for call in calls]
        return {
            "ok": choice.finish_reason == "tool_calls" and bool(arguments),
            "finish_reason": choice.finish_reason,
            "tool_arguments": arguments,
        }

    def step_schema(self) -> dict[str, Any]:
        prompt = (
            "List what you can see in this photo as claims of kind 'observation', "
            "each with evidence_ids ['photo']."
        )
        response = self.call([self.user_message(prompt)], response_format=CLAIMS_FORMAT)
        content = response.choices[0].message.content
        problems = validate_claims(content, {"photo"})
        return {"ok": not problems, "problems": problems, "answer": content}

    def step_all(self, max_turns: int = 4) -> dict[str, Any]:
        system = (
            "You investigate New York City streets. Label every claim: 'observation' for what "
            "the photo shows (evidence_ids ['photo']), 'record' for what a tool result states "
            "(cite its record id), 'hypothesis' for inferences. Cite only ids you were given."
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            self.user_message(QUESTION),
        ]
        tool_calls_made = 0
        for _ in range(max_turns):
            response = self.call(
                messages, tools=TOOLS, tool_choice="auto", response_format=CLAIMS_FORMAT
            )
            choice = response.choices[0]
            if choice.finish_reason != "tool_calls":
                content = choice.message.content
                problems = validate_claims(content, {"photo", FIXTURE_RECORD_ID})
                if tool_calls_made == 0:
                    problems.append("model answered without calling the tool")
                return {
                    "ok": not problems,
                    "tool_calls": tool_calls_made,
                    "problems": problems,
                    "answer": content,
                }
            # Append the full assistant message, then one tool message per call.
            messages.append(choice.message.model_dump(exclude_none=True))
            for call in choice.message.tool_calls:
                tool_calls_made += 1
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": json.dumps(FIXTURE_RESULT)}
                )
        return {"ok": False, "problems": [f"no final answer after {max_turns} turns"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("photo", type=Path)
    args = parser.parse_args()
    load_env()

    jpeg, size = load_photo(args.photo)
    runner = Runner(data_url(jpeg))
    steps = {
        "1 image": runner.step_image,
        "2 image + tools": runner.step_tools,
        "3 image + strict schema": runner.step_schema,
        "4 image + tools + strict schema": runner.step_all,
    }
    results: dict[str, Any] = {"model": runner.model, "photo_size": size, "steps": {}}
    for name, step in steps.items():
        started = time.monotonic()
        try:
            outcome = step()
        except SpendCapError as error:
            outcome = {"ok": False, "error": str(error)}
        except Exception as error:  # report every API failure and keep going
            status = getattr(error, "status_code", None)
            outcome = {"ok": False, "error": f"{type(error).__name__} {status or ''}: {error}"[:600]}
        outcome["seconds"] = round(time.monotonic() - started, 1)
        results["steps"][name] = outcome
        print(f"{'PASS' if outcome['ok'] else 'FAIL'}  {name}  ({outcome['seconds']}s)")
        for problem in outcome.get("problems", []):
            print(f"      - {problem}")
        if "error" in outcome:
            print(f"      - {outcome['error']}")
    results["spent_today_usd_estimate"] = round(runner.guard.spent_today(), 4)
    path = write_result("muse_spark", results)
    print(f"\nDetails: {path}  (estimated spend today: ${results['spent_today_usd_estimate']})")


if __name__ == "__main__":
    main()
