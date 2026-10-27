"""Read NYC Open Data (Socrata) with paging, an app token, and retries."""

from __future__ import annotations

import os
import time
from typing import Any

import requests

BASE = "https://data.cityofnewyork.us/resource"
PAGE_SIZE = 50_000


class SocrataError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def record_url(dataset: str, **filters: str) -> str:
    """A link that returns exactly the cited record(s)."""
    request = requests.Request("GET", f"{BASE}/{dataset}.json", params=filters).prepare()
    return str(request.url)


class Socrata:
    def __init__(
        self,
        token: str | None = None,
        session: requests.Session | None = None,
        pause_s: float = 1.0,
    ) -> None:
        self.session = session or requests.Session()
        token = token if token is not None else os.environ.get("SOCRATA_APP_TOKEN")
        if token:
            self.session.headers["X-App-Token"] = token
        self.pause_s = pause_s

    def get(self, dataset: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        retries = {403: 1, 429: 3, 500: 3, 502: 3, 503: 3, 504: 3}
        attempt = 0
        while True:
            response = self.session.get(f"{BASE}/{dataset}.json", params=params, timeout=120)
            if response.status_code == 200:
                return response.json()
            status = response.status_code
            if attempt < retries.get(status, 0):
                attempt += 1
                # Anonymous throttling shows up as 403 and needs a longer wait.
                time.sleep(self.pause_s * (30 if status == 403 else 2**attempt))
                continue
            hint = " (throttled: add SOCRATA_APP_TOKEN, or the network blocks the site)" if status == 403 else ""
            raise SocrataError(f"{dataset}: HTTP {status}{hint}: {response.text[:300]}", status)

    def rows(self, dataset: str, where: str, max_rows: int = 2_000_000) -> list[dict[str, Any]]:
        """Every row matching a SoQL where clause, in pages, in a stable order."""
        rows: list[dict[str, Any]] = []
        offset = 0
        while len(rows) < max_rows:
            page = self.get(
                dataset,
                {"$where": where, "$order": ":id", "$limit": PAGE_SIZE, "$offset": offset},
            )
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                break
            offset += PAGE_SIZE
        return rows
