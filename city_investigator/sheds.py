"""Chain each building's shed permits to answer "how long has this shed been up?".

Under Local Law 48 of 2025, shed permits expire every 90 days, so one shed appears
as a chain of permits. Gaps up to 30 days are treated as paperwork delay. DOB does
not track whether a shed is physically standing, so a chain shows authorization.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from city_investigator.config import PERMIT_GAP_BRIDGE_DAYS
from city_investigator.evidence import Evidence, day


@dataclass
class ShedChain:
    key: str
    address: str | None
    bin: str | None
    bbl: str | None
    lat: float | None
    lon: float | None
    permits: list[Evidence]
    runs: list[tuple[datetime, datetime]]  # continuous periods after bridging short gaps
    gaps: list[tuple[datetime, datetime]]  # gaps longer than the bridge

    @property
    def up_since(self) -> datetime:
        return self.runs[-1][0]

    @property
    def expires(self) -> datetime:
        return self.runs[-1][1]

    def active(self, at: datetime) -> bool:
        return self.up_since <= at <= self.expires

    def days_up(self, at: datetime) -> int:
        return max(0, (min(at, self.expires) - self.up_since).days)

    def permits_in_current_run(self) -> list[Evidence]:
        return [permit for permit in self.permits if permit.start and permit.start >= self.up_since]

    def to_dict(self, at: datetime) -> dict[str, Any]:
        current = self.permits_in_current_run()
        return {
            "address": self.address,
            "bin": self.bin,
            "bbl": self.bbl,
            "lat": self.lat,
            "lon": self.lon,
            "up_since": day(self.up_since),
            "permit_valid_until": day(self.expires),
            "active": self.active(at),
            "days_up": self.days_up(at),
            "permits_in_current_run": len(current),
            "renewals": max(0, len(current) - 1),
            "gaps_over_bridge": [{"from": day(a), "to": day(b), "days": (b - a).days} for a, b in self.gaps],
            "evidence_ids": [permit.id for permit in self.permits],
        }


def chain_key(permit: Evidence) -> str | None:
    if permit.bin:
        return f"bin:{permit.bin}"
    if permit.bbl:
        return f"bbl:{permit.bbl}"
    if permit.address:
        return f"address:{permit.address.upper()}"
    return None


def build_chains(
    evidence: Iterable[Evidence],
    category: str = "shed_permit",
    bridge_days: int = PERMIT_GAP_BRIDGE_DAYS,
) -> list[ShedChain]:
    groups: dict[str, list[Evidence]] = defaultdict(list)
    for item in evidence:
        if item.category == category and item.start and item.end:
            key = chain_key(item)
            if key:
                groups[key].append(item)
    bridge = timedelta(days=bridge_days)
    chains = []
    for key, permits in groups.items():
        permits.sort(key=lambda permit: permit.start)  # type: ignore[arg-type,return-value]
        runs: list[tuple[datetime, datetime]] = []
        gaps: list[tuple[datetime, datetime]] = []
        run_start, run_end = permits[0].start, permits[0].end
        for permit in permits[1:]:
            assert permit.start and permit.end and run_start and run_end
            if permit.start <= run_end + bridge:
                run_end = max(run_end, permit.end)
            else:
                runs.append((run_start, run_end))
                gaps.append((run_end, permit.start))
                run_start, run_end = permit.start, permit.end
        assert run_start and run_end
        runs.append((run_start, run_end))
        located = next((p for p in reversed(permits) if p.lat is not None), permits[-1])
        chains.append(
            ShedChain(
                key=key,
                address=located.address or next((p.address for p in permits if p.address), None),
                bin=located.bin,
                bbl=located.bbl or next((p.bbl for p in permits if p.bbl), None),
                lat=located.lat,
                lon=located.lon,
                permits=permits,
                runs=runs,
                gaps=gaps,
            )
        )
    return chains
