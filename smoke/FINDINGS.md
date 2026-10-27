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

- **Muse Spark 1.3 does everything in one request.** It is the main path.
- **Muse Spark Open takes images, tools and the schema, but ignores the schema when tools are in the same request.** Step 6 tests the workaround: run the tool loop first, then ask for the schema in a separate call without tools. It is also 2 to 3 times slower.

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
