"""Shared helpers for the Day 1 smoke tests.

The Meta clients, spend cap and photo preparation live in city_investigator.meta;
they are re-exported here so the smoke tests keep working.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from city_investigator.meta import (  # noqa: F401
    LEDGER,
    SpendCapError,
    SpendGuard,
    data_url,
    env_float,
    load_photo,
    meta_client,
    muse_cost,
    open_client,
)
from city_investigator.settings import ROOT, load_env  # noqa: F401

RESULTS = ROOT / "smoke" / "results"


def write_result(name: str, data: Any) -> Path:
    path = RESULTS / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
    return path
