"""Draws City Investigator's framework figure, left to right.

Usage: python docs/framework.py docs/framework.svg
(docs/framework.png is the same figure at 2x, for slides and the video.)
"""
from xml.sax.saxutils import escape
import sys

W, H = 1460, 812
TEXT, MUTED, LINE = "#1f2328", "#57606a", "#d0d7de"
BLUE, BLUE_BG, BLUE_LINE = "#1f4fbf", "#eef4ff", "#5b8def"
GREEN, GREEN_BG, GREEN_LINE = "#2b7a3d", "#eef7ef", "#6fb07f"
FLAGS = {"agree": ("#2b7a3d", "#e6f4ea"), "disagree": ("#b42318", "#fdecea"), "gap": ("#9a6700", "#fff4e5")}
NEEDS = {"Protection": ("#8a1c1c", "#fbeeee"), "Comfort": ("#1d4f8a", "#eef3fb"), "Enjoyment": ("#2b6a2f", "#eef8ef")}
out = []


def text(x, y, s, size=12.5, weight=400, color=TEXT, anchor="start", italic=False, rotate=None):
    extra = f' transform="rotate({rotate} {x} {y})"' if rotate else ""
    style = ' font-style="italic"' if italic else ""
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{style}{extra}>{escape(s)}</text>')


