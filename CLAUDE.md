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
python -m city_investigator.web                            # the page, http://127.0.0.1:8000 (?demo: presenter mode)
python -m city_investigator.after_photo latest             # Muse Image draws a run's proposals into its photo
python -m city_investigator.draft latest 10                # Muse Spark drafts the proposal at claim 10 to send
```

## Map of the code

- `snapshot.py`, `sources.py`, `socrata.py`, `geo.py`, `times.py`: download and place the records.
- `store.py`, `evidence.py`, `lookup.py`: the evidence store and coverage-aware lookups.
- `topics.py`, `checks.py`, `sheds.py`, `floodmap.py`, `buildings.py`: topics and the checks that raise flags.
- `photo_input.py`, `segment.py`, `meta.py`: photos, SAM 3.1, model clients and spend caps.
- `investigate.py`, `explain.py`, `actions.py`: a run, Muse Spark's checked claims, and the vetted proposals.
- `precedents.py`: how 311 reports like a site's ended across the district (share closed, days, outcomes).
- `needs.py`: Gehl's 12 quality criteria each topic bears on.
- `after_photo.py`: Muse Image (`muse-image-1.0`, `images.edit`, WebP back, about $0.01) redraws the run's blurred
  photo with its proposals done; an AI illustration, never evidence; water kept; no shed where the photo shows one.
- `draft.py`: Muse Spark drafts the 311 description or the letter a proposal names, from checked claims only
  (numbers must appear in them, no promises, one repair); the resident sends it, nothing is sent from here.
- `scene3d.py`, `valdrada/cityInvestigator.js`, `valdrada_addon.py`: the 3D scene and the Valdrada add-on
  (flood water, permitted sheds, scaffolding seen in the photo, unsafe façades, record pins, After view).
- `batch.py`, `web.py`, `static/`: batch runs, the web page and the district overview.

## Where things stand (Nov 4)

Done and pushed: everything above, plus precedents, ideas from elsewhere (actions.py `IDEAS`, FloodNet as a
flooding channel), and the framework figure (`docs/framework.svg` and `.png`, drawn by `docs/framework.py`; the
README's "five ideas" A to E match its badges). 120 tests pass.

Seen working in the owner's Valdrada: flood water, permitted sheds, the red façade wash, labels, record pins, and
at Carroll St in After (add-on 492970e30c, run 20261103-014844) 3 rain gardens placed of 5 possible spots, about
23 m³ a storm against 5,362 m³ of modeled flood within 150 m (0.4%). The add-on reports its version; the page warns when Valdrada runs an older one. After any
add-on change: run `valdrada_addon`, then restart Valdrada (Ctrl+C, `npm run dev`), then F5 the page.

Batch of Nov 2, 9:25 PM ET (with precedents and ideas): 26 sites, 8 where records and photo disagree, 276 of 276
claims kept, 11 look-agains, about $2.38; 24 sites cite a precedent, 2 an idea from elsewhere. The morning batch is
kept in `data/derived/batch-nov2-backup/`. Carroll St cites precedents and proposes the community board and rain
gardens, no idea. Good sites for the video: Carroll St and 4th Ave (flood), 90 8th Ave (façades, sheds).

Done on Nov 2 evening: README status line, `docs/submission.md` (description, five ideas, Meta tooling, credits, X
post), the video script's batch numbers; precedents read "within a day" instead of "within 0 days" (121 tests),
merged into main, and 90 8th Ave re-explained with it (run 20261103-020153, 12 of 12 claims kept, $0.09). The
framework figure was redrawn by gpt-6-astra (Codex 0.166.0 via `npx`; the installed 0.144.3 cannot use that model)
at 1920×1080 with AI-generated pictures in `docs/figure/` (committed on Nov 4).
Do not copy photos from `data/private/` into the figure.

Done on Nov 4: After in the photo (Muse Image) and drafts to send (Muse Spark) under What could be done, and a
presenter mode (`?demo`, space bar per shot; `DEMO_SITES` in web.py) that the video script follows (10 shots, about
340 words). Tried on real runs: Carroll St's photo with 3 rain gardens (10.5 s), letters to CB6 and DEP's Green
Infrastructure Program (29 to 51 s, no problems), a 311 draft at 431 Hicks St. In Valdrada, proposal labels draw
over tree crowns with up to 5 lines (add-on 3b2601f592). 126 tests pass.

Status at submission (Nov 4, evening): main is pushed to github.com/yirong-ding/city-investigator with the figure;
the 3-minute video was recorded in presenter mode with a synthetic voice and burned-in captions (cover, the
figure's parts highlighted in turn, then the shots; a 2.5% speed-up keeps it under 3:00); 126 tests pass. The
owner submits on the Cerebral Valley portal. After the hackathon, the ideas not built: a replay of a site's
records over time with a marker per department, and photos over time (SAM 3.1 on every Mapillary photo of a spot,
laid against the permits).
