"""The prototype's neighborhood and the exact strings its data uses.

The strings were confirmed against live data on Day 1 (see smoke/FINDINGS.md). They
must match exactly, including the city's own spelling ("Scafford").
"""

from __future__ import annotations

TIMEZONE = "America/New_York"

# Brooklyn Community District 6: Gowanus, Park Slope, Carroll Gardens, Cobble Hill, Red Hook.
NEIGHBORHOOD = {
    "name": "Brooklyn Community District 6 (Gowanus and surroundings)",
    "board_311": "06 BROOKLYN",
    "board_dob": "306",
    "district_floodnet": "BK06",
    "pluto_cd": "306",
    # Generous bounds (south, west, north, east) for clipping citywide map layers.
    "bounds": (40.650, -74.030, 40.700, -73.960),
}

DATASETS = {
    "311_2020_on": "erm2-nwe9",
    "311_2010s": "76ig-c548",
    "dob_now_permits": "rbx6-tga4",
    "dob_legacy_permits": "ipu4-2q9a",
    "floodnet_sensors": "kb2e-tjy3",
    "floodnet_events": "aq7i-eu5q",
    "pluto": "64uk-42ks",
}

FLOODING = "flooding"
SIDEWALK = "sidewalk"

# (complaint_type, descriptor) -> (topic, category). A descriptor of None matches any.
COMPLAINTS: dict[tuple[str, str | None], tuple[str, str]] = {
    ("Sewer", "Street Flooding (SJ)"): (FLOODING, "street_flooding"),
    ("Sewer", "Highway Flooding (SH)"): (FLOODING, "street_flooding"),
    ("Sewer", "Catch Basin Clogged/Flooding (Use Comments) (SC)"): (FLOODING, "catch_basin"),
    ("Sewer", "Catch Basin Search (SC2)"): (FLOODING, "catch_basin"),
    ("Sewer", "Sewer Backup (Use Comments) (SA)"): (FLOODING, "sewer_backup"),
    ("Sewer", "Manhole Overflow (Use Comments) (SA1)"): (FLOODING, "manhole_overflow"),
    ("Sewer Maintenance", "Catch Basin Clogged"): (FLOODING, "catch_basin"),
    ("Sewer Maintenance", "Backup"): (FLOODING, "sewer_backup"),
    (
        "General Construction/Plumbing",
        "Sidewalk Shed/Pipe Scafford - Inadequate Defective/None",
    ): (SIDEWALK, "shed_complaint"),
    ("Sidewalk Condition", "Blocked - Construction"): (SIDEWALK, "construction_blocking"),
    ("Street Condition", "Blocked - Construction"): (SIDEWALK, "construction_blocking"),
    ("Sidewalk Condition", "Broken Sidewalk"): (SIDEWALK, "sidewalk_condition"),
    ("Sidewalk Condition", "Sidewalk Violation"): (SIDEWALK, "sidewalk_condition"),
    ("Sidewalk Condition", "Sidewalk Collapsed"): (SIDEWALK, "sidewalk_condition"),
    ("Obstruction", None): (SIDEWALK, "obstruction"),
    ("Dumpster Complaint", "Blocking Sidewalk or Street"): (SIDEWALK, "obstruction"),
    ("Outdoor Dining", "Sidewalk Zone Blocked"): (SIDEWALK, "obstruction"),
    ("Curb Condition", None): (SIDEWALK, "curb_condition"),
    ("Scaffold Safety", None): (SIDEWALK, "scaffold_safety"),
}
# Flooding history before 2020 lives in a separate dataset; only these types are kept there.
FLOOD_COMPLAINT_TYPES = sorted({ctype for (ctype, _), (topic, _) in COMPLAINTS.items() if topic == FLOODING})
COMPLAINT_TYPES = sorted({ctype for ctype, _ in COMPLAINTS})

# DOB NOW work types and legacy permit subtypes -> category.
PERMIT_WORK_TYPES = {
    "Sidewalk Shed": "shed_permit",
    "Supported Scaffold": "scaffold_permit",
    "Suspended Scaffold": "scaffold_permit",
    "Construction Fence": "fence_permit",
}
LEGACY_PERMIT_SUBTYPES = {"SH": "shed_permit", "SF": "scaffold_permit", "FN": "fence_permit"}

# Fields never stored: names of property owners can single out private individuals.
DROPPED_FIELDS = {"ownername", "owner_name", "owner_s_first_name", "owner_s_last_name",
                  "owner_s_business_name", "owner_s_house__", "owner_s_house_street_name",
                  "owner_s_phone__", "owner_s_zip_code", "owner_business_name"}

# Central Park weather station (Iowa Environmental Mesonet ID "NYC").
RAIN_STATION = {"id": "NYC", "name": "Central Park weather station", "lat": 40.7790, "lon": -73.9692}
RAIN_START_YEAR = 2020

# Shed permits renew every 90 days; gaps up to this long are paperwork delay, not removal.
PERMIT_GAP_BRIDGE_DAYS = 30
# A gap longer than this means the shed came down and a different one went up later.
SEPARATE_SHED_DAYS = 180

# NYC Stormwater Flood Maps: modeled rain-driven flooding in design storms, citywide. The city
# publishes all scenarios as one collection; each is found in the download by words in its name.
STORMWATER_DATASET = "9i7c-xyvv"
STORMWATER_SCENARIOS = [
    {"key": "limited_current", "match": ("limited", "current"), "title": "a limited storm (1.77 in/hr) with today's sea levels"},
    {"key": "moderate_current", "match": ("moderate", "current"), "title": "a moderate storm (2.13 in/hr) with today's sea levels"},
    {"key": "moderate_2050", "match": ("moderate", "2050"), "title": "a moderate storm (2.13 in/hr) with 2050 sea level rise"},
    {"key": "extreme_2080", "match": ("extreme", "2080"), "title": "an extreme storm (3.66 in/hr) with 2080 sea level rise"},
]
STORMWATER_CATEGORIES = {
    1: "nuisance flooding (4 in to 1 ft deep)",
    2: "deep and contiguous flooding (1 ft or deeper)",
    3: "flooding from future high tides",
}
