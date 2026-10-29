"""The problems City Investigator looks into, each defined in one place.

A topic says which words in a question point to it, what SAM 3.1 looks for in the photo
(and which of those finds mean the problem is visible), how far around the pin and how
far back to search, and which categories of other topics' records also bear on it: a
dining structure or a construction dumpster also blocks a sidewalk. The 311 wording for
each topic is in config.COMPLAINTS; its agency records are in sources.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    noun: str  # for "311 {noun} complaints"
    example: str  # an example question
    words: tuple[str, ...]  # word starts that point to this topic in a question
    concepts: tuple[str, ...]  # what SAM 3.1 looks for
    problems: tuple[str, ...]  # the concepts whose presence means the problem is visible; none: the photo cannot show it
    radius_m: float
    lookback_days: int | None  # None: the topic gathers its records its own way
    related: frozenset[str] = field(default_factory=frozenset)


TOPICS: dict[str, Topic] = {
    topic.key: topic
    for topic in (
        Topic(
            "flooding", "Flooding", "flooding", "Is flooding a recurring problem here?",
            ("flood", "water", "rain", "drain", "puddle", "sewer", "catch basin", "storm", "ponding"),
            ("water", "puddle", "storm drain"), ("water", "puddle"), 150, None,
        ),
        Topic(
            "sidewalk", "Blocked sidewalk: sheds and scaffolding", "sidewalk",
            "What records relate to this blocked sidewalk?",
            ("sidewalk", "shed", "scaffold", "blocked", "obstruct", "walkway"),
            ("scaffolding", "construction fence", "construction barrier"),
            ("scaffolding", "construction fence", "construction barrier"), 50, None,
            frozenset({"dining_sidewalk_blocked", "construction_blocking", "construction_dumpster"}),
        ),
        Topic(
            "trees", "Street trees", "street tree", "Has this tree been reported before?",
            ("tree", "branch", "limb", "trunk", "root", "stump", "leaning"),
            ("tree", "dead tree", "broken branch", "fallen tree"), ("dead tree", "broken branch", "fallen tree"),
            30, 5 * 365,
        ),
        Topic(
            "facades", "Unsafe façades", "façade", "Is this building's façade unsafe?",
            ("facade", "façade", "falling", "debris", "brick", "cornice", "netting", "local law 11"),
            # Scaffolding and netting protect the public from a façade; they are not the problem itself.
            ("scaffolding", "safety netting"), (), 40, 10 * 365,
            frozenset({"shed_permit", "scaffold_permit", "shed_complaint"}),
        ),
        Topic(
            "sidewalk_damage", "Broken sidewalks", "sidewalk damage", "Has this broken sidewalk been reported?",
            ("broken sidewalk", "cracked", "uneven", "trip", "raised", "slab", "sidewalk damage", "pavement crack"),
            ("cracked sidewalk", "raised sidewalk slab", "tree roots"), ("cracked sidewalk", "raised sidewalk slab"),
            30, 10 * 365, frozenset({"tree_roots"}),
        ),
        Topic(
            "curb_ramps", "Curb ramps and curbs", "curb and ramp", "Is this curb ramp usable?",
            ("ramp", "curb", "wheelchair", "stroller", "accessib", "crossing"),
            ("curb ramp", "puddle", "broken curb"), ("puddle", "broken curb"), 25, 5 * 365,
        ),
        Topic(
            "potholes", "Potholes and road damage", "pothole and road", "Was this pothole ever fixed?",
            ("pothole", "road", "asphalt", "cave-in", "cave in", "street damage"),
            # Most streets show some cracked asphalt, so only a pothole counts as the problem.
            ("pothole", "cracked asphalt", "manhole cover"), ("pothole",), 40, 365,
        ),
        Topic(
            "street_construction", "Street construction", "street construction", "Is this street construction permitted?",
            ("construction", "road work", "roadwork", "steel plate", "plate", "street closed", "road closed", "closure", "excavat", "dig"),
            ("steel road plate", "construction barrier", "traffic cone"),
            ("steel road plate", "construction barrier", "traffic cone"), 75, 180,
        ),
        Topic(
            "outdoor_dining", "Outdoor dining structures", "outdoor dining", "Is this dining structure licensed?",
            ("dining", "restaurant", "outdoor seating", "cafe", "café", "roadway seating"),
            ("outdoor dining structure", "restaurant table", "planter"), ("outdoor dining structure", "restaurant table"),
            40, 2 * 365,
        ),
    )
}


def detect_topic(question: str) -> str | None:
    """The topic whose words the question uses most; None if no topic stands out.

    A phrase counts once per word, so "broken sidewalk" outweighs a bare "sidewalk".
    """
    text = question.lower()
    scores = {
        key: sum(len(word.split()) for word in topic.words if re.search(rf"\b{re.escape(word)}", text))
        for key, topic in TOPICS.items()
    }
    best = max(scores.values())
    leaders = [key for key, score in scores.items() if score == best]
    return leaders[0] if best and len(leaders) == 1 else None


def in_topic(topic: str, evidence_topic: str, category: str) -> bool:
    """Whether a record belongs to a topic, directly or as a related category."""
    return evidence_topic == topic or category in TOPICS[topic].related


def window(topic: str, when: datetime) -> tuple[datetime, datetime]:
    """The records an investigation of a moment looks at: the topic's lookback until a month after."""
    return when - timedelta(days=TOPICS[topic].lookback_days or 365), when + timedelta(days=30)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def problem_categories(topic: str) -> set[str]:
    """Observation categories that mean the topic's problem is visible."""
    return {f"seen_{slug(concept)}" for concept in TOPICS[topic].problems}
