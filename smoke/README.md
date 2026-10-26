# Day 1 smoke tests

Small scripts that check every outside service works before the real build starts. Run them from the repository root after the [setup](../README.md#setup).

| Command | What it checks | Cost |
|---|---|---|
| `python -m smoke.check_env` | Which keys are set; which services this machine can reach | Free |
| `python -m smoke.nyc_data` | 311 problem types in Brooklyn Community Board 6, flood complaints per year in three districts, DOB NOW work types, FloodNet sensors and events in BK06 | Free |
| `python -m smoke.rainfall` | Hourly rain for the Aug 22–24, 2026 storm from a weather station (a record) and from Open-Meteo (a model) | Free |
| `python -m smoke.muse_spark photo.jpg` | Muse Spark with an image; plus tools; plus a strict JSON schema; then all three in one tool loop | 5 to 8 calls, a few cents (estimate) |
| `python -m smoke.sam photo.jpg` | Hosted SAM 3.1, one request per concept, with confidence scores and a mask overlay | 4 requests, about $0.01 (reported price) |
| `python -m pytest tests` | Spend cap, evidence-ID check, SAM parsing and overlay, photo rotation, all offline | Free |

## The photo

Any street photo works (JPEG, PNG, or HEIC from an iPhone). Before sending, the scripts rotate it upright, shrink it to 1,600 pixels on the long side, and re-encode it, which also removes all metadata, including GPS. For SAM, pick concepts that fit the photo:

```bash
python -m smoke.sam photo.jpg --concept "standing water" --concept "catch basin"
python -m smoke.sam photo.jpg --concept scaffolding --concept "construction fence"
```

## Spending cap

Every paid call goes through `SpendGuard` in `smoke/_common.py`. It refuses a call when the run's call cap or the daily dollar cap (`DAILY_SPEND_CAP_USD` in `.env`) is reached. Meta's own spend limit only sends an alert, so this is the hard stop. Spend is estimated from the prices in `.env` and kept in `.cache/spend.json`; your Billing page has the real figures.

## Results

Each script prints PASS or FAIL per check and writes details to `smoke/results/` (not committed). The SAM test also writes `smoke/results/sam_overlay.png`.

## If something fails

- **`unreachable (ProxyError)` or HTTP 403 on NYC Open Data:** the network blocks the service, or anonymous requests are throttled. Add `SOCRATA_APP_TOKEN`, or run on another network.
- **`MODEL_API_KEY is not set`:** copy `.env.example` to `.env` and add the key.
- **A Muse Spark step fails with HTTP 400:** that step's feature combination is not supported as sent. The error text says which; the later build works around it.
