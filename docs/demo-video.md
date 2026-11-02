# Demo video: script and shot list (3 minutes)

Fill the `[brackets]` from the last batch (`data/derived/batch.md`) and the sites you pick. About 400 spoken words
fit 3 minutes; the voice-over below is about 390.

## Before recording

- Start the page and Valdrada, open Valdrada 3D once and wait for the city to load (the first load compiles its
  shaders; it must not be in the video). After that, other places open in seconds.
- Pick three runs from `python -m city_investigator.scene3d`: the Carroll St flood, one shed or façade site where the
  records and the photo disagree, and one with proposals that draw something in After.
- Browser at 100% zoom, one tab, notifications off. No `.env`, keys or terminal with keys on screen.
- Record at 1080p. Speak over the screen; cut the waiting.

## Shots

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:15 | Valdrada 3D at Carroll St and 4th Ave in rain; the camera turns to the water and the sensor's pole | "This corner in Brooklyn floods. Residents report it, a sensor measured it, the city's model expects it. But these records live in a dozen places, and nobody puts them next to what a resident actually sees." |
| 0:15–0:30 | The page: pick a Mapillary photo, confirm the pin, ask the question | "City Investigator starts from a street photo and a question. You confirm where it was taken, and ask." |
| 0:30–1:05 | The run streaming: SAM 3.1 looking, records gathered, Muse Spark reading, asking SAM 3.1 to look again, "[10] passed, [0] removed" | "SAM 3.1 segments the photo. Then Muse Spark investigates: it reads permits, complaints, sensor readings and the flood model, and when it needs to, it asks SAM 3.1 to look at the photo again. Every claim it writes is labeled: seen in the photo, recorded, modeled, or inferred, and each one is checked against its evidence before you see it." |
| 1:05–1:25 | The answer with its chips; click a claim, the map and timeline light up; the flags; the needs chips | "Where the photo and the records disagree, it says so. Here, [a shed permit is valid, but the photo shows no shed]. Each finding is tagged with the needs it bears on, from Jan Gehl's quality criteria: protection, comfort, enjoyment." |
| 1:25–1:55 | Valdrada 3D at that site: the amber permitted shed, the blue label from the photo, record pins, a red façade | "Then the same place in 3D, in Valdrada, an open digital twin of New York. Amber is what the permits say. Blue is what the photo shows. Pins are the records behind the answer. Valdrada's own randomly placed sheds are removed, so every shed you see comes from evidence." |
| 1:55–2:20 | "What could be done", then After: rain gardens around the low corner (or the required shed) | "Muse Spark can also propose next steps, but only through real channels, like a 311 report or the city's green infrastructure program, and only tied to evidence. After shows each proposal as an illustration: rain gardens on the higher sidewalks that drain to this corner. An illustration, not a prediction." |
| 2:20–2:45 | District overview: the map of sites by worst flag, the stats, the needs totals | "Run it across the district: [26] places, [N] where the records and the photo disagree, [N%] of [N] claims kept after checking, for about [$2] in model calls." |
| 2:45–3:00 | The stack in one frame: Muse Spark 1.3, SAM 3.1, Mapillary, NYC Open Data, FloodNet, Valdrada; then the title | "Built with Muse Spark and SAM 3.1, on NYC Open Data, FloodNet and Mapillary. Next: replaying each site's records over time, department by department. City Investigator. Evidence, not guesses." |

## Credits on screen or in the description

Valdrada by Mehmet Kerem Turkcan (MIT). Photos: Mapillary contributors (CC BY-SA 4.0). Data: NYC Open Data, FloodNet
(NYU and CUNY), NYC Stormwater Flood Maps, Iowa Environmental Mesonet. Needs: Jan Gehl, *Cities for People* (2010).
