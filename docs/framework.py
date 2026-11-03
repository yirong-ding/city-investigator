"""Draws City Investigator's framework figure, left to right, with the five key ideas marked A to E.

Usage: python docs/framework.py docs/framework.svg
(docs/framework.png is the same figure at 2x, for slides and the video.)
"""
import sys
from xml.sax.saxutils import escape

W, H, TOP = 1380, 660, 64  # TOP: the header band's height over the old layout
TEXT, MUTED, LINE, ARROW = "#0f172a", "#5b6475", "#d5dbe5", "#64748b"
BLUE, BLUE_LINE, BLUE_TINT = "#1d4ed8", "#7aa2f7", "#dbe7ff"
GREEN, GREEN_LINE, GREEN_TINT = "#15803d", "#7cc49a", "#dcf3e4"
WATER, WATER_TINT, GRAY_TINT = "#0e7490", "#d7f0f5", "#e8ecf2"
FLAGS = {"agree": ("#15803d", "#e3f6ea"), "disagree": ("#b42318", "#fdeceb"), "gap": ("#a16207", "#fff4dd")}
NEEDS = {"Protection": ("#9f1239", "#ffe8ee"), "Comfort": ("#1d4ed8", "#e7efff"), "Enjoyment": ("#15803d", "#e3f6ea")}
out = []


def text(x, y, s, size=13, weight=400, color=TEXT, anchor="start", spacing=None):
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{sp}>{escape(s)}</text>')


def card(x, y, w, h, fill="#ffffff", stroke=LINE, shadow=True):
    s = ' filter="url(#shadow)"' if shadow else ""
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="1.4"{s}/>')


