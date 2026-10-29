# Day 1 findings

Results from running the smoke tests on Oct 27, 2026. Counts come straight from the script output.

## Models

| Test | Muse Spark 1.3 (Meta Model API) | Muse Spark Open (Baseten) |
|---|---|---|
| 0 text only | PASS, 1.2 s | PASS, 1.2 s |
| 1 image | PASS, 3.5 s | PASS, 9.0 s |
| 2 image + tools | PASS, 2.9 s | PASS, 9.0 s |
| 3 image + strict schema | PASS, 4.1 s | PASS, 9.7 s |
| 4 image + tools + strict schema | PASS, 8.1 s | **FAIL**: final answer was not JSON (22.9 s) |
| 5 text + tools + strict schema | PASS, 6.9 s | **FAIL**: final answer was not JSON (6.6 s) |
| 6 image + tools, then strict schema in a separate call | not run | **PASS**, 29.9 s (after keeping the text answer and asking for a rewrite) |

- **Muse Spark 1.3 does everything in one request.** It is the main path.
- **Muse Spark Open takes images, tools and the schema, but ignores the schema when tools are in the same request.** Steps 4 and 5 returned a good plain-text answer instead of JSON.
- **Workaround that passes (step 6):** run the tool loop, keep the model's text answer, then ask in a separate call without tools for that answer rewritten as claims. The first version, which dropped the text answer, returned an empty claims list.
- **Speed:** the open model is 2 to 3 times slower (about 30 s for step 6, versus about 8 s for Muse Spark 1.3 doing it in one request).

**Decision:** the agent uses the split pattern for both providers, so the model is one setting. Muse Spark Open qualifies the project for the open-weights prize; hosted Muse Spark 1.3 is the faster fallback.

**SAM 3.1 (hosted)** works with confidence scores: on the test photo it found 3 cars (0.84, 0.63, 0.56) and returned valid empty results for standing water, scaffolding and catch basin. No box fell outside the photo, so orientation handling is right.

Estimated spend for all of Day 1: about $0.11.

## 311 problem types (Brooklyn Community Board 6, since Jan 1, 2024)

Strings must match exactly, including the city's own typos.

| Use | `complaint_type` | `descriptor` | Count |
|---|---|---|---|
| Sidewalk shed | General Construction/Plumbing | Sidewalk Shed/Pipe Scafford - Inadequate Defective/None | 300 |
| Construction blocking | Sidewalk Condition | Blocked - Construction | 423 |
| Construction blocking | Street Condition | Blocked - Construction | 535 |
| Sidewalk condition | Sidewalk Condition | Broken Sidewalk / Sidewalk Violation / Sidewalk Collapsed | 984 / 664 / 52 |
| Other obstructions | Obstruction | Cone / Trash or Recycling / Sign / Merchandise | 256 / 225 / 64 / 59 |
| Other obstructions | Dumpster Complaint | Blocking Sidewalk or Street | 89 |
| Other obstructions | Outdoor Dining | Sidewalk Zone Blocked | 106 |
| Parked cars (filter out for sheds) | Illegal Parking | Blocked Sidewalk | 14,941 |
| Curbs | Curb Condition | Broken Curb | 1,447 |
| Flooding | Sewer | Street Flooding (SJ) | 122 |
| Flooding | Sewer | Catch Basin Clogged/Flooding (Use Comments) (SC) | 243 |
| Flooding (indoor) | Sewer | Sewer Backup (Use Comments) (SA) | 232 |
| Flooding | Sewer | Manhole Overflow (Use Comments) (SA1) | 89 |
| Flooding | Sewer Maintenance | Catch Basin Clogged / Backup | 65 / 63 |

`Sewer Backup (SA)` is now confirmed. `Sewer Maintenance` is a second complaint type for drainage problems, so flood searches must include it as well as `Sewer`.

## 311 flood complaints since 2020 (complaint type `Sewer` only)

| District | Catch basin | Sewer backup | Street flooding |
|---|---|---|---|
| 06 BROOKLYN | 568 | 1,187 | 327 |
| 12 QUEENS | 1,987 | 6,659 | 917 |
| 13 QUEENS | 1,979 | 4,485 | 1,286 |

Southeast Queens has 3 to 6 times more flood complaints. Gowanus is still the better single site for both demos because of its sheds; complaint counts also reflect how often people report, not only how often it floods.

