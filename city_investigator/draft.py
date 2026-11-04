"""A ready-to-send draft of a proposal: the 311 report or the note to the community board, written by Muse Spark.

A proposal names a real channel (actions.py) and the evidence it answers. The draft turns it into text a resident
can paste and send themselves: the description for a 311 report, or a short email to the organization the proposal
names. Muse Spark writes it from the run's checked claims only, and the draft is checked like a claim: it must say
which claims it uses, every number in it must appear in those claims or their evidence, and it may not promise a
result. Nothing is sent from here; the resident reads it, edits it and sends it.

Usage:
  python -m city_investigator.draft latest 4      # the run, and the index of a proposal in its claims
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from city_investigator.actions import ACTIONS
from city_investigator.explain import PROMISE
from city_investigator.meta import PROVIDERS, SpendCapError, SpendGuard, chat_client, muse_cost

FILE = "drafts.json"
MAX_REPAIRS = 1
NUMBER = r"\d+(?:[.,:/-]\d+)*"

SYSTEM = """You write a short message that a resident of Brooklyn will read, edit and send themselves, through the \
channel a proposal names. You get the proposal, the channel, and numbered claims that were already checked against \
public records and a street photo.

Rules:
- Use only facts in the numbered claims. Every date, count and number you write must appear in them. Say in \
claims_used which claims you used.
- For a 311 report, write what a resident types into 311's description box: where, what the records and the photo \
show, and what they ask for. At most 120 words. The subject is the 311 complaint wording.
- For a letter, write a short, polite email: a subject line, then at most 180 words, ending with a clear ask and \
"[your name]" as the signature.
- Write in the first person, as the resident. Ask for an inspection, a review or an answer; do not promise or \
predict a result.
- Do not describe people, do not name owners or companies, do not assign blame, and no political framing.
- Say that the records were read with City Investigator only if it helps; never claim to be from the city.
"""

FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "draft",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "claims_used": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["subject", "body", "claims_used"],
            "additionalProperties": False,
        },
    },
}


def channel(proposal: dict[str, Any]) -> tuple[str, str] | None:
    """('311' or 'letter', what the channel is) for the proposal's action; None for an idea from elsewhere."""
    actions = {f"action:{action.key}": action for listed in ACTIONS.values() for action in listed}
    action = next((actions[eid] for eid in proposal.get("evidence_ids", []) if eid in actions), None)
    if action is None:
        return None
    return ("311" if action.key.startswith("311_") else "letter"), action.summary


def facts(explanation: dict[str, Any]) -> list[dict[str, Any]]:
    """The checked claims a draft may use: everything but the proposals, numbered from 1."""
    return [claim for claim in explanation["claims"] if claim["kind"] != "proposal"]


def source_text(claims: list[dict[str, Any]], explanation: dict[str, Any], proposal: dict[str, Any], summary: str) -> str:
    cited = {eid for claim in [*claims, proposal] for eid in claim["evidence_ids"]}
    evidence = [item.get("summary", "") + " " + (item.get("address") or "") for eid, item in explanation["evidence"].items() if eid in cited]
    return " ".join([*(claim["text"] for claim in claims), proposal["text"], summary, *evidence])


def numbers(text: str) -> set[str]:
    return {found.replace(",", "") for found in re.findall(NUMBER, text)}


def draft_problems(draft: Any, count: int, sources: str) -> list[str]:
    """Why a draft cannot be shown as it is; an empty list means it passes."""
    if not isinstance(draft, dict) or not str(draft.get("body") or "").strip():
        return ["the draft has no text"]
    used = draft.get("claims_used")
    if not isinstance(used, list) or not used:
        return ["the draft must say which claims it uses"]
    problems = []
    if [index for index in used if not isinstance(index, int) or not 1 <= index <= count]:
        problems.append(f"claims_used must be numbers from 1 to {count}")
    text = f"{draft.get('subject', '')} {draft['body']}"
    unknown = sorted(numbers(text) - numbers(sources))
    if unknown:
        problems.append(f"these numbers are in no checked claim or its evidence: {', '.join(unknown)}")
    if re.search(PROMISE, text, re.IGNORECASE):
        problems.append("the draft may ask for something, not promise a result")
    return problems


