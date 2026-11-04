# Demo video: script and shot list (3 minutes)

Numbers are from the batch of Nov 2 (`data/derived/batch.md`). About 400 spoken words fit 3 minutes; the voice-over
below is about 340, leaving room for pauses.

Sites to film (newest runs, from `python -m city_investigator.scene3d`):
- Flood: Carroll St and 4th Ave (flags: reported without a sensor, the model expects flooding, flooded in lighter
  rain, low ground).
- Sheds and façades: 90 8th Ave (two unsafe façade filings, protected; permitted sheds; scaffolding seen in the photo).
- Disagreement for the answer shot: 431 Hicks St (a shed permit, no shed in the photo) or 433 Dean St (a structure in
  the photo, no permit).

## Before recording

- Start the page and Valdrada, open Valdrada 3D once and wait for the city to load (the first load compiles its
  shaders; it must not be in the video). After that, other places open in seconds.
- Open the page in presenter mode, http://127.0.0.1:8000/?demo. Each press of the space bar (or →) plays the next
  shot below; ← plays the one before again; H hides the shot counter in the corner (hide it before recording).
  The shots open the newest run of Carroll St, 431 Hicks St and 90 8th Ave (`DEMO_SITES` in `web.py`).
- Shot 3 runs a live investigation of Carroll St (about 2 minutes, about $0.15); shots 7 to 9 then use that new run,
  so Muse Image and the draft are made live too (about 10 s and 30 to 50 s). Cut the waiting.
- Browser at 100% zoom, one tab, notifications off. No `.env`, keys or terminal with keys on screen.
- Record at 1080p with Windows' recorder (Win+Alt+R starts and stops it). Speak over the screen.

## Shots

The first column is the presenter shot (space bar) that sets up the screen.

| Shot | Time | Screen | Voice-over |
|---|---|---|---|
| 1 | 0:00–0:12 | Valdrada 3D at Carroll St and 4th Ave in rain; turn the camera to the water and the sensor's pole | "This corner in Brooklyn floods. Residents report it, a sensor measured it, the city's model expects it. But nobody puts those records next to what a resident actually sees." |
| 2 | 0:12–0:22 | The page: the Carroll St photo loads, the pin, the question | "City Investigator starts from a street photo and a question. You confirm where it was taken, and ask." |
| 3 | 0:22–0:52 | The run streaming: SAM 3.1 looking, records gathered, Muse Spark reading, asking SAM 3.1 to look again, "passed, 0 removed" | "SAM 3.1 segments the photo. Muse Spark investigates: it reads permits, complaints, sensors and the flood model, and asks SAM 3.1 to look again when it needs to. Every claim is labeled, seen, recorded, modeled or inferred, and checked against its evidence before you see it." |
| 4 | 0:52–1:07 | 431 Hicks St: a claim lights up the map and the timeline | "Where the photo and the records disagree, it says so. Here a shed permit is valid, but the photo shows no shed." |
| 5 | 1:07–1:15 | The flags and the needs chips | "Each finding is tagged with the needs it bears on, from Jan Gehl's criteria: protection, comfort, enjoyment." |
| 6 | 1:15–1:38 | Valdrada 3D at 90 8th Ave: the amber permitted shed, the red façade, record pins | "The same place in 3D, in Valdrada, an open digital twin of New York. Amber is what the permits say, red an unsafe façade filing, pins the records behind the answer. Valdrada's own random sheds are removed: every shed you see comes from evidence." |
| 7 | 1:38–2:00 | Back at Carroll St: "What could be done", then After in 3D, the rain gardens and their label | "Muse Spark proposes next steps only through real channels, tied to evidence. After shows them at real scale: three rain gardens hold about 23 cubic meters a storm, against about 5,400 of modeled flood. Under one percent, so the water stays. Part of the answer, not all of it." |
| 8 | 2:00–2:15 | The proposals drawn into the photo by Muse Image; switch between After and the photo | "Muse Image draws the same proposals into the resident's own photo: rain gardens at this corner, everything else kept, the water too. It is marked as an illustration, never evidence." |
| 9 | 2:15–2:32 | "Write it for me": the draft to the community board or the 311 description, the Copy button | "And Muse Spark drafts the letter or the 311 report, from the checked claims only: every number in it must appear in them, and it promises nothing. The resident reads it and sends it." |
| 10 | 2:32–2:48 | District overview: the map of sites by worst flag, the stats, the needs totals | "Across the district: 26 places, 8 where the records and the photo disagree, all 276 claims kept after checking, for under two dollars fifty in model calls." |
| – | 2:48–3:00 | The framework figure (`docs/framework.png`), its badges A to E in turn; then the title (cut in when editing) | "Built with Muse Spark, SAM 3.1 and Muse Image, on NYC Open Data, FloodNet and Mapillary. City Investigator. Evidence, not guesses." |

## Credits on screen or in the description

Valdrada by Mehmet Kerem Turkcan (MIT). Photos: Mapillary contributors (CC BY-SA 4.0). Data: NYC Open Data, FloodNet
(NYU and CUNY), NYC Stormwater Flood Maps, Iowa Environmental Mesonet. Needs: Jan Gehl, *Cities for People* (2010).