## DOB NOW approved permits (`rbx6-tga4`)

- `community_board` is a three-digit code: borough digit plus district. **Brooklyn CD 6 is `306`** (3,137 shed permits, all time).
- Work types: `Sidewalk Shed` (112,877), `Supported Scaffold` (55,318), `Construction Fence` (85,708), `Suspended Scaffold` (15,510).

## FloodNet in BK06

16 sensor records. A replaced sensor gets a new ID, so group by sensor name.

| Sensor | Events | Max depth (in) | Latest event (UTC) |
|---|---|---|---|
| Hoyt St/5th St | 29 | 10.35 | 2026-07-18 |
| Carroll St/4th Av | 13 | 35.94 | 2026-08-23 11:32 |
| 9th St/Smith St (current) | 12 | 25.35 | 2026-08-23 10:44 |
| 9th St/Smith St (earlier sensor) | 2 | 27.76 | **2021-09-02 (Hurricane Ida)** |
| Lorraine St/Henry St | 8 | 5.28 | 2025-10-30 |
| 4th Av/Garfield Pl | 4 | 16.42 | 2026-07-28 |
| Pioneer St/Conover St | 4 | 3.5 | 2026-08-23 |
| Bergen St/3rd Ave | 3 | 5.04 | 2026-08-23 |
| Van Brunt St/Reed St (current) | 3 | 18.15 | 2026-09-27 |
| Dwight St/King St | 2 | 2.01 | 2026-03-17 |
| Coffey St/Richards St | 1 | 2.01 | 2026-08-20 |
| Van Brunt St/Reed St (earlier sensor) | 1 | 4.92 | 2022-09-13 |
| Henry St/Mill St | 1 | 1.61 | 2026-08-23 |

**Demo candidate:** 9th St/Smith St flooded in Hurricane Ida (2021) and again on Aug 23, 2026, recorded under two sensor IDs.

## Rainfall, Aug 22 to 24, 2026

| Source | Label | Total | Peak |
|---|---|---|---|
| Central Park weather station (Iowa Environmental Mesonet) | record | 0.96 in | 0.49 in/hr, hour ending 07:51 local |
| Open-Meteo archive | model | 0.42 in | 0.157 in/hr at 08:00 local |

The measurement and the model disagree by more than half, which is why rainfall must carry its label. Flooding at Carroll St/4th Av started at 11:32 UTC (07:32 local), during the peak hour, so converting UTC to local time lines the sources up. Central Park is several kilometers from Gowanus; a closer station would be better.

# Day 2 findings: the data layer on real data (Oct 27, 2026)

## Snapshot

| Dataset | Rows |
|---|---|
| 311 since 2020 (flooding and sidewalk types, Brooklyn CB 6) | 13,591 |
| 311 flooding, 2010s | 2,800 |
| DOB NOW shed, scaffold and fence permits (board 306) | 7,835 |
| Older DOB permits (board 306) | 11,473 |
| FloodNet sensors / events (BK06) | 16 / 83 |
| PLUTO lots (cd 306) | 13,764 |
| Hourly rain, Central Park, since 2020 | 59,524 |

All field-name guesses held: every dataset downloaded on the first run.

## Coverage logic on real data

A lookup at 40.6787, -73.9830 (about 290 m from the real Carroll St/4th Av sensor at 40.676281, -73.984089) correctly reported no FloodNet sensor within 150 m and named the nearest, 3rd Ave/Union St at 197 m. Rain for Aug 22 to 26, 2026 matched the Day 1 smoke test: 0.96 in, peak 0.49 in/hr in the hour ending 07:51.

## Demo candidates

**Sidewalk sheds (permits active on Oct 27, 2026):**

| Site | Permitted since | 311 complaints within 50 m since then | Mapillary photos |
|---|---|---|---|
| 433 Dean St | 2020-09-01 (6.2 years) | shed 17, construction blocking 16, sidewalk 7 | 2018 to 2019 (before the permits) |
| 596 Baltic St | 2022-10-04 (4.1 years) | shed 12 | 2020, 6 m away (before) |
| 230 Court St | 2022-07-14 (4.3 years) | shed 2, construction blocking 2 | 2025-03-30, 8 m away (while permits were valid) |
| 431 Hicks St | 2019-11-08 (7.0 years, longest) | sidewalk 3, shed 1 | 2018 to 2022 |

