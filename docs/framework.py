"""Draws City Investigator's framework figure, left to right, with the five key ideas marked A to E.

Usage: python docs/framework.py docs/framework.svg
(docs/framework.png is the same figure at 2x, for slides and the video.)
"""
import sys
from xml.sax.saxutils import escape

W, H = 1380, 592
TEXT, MUTED, LINE = "#1f2328", "#57606a", "#d0d7de"
BLUE, BLUE_BG, BLUE_LINE = "#1f4fbf", "#eef4ff", "#5b8def"
GREEN, GREEN_BG, GREEN_LINE = "#2b7a3d", "#eef7ef", "#6fb07f"
WATER = "#1d6fa5"
FLAGS = {"agree": ("#2b7a3d", "#e6f4ea"), "disagree": ("#b42318", "#fdecea"), "gap": ("#9a6700", "#fff4e5")}
NEEDS = {"Protection": ("#8a1c1c", "#fbeeee"), "Comfort": ("#1d4f8a", "#eef3fb"), "Enjoyment": ("#2b6a2f", "#eef8ef")}
out = []


def text(x, y, s, size=13, weight=400, color=TEXT, anchor="start"):
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')


def box(x, y, w, h, fill="#f6f8fa", stroke=LINE):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')


# Icons: 28 by 28, drawn from their top-left corner in one color.
def icon(kind, x, y, c):
    g = f'<g transform="translate({x} {y})" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    soft = f'fill="{c}" fill-opacity="0.18"'
    shapes = {
        "camera": f'<rect x="2" y="8" width="24" height="16" rx="3"/><path d="M9 8 L11 4 H17 L19 8"/><circle cx="14" cy="16" r="5" {soft}/>',
        "records": '<path d="M7 2 H19 L24 7 V26 H7 Z"/><path d="M19 2 V7 H24"/><path d="M4 6 V26"/><line x1="11" y1="13" x2="20" y2="13"/>'
                   '<line x1="11" y1="17" x2="20" y2="17"/><line x1="11" y1="21" x2="17" y2="21"/>',
        "segment": f'<rect x="2" y="4" width="24" height="20" rx="3"/><path d="M8 20 C6 14 9 9 14 9 C19 9 21 13 20 17 C19 21 12 22 8 20 Z" {soft}/>'
                   '<circle cx="8" cy="20" r="1.6" fill="currentColor"/>',
        "compare": f'<circle cx="10" cy="14" r="8"/><circle cx="18" cy="14" r="8" {soft}/>',
        "database": f'<ellipse cx="14" cy="6" rx="10" ry="4" {soft}/><path d="M4 6 V22 C4 24.2 8.5 26 14 26 C19.5 26 24 24.2 24 22 V6"/>'
                    '<path d="M4 14 C4 16.2 8.5 18 14 18 C19.5 18 24 16.2 24 14"/>',
        "bulb": f'<path d="M10 20 C10 16 6 14.5 6 10 A8 8 0 0 1 22 10 C22 14.5 18 16 18 20 Z" {soft}/><line x1="10" y1="23" x2="18" y2="23"/>'
                '<line x1="11.5" y1="26" x2="16.5" y2="26"/>',
        "spark": f'<path d="M13 3 L15.5 11 L23.5 13.5 L15.5 16 L13 24 L10.5 16 L2.5 13.5 L10.5 11 Z" {soft}/>'
                 '<path d="M22 2 L23 5 L26 6 L23 7 L22 10 L21 7 L18 6 L21 5 Z"/>',
        "shield": f'<path d="M14 2 L24 6 V13 C24 20 19.5 24 14 26 C8.5 24 4 20 4 13 V6 Z" {soft}/><polyline points="9,14 13,18 19.5,10"/>',
        "answer": '<rect x="3" y="3" width="22" height="22" rx="3"/><polyline points="7,10 9,12 12,8"/><line x1="15" y1="10" x2="21" y2="10"/>'
                  '<polyline points="7,18 9,20 12,16"/><line x1="15" y1="18" x2="21" y2="18"/>',
        "city": f'<path d="M2 26 H26"/><rect x="4" y="12" width="6" height="14" {soft}/><rect x="11" y="4" width="7" height="22"/>'
                f'<rect x="19" y="9" width="6" height="17" {soft}/><line x1="14.5" y1="9" x2="14.5" y2="21"/>',
        "water": '<path d="M2 11 C5 8 8 8 11 11 C14 14 17 14 20 11 C22 9 24 9 26 10"/><path d="M2 18 C5 15 8 15 11 18 C14 21 17 21 20 18 C22 16 24 16 26 17"/>'
                 '<path d="M14 2 C14 2 10 6.5 10 8.5 A4 4 0 0 0 18 8.5 C18 6.5 14 2 14 2 Z"/>',
        "sprout": f'<path d="M14 26 V12"/><path d="M14 15 C14 9 9 6 4 6 C4 12 8 15 14 15 Z" {soft}/><path d="M14 12 C14 6 18 3 24 3 C24 9 20 12 14 12 Z" {soft}/>'
                  '<path d="M7 26 H21"/>',
        "map": f'<path d="M2 7 L10 4 L18 7 L26 4 V22 L18 25 L10 22 L2 25 Z"/><path d="M10 4 V22 M18 7 V25"/>'
               f'<circle cx="6" cy="12" r="2" fill="{c}"/><circle cx="14" cy="17" r="2" fill="{c}"/><circle cx="22" cy="11" r="2" fill="{c}"/>',
    }
    out.append(g + shapes[kind].replace('fill="currentColor"', f'fill="{c}"') + "</g>")


