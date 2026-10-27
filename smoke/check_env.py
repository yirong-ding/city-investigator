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


if __name__ == "__main__":
    main()
