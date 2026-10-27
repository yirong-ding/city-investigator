"""Meta Model API clients, the hard spend cap, and photo preparation."""

from __future__ import annotations

import base64
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from city_investigator.settings import ROOT

LEDGER = ROOT / ".cache" / "spend.json"


def env_float(name: str, default: float) -> float:
    return float(os.environ.get(name) or default)


class SpendCapError(RuntimeError):
    pass


class SpendGuard:
    """Hard stop for paid API calls.

    Meta's spend limit only sends an alert and does not stop billing, so every paid
    call goes through check() first. Costs are estimates from the per-token and
    per-image prices in .env; check the Billing page for actual charges.
    """

    def __init__(self, max_calls: int | None = None) -> None:
        self.max_calls = max_calls or int(os.environ.get("MAX_CALLS_PER_INVESTIGATION") or 60)
        self.daily_cap = env_float("DAILY_SPEND_CAP_USD", 5.0)
        self.calls = 0

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def spent_today(self) -> float:
        if not LEDGER.is_file():
            return 0.0
        return float(json.loads(LEDGER.read_text()).get(self._today(), 0.0))

    def check(self) -> None:
        if self.calls >= self.max_calls:
            raise SpendCapError(f"Call cap reached ({self.max_calls} calls this run).")
        spent = self.spent_today()
        if spent >= self.daily_cap:
            raise SpendCapError(
                f"Daily spend cap reached (${spent:.4f} of ${self.daily_cap:.2f}, UTC day)."
            )
        self.calls += 1

    def record(self, usd: float) -> None:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        ledger = json.loads(LEDGER.read_text()) if LEDGER.is_file() else {}
        ledger[self._today()] = round(ledger.get(self._today(), 0.0) + usd, 6)
        LEDGER.write_text(json.dumps(ledger, indent=2))


def muse_cost(usage: Any, prefix: str = "MUSE") -> float:
    """Estimated cost of one Chat Completions call; reasoning tokens bill as output.

    Prices come from {prefix}_INPUT_USD_PER_M and {prefix}_OUTPUT_USD_PER_M.
    """
    if usage is None:
        return 0.0
    input_price = env_float(f"{prefix}_INPUT_USD_PER_M", 1.25)
    output_price = env_float(f"{prefix}_OUTPUT_USD_PER_M", 4.25)
    return (usage.prompt_tokens * input_price + usage.completion_tokens * output_price) / 1e6


def meta_client(async_client: bool = False) -> Any:
    from openai import AsyncOpenAI, OpenAI

    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise SystemExit("MODEL_API_KEY is not set. Copy .env.example to .env and add your key.")
    base_url = os.environ.get("META_BASE_URL") or "https://api.meta.ai/v1"
    # The OpenAI SDK does not read MODEL_API_KEY on its own, so pass it explicitly.
    return (AsyncOpenAI if async_client else OpenAI)(base_url=base_url, api_key=key)


def open_client() -> Any:
    """Client for the open-weight Muse model on a partner (Baseten by default)."""
    from openai import OpenAI

    key = os.environ.get("OPEN_MODEL_API_KEY")
    if not key:
        raise SystemExit("OPEN_MODEL_API_KEY is not set. Add your Baseten key to .env.")
    base_url = os.environ.get("OPEN_MODEL_BASE_URL") or "https://inference.baseten.co/v1"
    return OpenAI(base_url=base_url, api_key=key)


def load_photo(path: Path, max_side: int = 1600) -> tuple[bytes, tuple[int, int]]:
    """Return the photo as JPEG bytes in display orientation, plus its size.

    SAM coordinates are in display orientation after EXIF rotation, so the photo is
    rotated here, once, for every later step. Re-encoding drops all metadata,
    including GPS. HEIC is converted because the API accepts JPEG, PNG, GIF and WebP.
    """
    from PIL import Image, ImageOps

    if path.suffix.lower() in {".heic", ".heif"}:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue(), image.size


def data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
