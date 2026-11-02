# City Investigator: notes for Claude Code

Built for the Meta Global AI Developer Hackathon. **Submissions close Nov 4, 2026, 9 PM ET.** Meta models are
required, and "Use of Meta AI Tooling" is a quarter of the score. A public repo and a 3-minute video are required.

A resident brings a street photo and a question. SAM 3.1, Muse Spark and NYC public records for Brooklyn Community
District 6 become cited, labeled claims, flags, a map, a timeline, and a 3D view in Valdrada. See `README.md` for
the full picture and `smoke/FINDINGS.md` for what was learned on real data.

## Working with the owner

- Windows, PowerShell (no `&&`; give commands one per line), project at `G:\Projects\city-investigator` with
  `.venv` (`.\.venv\Scripts\Activate.ps1`).
- Valdrada is a separate clone at `G:\Projects\valdrada`; run it from `G:\Projects\valdrada\client` with
  `$env:NYC_NOHMR = "1"` then `npm run dev` (port 5219). The page runs on port 8000.
- Prefer short, step-by-step answers that say which window each command goes in. The owner sometimes writes in
  Chinese; answer in the language they use.

## Rules

- Never ask for keys or tokens in chat. Keys live in `.env` (see `.env.example`); never commit `.env`, and do not
  edit it: give the owner the line to change instead.
- `data/private/` (photos, investigations, uploads) is never committed.
- Drop owner names from records (FISP `owner_*`, `qewi_*` and the like). Blur faces and license plates before any
  analysis of a photo that Mapillary has not already blurred.
- Do not fetch, analyze or store Google Street View images; links are for people only.
- Use the standard model tier (`muse-spark-1.3`, `sam-3.1`), never a `-contributor` model.
- No political framing; do not describe people; do not assign blame or name owners.
- Valdrada (github.com/mkturkcan/valdrada, MIT) is third-party: credit it, never present its view as evidence (it
  places some details, like shop signs, at random), and keep its code out of this repo. Our add-on lives in
  `city_investigator/valdrada/` and is copied into a local Valdrada by `valdrada_addon`.
- Spending stops at `DAILY_SPEND_CAP_USD` in `.env` (a `SpendCapError`).

## Commands

```powershell
python -m pytest tests                                     # offline, no keys
python -m smoke.check_env                                  # keys, services, models on the Meta Model API
python -m city_investigator.snapshot                       # download the district's records (--only NAME)
python -m city_investigator.shortlist --topic trees        # sites worth investigating, with photos
python -m city_investigator.batch --limit 3 --again        # investigate 3 sites PER TOPIC (about 26), again
python -m city_investigator.scene3d                        # newest run per site and what it draws in Valdrada (--all)
python -m city_investigator.valdrada_addon G:\Projects\valdrada   # install or update the add-on, then RESTART Valdrada
python -m city_investigator.web                            # the page, http://127.0.0.1:8000
```

## Map of the code

- `snapshot.py`, `sources.py`, `socrata.py`, `geo.py`, `times.py`: download and place the records.
- `store.py`, `evidence.py`, `lookup.py`: the evidence store and coverage-aware lookups.
- `topics.py`, `checks.py`, `sheds.py`, `floodmap.py`, `buildings.py`: topics and the checks that raise flags.
- `photo_input.py`, `segment.py`, `meta.py`: photos, SAM 3.1, model clients and spend caps.
- `investigate.py`, `explain.py`, `actions.py`: a run, Muse Spark's checked claims, and the vetted proposals.
- `needs.py`: Gehl's 12 quality criteria each topic bears on.
- `scene3d.py`, `valdrada/cityInvestigator.js`, `valdrada_addon.py`: the 3D scene and the Valdrada add-on
  (flood water, permitted sheds, scaffolding seen in the photo, unsafe façades, record pins, After view).
- `batch.py`, `web.py`, `static/`: batch runs, the web page and the district overview.

## Where things stand (Nov 2)

Done and pushed: everything above. Tested offline and in Node with stand-ins. Seen in the owner's Valdrada: the
flood water, permitted sheds and the red façade wash (look right). Labels were out of frame and After duplicated a
standing shed (fixed Nov 2, not yet seen again); record pins and rain gardens not yet seen there.

Next, in order:
1. Check the 3D layers in the owner's Valdrada (`scene3d` list, then screenshots of Before and After); fix what
   they show.
2. Video script and shot list (`docs/demo-video.md`), then the owner records.
3. README status line and submission text; an X post.
4. Only if time is left: a replay of a site's records over time with a marker per department; an AI-labeled
   "After" version of the photo with `muse-image-1.0`.
