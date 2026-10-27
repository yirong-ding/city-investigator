# City Investigator

**Snap a flooded corner or a years-old sidewalk shed, and City Investigator uncovers its story from city records, permits and flood sensors: how long it's been there, whether it keeps happening, and what nobody recorded.**

Built for the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026).

> **Status:** Day 4. One command runs a whole investigation in the terminal, and Muse Spark writes the labeled, cited explanation. The Day 1 and 2 findings, including the chosen demo sites, are in [`smoke/FINDINGS.md`](smoke/FINDINGS.md).

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
| Muse Spark Open | Open-weight option for the explanation (`--provider open`, on Baseten) |

## Data

NYC Open Data (311 service requests, PLUTO property data, Department of Buildings permits), FloodNet street flooding sensors (New York University and The City University of New York), hourly rain at the Central Park weather station, and the [NYC Stormwater Flood Maps](https://data.cityofnewyork.us/d/7r5q-vr7p). Sources are credited in the app.

The flood maps are the **model** evidence: where the city's models expect rain to pond (4 in or deeper, over at least a quarter acre) in a moderate storm today, a moderate storm with 2050 sea levels, and an extreme storm with 2080 sea levels. Checks compare them with what was recorded: flooding the model also expects, or flooding the model does not map.

City Investigator is a research aid, **not an official determination**. For life-threatening flooding call 911; to report a problem use 311.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
python -m pytest tests # offline checks, no key needed
```

Then run the [Day 1 smoke tests](smoke/README.md).

## Investigate

```bash
python -m city_investigator.investigate 1306991370360816 --question "What records relate to this blocked sidewalk?"
python -m city_investigator.investigate 1385498442151420 --question "Is flooding a recurring problem here?" --when 2026-08-23
python -m city_investigator.investigate my_photo.jpg --question "Is this flooding recurring?"
```

The source is a Mapillary photo ID or your own photo. The command confirms where and when the photo was taken, blurs faces and license plates (Mapillary photos arrive already blurred), finds what the question is about with SAM 3.1, gathers records and coverage notes for that place and time, and runs rule-based checks. Results go to `data/private/investigations/` (never committed): the blurred photo, an overlay, and `result.json`.

Checks raise typed flags: a permit that matches the structure in the photo, a structure with no permit, a permit with no visible structure, permit chain gaps, a sensor flood nobody reported, complaints the sensor did not see, water with no rain, complaints arriving hours after the sensor, and a photo taken at a different moment from the one asked about. Flooding questions also get a recurrence summary per source, with its definition.

## Explain

Add `--explain` to the investigate command, or explain a saved run:

```bash
python -m city_investigator.explain latest
python -m city_investigator.explain 1306991370360816         # the newest run of this photo
python -m city_investigator.explain latest --provider open   # Muse Spark Open on Baseten
```

Muse Spark gets the question, the blurred photo and every piece of evidence with an ID, then checks what matters with four tools:

- `check_photo`: asks SAM 3.1 to find something in the photo, so Muse Spark verifies what it thinks it sees (a drain, a sign, a ramp) before claiming it. At most 4 checks.
- `get_record`: every field of one record, such as what the city did about a complaint (`resolution_description`).
- `search_records`: any period around the confirmed pin.
- `building_records`: everything filed under one building.

It answers in short claims, each labeled observation, record, model, hypothesis or no_coverage and citing evidence IDs, including the IDs its tool calls returned. The report lists what it checked.

Code checks every claim before it is shown:

- A claim that cites an ID that does not exist is dropped.
- A label must fit what it cites: observations cite only the photo, records cite records or coverage notes and never the photo, no_coverage claims cite a coverage note. A claim that combines the photo and records must be labeled a hypothesis.
- Every flag, and every source with no coverage, must be mentioned.
- When Muse Spark says the photo shows something SAM 3.1 looked for and did not find (say, "street drains" when SAM found no catch basin), the disagreement is reported. Either model can be wrong, so the claim stays and the reader is told to check the photo.

When a check fails, Muse Spark gets one chance to fix its answer, and the better of the two answers is kept. Flags always come from the rules, never from the model. The run folder gets `explanation.md` and `explanation.json`, including the dropped claims and the tool calls.

## Data layer

```bash
python -m city_investigator.snapshot            # download Brooklyn Community District 6 records
python -m city_investigator.shortlist --photos  # candidate demo sites, with Mapillary photos
python -m city_investigator.lookup --lat 40.6787 --lon -73.9830 --start 2026-08-22 --end 2026-08-26 --topic flooding
```

- **Snapshot** saves 311 complaints (2020 on, plus flooding from the 2010s), DOB shed, scaffold and fence permits, FloodNet sensors and flood events, PLUTO property data, hourly rain at the Central Park weather station, and the three stormwater flood map scenarios (clipped to the neighborhood) to `data/snapshots/`, each with its query and download time. Owner names are dropped. Run `--only NAME` to refresh one dataset, for example `--only stormwater`.
- **Lookup** returns the records near a point and time window (or for one building) and, for every source, a coverage note that separates "searched and found nothing" from "no data could exist here", such as a flood sensor installed after the storm in question.
- **Shortlist** ranks the longest-standing sheds (chaining 90-day permits and bridging gaps up to 30 days) and the most-flooded sensor corners, with Street View links for scouting by eye and nearby Mapillary photos the app can use with credit.

Never commit `.env`; it is listed in `.gitignore`.

## Prior work disclosure

Background research and planning were done before the hackathon in a separate private repository. All code in this repository is written during the event.

## License

[MIT](LICENSE)
