"""Self-contained 1920 x 1080 infographic; Python stdlib only.

Run from the workspace root: python docs/framework.py docs/framework.svg
All generated JPEGs are embedded once. All words are exact SVG text.
"""

# Update only after a district batch re-run.
DISTRICT_PLACES = 26
DISTRICT_DISAGREEMENTS = 8

import base64
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

W, H = 1920, 1080
INK, MUTED, WHITE = '#102d4b', '#456078', '#ffffff'
BLUE, TEAL, NAVY = '#0879b4', '#008676', '#062b50'
LINE, PALE, GOLD = '#c9dce6', '#f2f8fb', '#a96b13'
HERE = Path(__file__).resolve().parent
out, definitions = [], []


def text(x, y, value, size=17, weight=400, color=INK, anchor='start', spacing=None):
    """Explicit baselines; text never inherits a scaled image transform."""
    if size < 13:
        raise ValueError('Minimum figure text size is 13 px')
    sp = f' letter-spacing="{spacing}"' if spacing is not None else ''
    out.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{sp}>{escape(str(value))}</text>')


def rect(x, y, w, h, fill=WHITE, stroke=LINE, radius=12, sw=1):
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def path(d, color=LINE, width=1.5, fill='none', extra=''):
    out.append(f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" {extra}/>')


def line(x1, y1, x2, y2, color=LINE, width=1.5):
    path(f'M{x1} {y1}L{x2} {y2}', color, width)


def circle(x, y, r, fill, stroke='none', sw=1):
    out.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


def badge(x, y, letter, color=TEAL, radius=16):
    circle(x, y, radius, color)
    text(x, y+5.5, letter, 17, 700, WHITE, 'middle')


def chip(x, y, label, width, fg=INK, bg=WHITE, border=LINE, size=15, height=28):
    rect(x, y, width, height, bg, border, 7)
    text(x+width/2, y+height/2+size*.35, label, size, 600, fg, 'middle')


def arrow(points, color=BLUE, both=False, dashed=False, width=2.4):
    d = 'M'+' L'.join(f'{x} {y}' for x, y in points)
    extra = f'marker-end="url(#arrow-{color[1:]})"'
    if both:
        extra += f' marker-start="url(#arrow-{color[1:]})"'
    if dashed:
        extra += ' stroke-dasharray="6 5"'
    path(d, color, width, extra=extra)


ASSETS = {
    'street': ('street-photo.jpg', 900, 600),
    'sam': ('sam-masks.jpg', 900, 600),
    'layers': ('public-record-layers.jpg', 900, 600),
    'muse': ('muse-agent.jpg', 900, 600),
    'map': ('claims-map.jpg', 900, 600),
    'before': ('twin-before.jpg', 900, 600),
    'after': ('twin-after.jpg', 900, 600),
    'resident': ('resident-channels.jpg', 900, 507),
}


def picture(name, x, y, w, h, radius=9):
    """Crop only illustrations; labels stay outside their clips."""
    _, iw, ih = ASSETS[name]
    clip = f'picture-clip-{len(definitions)}'
    definitions.append(f'<clipPath id="{clip}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}"/></clipPath>')
    out.append(f'<g clip-path="url(#{clip})"><svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 {iw} {ih}" preserveAspectRatio="xMidYMid slice"><use href="#asset-{name}"/></svg></g>')


def icon(kind, x, y, color=INK, scale=1):
    """Small unbranded vector icons; no font glyphs."""
    shapes = {
        'eye': 'M1 12Q12 0 23 12Q12 24 1 12Z M16 12A4 4 0 1 0 8 12A4 4 0 1 0 16 12',
        'file': 'M5 2H15L21 8V23H5Z M15 2V8H21 M9 12H17 M9 16H17 M9 20H14',
        'search': 'M18 10A8 8 0 1 0 2 10A8 8 0 1 0 18 10 M16 16L23 23',
        'building': 'M4 23V3H19V23 M1 23H23 M8 7H10 M14 7H16 M8 12H10 M14 12H16 M9 23V18H14V23',
        'shield': 'M12 1L22 5V13Q20 20 12 24Q4 20 2 13V5Z M7 12L11 16L18 8',
        'bench': 'M3 7H21V14H3Z M1 17H23 M5 14V23 M19 14V23 M3 10H21',
        'leaf': 'M3 21Q0 3 23 2Q23 24 3 21Z M3 21L17 7',
        'database': 'M2 5C2 0 22 0 22 5C22 10 2 10 2 5Z M2 5V20C2 25 22 25 22 20V5 M2 12C2 17 22 17 22 12',
        'check': 'M3 12L9 18L22 4',
        'pin': 'M12 23Q2 13 2 9A10 10 0 0 1 22 9Q22 13 12 23Z M15 9A3 3 0 1 0 9 9A3 3 0 1 0 15 9',
    }
    out.append(f'<g transform="translate({x} {y}) scale({scale})">')
    path(shapes[kind], color, 1.8)
    out.append('</g>')


def panel(x, width, number, title, gradient, fill=PALE, title_size=24):
    rect(x, 126, width, 718, fill, LINE, 16, 1.2)
    rect(x, 126, width, 52, f'url(#{gradient})', 'none', 14)
    circle(x+30, 152, 21, 'none', '#ffffff55', 5)
    circle(x+30, 152, 17, '#ffffff1c')
    text(x+30, 159, number, 25, 700, WHITE, 'middle')
    text(x+61, 160, title, title_size, 700, WHITE, spacing=.6)


# Title and prominent model credit.
rect(0, 0, W, H, '#f5f9fc', 'none', 0)
rect(0, 0, W, 112, 'url(#page-top)', 'none', 0)
rect(24, 23, 7, 70, BLUE, 'none', 3)
text(47, 57, 'City Investigator', 44, 750)
text(48, 91, "Evidence, not guesses: a resident's street photo, checked against New York City's public records", 21, 400, MUTED)
rect(1312, 24, 584, 75, NAVY, 'none', 13)
text(1335, 49, "Built with Meta's", 17, 600, '#a9e3ff')
text(1335, 81, 'SAM 3.1 and Muse Spark 1.3', 29, 700, WHITE)

panel(24, 568, '1', 'INPUTS AND EVIDENCE', 'blue-band')
panel(608, 680, '2', 'REASONING', 'teal-band')
panel(1304, 592, '3', 'WHAT THE RESIDENT SEES', 'navy-band', '#edf4f9', 23)

# 1: Resident image and segmentation share the same invented scene.
rect(36, 190, 544, 298, WHITE, '#c3dce9')
text(50, 219, 'Photo + question', 23, 700)
text(318, 218, 'SAM 3.1', 25, 750, BLUE)
chip(445, 198, 'Meta model', 122, BLUE, '#e7f5fd', '#c7e6f5', 15)
picture('street', 48, 237, 250, 166)
picture('sam', 314, 237, 254, 166)
text(50, 425, 'faces and plates blurred', 15, 500, MUTED)
text(318, 425, 'segments the photo', 15, 600, BLUE)
rect(474, 413, 11, 11, '#d42db7', 'none', 2)
text(489, 424, 'shed', 13, 500, MUTED)
rect(526, 413, 11, 11, '#00c8da', 'none', 2)
text(541, 424, 'water', 13, 500, MUTED)
rect(48, 441, 520, 35, '#eaf4fa', 'none', 7)
text(308, 465, '“Is flooding a recurring problem here?”', 21, 600, INK, 'middle')

rect(36, 500, 544, 158, WHITE, '#c3dce9')
picture('layers', 44, 507, 226, 143)
text(285, 528, 'Public records', 23, 700)
icon('file', 285, 541, BLUE, .75)
text(312, 557, '311 complaints · permits', 17)
icon('pin', 285, 571, BLUE, .75)
text(312, 587, 'Sensors (FloodNet)', 17)
icon('building', 285, 602, BLUE, .75)
text(312, 620, "The city's flood model", 17)

rect(36, 670, 544, 162, WHITE, '#c3dce9')
icon('database', 50, 683, BLUE, .85)
text(82, 704, 'Evidence store and its blind spots', 22, 700)
line(50, 718, 566, 718)
badge(67, 743, 'A', BLUE)
text(92, 750, 'Records against reality', 22, 700)
text(51, 779, 'Photo vs. records', 17, 600, MUTED)
chip(214, 760, 'agree', 86, '#086d57', '#e7f5ee', '#cde6db')
chip(309, 760, 'disagree', 113, '#a14137', '#fff0ed', '#efdbd7')
chip(431, 760, 'gap', 79, GOLD, '#fff5e4', '#ecdfc4')
text(51, 815, 'Example: “permit valid, no shed in view”', 19, 500)

# 2: Muse is the central agent, with a SAM loop and a checked exit.
rect(620, 190, 656, 300, 'url(#muse-card)', '#268fa9', 13, 1.2)
text(641, 228, 'Muse Spark 1.3', 37, 750, WHITE)
chip(1117, 206, 'Meta model', 139, '#d8faff', '#174f6a', '#43849a', 17)
text(642, 255, 'An agent with tools', 20, 500, '#c7edf7')
picture('muse', 634, 273, 239, 145, 9)
for y, kind, label in ((285, 'eye', 'look again with SAM 3.1'),
                        (320, 'file', 'read records'),
                        (355, 'search', 'search records'),
                        (390, 'building', 'building records')):
    icon(kind, 896, y-16, '#9fe7f1', .85)
    text(928, y+2, label, 19, 500, WHITE)
text(642, 439, 'LABELED CLAIMS', 14, 700, '#9fe7f1', spacing=1)
for x, label, width in ((638, 'Observed', 96), (742, 'Recorded', 96), (846, 'Modeled', 86),
                         (940, 'Inferred', 86), (1034, 'No coverage', 120), (1162, 'Proposal', 96)):
    chip(x, 450, label, width, WHITE, '#164e6a', '#477c92', 15)
arrow([(575, 337), (631, 337)], BLUE, both=True, width=2.8)
arrow([(580, 702), (600, 702), (600, 410), (620, 410)], BLUE, width=1.8)

# Checker is the sole route to the resident-facing answer.
arrow([(946, 490), (946, 514)], TEAL)
rect(620, 514, 656, 132, '#e9f6f2', '#99c9bc', 12, 1.3)
badge(646, 539, 'B')
text(671, 546, 'Evidence, not guesses', 23, 700, '#075d52')
text(1249, 545, 'Claim checker', 17, 600, '#3f6f66', 'end')
icon('shield', 641, 563, TEAL, 1.1)
text(685, 579, 'No evidence of the right kind:', 19)
chip(967, 557, 'dropped', 105, '#a14137', '#fff0ed', '#e8d2cd', 17, 30)
rect(684, 601, 418, 32, TEAL, 'none', 7)
text(893, 623, 'Only checked claims pass', 20, 700, WHITE, 'middle')
icon('check', 1116, 603, TEAL, 1.05)
arrow([(1218, 514), (1218, 502), (1261, 502), (1261, 486)], TEAL, dashed=True)
text(1197, 508, 'repair', 15, 600, TEAL, 'end')

rect(620, 665, 656, 167, WHITE, '#bbd7cc', 12)
badge(646, 691, 'C')
text(671, 699, 'Grounded proposals', 24, 700, '#075d52')
text(1255, 697, 'No promises.', 18, 700, TEAL, 'end')
text(638, 730, 'Real channels:', 17, 600)
text(760, 730, '311 · Brooklyn Community Board 6', 17)
text(760, 753, 'DEP Green Infrastructure', 17)
text(638, 782, 'Precedents: how similar reports ended across the district', 17)
text(638, 812, 'At most one idea from elsewhere.', 18, 600, TEAL)
# Proposals feed into the agent and checker; no bypass to the answer.
arrow([(628, 665), (611, 665), (611, 454), (620, 454)], TEAL, width=1.8)
arrow([(1276, 614), (1296, 614), (1296, 271), (1316, 271)], TEAL, width=2.8)

# 3: Answer, human needs, third-party visualization, district overview.
rect(1316, 190, 568, 145, WHITE, '#bfd3e1')
text(1331, 218, 'Answer', 25, 700)
text(1445, 218, 'Claims linked to a map and a timeline', 18, 500, MUTED)
picture('map', 1328, 232, 260, 90)
chip(1620, 236, 'Observed', 115, BLUE, '#edf7fd', '#c9e2ee', 15)
chip(1744, 236, 'Recorded', 115, TEAL, '#edf8f3', '#cbe2d8', 15)
line(1590, 251, 1620, 251, '#7f9eae', 1.8)
line(1604, 251, 1604, 285, '#7f9eae', 1.8)
line(1604, 285, 1855, 285, '#7f9eae', 2)
for tx, color in ((1632, BLUE), (1702, TEAL), (1773, BLUE), (1843, TEAL)):
    circle(tx, 285, 5, WHITE, color, 2)
line(1677, 264, 1677, 280, '#8daab9')
line(1800, 264, 1800, 280, '#8daab9')
text(1735, 317, 'Timeline', 15, 600, MUTED, 'middle')

rect(1316, 347, 568, 88, WHITE, '#bfd3e1')
badge(1341, 371, 'D', NAVY)
text(1366, 379, 'Needs at stake', 22, 700)
text(1867, 376, "Jan Gehl's criteria", 16, 400, MUTED, 'end')
for x, kind, label in ((1335, 'shield', 'Protection'), (1516, 'bench', 'Comfort'), (1688, 'leaf', 'Enjoyment')):
    icon(kind, x, 398, NAVY, .8)
    text(x+31, 418, label, 18, 600)

rect(1316, 447, 568, 296, NAVY, '#366484', 12)
badge(1342, 473, 'E', '#2d6c92')
text(1367, 481, 'An honest 3D twin', 24, 700, WHITE)
text(1331, 508, '3D city in Valdrada · third-party, MIT', 17, 500, '#c5e2f4')
picture('before', 1328, 520, 270, 163)
picture('after', 1606, 520, 266, 163)
chip(1336, 528, 'Before', 80, WHITE, '#153a55', '#487089', 15, 25)
chip(1614, 528, 'After', 73, WHITE, '#166451', '#62a491', 15, 25)
text(1331, 706, 'Evidence in place', 18, 700, WHITE)
text(1609, 706, 'Proposals at real scale', 18, 700, '#c3f2dc')
text(1331, 729, 'Flood water · permitted sheds', 16, 400, '#c5deef')
text(1609, 729, 'Rain gardens added; water remains', 16, 500, '#c3f2dc')
text(1330, 765, 'The gardens hold only a small share of the water.', 17, 600, NAVY)

rect(1316, 777, 568, 55, WHITE, '#bfd3e1')
picture('map', 1324, 784, 112, 41, 5)
text(1451, 800, 'District overview', 19, 700)
text(1451, 824, f'{DISTRICT_PLACES} places · {DISTRICT_DISAGREEMENTS} where records and photo disagree', 17, 500, MUTED)

# Bottom picture pipeline; images reuse their embedded definitions.
pipeline = [
    (24, 'street', 'A street photo and a question'),
    (408, 'layers', 'NYC public records'),
    (792, 'muse', 'SAM 3.1 + Muse Spark 1.3'),
    (1176, 'map', 'Checked, labeled claims'),
    (1560, 'resident', 'Residents act through real channels'),
]
for x, name, label in pipeline:
    rect(x, 860, 336, 124, WHITE, '#c8dce7', 10)
    picture(name, x+1, 861, 334, 87, 9)
    text(x+168, 973, label, 17, 650, INK, 'middle')
    if name == 'map':
        circle(x+296, 905, 19, WHITE, '#72b9a3', 2)
        icon('check', x+284, 893, TEAL, 1)
    if x < 1560:
        path(f'M{x+355} 899L{x+370} 914L{x+355} 929', '#3e87a6', 6)

# Legend and exact provenance footer.
line(24, 998, 1896, 998, '#c6d9e5')
text(25, 1026, 'THE FIVE IDEAS', 16, 750, MUTED, spacing=1)
for x, letter, label in ((218, 'A', 'Records against reality'), (573, 'B', 'Evidence, not guesses'),
                         (932, 'C', 'Grounded proposals'), (1262, 'D', 'Needs at stake'),
                         (1547, 'E', 'An honest 3D twin')):
    badge(x, 1020, letter, BLUE if letter == 'A' else (TEAL if letter in 'BC' else NAVY), 12)
    text(x+22, 1026, label, 18, 500)
text(25, 1062, 'Data: NYC Open Data · FloodNet · NYC Stormwater Flood Maps · Mapillary | 3D: Valdrada (MIT)', 16, 400, MUTED)
text(1896, 1062, 'Pictures are AI-generated illustrations, not evidence.', 16, 600, MUTED, 'end')


def build_svg():
    defs = [
        '<linearGradient id="page-top"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#e7f3f8"/></linearGradient>',
        '<linearGradient id="blue-band"><stop stop-color="#149bcc"/><stop offset="1" stop-color="#075184"/></linearGradient>',
        '<linearGradient id="teal-band"><stop stop-color="#009c86"/><stop offset="1" stop-color="#006955"/></linearGradient>',
        '<linearGradient id="navy-band"><stop stop-color="#123e65"/><stop offset="1" stop-color="#052747"/></linearGradient>',
        '<linearGradient id="muse-card" x2="1" y2="1"><stop stop-color="#0b4c70"/><stop offset="1" stop-color="#072641"/></linearGradient>',
    ]
    for color in (BLUE, TEAL):
        defs.append(f'<marker id="arrow-{color[1:]}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M1 1L9 5L1 9Z" fill="{color}"/></marker>')
    for key, (filename, width, height) in ASSETS.items():
        encoded = base64.b64encode((HERE/'figure'/filename).read_bytes()).decode('ascii')
        defs.append(f'<image id="asset-{key}" width="{width}" height="{height}" href="data:image/jpeg;base64,{encoded}"/>')
    defs.extend(definitions)
    aria = (
        "City Investigator. Evidence, not guesses: a resident's street photo, checked against New York City's public records. "
        "Built with Meta's SAM 3.1 and Muse Spark 1.3. Three numbered panels. "
        "1, Inputs and evidence: an illustrated Brooklyn rowhouse street with a sidewalk shed and a flooded corner. "
        "Photo plus question: Is flooding a recurring problem here? Faces and plates blurred. "
        "SAM 3.1, a Meta model, segments the same scene with colored masks on the shed and water. "
        "Public records: 311 complaints, permits, sensors (FloodNet), and the city's flood model, shown as stacked map layers. "
        "Evidence store and its blind spots. A, Records against reality: photo vs. records; agree, disagree, gap. "
        "Example: permit valid, no shed in view. "
        "2, Reasoning: Muse Spark 1.3, a Meta model and agent with tools: look again with SAM 3.1 in a two-way loop, "
        "read records, search records, building records. Labeled claims: Observed, Recorded, Modeled, Inferred, No coverage, Proposal. "
        "B, Evidence, not guesses: a claim checker. No evidence of the right kind: dropped. Only checked claims pass to the answer. "
        "A dashed repair loop returns to Muse Spark. C, Grounded proposals feed into the agent and checker: real channels "
        "(311, Brooklyn Community Board 6, DEP Green Infrastructure); precedents (how similar reports ended across the district); "
        "at most one idea from elsewhere. No promises. "
        "3, What the resident sees: Answer with claims linked to a map and a timeline. D, Needs at stake: Protection, Comfort, "
        "Enjoyment (Jan Gehl's criteria). E, An honest 3D twin: 3D city in Valdrada, third-party, MIT, a visualization, "
        "not evidence or a Meta model. Before: evidence in place, flood water and permitted sheds. After: proposals at real scale; "
        "rain gardens added, the water remains. The gardens hold only a small share of the water. "
        f"District overview: {DISTRICT_PLACES} places, {DISTRICT_DISAGREEMENTS} where records and photo disagree. "
        "Bottom picture pipeline: A street photo and a question; NYC public records; SAM 3.1 + Muse Spark 1.3; "
        "Checked, labeled claims; Residents act through real channels. THE FIVE IDEAS legend repeats A through E. "
        "Data: NYC Open Data · FloodNet · NYC Stormwater Flood Maps · Mapillary | 3D: Valdrada (MIT). "
        "Pictures are AI-generated illustrations, not evidence."
    )
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            f'role="img" aria-label={quoteattr(aria)} font-family="Segoe UI, Arial, sans-serif">'
            '<title>City Investigator</title><defs>'+''.join(defs)+'</defs>'+''.join(out)+'</svg>\n')


if __name__ == '__main__':
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE/'framework.svg'
    svg = build_svg()
    if len(svg.encode('utf-8')) > 3_000_000:
        raise ValueError('Self-contained SVG exceeds the 3 MB budget')
    destination.write_text(svg, encoding='utf-8')
    print(f'{destination}: {len(svg.encode("utf-8")):,} bytes; {W} x {H}; {len(ASSETS)} embedded JPEGs')
