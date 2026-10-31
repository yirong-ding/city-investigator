# City Investigator

**Snap a flooded corner or a years-old sidewalk shed, and City Investigator uncovers its story from city records, permits and flood sensors: how long it's been there, whether it keeps happening, and what nobody recorded.**

Built for the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026).

> **Status:** Day 5. Nine kinds of street problems, a web page that runs the whole investigation and streams each step, and an answer whose every claim links to its evidence on a map and a timeline. Findings so far are in [`smoke/FINDINGS.md`](smoke/FINDINGS.md).

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

NYC Open Data (311 service requests, PLUTO property data, Department of Buildings permits), FloodNet street flooding sensors (New York University and The City University of New York), hourly rain at the Central Park weather station, and the [NYC Stormwater Flood Maps](https://data.cityofnewyork.us/d/9i7c-xyvv) from the Mayor's Office of Climate and Environmental Justice. Sources are credited in the app.

[Building footprints](https://data.cityofnewyork.us/d/5zhs-2jue) give each building's roof height and the ground elevation it stands on. A flood investigation compares the ground at the pin with the buildings within 200 m: a spot lower than its blocks collects their runoff; one higher than them that still floods points to drains rather than terrain.

The flood maps are the **model** evidence: where the city's models expect rain to pond (4 in or deeper, over at least a quarter acre) in a moderate storm (2.13 in/hr), with today's sea levels and with 2050 sea levels. Checks compare them with what was recorded: flooding the model also expects, or flooding the model does not map.

City Investigator is a research aid, **not an official determination**. For life-threatening flooding call 911; to report a problem use 311.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
python -m pytest tests # offline checks, no key needed
```

Then run the [Day 1 smoke tests](smoke/README.md).

## Topics

Each topic says what SAM 3.1 looks for, which 311 complaints and agency records apply, and how far around the pin and how far back to search ([`topics.py`](city_investigator/topics.py), [`sources.py`](city_investigator/sources.py)). The 311 wording is the district's own, read from its complaints.

| Topic | SAM 3.1 looks for | Agency records |
|---|---|---|
| Flooding | water, puddle, storm drain | FloodNet sensors, rainfall, the city's stormwater flood model |
| Blocked sidewalk: sheds and scaffolding | scaffolding, construction fence, barrier | DOB shed, scaffold and fence permits, with how long each shed has stood |
| Street trees | tree, dead tree, broken branch, fallen tree | Parks tree inventory, inspections, work orders |
| Unsafe façades | scaffolding, safety netting | Façade inspection filings (Local Law 11), DOB shed permits |
| Broken sidewalks | cracked sidewalk, raised slab, tree roots | DOT sidewalk violations, sidewalk damage from street trees |
| Curb ramps and curbs | curb ramp, puddle, broken curb | DOT ramp survey (with ponding), ramp complaints |
| Potholes and road damage | pothole, cracked asphalt, manhole cover | DOT pothole work orders (closed) |
| Street construction | steel road plate, construction barrier, traffic cone | DOT street construction permits, street closures |
| Outdoor dining structures | outdoor dining structure, restaurant table, planter | Dining Out NYC licenses, Open Restaurants inspections |

Every topic gets the same checks: the problem seen and reported; seen but never reported; reported but not seen; an agency record that closed it out before the photo while the photo still shows it; and repeat reports. Topics add their own: a permit or license in force for the structure in the photo, an unsafe façade filing with or without a shed, the inventory tree nearest the camera, ponding recorded at a ramp. Each source carries a coverage note on what it cannot show (only buildings over six stories file façade inspections; only closed pothole work orders are published).

## Web page

```bash
python -m city_investigator.web   # opens http://127.0.0.1:8000
```

1. **Photo:** pick one of the three demos, type a Mapillary photo ID, or upload your own photo.
2. **Place and time:** drag the pin if it is off (or click the map when the photo has no location). The confirmed pin is what the records are matched to.
3. **Question:** ask, choose Muse Spark 1.3 or Muse Spark Open, and press Investigate.

Each step streams in as it happens: SAM 3.1 looking for each object, the records gathered, the checks, and every lookup Muse Spark makes. The map and timeline fill in as soon as the records are gathered; the answer follows. Hover a claim to light up the evidence it cites on the map and the timeline; click a citation to jump to it. The map shades the city's flood model around the pin, with today's and 2050 sea levels.

**3D:** the 3D button tilts the map toward the photo's compass heading and raises the buildings to their measured roof heights; the buildings the flags or the answer cite are orange. For flooding, the city model's water stands at its depth class and the nearby sensor's deepest measured flood is a column of that height, at true scale. **District overview** maps every place of the last batch run, colored by its worst flag. The **Valdrada 3D** view (and a link in the Photo tab) opens the spot in [Valdrada](https://github.com/mkturkcan/valdrada), a 3D city of New York built from public records (third-party, MIT license), at eye height and facing the photo's direction. It needs Valdrada running on this computer (its `BUILDING.md`: about 3.1 GB of city files, then `npm run dev` in `client/`); its online demo is a light edition of a few Manhattan places. Some of Valdrada's street details are generated, so it shows the place, not the evidence. Valdrada has rain but no flood water; `python -m city_investigator.valdrada_flood <Valdrada folder>` adds a small module to a local copy so that, for a flooding investigation, the city flood model's areas appear as water at their depth class over Valdrada's ground, with a marker pole of the nearby sensor's deepest reading. It draws the records, not a simulation of water. Valdrada's first load is slow (it compiles hundreds of shaders), so the page loads it once; with the module installed, opening another place or flood scenario moves the camera and swaps the records instead of loading the city again.

Saved investigations open from the list at the top without any API calls. The page runs on this computer only, with the same keys, snapshots and spend cap as the command line.

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

It ends with up to three **proposals: what could be done**. Each must cite one of the topic's real channels, listed in `city_investigator/actions.py` (a 311 report under the exact wording the city's own records use, Brooklyn Community Board 6, and for flooding DEP's Green Infrastructure Program), and the evidence it answers. Muse Spark is asked to fit a proposal to what was already tried: when the same complaint was closed again and again, raising it with the community board rather than filing it once more.

Code checks every claim before it is shown:

- A claim that cites an ID that does not exist is dropped.
- A label must fit what it cites: observations cite only the photo, records cite records or coverage notes and never the photo, no_coverage claims cite a coverage note. A claim that combines the photo and records must be labeled a hypothesis.
- Every flag, and every source with no coverage, must be mentioned.
- A proposal must cite a channel and the evidence it answers, may not promise a result ("will fix"), and there are at most three. No other claim may cite a channel.
- When Muse Spark says the photo shows something SAM 3.1 looked for and did not find (say, "street drains" when SAM found no catch basin), the disagreement is reported. Either model can be wrong, so the claim stays and the reader is told to check the photo.

When a check fails, Muse Spark gets one chance to fix its answer, and the better of the two answers is kept. Flags always come from the rules, never from the model. The run folder gets `explanation.md` and `explanation.json`, including the dropped claims and the tool calls.

## Data layer

```bash
python -m city_investigator.snapshot            # download Brooklyn Community District 6 records
python -m city_investigator.shortlist --photos  # candidate demo sites for every topic, with Mapillary photos
python -m city_investigator.shortlist --photos --topic trees --top 5  # one newer topic, with the command to investigate each site
python -m city_investigator.batch --limit 3  # investigate the shortlisted sites and add up the flags (data/derived/batch.md)
python -m city_investigator.lookup --lat 40.6787 --lon -73.9830 --start 2026-08-22 --end 2026-08-26 --topic flooding
```

- **Snapshot** saves 311 complaints (2020 on, plus flooding from the 2010s), DOB shed, scaffold and fence permits, FloodNet sensors and flood events, PLUTO property data, hourly rain at the Central Park weather station, and the stormwater flood map scenarios (clipped to the neighborhood) to `data/snapshots/`, each with its query and download time. Owner names are dropped. Run `--only NAME` to refresh one dataset, for example `--only stormwater`.
- **Lookup** returns the records near a point and time window (or for one building) and, for every source, a coverage note that separates "searched and found nothing" from "no data could exist here", such as a flood sensor installed after the storm in question.
- **Shortlist** ranks the longest-standing sheds (chaining 90-day permits and bridging gaps up to 30 days) and the most-flooded sensor corners, with Street View links for scouting by eye and nearby Mapillary photos the app can use with credit.

Never commit `.env`; it is listed in `.gitignore`.

## Prior work disclosure

Background research and planning were done before the hackathon in a separate private repository. All code in this repository is written during the event. Valdrada, linked from the page, is a separate open-source project by Mehmet Kerem Turkcan; none of its code is included here.

## License

[MIT](LICENSE)