# Icons: drawn on a 28 by 28 grid, placed by their center inside a tinted circle.
def icon(kind, cx, cy, c, tint, r=17, scale=0.8):
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{tint}"/>')
    half = 14 * scale
    g = (f'<g transform="translate({cx - half} {cy - half}) scale({scale})" fill="none" stroke="{c}" stroke-width="2.2" '
         f'stroke-linecap="round" stroke-linejoin="round">')
    soft = f'fill="{c}" fill-opacity="0.22"'
    shapes = {
        "camera": f'<rect x="2" y="8" width="24" height="16" rx="3"/><path d="M9 8 L11 4 H17 L19 8"/><circle cx="14" cy="16" r="5" {soft}/>',
        "records": '<path d="M7 2 H19 L24 7 V26 H7 Z"/><path d="M19 2 V7 H24"/><path d="M4 6 V26"/><line x1="11" y1="13" x2="20" y2="13"/>'
                   '<line x1="11" y1="17" x2="20" y2="17"/><line x1="11" y1="21" x2="17" y2="21"/>',
        "segment": f'<rect x="2" y="4" width="24" height="20" rx="3"/><path d="M8 20 C6 14 9 9 14 9 C19 9 21 13 20 17 C19 21 12 22 8 20 Z" {soft}/>'
                   f'<circle cx="8" cy="20" r="1.6" fill="{c}"/>',
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
    out.append(g + shapes[kind] + "</g>")


def titled(x, y, w, h, title, sub=None, fill="#ffffff", stroke=LINE, color=TEXT, mark=None, ink=MUTED, tint=GRAY_TINT, small=False):
    card(x, y, w, h, fill, stroke)
    left = x + 16
    if mark:
        r = 14 if small else 17
        icon(mark, x + 12 + r, y + 12 + r, ink, tint, r, 0.66 if small else 0.8)
        left = x + 20 + 2 * r
    text(left, y + 27, title, 15, 700, color)
    if sub:
        text(left, y + 47, sub, 12.5, 400, MUTED)


def chip(x, y, label, fg, bg, size=12):
    w = round(len(label) * size * 0.56 + 16)
    out.append(f'<rect x="{x}" y="{y - 14}" width="{w}" height="20" rx="10" fill="{bg}" stroke="{fg}" stroke-opacity="0.4"/>')
    text(x + w / 2, y + 0.5, label, size, 600, fg, "middle")
    return w


def chips(x, y, labels, colors, gap=6):
    for label in labels:
        fg, bg = colors[label] if isinstance(colors, dict) else colors
        x += chip(x, y, label, fg, bg) + gap


def tag(xr, y, label):
    """A small tag at a card's top right: the card is a Meta model."""
    w = round(len(label) * 10.5 * 0.6 + 14)
    out.append(f'<rect x="{xr - w}" y="{y - 12}" width="{w}" height="18" rx="9" fill="url(#meta)"/>')
    text(xr - w / 2, y + 1, label, 10.5, 700, "#ffffff", "middle", 0.3)


def badge(x, y, letter):
    """A key idea, explained under the same letter in the README."""
    out.append(f'<circle cx="{x}" cy="{y}" r="12.5" fill="url(#idea)" stroke="#ffffff" stroke-width="2" filter="url(#shadow)"/>')
    text(x, y + 4.5, letter, 13, 800, "#ffffff", "middle")


def path(points, radius=12):
    """A polyline with rounded corners."""
    d = f"M{points[0][0]},{points[0][1]}"
    for (x0, y0), (x1, y1), (x2, y2) in zip(points, points[1:], points[2:]):
        r1 = min(radius, abs(x1 - x0) + abs(y1 - y0)) / max(abs(x1 - x0) + abs(y1 - y0), 1)
        r2 = min(radius, abs(x2 - x1) + abs(y2 - y1)) / max(abs(x2 - x1) + abs(y2 - y1), 1)
        d += f" L{x1 - (x1 - x0) * r1},{y1 - (y1 - y0) * r1} Q{x1},{y1} {x1 + (x2 - x1) * r2},{y1 + (y2 - y1) * r2}"
    return d + f" L{points[-1][0]},{points[-1][1]}"


def arrow(points, label=None, at=None, dash=False, both=False, anchor="middle"):
    d = ' stroke-dasharray="5 4"' if dash else ""
    start = ' marker-start="url(#head)"' if both else ""
    out.append(f'<path d="{path(points)}" fill="none" stroke="{ARROW}" stroke-width="2"{d}{start} marker-end="url(#head)"/>')
    if label:
        text(at[0], at[1], label, 11.5, 600, MUTED, anchor)


def pill(x, y, label, fill, color="#ffffff", stroke=None):
    w = round(len(label) * 12.5 * 0.58 + 22)
    s = f' stroke="{stroke}"' if stroke else ""
    out.append(f'<rect x="{x}" y="{y - 15}" width="{w}" height="24" rx="12" fill="{fill}"{s}/>')
    text(x + w / 2, y + 1.5, label, 12.5, 600, color, "middle")
    return w


# background and header
out.append(f'<rect width="{W}" height="{H}" fill="url(#page)"/>')
out.append(f'<rect width="{W}" height="{H}" fill="url(#dots)"/>')
out.append(f'<rect width="{W}" height="92" fill="url(#band)"/>')
out.append(f'<circle cx="{W - 120}" cy="-40" r="160" fill="#ffffff" fill-opacity="0.05"/><circle cx="{W - 300}" cy="130" r="90" fill="#ffffff" fill-opacity="0.04"/>')
text(32, 46, "City Investigator", 30, 800, "#ffffff")
text(32, 72, "Evidence, not guesses: a resident's street photo, checked against New York City's public records", 14, 500, "#c7d7fe")
xp = W - 32
for label, fill, color, stroke in reversed((("SAM 3.1", "url(#meta)", "#ffffff", None), ("Muse Spark 1.3", "url(#meta)", "#ffffff", None),
                                           ("NYC Open Data", "#ffffff22", "#e2e8f0", "#ffffff55"), ("Valdrada 3D", "#ffffff22", "#e2e8f0", "#ffffff55"))):
    w = round(len(label) * 12.5 * 0.58 + 22)
    xp -= w
    pill(xp, 52, label, fill, color, stroke)
    xp -= 8

out.append(f'<g transform="translate(0 {TOP})">')
C1, C2, C3, C4 = (24, 220), (294, 240), (604, 310), (984, 372)
right = lambda c: c[0] + c[1]
for n, ((x, w), head) in enumerate(zip((C1, C2, C3, C4), ("INPUTS", "EVIDENCE", "REASONING", "WHAT IT SHOWS")), 1):
    out.append(f'<rect x="{x - 10}" y="66" width="{w + 20}" height="484" rx="18" fill="#eef2f7" fill-opacity="0.75"/>')
    out.append(f'<circle cx="{x + 10}" cy="{82}" r="10" fill="{TEXT}"/>')
    text(x + 10, 86, str(n), 11.5, 800, "#ffffff", "middle")
    text(x + 27, 87, head, 12, 800, TEXT, spacing=1.2)

# inputs
x, w = C1
titled(x, 100, w, 80, "Photo + question", "faces and plates blurred", mark="camera")
titled(x, 330, w, 80, "Public records", "311, permits, sensors", mark="records")

# evidence
x, w = C2
titled(x, 100, w, 80, "SAM 3.1", "segments the photo", "url(#blue)", BLUE_LINE, BLUE, "segment", BLUE, BLUE_TINT)
tag(right(C2) - 12, 116, "META MODEL")
titled(x, 215, w, 80, "Photo vs. records", mark="compare")
chips(x + 56, 275, ["agree", "disagree", "gap"], FLAGS)
badge(right(C2) - 18, 233, "A")
titled(x, 330, w, 80, "Evidence store", "and its blind spots", mark="database")
titled(x, 445, w, 90, "Proposals may use", None, "url(#green)", GREEN_LINE, GREEN, "bulb", GREEN, GREEN_TINT)
chips(x + 16, 499, ["real channels", "precedents"], (GREEN, "#ffffff"))
chips(x + 16, 525, ["one idea from elsewhere"], (GREEN, "#ffffff"))
badge(right(C2) - 18, 463, "C")

# reasoning
x, w = C3
titled(x, 100, w, 310, "Muse Spark 1.3", "an agent with tools", "url(#blue)", BLUE_LINE, BLUE, "spark", BLUE, BLUE_TINT)
tag(right(C3) - 12, 116, "META MODEL")
text(x + 16, 182, "TOOLS", 11, 800, MUTED, spacing=1)
chips(x + 16, 206, ["look again with SAM 3.1", "read records"], (BLUE, "#ffffff"))
text(x + 16, 262, "LABELED CLAIMS", 11, 800, MUTED, spacing=1)
claim = (TEXT, "#ffffff")
chips(x + 16, 286, ["Observed", "Recorded", "Modeled"], claim)
chips(x + 16, 316, ["Inferred", "No coverage"], claim)
chips(x + 16, 346, ["Proposal"], (GREEN, GREEN_TINT))
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
chips(x + 56, 186, ["Protection", "Comfort", "Enjoyment"], NEEDS)
badge(right(C4) - 18, 118, "D")
card(x, 245, w, 130)
icon("city", x + 29, 262, MUTED, GRAY_TINT)
text(x + 56, 268, "3D city (Valdrada)", 15, 700)
half = (w - 42) / 2
titled(x + 14, 290, half, 70, "Before", "evidence in place", "#ffffff", mark="water", ink=WATER, tint=WATER_TINT, small=True)
titled(x + 28 + half, 290, half, 70, "After", "real scale", "url(#green)", GREEN_LINE, GREEN, "sprout", GREEN, GREEN_TINT, small=True)
badge(x + 28 + 2 * half - 16, 306, "E")
titled(x, 445, w, 90, "District overview", "26 places · 8 where records and photo disagree", mark="map")
bus = (right(C3) + C4[0]) / 2
arrow([(right(C3), 490), (bus, 490), (bus, 155), (C4[0], 155)])
arrow([(bus, 325), (C4[0], 325)])
arrow([(bus, 490), (C4[0], 490)])
out.append("</g>")

# key
y = H - 26
xk = 24
out.append(f'<rect x="{xk}" y="{y - 11}" width="22" height="14" rx="4" fill="url(#blue)" stroke="{BLUE_LINE}"/>')
text(xk + 30, y + 1, "Meta model", 12, 600, MUTED)
out.append(f'<rect x="{xk + 120}" y="{y - 11}" width="22" height="14" rx="4" fill="url(#green)" stroke="{GREEN_LINE}"/>')
text(xk + 150, y + 1, "proposal", 12, 600, MUTED)
out.append(f'<circle cx="{xk + 236}" cy="{y - 4}" r="9" fill="url(#idea)"/>')
text(xk + 236, y, "A", 10.5, 800, "#ffffff", "middle")
text(xk + 252, y + 1, "A–E: the five key ideas (README)", 12, 600, MUTED)
text(W - 24, y + 1, "Data: NYC Open Data · FloodNet · NYC Stormwater Flood Maps · Mapillary  |  3D: Valdrada (MIT)", 12, 500, MUTED, "end")

defs = f'''<defs>
<marker id="head" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0.5 L10,5 L0,9.5 L2.5,5 z" fill="{ARROW}"/></marker>
<filter id="shadow" x="-10%" y="-10%" width="120%" height="140%"><feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#0f172a" flood-opacity="0.10"/></filter>
<linearGradient id="page" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f8fafc"/><stop offset="1" stop-color="#ffffff"/></linearGradient>
<pattern id="dots" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#cbd5e1" fill-opacity="0.45"/></pattern>
<linearGradient id="band" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1220"/><stop offset="0.55" stop-color="#1e3a8a"/><stop offset="1" stop-color="#4338ca"/></linearGradient>
<linearGradient id="meta" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2563eb"/><stop offset="1" stop-color="#7c3aed"/></linearGradient>
<linearGradient id="blue" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e3ecff"/><stop offset="1" stop-color="#ffffff"/></linearGradient>
<linearGradient id="green" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#dcf3e4"/><stop offset="1" stop-color="#ffffff"/></linearGradient>
<linearGradient id="idea" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#a855f7"/><stop offset="1" stop-color="#db2777"/></linearGradient>
</defs>'''

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
       f'aria-label="City Investigator framework: a photo and public records become evidence (SAM 3.1, an evidence store, '
       f'photo versus records checks), Muse Spark reasons with tools and writes labeled claims that a checker verifies, and '
       f'the result shows as an answer, a 3D city before and after the proposals, and a district overview" '
       f'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif">' + defs + "".join(out) + "</svg>\n")
open(sys.argv[1], "w").write(svg)
