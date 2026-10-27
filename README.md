# City Investigator

**Snap a flooded corner or a years-old sidewalk shed, and City Investigator uncovers its story from city records, permits and flood sensors: how long it's been there, whether it keeps happening, and what nobody recorded.**

Built for the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026).

> **Status:** Day 2. The data layer is in [`city_investigator/`](city_investigator/); the Day 1 smoke tests and findings are in [`smoke/`](smoke/README.md).

## What it does

1. You upload a street photo in New York City (or pick a block on the map) and confirm where it was taken.
2. You ask a question, such as *"Is this flooding a recurring problem?"* or *"How long has this sidewalk shed been up?"*
3. An agent segments the photo, looks up nearby public records by place and time, and checks them against each other.
4. You get a map, an evidence timeline, and a short explanation in which every claim is labeled:
   - **Observed** in your photo
   - **Recorded** in a public record, with a link
   - **Modeled** by a city flood map
   - **Inferred** by the agent, with the evidence it rests on
   - **No coverage** where no dataset could have seen anything

Conflicts between sources and gaps in the records are flagged, not smoothed over.

## Meta models

| Model | Role |
|---|---|
| Muse Spark | Plans the investigation and writes the explanation |
| SAM 3.1 | Segments the photo (water, scaffolding, curbs, catch basins) |
| Muse Voice Transcribe | Spoken questions (planned) |
| Muse Spark Open | Open-weight option for the agent (planned) |

## Data

NYC Open Data (311 service requests, PLUTO property data, Department of Buildings permits), FloodNet street flooding sensors (New York University and The City University of New York), and city stormwater flood maps. Sources are credited in the app.

City Investigator is a research aid, **not an official determination**. For life-threatening flooding call 911; to report a problem use 311.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
python -m pytest tests # offline checks, no key needed
```

Then run the [Day 1 smoke tests](smoke/README.md).

## Data layer

```bash
python -m city_investigator.snapshot            # download Brooklyn Community District 6 records
python -m city_investigator.shortlist --photos  # candidate demo sites, with Mapillary photos
python -m city_investigator.lookup --lat 40.6787 --lon -73.9830 --start 2026-08-22 --end 2026-08-26 --topic flooding
```

- **Snapshot** saves 311 complaints (2020 on, plus flooding from the 2010s), DOB shed, scaffold and fence permits, FloodNet sensors and flood events, PLUTO property data, and hourly rain at the Central Park weather station to `data/snapshots/`, each with its query and download time. Owner names are dropped. Run `--only NAME` to refresh one dataset.
- **Lookup** returns the records near a point and time window (or for one building) and, for every source, a coverage note that separates "searched and found nothing" from "no data could exist here", such as a flood sensor installed after the storm in question.
- **Shortlist** ranks the longest-standing sheds (chaining 90-day permits and bridging gaps up to 30 days) and the most-flooded sensor corners, with Street View links for scouting by eye and nearby Mapillary photos the app can use with credit.

Never commit `.env`; it is listed in `.gitignore`.

## Prior work disclosure

Background research and planning were done before the hackathon in a separate private repository. All code in this repository is written during the event.

## License

[MIT](LICENSE)
