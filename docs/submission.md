# Submission text

## Short description

Snap a flooded corner or a years-old sidewalk shed, and City Investigator reads its story from city records, permits and flood sensors: how long it's been there, whether it keeps happening, and where the records and the photo disagree. A research aid, not an official determination.

## Description

A street's problems are recorded in a dozen places, and none of them are set next to what a resident actually sees. City Investigator starts from a street photo and a question, for Brooklyn Community District 6. SAM 3.1 segments the photo. Muse Spark then investigates with tools, reading 311 complaints, permits, sensor readings and the city's flood model, and asking SAM 3.1 to look at the photo again when it needs to. The result is a short answer of labeled claims, linked to a map and a timeline, and a view of the place in 3D.

Five ideas shape it:

- **A. Records against reality.** The photo and the records are checked against each other: agree, disagree, or a gap, and every source says what it cannot see.
- **B. Evidence, not guesses.** Muse Spark investigates with tools, and every claim must cite its evidence or a code checker drops it.
- **C. Grounded proposals.** Next steps only through real channels, backed by how similar reports ended here, plus at most one sourced idea from elsewhere; no promises. Each comes with a draft to send, and Muse Image shows it done in the resident's own photo.
- **D. Needs at stake.** Each finding is tagged with Jan Gehl's criteria: protection, comfort, enjoyment.
- **E. An honest 3D twin.** The evidence placed in the city, and After shows proposals at their real scale, not a made-up prediction.

Across 26 places in the district, the records and the photo disagree at 8. All 276 claims passed the checker, Muse Spark chose to ask SAM 3.1 to look again 11 times, and the explanations cost about $2.38 in model calls. Nine kinds of street problems are covered, and 126 offline tests pass without a key.

City Investigator is a research aid, not an official determination.

## Use of Meta AI tooling

- **Muse Spark 1.3** plans the investigation, calls its tools (`check_photo`, `get_record`, `search_records`, `building_records`), and returns the answer under a strict JSON schema: each claim labeled observed, recorded, modeled, inferred, no coverage or proposal, with the evidence ids it rests on. A code checker drops any claim whose evidence is missing or of the wrong kind, and Muse Spark gets one round to repair. It then drafts the 311 report or letter each proposal names, from the checked claims only; the checker rejects any number that is not in them.
- **SAM 3.1** blurs faces and license plates first (it is asked for both before any other model sees a photo Mapillary has not blurred), segments what the question is about, and answers Muse Spark's follow-up checks (`check_photo`, one noun phrase at a time), so a claim about the photo can be tested against what SAM 3.1 finds.
- **Muse Image 1.0** (`images.edit`) redraws the resident's own blurred photo with the proposals done (curbside rain gardens at a flooded corner, the shed an unsafe façade must have), asked to keep everything else, flood water included; the page and the saved file label it an AI illustration, not evidence.
- **Muse Spark Open** is an open-weight option for the explanation (`--provider open`, on Baseten).

## Credits

Valdrada by Mehmet Kerem Turkcan (MIT; third-party, its code is not in this repo). Photos: Mapillary contributors (CC BY-SA 4.0). Data: NYC Open Data, FloodNet (NYU and CUNY), NYC Stormwater Flood Maps, Iowa Environmental Mesonet. Needs: Jan Gehl, *Cities for People* (2010).

## X post

City Investigator checks a NYC street photo against public records with SAM 3.1 and Muse Spark, drafts the 311 report, and shows the fix in your own photo with Muse Image. Every claim cites its evidence, or a checker drops it. [video link] https://github.com/yirong-ding/city-investigator