def titled(x, y, w, h, title, sub=None, fill="#f6f8fa", stroke=LINE, color=TEXT, mark=None, icon_color=None):
    box(x, y, w, h, fill, stroke)
    left = x + 14
    if mark:
        icon(mark, x + 12, y + 12, icon_color or (color if color != TEXT else MUTED))
        left = x + 50
    text(left, y + 27, title, 15, 700, color)
    if sub:
        text(left, y + 48, sub, 12.5, 400, MUTED)


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


C1, C2, C3, C4 = (24, 220), (294, 240), (604, 310), (984, 372)
right = lambda c: c[0] + c[1]
out.append(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
text(24, 42, "City Investigator: evidence, not guesses", 24, 700)
for (x, _), head in zip((C1, C2, C3, C4), ("INPUTS", "EVIDENCE", "REASONING", "WHAT IT SHOWS")):
    text(x, 86, head, 12, 700, MUTED)

# inputs
x, w = C1
titled(x, 100, w, 80, "Photo + question", "faces and plates blurred", mark="camera")
titled(x, 330, w, 80, "Public records", "311, permits, sensors", mark="records")

# evidence
x, w = C2
titled(x, 100, w, 80, "SAM 3.1", "segments the photo", BLUE_BG, BLUE_LINE, BLUE, "segment")
titled(x, 215, w, 80, "Photo vs. records", mark="compare")
chips(x + 50, 275, ["agree", "disagree", "gap"], FLAGS)
badge(right(C2) - 18, 233, "A")
titled(x, 330, w, 80, "Evidence store", "and its blind spots", mark="database")
titled(x, 445, w, 90, "Proposals may use", None, GREEN_BG, GREEN_LINE, GREEN, "bulb")
chips(x + 14, 499, ["real channels", "precedents"], (GREEN, "#ffffff"))
chips(x + 14, 525, ["one idea from elsewhere"], (GREEN, "#ffffff"))
badge(right(C2) - 18, 463, "C")

# reasoning
x, w = C3
titled(x, 100, w, 310, "Muse Spark 1.3", "an agent with tools", BLUE_BG, BLUE_LINE, BLUE, "spark")
text(x + 14, 182, "tools", 12, 700, MUTED)
chips(x + 14, 206, ["look again with SAM 3.1", "read records"], (BLUE, "#ffffff"))
text(x + 14, 262, "labeled claims", 12, 700, MUTED)
claim = (TEXT, "#ffffff")
chips(x + 14, 286, ["Observed", "Recorded", "Modeled"], claim)
chips(x + 14, 316, ["Inferred", "No coverage"], claim)
chips(x + 14, 346, ["Proposal"], (GREEN, GREEN_BG))
titled(x, 445, w, 90, "Claim checker", "no evidence of the right kind: dropped", mark="shield")
badge(right(C3) - 18, 463, "B")
arrow([(x + 110, 410), (x + 110, 445)], "claims", (x + 102, 432), anchor="end")
arrow([(x + 190, 445), (x + 190, 410)], "repair", (x + 198, 432), dash=True, anchor="start")

# arrows into evidence and reasoning
gap1, gap2 = (right(C1) + C2[0]) / 2, (right(C2) + C3[0]) / 2
mid2 = C2[0] + C2[1] / 2
arrow([(right(C1), 140), (C2[0], 140)], "photo", (gap1, 132))
arrow([(right(C1), 370), (C2[0], 370)])
arrow([(mid2, 180), (mid2, 215)])
arrow([(mid2, 330), (mid2, 295)])
arrow([(right(C2), 140), (C3[0], 140)], "look again", (gap2, 132), both=True)
arrow([(right(C2), 255), (C3[0], 255)], "flags", (gap2, 247))
arrow([(right(C2), 370), (C3[0], 370)], "evidence", (gap2, 362))
arrow([(right(C2), 490), (gap2, 490), (gap2, 395), (C3[0], 395)])

# what it shows
x, w = C4
titled(x, 100, w, 110, "Answer", "claims linked to the map and timeline", mark="answer")
chips(x + 50, 186, ["Protection", "Comfort", "Enjoyment"], NEEDS)
badge(right(C4) - 18, 118, "D")
box(x, 245, w, 130)
icon("city", x + 12, 252, MUTED)
text(x + 50, 272, "3D city (Valdrada)", 15, 700)
half = (w - 42) / 2
titled(x + 14, 290, half, 70, "Before", "evidence in place", "#ffffff", mark="water", icon_color=WATER)
titled(x + 28 + half, 290, half, 70, "After", "real scale", GREEN_BG, GREEN_LINE, GREEN, "sprout")
badge(x + 28 + 2 * half - 16, 306, "E")
titled(x, 445, w, 90, "District overview", "26 places · 8 where records and photo disagree", mark="map")
bus = (right(C3) + C4[0]) / 2
arrow([(right(C3), 490), (bus, 490), (bus, 155), (C4[0], 155)])
arrow([(bus, 325), (C4[0], 325)])
arrow([(bus, 490), (C4[0], 490)])

text(24, 574, "Blue: Meta models.  Green: proposals.  A–E: the five key ideas (README).", 12, 400, MUTED)

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
       f'aria-label="City Investigator framework: a photo and public records become evidence (SAM 3.1, an evidence store, '
       f'photo versus records checks), Muse Spark reasons with tools and writes labeled claims that a checker verifies, and '
       f'the result shows as an answer, a 3D city before and after the proposals, and a district overview" '
       f'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">'
       f'<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
       f'<path d="M0,0 L10,5 L0,10 z" fill="{MUTED}"/></marker></defs>' + "".join(out) + "</svg>\n")
open(sys.argv[1], "w").write(svg)
