"""How reports like a site's ended across the district: the outcomes of the same 311 complaints, from the snapshot.

311 keeps each complaint's closing date and the agency's resolution text. For a topic's complaint wordings (those
filed at the site first), this counts the district's reports, how many were closed, the median days to close, and
the most common outcomes, so a proposal can rest on what happened to reports like these rather than on a guess.
A precedent describes the district's reports, not the site's; a closed complaint is what the agency recorded,
not that the problem is gone.

`python -m city_investigator.precedents` prints each topic's precedents from the snapshot.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any

from city_investigator import times
from city_investigator.evidence import classify_complaint, outcome_text
from city_investigator.settings import SNAPSHOT_DIR
from city_investigator.topics import slug

DATASETS = ("311_2020_on", "311_2010s")
MAX_WORDINGS = 3  # precedents per run
TOP_OUTCOMES = 3
MIN_REPORTS = 5  # fewer reports than this say little about how such reports end


@dataclass(frozen=True)
class Precedent:
    complaint_type: str
    descriptor: str | None
    category: str
    reports: int
    closed: int
    median_days: float | None
    since: int | None  # the year of the earliest report
    outcomes: tuple[tuple[str, int], ...]

    @property
    def id(self) -> str:
        return "precedent:" + slug(self.descriptor or self.complaint_type)[:48]

    def item(self) -> dict[str, Any]:
        """The precedent as an evidence item the explanation can cite."""
        wording = self.complaint_type + (f" / {self.descriptor}" if self.descriptor else "")
        closed = f"{self.closed / self.reports:.0%} closed"
        if self.median_days is not None:
            closed += f", half of those within {self.median_days:.0f} day{'s' if round(self.median_days) != 1 else ''}"
        outcomes = "; ".join(f'"{text}" ({count / self.reports:.0%})' for text, count in self.outcomes)
        return {
            "id": self.id,
            "type": "precedent",
            "category": self.category,
            "summary": (
                f"Across Brooklyn Community District 6{f' since {self.since}' if self.since else ''}, {self.reports:,} 311 "
                f"reports of '{wording}': {closed}. Most common outcomes the agency recorded: {outcomes or 'none recorded'}. "
                "A closed report is what the agency recorded, not that the problem is gone."
            ),
        }


@lru_cache(maxsize=2)
def rows(snapshot_dir: Path) -> tuple[dict[str, Any], ...]:
    """The district's 311 complaints from the snapshot, those of the topics' wordings."""
    found = []
    for name in DATASETS:
        path = snapshot_dir / f"{name}.json"
        if path.is_file():
            found += json.loads(path.read_text())["rows"]
    return tuple(row for row in found if classify_complaint(row.get("complaint_type"), row.get("descriptor")))


def summarize(group: list[dict[str, Any]], complaint_type: str, descriptor: str | None, category: str) -> Precedent:
    days, years, outcomes = [], [], Counter()
    for row in group:
        created, closed = times.parse(row.get("created_date")), times.parse(row.get("closed_date"))
        if created:
            years.append(times.to_local(created).year)
        if created and closed and closed >= created:
            days.append((closed - created).total_seconds() / 86400)
        if text := outcome_text(row.get("resolution_description")):
            outcomes[re.sub(r"\d+", "#", text)] += 1  # dates and numbers vary within one outcome
    return Precedent(
        complaint_type, descriptor, category, len(group), len(days), median(days) if days else None,
        min(years) if years else None, tuple(outcomes.most_common(TOP_OUTCOMES)),
    )


def for_site(topic: str, site_categories: set[str], snapshot_dir: Path | None = None) -> list[Precedent]:
    """Precedents for a topic's complaint wordings: those filed at the site first, then the most reported."""
    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    categories: dict[tuple[str, str | None], str] = {}
    for row in rows(snapshot_dir or SNAPSHOT_DIR):
        found = classify_complaint(row.get("complaint_type"), row.get("descriptor"))
        if not found or found[0] != topic:
            continue
        key = (str(row.get("complaint_type")).strip(), (str(row.get("descriptor") or "").strip() or None))
        groups.setdefault(key, []).append(row)
        categories[key] = found[1]
    ranked = sorted(groups, key=lambda key: (categories[key] not in site_categories, -len(groups[key])))
    return [
        summarize(groups[key], key[0], key[1], categories[key])
        for key in ranked if len(groups[key]) >= MIN_REPORTS
    ][:MAX_WORDINGS]


def main() -> None:
    from city_investigator.topics import TOPICS

    for topic in TOPICS:
        print(f"\n{TOPICS[topic].label}")
        found = for_site(topic, set())
        for precedent in found:
            print(f"  {precedent.item()['summary']}")
        if not found:
            print(f"  no wording with {MIN_REPORTS} or more reports in the snapshot")


if __name__ == "__main__":
    main()
