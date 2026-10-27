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
TREES = "trees"
FACADES = "facades"
SIDEWALK_DAMAGE = "sidewalk_damage"
CURB_RAMPS = "curb_ramps"
POTHOLES = "potholes"
STREET_CONSTRUCTION = "street_construction"
OUTDOOR_DINING = "outdoor_dining"
GENERAL = "General Construction/Plumbing"

# (complaint_type, descriptor) -> (topic, category). A descriptor of None matches any.
# The wording was read from this district's own complaints (city_investigator.probe).
COMPLAINTS: dict[tuple[str, str | None], tuple[str, str]] = {
    ("Sewer", "Street Flooding (SJ)"): (FLOODING, "street_flooding"),
    ("Sewer", "Highway Flooding (SH)"): (FLOODING, "street_flooding"),
    ("Sewer", "Catch Basin Clogged/Flooding (Use Comments) (SC)"): (FLOODING, "catch_basin"),
    ("Sewer", "Catch Basin Search (SC2)"): (FLOODING, "catch_basin"),
    ("Sewer", "Sewer Backup (Use Comments) (SA)"): (FLOODING, "sewer_backup"),
    ("Sewer", "Manhole Overflow (Use Comments) (SA1)"): (FLOODING, "manhole_overflow"),
    ("Sewer Maintenance", "Catch Basin Clogged"): (FLOODING, "catch_basin"),
    ("Sewer Maintenance", "Backup"): (FLOODING, "sewer_backup"),
    ("Sewer Maintenance", "Flooding on Street"): (FLOODING, "street_flooding"),
    # Sheds, scaffolds and other things standing on the sidewalk
    (GENERAL, "Sidewalk Shed/Pipe Scafford - Inadequate Defective/None"): (SIDEWALK, "shed_complaint"),
    ("Scaffold Safety", None): (SIDEWALK, "scaffold_safety"),
    ("Obstruction", None): (SIDEWALK, "obstruction"),
    ("Dumpster Complaint", "Blocking Sidewalk or Street"): (SIDEWALK, "obstruction"),
    # Street trees
    ("Damaged Tree", None): (TREES, "damaged_tree"),
    ("Dead/Dying Tree", None): (TREES, "dead_tree"),
    ("Overgrown Tree/Branches", None): (TREES, "overgrown_tree"),
    ("Root/Sewer/Sidewalk Condition", None): (TREES, "tree_roots"),
    ("Illegal Tree Damage", None): (TREES, "tree_harmed"),
    ("Uprooted Stump", None): (TREES, "stump"),
    ("Wood Pile Remaining", None): (TREES, "wood_pile"),
    # Façades
    (GENERAL, "Debris - Falling Or In Danger Of Falling"): (FACADES, "falling_debris"),
    (GENERAL, "Wall/Retaining Wall - Bulging/Cracked"): (FACADES, "wall_cracked"),
    (GENERAL, "Failure To Maintain"): (FACADES, "failure_to_maintain"),
    (GENERAL, "Building Shaking/Vibrating/Structural Stability"): (FACADES, "structural_stability"),
    (GENERAL, "Safety Netting/Guard Rails - Damaged/Inadequate/None (6 Stories/75 Feet Or Less)"): (FACADES, "netting"),
    ("BEST/Site Safety", "Safety Netting/Guard Rails - Damaged/Inadequate/None (Over 6 Stories/75 Feet)"): (FACADES, "netting"),
    # Broken sidewalks
    ("Sidewalk Condition", "Broken Sidewalk"): (SIDEWALK_DAMAGE, "broken_sidewalk"),
    ("Sidewalk Condition", "Sidewalk Collapsed"): (SIDEWALK_DAMAGE, "broken_sidewalk"),
    ("Sidewalk Condition", "Sidewalk Violation"): (SIDEWALK_DAMAGE, "sidewalk_violation_question"),
    ("Sidewalk Condition", "Defective Hardware"): (SIDEWALK_DAMAGE, "sidewalk_hazard"),
    ("Sidewalk Condition", "Sidewalk Grating - Defective"): (SIDEWALK_DAMAGE, "sidewalk_hazard"),
    ("Sidewalk Condition", "Cellar Door Open/Unprotected"): (SIDEWALK_DAMAGE, "sidewalk_hazard"),
    ("Sidewalk Condition", "Cellar Door Defective"): (SIDEWALK_DAMAGE, "sidewalk_hazard"),
    ("Sidewalk Condition", "Metal Protruding - Sign Stump"): (SIDEWALK_DAMAGE, "sidewalk_hazard"),
    # Curb ramps and curbs
    ("Sidewalk Condition", "Pedestrian Ramp Defective"): (CURB_RAMPS, "ramp_defective"),
    ("Curb Condition", "Broken Curb"): (CURB_RAMPS, "broken_curb"),
    ("Curb Condition", "Curb Defect-Metal Protruding"): (CURB_RAMPS, "broken_curb"),
    # Potholes and road damage
    ("Street Condition", "Pothole"): (POTHOLES, "pothole"),
    ("Street Condition", "Cave-in"): (POTHOLES, "cave_in"),
    ("Street Condition", "Failed Street Repair"): (POTHOLES, "failed_repair"),
    ("Street Condition", "Rough, Pitted or Cracked Roads"): (POTHOLES, "rough_road"),
    ("Street Condition", "Wear & Tear"): (POTHOLES, "rough_road"),
    ("Street Condition", "Defective Hardware"): (POTHOLES, "road_hardware"),
    # Street construction
    ("Sidewalk Condition", "Blocked - Construction"): (STREET_CONSTRUCTION, "construction_blocking"),
    ("Street Condition", "Blocked - Construction"): (STREET_CONSTRUCTION, "construction_blocking"),
    ("Street Condition", "Plate Condition - Noisy"): (STREET_CONSTRUCTION, "road_plate"),
    ("Street Condition", "Plate Condition - Shifted"): (STREET_CONSTRUCTION, "road_plate"),
    ("Street Condition", "Dumpster - Construction Waste"): (STREET_CONSTRUCTION, "construction_dumpster"),
    ("Sidewalk Condition", "Dumpster - Construction Waste"): (STREET_CONSTRUCTION, "construction_dumpster"),
    # Outdoor dining
    ("Outdoor Dining", "Sidewalk Zone Blocked"): (OUTDOOR_DINING, "dining_sidewalk_blocked"),
    ("Outdoor Dining", None): (OUTDOOR_DINING, "dining_complaint"),
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
# The façade filings also name owners and the engineers who inspected.
DROPPED_FIELDS = {"ownername", "owner_name", "owner_s_first_name", "owner_s_last_name",
                  "owner_s_business_name", "owner_s_house__", "owner_s_house_street_name",
                  "owner_s_phone__", "owner_s_zip_code", "owner_business_name",
                  "owner_bus_name", "owner_bus_street_name", "owner_city", "owner_state", "owner_zip",
                  "qewi_name", "qewi_nys_lic_no", "qewi_bus_name", "qewi_bus_street_name", "qewi_city",
                  "qewi_state", "qewi_zip", "callercity", "callerstate"}

# Central Park weather station (Iowa Environmental Mesonet ID "NYC").
RAIN_STATION = {"id": "NYC", "name": "Central Park weather station", "lat": 40.7790, "lon": -73.9692}
RAIN_START_YEAR = 2020

# Shed permits renew every 90 days; gaps up to this long are paperwork delay, not removal.
PERMIT_GAP_BRIDGE_DAYS = 30
# A gap longer than this means the shed came down and a different one went up later.
SEPARATE_SHED_DAYS = 180

# NYC Stormwater Flood Maps: modeled rain-driven flooding in design storms, citywide. The Mayor's
# Office of Climate and Environmental Justice (MOCEJ) publishes each scenario as an ArcGIS layer,
# found among its services by words in the name. The same maps are on NYC Open Data (9i7c-xyvv),
# but as Esri compressed geodatabases that open-source GIS libraries cannot read.
STORMWATER_DATASET = "9i7c-xyvv"
STORMWATER_PUBLISHER = {
    "name": "NYC Mayor's Office of Climate and Environmental Justice",
    "account": "mocej.nyc.data",
    "services": "https://services6.arcgis.com/yG5s3afENB5iO9fj/arcgis/rest/services",
}
# Not used: the limited storm (1.77 in/hr) is only in the Open Data geodatabases, and the extreme
# storm with 2080 sea levels times out on the ArcGIS server (504), even one shape at a time.
STORMWATER_SCENARIOS = [
    {"key": "moderate_current", "match": ("moderate", "current"), "title": "a moderate storm (2.13 in/hr) with today's sea levels"},
    {"key": "moderate_2050", "match": ("moderate", "2050"), "title": "a moderate storm (2.13 in/hr) with 2050 sea level rise"},
]
STORMWATER_CATEGORIES = {
    1: "nuisance flooding (4 in to 1 ft deep)",
    2: "deep and contiguous flooding (1 ft or deeper)",
    3: "flooding from future high tides",
}
