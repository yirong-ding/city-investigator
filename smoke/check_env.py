"""Day 1 smoke test: which keys are set, and which services can this machine reach?

Usage: python -m smoke.check_env
"""

from __future__ import annotations

import os

import requests

from smoke._common import load_env

KEYS = {
    "MODEL_API_KEY": "required: Muse Spark and SAM 3.1",
    "OPEN_MODEL_API_KEY": "optional: Muse Spark Open on Baseten",
    "SOCRATA_APP_TOKEN": "recommended: avoids NYC Open Data throttling",
    "NYC_GEOCLIENT_KEY": "optional: GeoSearch works without a key",
    "MAPILLARY_TOKEN": "optional: street photos",
}

HOSTS = {
    "Meta Model API": "https://api.meta.ai/v1/models",
    "Baseten inference": "https://inference.baseten.co/v1/models",
    "NYC Open Data": "https://data.cityofnewyork.us/resource/aq7i-eu5q.json?$limit=1",
    "NYC GeoSearch": "https://geosearch.planninglabs.nyc/v2/search?text=Carroll%20St%20Brooklyn",
    "Iowa Environmental Mesonet": "https://mesonet.agron.iastate.edu/",
    "Open-Meteo archive": "https://archive-api.open-meteo.com/v1/archive",
    "Mapillary API": "https://graph.mapillary.com/",
}


def check_mapillary() -> str:
    """Try the token on a tiny Gowanus search; a Client Secret is rejected."""
    token = os.environ.get("MAPILLARY_TOKEN")
    if not token:
        return "no token set"
    try:
        response = requests.get(
            "https://graph.mapillary.com/images",
            params={"access_token": token, "fields": "id", "bbox": "-73.99,40.67,-73.98,40.68", "limit": 1},
            timeout=20,
        )
    except requests.RequestException as error:
        return f"unreachable ({type(error).__name__})"
    if response.ok:
        return "token works"
    return f"token rejected (HTTP {response.status_code}): copy the Client Token, not the Client Secret"


def main() -> None:
    load_env()
    print("Keys")
    for name, purpose in KEYS.items():
        state = "set" if os.environ.get(name) else "missing"
        print(f"  {name:20} {state:8} {purpose}")
    print("\nServices (any HTTP status means reachable; 401 is expected without a key)")
    for label, url in HOSTS.items():
        try:
            status = str(requests.get(url, timeout=15).status_code)
        except requests.RequestException as error:
            status = f"unreachable ({type(error).__name__})"
        print(f"  {label:28} {status}")
    print(f"\nMapillary token: {check_mapillary()}")


if __name__ == "__main__":
    main()