**Flood corners:**

| Sensor | Events | Deepest | 311 flood complaints within 150 m since install | Notes |
|---|---|---|---|---|
| Carroll St/4th Av | 13 | 35.94 in | 55 | 2024 Mapillary photos nearby; main flood demo |
| 9th St/Smith St | 14 | 27.76 in | 9 | Includes Hurricane Ida (2021-09-02) |
| Hoyt St/5th St | 29 | 10.35 in | 6 | Most events but few complaints: a reporting-gap example |
| 4th Av/Garfield Pl | 4 | 16.42 in | 53 | Next to Carroll St/4th Av |

Hoyt St/5th St (29 sensor events, 6 complaints) against Carroll St/4th Av (13 events, 55 complaints) is a ready example of why complaint counts and sensor counts must be read separately.

## Checking candidate photos (Oct 27, 2026)

SAM 3.1 found no "scaffolding", "sidewalk shed" or "covered walkway" in four candidate photos, and looking at them confirmed it:

| Photo | Site | Taken | What it shows |
|---|---|---|---|
| 1621408108523341 | 230 Court St | 2025-03-30, while shed permits were valid | The corner building next to No. 234, renovated with a new shopfront. No shed on the Court St front |
| 955892331835596 | 230 Court St | 2020-05-13, before | The same corner with an empty, run-down shopfront. No shed |
| 537647067273034 | 431 Hicks St | 2020-05-12, while shed permits were valid | A dashcam on the expressway below street level; it cannot see Hicks St |
| 487700919150129 | 431 Hicks St | 2018-07-15, before | Blurry, rainy view along the expressway fence; no shed visible |

Lessons:

- **230 Court St is a real records-versus-photo conflict.** Shed permits have been valid continuously since July 2022, the building was clearly renovated between 2020 and 2025, yet the 2025 photo shows no shed on the Court St front. Either the shed is on another side, or it came down while the permit stayed open. Good material for "What has changed here?" and for showing that a permit is authorization, not presence.
- **Distance and direction are not enough to pick photos.** Near 431 Hicks St, the closest photos come from the expressway below street level. Candidate photos need a visual check; `find_shed_photos` uses SAM 3.1 for that.

## Shed photo search and demo sites (Oct 27, 2026)

`find_shed_photos` searched 2,097 shed permit chains with permits since 2014: 182 had a Mapillary photo within 15 m, facing the building, taken while the permits were valid. SAM 3.1 checked the 10 newest and found scaffolding in two (279 Van Brunt St, 0.59; 214 Court St, 0.55).

- **"Sidewalk shed" never matched anything; "scaffolding" works.** The app prompts for "scaffolding".
- **214 Court St, photo 1306991370360816 (RobinZyx, 2025-03-30, CC BY-SA 4.0), checked by eye:** a green sidewalk shed along several storefronts, people underneath. SAM's mask covers the shed's poles and cross-bracing, not its roof. The photo shows a building sign reading "218 Court Street" and a contractor banner listing "Sidewalk Shed | Scaffolding", so the sign itself points to the permit. Shed permits for 214, 216 and 218 Court St were issued in February 2025, six weeks before the photo.

**Demo sites:**

| Demo | Site | Story |
|---|---|---|
| Sidewalk | 214 to 218 Court St, with 230 Court St on the same block | Photos from the same day: a shed the photo confirms (permits issued Feb 2025, shed visible in March) and one it contradicts (230 Court St: permits valid since July 2022, no shed visible) |
| Flooding | Carroll St/4th Av sensor, Aug 23, 2026 | Sensor flooding from 06:45 local (28.1 in at the sensor), heaviest rain in the hour ending 07:51 at Central Park, 311 complaints at 09:48, 21:13 and 21:25 |

# Day 3 findings: the investigate command on the demo photos (Oct 27, 2026)