def box(x, y, w, h, fill="#f6f8fa", stroke=LINE, rx=10, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"{d}/>')


def chip(x, y, label, fg, bg, size=11.5):
    w = round(len(label) * size * 0.56 + 16)
    out.append(f'<rect x="{x}" y="{y - 13}" width="{w}" height="19" rx="9.5" fill="{bg}" stroke="{fg}" stroke-opacity="0.45"/>')
    text(x + w / 2, y + 0.5, label, size, 500, fg, "middle")
    return w


def chips(x, y, labels, colors, gap=6):
    for label in labels:
        fg, bg = colors[label] if isinstance(colors, dict) else colors
        x += chip(x, y, label, fg, bg) + gap


def arrow(points, label=None, at=None, dash=False, both=False, anchor="middle", rotate=None):
    pts = " ".join(f"{x},{y}" for x, y in points)
    d = ' stroke-dasharray="5 4"' if dash else ""
    start = ' marker-start="url(#head)"' if both else ""
    out.append(f'<polyline points="{pts}" fill="none" stroke="{MUTED}" stroke-width="1.6"{d}{start} marker-end="url(#head)"/>')
    if label:
        text(at[0], at[1], label, 11, 500, MUTED, anchor, rotate=rotate)


def badge(x, y, letter):
    """A key idea, explained under the same letter in the README."""
    out.append(f'<circle cx="{x}" cy="{y}" r="11" fill="{TEXT}"/>')
    text(x, y + 4.5, letter, 12.5, 700, "#ffffff", "middle")


def lines(x, y, rows, size=12.5, step=20, color=TEXT):
    for i, row in enumerate(rows):
        text(x, y + i * step, row, size, 400, color)


# columns
C1, C2, C3, C4 = (24, 230), (294, 240), (594, 340), (994, 442)
out.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
text(24, 40, "City Investigator: evidence, not guesses", 22, 700)
text(24, 64, "A resident's street photo and question, checked against New York City's public records by two Meta models, SAM 3.1 and Muse Spark", 13, 400, MUTED)
for (x, w), head in zip((C1, C2, C3, C4), ("1  INPUTS", "2  EVIDENCE", "3  REASONING", "4  WHAT IT SHOWS")):
    text(x, 102, head, 11.5, 700, MUTED)

# 1 inputs
x, w = C1
box(x, 120, w, 96)
text(x + 14, 144, "Street photo + question", 14.5, 700)
lines(x + 14, 166, ["a Mapillary photo or an upload", "faces and plates blurred", "“Is this flooding recurring?”"], 12, 18, MUTED)
box(x, 296, w, 262)
text(x + 14, 320, "Public records", 14.5, 700)
text(x + 14, 339, "Brooklyn Community District 6", 12, 400, MUTED)
lines(x + 14, 366, ["311 complaints and their outcomes", "DOB shed and scaffold permits", "façade inspection filings",
                    "Parks street trees", "DOT sidewalks, potholes, permits", "FloodNet sensors, hourly rain",
                    "city stormwater flood model", "building footprints, ground height"], 12, 23)
# legend
box(x, 600, w, 152, fill="#ffffff")
text(x + 14, 624, "How to read it", 13, 700)
out.append(f'<rect x="{x + 14}" y="{636}" width="22" height="14" rx="4" fill="{BLUE_BG}" stroke="{BLUE_LINE}" stroke-width="1.5"/>')
text(x + 44, 648, "a Meta model", 12)
out.append(f'<rect x="{x + 14}" y="{660}" width="22" height="14" rx="4" fill="{GREEN_BG}" stroke="{GREEN_LINE}" stroke-width="1.5"/>')
text(x + 44, 672, "grounds a proposal", 12)
badge(x + 25, 692, "A")
text(x + 44, 696, "a key idea (README)", 12)
chips(x + 14, 722, ["agree", "disagree", "gap"], FLAGS)
text(x + 188, 726, "flags", 12, 400, MUTED)
out.append(f'<line x1="{x + 14}" y1="742" x2="{x + 44}" y2="742" stroke="{MUTED}" stroke-width="1.6" stroke-dasharray="5 4"/>')
text(x + 52, 746, "repair round", 12, 400, MUTED)

# 2 evidence
x, w = C2
box(x, 120, w, 96, BLUE_BG, BLUE_LINE)
text(x + 14, 144, "SAM 3.1", 14.5, 700, BLUE)
lines(x + 14, 166, ["segments the photo:", "what is seen, and what is not"], 12.5, 19)
box(x, 256, w, 100)
text(x + 14, 280, "Checks (code)", 14.5, 700)
text(x + 14, 301, "photo vs. records, place and time", 12.5)
chips(x + 14, 335, ["agree", "disagree", "gap"], FLAGS)
box(x, 396, w, 120)
text(x + 14, 420, "Evidence store", 14.5, 700)
lines(x + 14, 442, ["records placed by place and time", "coverage notes: what each", "source cannot see"], 12.5, 20)
box(x, 556, w, 196, GREEN_BG, GREEN_LINE)
text(x + 14, 580, "What a proposal may use", 14.5, 700, GREEN)
for i, (head, sub) in enumerate((("Vetted channels", "311 wording, DEP, FloodNet, CB6"),
                                 ("Precedents", "how reports like it ended here"),
                                 ("Ideas from elsewhere", "sourced, at most one, labeled"))):
    yy = 608 + i * 48
    out.append(f'<rect x="{x + 14}" y="{yy - 12}" width="4" height="34" rx="2" fill="{GREEN}"/>')
    text(x + 26, yy, head, 12.5, 700)
    text(x + 26, yy + 18, sub, 12, 400, MUTED)

# 3 reasoning
x, w = C3
box(x, 120, w, 480, BLUE_BG, BLUE_LINE)
text(x + 16, 146, "Muse Spark 1.3 (agent)", 16, 700, BLUE)
lines(x + 16, 172, ["reads the photo, the flags and the evidence,", "then investigates with tools:"], 13, 20)
tool = ("#1f4fbf", "#ffffff")
chips(x + 16, 228, ["look again with SAM 3.1", "read a record"], tool)
chips(x + 16, 256, ["search records", "a building's records"], tool)
text(x + 16, 300, "and writes its answer as labeled claims:", 13)
claim = ("#1f2328", "#ffffff")
chips(x + 16, 330, ["Observed", "Recorded", "Modeled"], claim)
chips(x + 16, 358, ["Inferred", "No coverage"], claim)
chips(x + 16, 386, ["Proposal"], (GREEN, GREEN_BG))
lines(x + 16, 426, ["Every claim cites the evidence it rests on.", "Proposals come last: a real channel, the",
                    "evidence they answer, and no promises."], 12.5, 20, MUTED)
text(x + 16, 500, "Muse Spark asked SAM 3.1 to look again", 12.5, 400, MUTED)
text(x + 16, 520, "12 times across the district batch.", 12.5, 400, MUTED)
box(x, 640, w, 112)
text(x + 16, 664, "Claim checker (code)", 14.5, 700)
lines(x + 16, 686, ["drops a claim that cites the wrong kind of", "evidence, or a proposal without a real channel", "or with a promise; one repair round"], 12.5, 20)
arrow([(x + 130, 600), (x + 130, 640)], "claims", (x + 124, 624), anchor="end")
arrow([(x + 210, 640), (x + 210, 600)], "repair", (x + 216, 624), dash=True, anchor="start")

# arrows between columns
arrow([(254, 168), (294, 168)], "photo", (274, 160))
arrow([(254, 456), (294, 456)], "placed", (274, 448))
arrow([(414, 216), (414, 256)], "seen / not seen", (422, 240), anchor="start")
arrow([(414, 396), (414, 356)], "records", (422, 380), anchor="start")
arrow([(534, 168), (594, 168)], "look again", (564, 160), both=True)
arrow([(534, 306), (594, 306)], "flags", (564, 298))
arrow([(534, 456), (594, 456)], "evidence", (564, 448))
arrow([(534, 590), (594, 590)], "may cite", (564, 582))

# 4 what it shows
x, w = C4
box(x, 120, w, 196)
text(x + 16, 144, "Answer page", 14.5, 700)
lines(x + 16, 168, ["the answer as labeled claims, each linked to its evidence;", "the map and the timeline light up what a claim cites;",
                    "flags explain where the photo and the records disagree"], 12.5, 20)
text(x + 16, 248, "Needs at stake, in Jan Gehl's quality criteria:", 12.5, 400, MUTED)
chips(x + 16, 278, ["Protection", "Comfort", "Enjoyment"], NEEDS)
box(x, 356, w, 244)
text(x + 16, 380, "3D city twin (Valdrada)", 14.5, 700)
sub = (w - 48) / 2
box(x + 16, 396, sub, 188, "#ffffff")
text(x + 30, 420, "Before", 13.5, 700)
lines(x + 30, 442, ["the flood model's water", "sheds with a permit (amber)", "scaffolding in the photo (blue)",
                    "unsafe façades (red)", "pins for the records cited", "random sheds removed"], 12, 22)
box(x + 32 + sub, 396, sub, 188, GREEN_BG, GREEN_LINE)
text(x + 46 + sub, 420, "After", 13.5, 700, GREEN)
lines(x + 46 + sub, 442, ["proposals as illustrations:", "rain gardens, the shed the law", "requires, a young tree",
                          "honest scale: the gardens hold", "under 1% of the modeled", "flood; the water stays"], 12, 22)
box(x, 640, w, 112)
text(x + 16, 664, "District overview (batch)", 14.5, 700)
lines(x + 16, 686, ["26 places; 8 where the records and the photo disagree", "259 of 259 claims kept after checking",
                    "about $2 in model calls for the whole district"], 12.5, 20)
# from the checker to what it shows
bus = 964
arrow([(934, 696), (bus, 696), (bus, 218), (994, 218)])
arrow([(bus, 478), (994, 478)])
arrow([(bus, 696), (994, 696)])
text(bus - 8, 457, "kept claims and their evidence", 11, 500, MUTED, "middle", rotate=-90)

# the five key ideas
badge(C2[0] + C2[1] - 18, 274, "A")
badge(C3[0] + C3[1] - 18, 658, "B")
badge(C2[0] + C2[1] - 18, 574, "C")
badge(C4[0] + C4[1] - 22, 244, "D")
badge(C4[0] + 32 + (C4[1] - 48) / 2 * 2 - 18, 414, "E")
text(W / 2, 790, "What cannot be checked is not shown: every claim cites its evidence, and every check is code.", 13, 500, MUTED, "middle")

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
       f'aria-label="City Investigator framework: a street photo and public records become evidence (SAM 3.1, an evidence '
       f'store, rule checks), Muse Spark reasons over it with tools and writes labeled claims a code checker verifies, and '
       f'the result shows as an answer page, a 3D city before and after the proposals, and a district overview" '
       f'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">'
       f'<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
       f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>' + "".join(out) + "</svg>\n")
open(sys.argv[1], "w").write(svg)