def request_text(result: dict[str, Any], claims: list[dict[str, Any]], proposal: dict[str, Any], kind: str, summary: str) -> str:
    places = sorted({item["address"] for item in result["records"] if item.get("address")})[:3]
    location = result["photo"]["location"]
    lines = [
        f"Proposal: {proposal['text']}",
        f"Channel ({'a 311 report' if kind == '311' else 'a letter'}): {summary}",
        f"Where: the photo was taken at {location['lat']:.5f}, {location['lon']:.5f}"
        + (f"; nearby addresses in the records: {'; '.join(places)}" if places else ""),
        f"The resident's question: {result['question']}",
        "Checked claims:",
        *(f"{n}. [{claim['kind']}] {claim['text']}" for n, claim in enumerate(claims, 1)),
    ]
    return "\n".join(lines)


def write_draft(run_dir: Path, index: int, client: Any = None, provider: str = "meta") -> dict[str, Any]:
    """Write the draft of the proposal at `index` in the run's claims; save it in drafts.json and return it."""
    result = json.loads((run_dir / "result.json").read_text())
    explanation = json.loads((run_dir / "explanation.json").read_text())
    claims_all = explanation["claims"]
    if not 0 <= index < len(claims_all) or claims_all[index]["kind"] != "proposal":
        raise ValueError(f"Claim {index} of this run is not a proposal.")
    proposal = claims_all[index]
    found = channel(proposal)
    if found is None:
        raise ValueError("This proposal is an idea from elsewhere, not a channel a resident can use yet.")
    kind, summary = found
    claims = facts(explanation)
    sources = source_text(claims, explanation, proposal, summary)
    if client is None:
        client, model, prefix = chat_client(provider)
    else:
        _, model, prefix = PROVIDERS[provider]
    guard = SpendGuard(max_calls=1 + MAX_REPAIRS)
    started, cost = time.monotonic(), 0.0

    def call(messages: list[dict[str, Any]]) -> str:
        nonlocal cost
        guard.check()
        response = client.chat.completions.create(model=model, messages=messages, response_format=FORMAT)
        spent = muse_cost(response.usage, prefix)
        cost += spent
        guard.record(spent)
        return response.choices[0].message.content or ""

    def parse(text: str) -> Any:
        try:
            return json.loads(text[text.find("{"): text.rfind("}") + 1])
        except ValueError:
            return None

    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": request_text(result, claims, proposal, kind, summary)}]
    answer = call(messages)
    draft = parse(answer)
    problems = draft_problems(draft, len(claims), sources)
    repairs = 0
    while problems and repairs < MAX_REPAIRS:
        repairs += 1
        messages += [{"role": "assistant", "content": answer},
                     {"role": "user", "content": "The checks found: " + "; ".join(problems) + ". Write the draft again, fixing them."}]
        try:
            retry = call(messages)
        except SpendCapError as error:
            problems.append(f"repair skipped: {error}")
            break
        retried = parse(retry)
        retried_problems = draft_problems(retried, len(claims), sources)
        if len(retried_problems) <= len(problems):
            answer, draft, problems = retry, retried, retried_problems
    if not isinstance(draft, dict):
        raise ValueError("Muse Spark did not write a draft; try again.")
    used = [n for n in draft.get("claims_used", []) if isinstance(n, int) and 1 <= n <= len(claims)]
    saved = {
        "proposal": index,
        "kind": kind,
        "channel": summary,
        "subject": str(draft.get("subject") or "").strip(),
        "body": str(draft.get("body") or "").strip(),
        "claims_used": [claims[n - 1]["text"] for n in used],
        "problems": problems,
        "model": model,
        "repairs": repairs,
        "seconds": round(time.monotonic() - started, 1),
        "estimated_cost_usd": round(cost, 4),
    }
    path = run_dir / FILE
    drafts = json.loads(path.read_text()) if path.is_file() else {}
    drafts[str(index)] = saved
    path.write_text(json.dumps(drafts, indent=2))
    return saved


def main() -> None:
    from city_investigator.explain import find_run
    from city_investigator.settings import load_env

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="'latest', a photo ID or file name, or an investigation folder")
    parser.add_argument("proposal", type=int, help="the index of a proposal in the run's claims")
    args = parser.parse_args()
    load_env()
    draft = write_draft(find_run(args.run), args.proposal)
    print(f"{draft['subject']}\n\n{draft['body']}\n")
    for problem in draft["problems"]:
        print(f"CHECK: {problem}")


if __name__ == "__main__":
    main()