| Run | Observed | Key records | Flags |
|---|---|---|---|
| 214 to 218 Court St, photo 1306991370360816 (2025-03-30) | Scaffolding, confidence 0.55, about 3% of the image | Shed permits valid on the photo date at 214, 216, 218, 224 and 226 Court St; 226 Court St permitted without a break since 2021-08-19; 218 Court St had an earlier shed in 2017 to 2018 | Agreement: consistent with the permits (the photo alone does not show which building's permit covers it); a 42-day paperwork gap at 224 Court St |
| 230 Court St, photo 1332532847863656 (2025-03-30) | No scaffolding, fence or barrier | Shed permits at 226 and 230 Court St within 20 m; 230 Court St permitted without a break since 2022-07-14; a 311 complaint 2 m away on 2025-01-29: "Sidewalk Shed/Pipe Scafford - Inadequate Defective/None" | Conflict: permits valid within 20 m of the camera, no scaffolding visible |
| Carroll St/4th Av, photo 1385498442151420 (2024-04-04), question about 2026-08-23 | No water, puddle or catch basin (a dry day) | Two FloodNet events on Aug 23 (from 06:45, 28.1 in); 0.96 in of rain at Central Park, heaviest hour ending 07:51; two catch basin complaints and one indoor backup | Different moments (2024 photo, 2026 question); complaints lag the sensor: first street complaint about 14 hours later, first indoor backup about 3 hours later |

Recurrence at Carroll St/4th Av within 150 m: FloodNet 17 events on 13 days since 2021-07-15 (deepest 35.94 in); 311 street flooding and catch basins 82 complaints on 65 days since 2010; 50 indoor sewer backups. Recurring by the 3-day definition for both sources.

Fixes made after reading the real output: gaps over 180 days are separate earlier sheds, not paperwork gaps; permit status is labeled as today's status; the agreement flag says "consistent with"; lots come from the permit buildings; only permits within 20 m of the camera can contradict the photo; complaint timing separates street complaints from indoor backups.

# Day 4 findings: Muse Spark writes the explanation (Oct 27, 2026)

First real run, Carroll St/4th Av flooding (photo 1385498442151420, question about 2026-08-23), hosted Muse Spark 1.3, 24.4 s:

- **The split pattern (tools, then the strict schema in a call without tools) works on hosted Muse Spark too**, not only on Muse Spark Open.
- 10 claims, all passed the checks on the first try: 6 records, 2 observations, 2 inferences, 1 no coverage. Both flags were mentioned. It made no tool calls: the evidence list already answered the question.
- It kept the caveats: "a complaint only means someone reported, not how bad it was", the Central Park gauge is 11.5 km away, and the 2024 photo "shows the place, not what it looked like on 2026-08-23".
- **Muse Spark and SAM 3.1 disagreed:** Muse Spark said the photo shows "street drains"; SAM 3.1 found no catch basin. A rule now reports this kind of disagreement instead of letting either model win silently.

Fixes made after reading the output: the FloodNet coverage note named every sensor in range as if both had recorded the events (both were at Carroll St/4th Av); the sources list repeated the flags; the report now gives this run's own cost and a one-line summary of the checks.

Second run, 230 Court St (photo 1332532847863656), hosted Muse Spark 1.3: 10 of 10 claims passed, 2 model calls, about $0.045.

- It explained the conflict without blame: the permitted sheds "may be out of frame, on another side, or already down, because a permit shows authorization not that it is standing."
- It did the date arithmetic right: 5 permits in the search window, 4 valid on the photo date (224 Court St's permit had ended 3 days earlier).
- **It made no tool calls in either run.** Muse Spark only summarized evidence handed to it. Changed: Muse Spark now has `check_photo` (SAM 3.1 as a tool) to verify what it thinks it sees before claiming it, and is told to read complaint resolutions and permits with `get_record`. The report lists every check.
- The sources list now shows each record's address and distance, so a claim such as "permits at 239 Court Street" can be checked. Muse Spark no longer describes people in the photo.

Third and fourth runs, with the tools (hosted Muse Spark 1.3, about 41 to 45 s and $0.07 each):

- **230 Court St:** Muse Spark checked the photo with SAM 3.1 ("sidewalk shed": not found), then read the complaint and both permits. The Jan 29, 2025 complaint ("Inadequate Defective/None") was closed the next day with no further action; two months later the photo shows no shed while the permit was valid.
- **214 Court St:** it read the "218 Court Street" sign, confirmed the scaffolding with SAM 3.1 (0.55), and read the resolution of four outdoor dining "Sidewalk Zone Blocked" complaints at 208 Court St in April 2025.
- **Bug in the rules, repeated by the model:** the agreement flag listed 224 Court St as "valid on 2025-03-30", but that permit ended 2025-03-27. Records came from a week around the photo and the flag treated all of them as valid on the day. Fixed: checks get only permits valid on the photo's day. Muse Spark is also told not to re-check what SAM 3.1 already looked for (it checked "sidewalk shed scaffolding" after "scaffolding").

## Getting the city's stormwater flood maps (Oct 27, 2026)

- The older single-scenario datasets on NYC Open Data (7r5q-vr7p, 5rzh-cyqd, w8eg-8ha6) now return HTTP 403.
- The current collection, 9i7c-xyvv (`NYCFloodStormwaterFloodMaps.zip`, updated 2024-07-03, four scenarios including a new "Limited Flood, 1.77 in/hr"), holds **Esri compressed file geodatabases (CDF)**. GDAL's open-source OpenFileGDB driver cannot read them.
- ArcGIS Online has many copies. The one web search found (organization `IsDCghZ73NgoYoz5`) is a university teaching account, not a city source. The city's copy is published by the account **`mocej.nyc.data`** (NYC Mayor's Office of Climate and Environmental Justice, which makes the maps).
- **Decision:** the snapshot lists the climate office's ArcGIS services, picks each scenario by name, and asks only for the part inside the neighborhood. Evidence cites the Open Data collection page.

Flood demo rerun with the tools (Carroll St/4th Av, hosted Muse Spark 1.3, about $0.07): 11 of 11 claims passed, 5 lookups.

- **Muse Spark settled the "street drains" disagreement itself.** It asked SAM 3.1 for "storm drain" and SAM found 5 regions (best 0.89), where our fixed prompt "catch basin" had found nothing. The flooding prompts now use "storm drain".
- It read the 311 resolutions: debris blocking the catch basin, and "surcharge" from heavy rain for the backup.
- The flood maps were missing ("not loaded"): the snapshot read the moderate layers but saved nothing because the extreme 2080 layer did not finish. Each layer now saves on its own, with progress printed per page.

Flood demo with the city's flood model loaded (hosted Muse Spark 1.3, 48.7 s, about $0.08): 12 of 12 claims passed, 4 lookups.

- The moderate-storm model (today's and 2050 sea levels) maps **deep and contiguous flooding (1 ft or more) at the corner itself**, nuisance flooding 7 m away. New flag: the model, the sensor and the complaints agree this is a place that floods. Muse Spark wrote its first **model** claim.
- **Finding:** the wettest hour at Central Park on Aug 23 had 0.49 in of rain, a quarter of the model's 2.13 in/hr design storm, yet the sensor measured 28.1 in. A new flag says so: rain in Brooklyn may have been heavier, or the corner floods in smaller storms than the model's.
- The extreme 2080 layer timed out on the server (504): its citywide shapes are huge. Timeouts now retry one shape at a time; the two moderate layers saved on their own.
- The extreme 2080 layer still timed out one shape at a time (three 504s), so it is no longer requested. The flood maps used are the moderate storm with today's and with 2050 sea levels.
- Final Day 4 flood run (44.3 s, about $0.08): 11 of 11 claims passed, all four flags covered. Muse Spark answered first ("flooding here likely keeps coming back"), wrote one model claim with its caveat ("where water is expected to pond, not what happened that day"), and turned the lighter-rain flag into "it may flood in smaller rain than the model storm ... though rain 11.5 km away can differ a lot".

## How three DOT datasets write places (Oct 29, 2026)

`probe --look` showed why three snapshot steps kept nothing:

- **Street construction permits (tqtj-sjs8):** the geometry is text, so the server cannot select by area. `wkt` is in **New York State Plane feet** (EPSG:2263), not degrees; `locationgeometry` is SQL Server binary. Recent permits often have no geometry at all. The snapshot now asks by the district's street names (85k Brooklyn rows since 2024, against 584k for all of Brooklyn), converts the feet to degrees (checked against pyproj), and places a permit without geometry at its house number's lot, or where its cross streets meet its street (midway between the closest lots on each).
- **Sidewalk violations (6kbp-uz6m) and tree sidewalk damage (j6v2-6uxq):** `cb` is the bare board number (6), shared by four boroughs, and nothing records the borough. `bblid` is an internal ID, not a BBL. Rows are now matched to district lots by house number and street, in one spelling ("7TH ST." = "7 STREET"); a violation whose cross streets are given must cross a district street, which drops a same-address row in Manhattan.

Placement check (`python -m smoke.placements`): no sidewalk record came from another borough. Of 249 tree damage records at a violation's address, 246 share DOT's lot ID; the 3 that differ are still in the district's ID range (likely re-numbered lots). DOT lot IDs run 253,791 to 284,337 for both datasets, plus a few new lots above 1.19 million at Park Slope addresses; none is near Manhattan's range. Street permits: 28,498 placed by mapped segment, 12,242 by cross streets, 6,784 by house number.

## First street tree run (Oct 29, 2026)

107 Berkeley Place, Mapillary photo of 2024-04-04 (hosted Muse Spark 1.3, 30.9 s, about $0.07): 10 of 10 claims passed, 3 lookups. Muse Spark read the three 311 complaints and quoted their resolutions ("not enough location detail"; "Parks did the work").

- **Bug:** the inventory record nearest the photo (4 m) was a London planetree with structure **Retired**, and the rule flagged it as "likely the tree in the photo". The records tell a replacement story instead: Poor inspection and removal in 2022, stump removal finished 2023-04, a planting work order closed 2023-07, and a standing honeylocust 7 m away. The match now uses the nearest **standing** tree and names a closer removed one; if only removed trees are near, a conflict flag says the tree seen may be a newer planting. (Assumption to confirm against the Parks data dictionary: "Retired" marks the record of a removed tree.)
- `placements` also showed **pothole work orders: 4,138 saved, 0 placed**: DOT writes `rptdate` as `2019/01/02 00:00:00`, a form the date reader did not know. Fixed; no new download needed.
- Façade filings (159 of 684) and ramp complaints (16 of 103) that are not placed have no date: e.g. auto-generated "No Report Filed" façade rows.

## First batch run (Oct 29, 2026)

`batch --limit 3` over the shortlist (hosted Muse Spark 1.3, about 20 minutes, $1.84 for the explanations): 26 places, 0 failed, 656 records considered.

- **17 of 26 places** have a conflict or a gap between records, photo and model (flags: 11 conflict, 13 gap, 8 agreement).
- **243 of 243 claims** passed the evidence check, with no repair round.
- Muse Spark looked things up 103 times on its own: 75 record reads, 10 building lookups, 6 searches, and **12 times it asked SAM 3.1 to look again** for something new ("sidewalk shed", "orange traffic barrel", "parked car along curb"). Its reading and SAM 3.1 never disagreed.
- Harmless "Exception ignored ... async generator already executing" messages appeared after some SAM look-agains: half-read response streams were closed later by the garbage collector from another thread's loop. SAM streams are now read to the end, and the batch runs explanations the way the single command does.
- The page has a **District overview**: every batch place on the map, colored by its worst flag, each opening its full investigation.

Audit of the batch's 24 conflict and gap flags, by hand:

- **Held up (13):** both repeat-report patterns and record gaps (9 `repeat_reports`, the 180 Kane permit-chain gap), the Carroll St/4th Av flood pair (311 flood reports around the photo's date, April 4, 2024, no sensor reading, Central Park's wettest hour 0.25 in), 431 Hicks (shed permit valid, photo 12 m away facing it, no shed), 433 Dean (structure seen, no permit in 2018).
- **Rules fixed (6):**
  - 180 Kane `permit_without_structure`: every photo there faced away. The batch now skips photos that face away.
  - 473 14 St `removed_tree_listed`: the stump record was updated in 2026, years after the 2019 photo. Removal now counts only if recorded before the photo; a tree removed later is matched as the photo's tree, with "since recorded as removed".
  - 500 4 Av and 90 8 Av `seen_not_reported`: scaffolding protects the public; it is not a façade problem nobody reported. Façades now have no photo-visible problem; their filings carry the topic.
  - 81 Ferris `closed_but_still_seen`: fired on "cracked asphalt", which most streets show. Only a pothole counts now.
  - 515 6 St `facade_unsafe_unprotected`: the UNSAFE filing was for 501 6 St, about 30 m off. It now needs the building within 20 m of the pin.
- **Reworded (4 `reported_not_seen`):** complaints closed before the photo and nothing visible now read as agreement ("consistent with a repair"); only complaints still open on the photo's date are a conflict.
- The summary now counts places by kind (records and photo disagree; reported again and again; other gaps; agree) instead of one "conflict or gap" number that mixed patterns with mismatches.
