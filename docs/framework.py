"""Draws City Investigator's framework figure, left to right, with the five key ideas marked A to E.

Usage: python docs/framework.py docs/framework.svg
(docs/framework.png is the same figure at 2x, for slides and the video.)
"""
import sys
from xml.sax.saxutils import escape

W, H = 1320, 592
TEXT, MUTED, LINE = "#1f2328", "#57606a", "#d0d7de"
BLUE, BLUE_BG, BLUE_LINE = "#1f4fbf", "#eef4ff", "#5b8def"
GREEN, GREEN_BG, GREEN_LINE = "#2b7a3d", "#eef7ef", "#6fb07f"
FLAGS = {"agree": ("#2b7a3d", "#e6f4ea"), "disagree": ("#b42318", "#fdecea"), "gap": ("#9a6700", "#fff4e5")}
NEEDS = {"Protection": ("#8a1c1c", "#fbeeee"), "Comfort": ("#1d4f8a", "#eef3fb"), "Enjoyment": ("#2b6a2f", "#eef8ef")}
out = []


def text(x, y, s, size=13, weight=400, color=TEXT, anchor="start"):
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')


def box(x, y, w, h, fill="#f6f8fa", stroke=LINE):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')


def titled(x, y, w, h, title, sub=None, fill="#f6f8fa", stroke=LINE, color=TEXT):
    box(x, y, w, h, fill, stroke)
    text(x + 14, y + 25, title, 15, 700, color)
    if sub:
        text(x + 14, y + 46, sub, 12.5, 400, MUTED)


def chip(x, y, label, fg, bg, size=12):
    w = round(len(label) * size * 0.56 + 16)
    out.append(f'<rect x="{x}" y="{y - 14}" width="{w}" height="20" rx="10" fill="{bg}" stroke="{fg}" stroke-opacity="0.45"/>')
    text(x + w / 2, y + 0.5, label, size, 500, fg, "middle")
    return w


def chips(x, y, labels, colors, gap=6):
    for label in labels:
        fg, bg = colors[label] if isinstance(colors, dict) else colors
        x += chip(x, y, label, fg, bg) + gap


def badge(x, y, letter):
    """A key idea, explained under the same letter in the README."""
    out.append(f'<circle cx="{x}" cy="{y}" r="11" fill="{TEXT}"/>')
    text(x, y + 4.5, letter, 12.5, 700, "#ffffff", "middle")


def arrow(points, label=None, at=None, dash=False, both=False, anchor="middle"):
    pts = " ".join(f"{x},{y}" for x, y in points)
    d = ' stroke-dasharray="5 4"' if dash else ""
    start = ' marker-start="url(#head)"' if both else ""
    out.append(f'<polyline points="{pts}" fill="none" stroke="{MUTED}" stroke-width="1.6"{d}{start} marker-end="url(#head)"/>')
    if label:
        text(at[0], at[1], label, 11.5, 500, MUTED, anchor)


C1, C2, C3, C4 = (24, 190), (264, 220), (554, 300), (914, 382)
out.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
text(24, 42, "City Investigator: evidence, not guesses", 24, 700)
for (x, _), head in zip((C1, C2, C3, C4), ("INPUTS", "EVIDENCE", "REASONING", "WHAT IT SHOWS")):
    text(x, 86, head, 12, 700, MUTED)

# inputs
x, w = C1
titled(x, 100, w, 80, "Photo + question", "faces and plates blurred")
titled(x, 330, w, 80, "Public records", "311, permits, sensors")

# evidence
x, w = C2
titled(x, 100, w, 80, "SAM 3.1", "segments the photo", BLUE_BG, BLUE_LINE, BLUE)
titled(x, 215, w, 80, "Photo vs. records")
chips(x + 14, 275, ["agree", "disagree", "gap"], FLAGS)
badge(x + w - 18, 233, "A")
titled(x, 330, w, 80, "Evidence store", "with what each source can't see")
titled(x, 445, w, 90, "Proposals may use", None, GREEN_BG, GREEN_LINE, GREEN)
chips(x + 14, 497, ["real channels", "precedents"], (GREEN, "#ffffff"))
chips(x + 14, 523, ["one idea from elsewhere"], (GREEN, "#ffffff"))
badge(x + w - 18, 463, "C")

# reasoning
x, w = C3
titled(x, 100, w, 310, "Muse Spark 1.3", "an agent with tools", BLUE_BG, BLUE_LINE, BLUE)
text(x + 14, 182, "tools", 12, 700, MUTED)
chips(x + 14, 206, ["look again with SAM 3.1", "read records"], (BLUE, "#ffffff"))
text(x + 14, 262, "labeled claims", 12, 700, MUTED)
claim = (TEXT, "#ffffff")
chips(x + 14, 286, ["Observed", "Recorded", "Modeled"], claim)
chips(x + 14, 316, ["Inferred", "No coverage"], claim)
chips(x + 14, 346, ["Proposal"], (GREEN, GREEN_BG))
titled(x, 445, w, 90, "Claim checker", "no evidence of the right kind: dropped")
badge(x + w - 18, 463, "B")
arrow([(x + 110, 410), (x + 110, 445)], "claims", (x + 102, 432), anchor="end")
arrow([(x + 190, 445), (x + 190, 410)], "repair", (x + 198, 432), dash=True, anchor="start")

# arrows into evidence and reasoning
arrow([(214, 140), (264, 140)], "photo", (239, 132))
arrow([(214, 370), (264, 370)])
arrow([(374, 180), (374, 215)])
arrow([(374, 330), (374, 295)])
arrow([(484, 140), (554, 140)], "look again", (519, 132), both=True)
arrow([(484, 255), (554, 255)], "flags", (519, 247))
arrow([(484, 370), (554, 370)], "evidence", (519, 362))
arrow([(484, 490), (519, 490), (519, 395), (554, 395)])

# what it shows
x, w = C4
titled(x, 100, w, 110, "Answer", "claims linked to the map and timeline")
chips(x + 14, 186, ["Protection", "Comfort", "Enjoyment"], NEEDS)
badge(x + w - 18, 118, "D")
box(x, 245, w, 130)
text(x + 14, 270, "3D city (Valdrada)", 15, 700)
half = (w - 42) / 2
titled(x + 14, 285, half, 75, "Before", "the evidence, in place", "#ffffff")
titled(x + 28 + half, 285, half, 75, "After", "proposals, at real scale", GREEN_BG, GREEN_LINE, GREEN)
badge(x + 28 + 2 * half - 18, 303, "E")
titled(x, 445, w, 90, "District overview", "26 places · 8 where records and photo disagree")
bus = 884
arrow([(854, 490), (bus, 490), (bus, 155), (914, 155)])
arrow([(bus, 310), (914, 310)])
arrow([(bus, 490), (914, 490)])

text(24, 574, "Blue: Meta models.  Green: proposals.  A–E: the five key ideas (README).", 12, 400, MUTED)

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
       f'aria-label="City Investigator framework: a photo and public records become evidence (SAM 3.1, an evidence store, '
       f'photo versus records checks), Muse Spark reasons with tools and writes labeled claims that a checker verifies, and '
       f'the result shows as an answer, a 3D city before and after the proposals, and a district overview" '
       f'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">'
       f'<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
       f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>' + "".join(out) + "</svg>\n")
open(sys.argv[1], "w").write(svg)
