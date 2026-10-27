"""Agency records for the newer topics: what each city dataset says, where and when.

Each source names its dataset, how the snapshot selects this district's rows (several
where clauses, tried in order, because the city stores places in different column
types), what its records can and cannot show, and how one row becomes evidence. Rows
are placed by their own coordinates where they have them, otherwise at their tax lot.

Column names were read from the city's catalog (city_investigator.probe).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import shapely
from shapely.errors import GEOSException
from shapely.geometry import shape

from city_investigator import times
from city_investigator.config import CURB_RAMPS, FACADES, OUTDOOR_DINING, POTHOLES, SIDEWALK_DAMAGE, STREET_CONSTRUCTION, TREES
from city_investigator.evidence import Evidence, day, first, join_address, norm_bbl, norm_bin
from city_investigator.geo import point
from city_investigator.socrata import record_url

Box = tuple[float, float, float, float]  # south, west, north, east
LotFinder = Callable[[str | None], tuple[float | None, float | None, str | None]]  # bbl -> lat, lon, address
SINCE = "2019-01-01T00:00:00"
# Records that describe a standing state rather than an event: they apply at any date.
STATE_CATEGORIES = {"tree_inventory", "ramp_survey"}
FISP_STATUS = {
    "SAFE": "safe",
    "SWARMP": "safe with a repair and maintenance program",
    "UNSAFE": "unsafe",
}


@dataclass(frozen=True)
class District:
    """What the snapshot knows about the district when it selects rows."""

    box: Box  # around its tax lots
    lots: frozenset[str] = frozenset()  # their BBLs
    streets: tuple[str, ...] = ()  # street names in their addresses, as PLUTO writes them


def keep_all(row: dict[str, Any], district: District) -> bool:
    return True


@dataclass(frozen=True)
class Source:
    name: str  # snapshot file name
    dataset: str
    topic: str
    label: str  # for coverage notes
    caveat: str  # what the records cannot show
    where: Callable[[District], list[str]]  # SoQL where clauses, tried in order
    to_evidence: Callable[[dict[str, Any], str, LotFinder], Evidence | None]
    keep: Callable[[dict[str, Any], District], bool] = keep_all  # for rows a where clause cannot narrow


# Selecting rows


def polygon(box: Box) -> str:
    south, west, north, east = box
    return f"POLYGON(({west} {south}, {east} {south}, {east} {north}, {west} {north}, {west} {south}))"


def with_extra(clauses: list[str], extra: str) -> list[str]:
    return [f"{clause} AND {extra}" if extra else clause for clause in clauses]


def inside(columns: tuple[str, ...], extra: str = "") -> Callable[[District], list[str]]:
    """Rows whose geometry, in any of the columns, falls in the district's box."""
    return lambda district: with_extra([f"intersects({column}, '{polygon(district.box)}')" for column in columns], extra)


def in_district(column: str, extra: str = "") -> Callable[[District], list[str]]:
    """A community district column, in the forms the city uses."""
    forms = [f"{column} = '306'", f"{column} = 306", f"{column} = '306 BROOKLYN'", f"{column} = '06 BROOKLYN'"]
    return lambda district: with_extra(forms, extra)


def board_or_borough(column: str, bbl_column: str, extra: str = "") -> Callable[[District], list[str]]:
    """The district's forms first; then district 6 of every borough, and last all of Brooklyn,
    both narrowed to the district's tax lots by the source's keep."""
    wider = [
        f"{column} = '6'", f"{column} = 6", f"{column} = 'BK06'", f"{column} = '06'",
        f"starts_with({bbl_column}, '3')", f"{bbl_column} >= 3000000000 AND {bbl_column} < 4000000000",
    ]
    return lambda district: [*in_district(column, extra)(district), *with_extra(wider, extra)]


def on_streets(column: str, extra: str) -> Callable[[District], list[str]]:
    """For geometry stored as text: the district's street names first, then everything matching extra."""
    def where(district: District) -> list[str]:
        if not district.streets:
            return [extra]
        names = ", ".join("'" + street.replace("'", "''") + "'" for street in district.streets)
        return [f"{column} IN ({names}) AND {extra}", extra]

    return where


def on_lots(read_bbl: Callable[[dict[str, Any]], str | None]) -> Callable[[dict[str, Any], District], bool]:
    return lambda row, district: not district.lots or read_bbl(row) in district.lots


def in_box(*columns: str) -> Callable[[dict[str, Any], District], bool]:
    def keep(row: dict[str, Any], district: District) -> bool:
        lat, lon = center(row, *columns)
        south, west, north, east = district.box
        return lat is not None and lon is not None and south <= lat <= north and west <= lon <= east

    return keep


# Reading rows


def center(row: dict[str, Any], *columns: str) -> tuple[float | None, float | None]:
    """The center of a row's geometry: a GeoJSON or WKT value in one of the columns, or lat/lon fields."""
    for column in columns:
        value = row.get(column)
        try:
            if isinstance(value, dict) and "coordinates" in value:
                geometry = shape(value)
            elif isinstance(value, str) and value.strip()[:5].upper() in {"POINT", "LINES", "MULTI", "POLYG"}:
                geometry = shapely.from_wkt(value)
            elif isinstance(value, dict) and "latitude" in value:
                lat, lon = point(value, ("latitude", "longitude"))
                if lat is not None:
                    return lat, lon
                continue
            else:
                continue
        except (ValueError, TypeError, GEOSException):
            continue
        if not geometry.is_empty:
            middle = geometry.centroid
            return middle.y, middle.x
    return point(row, ("latitude", "longitude"))


def when(row: dict[str, Any], *keys: str) -> datetime | None:
    return times.parse(first(row, *keys))


def yes(value: Any) -> bool:
    return str(value or "").strip().lower() in {"y", "yes", "true", "1", "t"}


def between(*streets: Any) -> str:
    names = [str(street).strip().title() for street in streets if str(street or "").strip()]
    if len(names) >= 3:
        return f"on {names[0]} between {names[1]} and {names[2]}"
    return f"on {names[0]}" if names else ""


def evidence(
    row: dict[str, Any], source: Source, rid: str, category: str, summary: str, *,
    lat: float | None, lon: float | None, located_by: str, start: datetime | None = None,
    end: datetime | None = None, address: str | None = None, bbl: str | None = None,
    bin_: str | None = None, url_filter: dict[str, str] | None = None,
) -> Evidence:
    return Evidence(
        id=f"{source.name}:{rid}",
        kind="record",
        topic=source.topic,
        category=category,
        source=source.label,
        dataset=source.dataset,
        summary=summary,
        lat=lat,
        lon=lon,
        located_by=located_by,
        start=start,
        end=end,
        url=record_url(source.dataset, **(url_filter or {})),
        address=address,
        bbl=bbl,
        bin=bin_,
        raw=row,
    )


def bbl_from(row: dict[str, Any], key: str = "bbl") -> str | None:
    return norm_bbl(row.get(key))


def bbl_from_block_lot(row: dict[str, Any]) -> str | None:
    block, lot = str(row.get("block") or "").strip(), str(row.get("lot") or "").strip()
    if not (block.isdigit() and lot.isdigit()):
        return None
    return f"3{int(block):05d}{int(lot):04d}"


# One function per source


def tree_point(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = first(row, "globalid", "objectid")
    lat, lon = center(row, "geometry", "location")
    if not rid or lat is None:
        return None
    species = str(row.get("genusspecies") or "species not recorded").split(" - ")[-1]
    details = [
        f"trunk {row['dbh']} in across" if row.get("dbh") else None,
        f"condition {row['tpcondition']}" if row.get("tpcondition") else None,
        f"structure {row['tpstructure']}" if row.get("tpstructure") else None,
        f"risk rating {row['riskrating']}" if row.get("riskrating") else None,
    ]
    updated = when(row, "updateddate", "createddate")
    return evidence(
        row, SOURCES["tree_points"], str(rid), "tree_inventory",
        f"Street tree in the Parks inventory: {species}, " + ", ".join(d for d in details if d)
        + (f" (record updated {day(updated)})" if updated else ""),
        lat=lat, lon=lon, located_by="tree", url_filter={"globalid": str(rid)} if row.get("globalid") else None,
    )


def tree_inspection(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = first(row, "globalid", "objectid")
    lat, lon = center(row, "geometry", "location")
    inspected = when(row, "inspectiondate", "createddate")
    if not rid or lat is None or inspected is None:
        return None
    details = [
        str(row["inspectiontype"]) if row.get("inspectiontype") else None,
        f"tree condition {row['inspectiontpcondition']}" if row.get("inspectiontpcondition") else None,
        f"structure {row['inspectiontpstructure']}" if row.get("inspectiontpstructure") else None,
        f"sidewalk damage rating {row['swdamagerating']}" if row.get("swdamagerating") else None,
        f"status {row['inspectionstatus']}" if row.get("inspectionstatus") else None,
    ]
    return evidence(
        row, SOURCES["tree_inspections"], str(rid), "tree_inspection",
        f"Parks tree inspection on {day(inspected)}: " + ", ".join(d for d in details if d),
        lat=lat, lon=lon, located_by="tree", start=inspected, end=when(row, "closeddate"),
        url_filter={"globalid": str(rid)} if row.get("globalid") else None,
    )


def tree_work_order(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = first(row, "globalid", "objectid")
    lat, lon = center(row, "geometry", "location")
    created = when(row, "createddate")
    if not rid or created is None:
        return None
    address = join_address(row.get("buildingnumber"), row.get("streetname"))
    if lat is None:
        lat, lon, _ = lot(bbl_from(row))
    if lat is None:
        return None
    finished = when(row, "actualfinishdate", "closeddate")
    canceled = when(row, "canceldate")
    outcome = (
        f"finished {day(finished)}" if finished
        else f"canceled {day(canceled)}" + (f" ({row['cancelreason']})" if row.get("cancelreason") else "") if canceled
        else f"status {row.get('wostatus') or 'unknown'}"
    )
    kind = " / ".join(str(row[key]) for key in ("wotype", "wocategory") if row.get(key))
    return evidence(
        row, SOURCES["tree_work_orders"], str(rid), "tree_work_order",
        f"Parks tree work order ({kind or 'type not recorded'}) created {day(created)}, {outcome}",
        lat=lat, lon=lon, located_by="tree", start=created, end=finished or canceled, address=address,
        bbl=bbl_from(row), url_filter={"globalid": str(rid)} if row.get("globalid") else None,
    )


def facade_filing(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = first(row, "tr6_no", "control_no")
    bbl = bbl_from_block_lot(row)
    filed = when(row, "filing_date", "submitted_on")
    lat, lon, lot_address = lot(bbl)
    if not rid or filed is None or lat is None:
        return None
    status = str(row.get("filing_status") or "").strip().upper()
    meaning = FISP_STATUS.get(status)
    address = join_address(row.get("house_no"), row.get("street_name")) or lot_address
    summary = (
        f"Façade inspection filing (Local Law 11, cycle {row.get('cycle') or '?'}) filed {day(filed)}: "
        + (f"{status} ({meaning})" if meaning else status or "status not recorded")
        + (f"; status now {row['current_status']}" if row.get("current_status") else "")
    )
    return evidence(
        row, SOURCES["facade_filings"], str(rid), "facade_filing", summary,
        lat=lat, lon=lon, located_by="lot", start=filed, address=address, bbl=bbl, bin_=norm_bin(row.get("bin")),
        url_filter={"tr6_no": str(rid)} if row.get("tr6_no") else None,
    )


SIDEWALK_DEFECTS = {
    "trip_haz": "trip hazard", "broken": "broken", "undermined": "undermined", "patchwork": "patchwork",
    "hardware": "defective hardware", "slope": "bad slope", "sw_missing": "missing sidewalk", "flag": "uneven flags",
}


def sidewalk_violation(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = first(row, "violationid", "swv_number")
    issued = when(row, "vissuedate", "entrydate")
    bbl = bbl_from(row, "bblid")
    lat, lon, lot_address = lot(bbl)
    if not rid or issued is None or lat is None:
        return None
    defects = [label for key, label in SIDEWALK_DEFECTS.items() if yes(row.get(key))]
    dismissed = when(row, "vdismissdate")
    return evidence(
        row, SOURCES["sidewalk_violations"], str(rid), "sidewalk_violation",
        f"DOT sidewalk violation issued {day(issued)}" + (f": {', '.join(defects)}" if defects else "")
        + (f"; dismissed {day(dismissed)} (repaired, or withdrawn)" if dismissed else "; not dismissed"),
        lat=lat, lon=lon, located_by="lot", start=issued, end=dismissed,
        address=join_address(row.get("house_num"), row.get("onstname")) or lot_address, bbl=bbl,
        url_filter={"violationid": str(rid)} if row.get("violationid") else None,
    )


def tree_sidewalk_damage(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = first(row, "atdid", "atd_number")
    issued = when(row, "atdissuedate", "inspect_date")
    bbl = bbl_from(row, "bblid")
    lat, lon, lot_address = lot(bbl)
    if not rid or issued is None or lat is None:
        return None
    dismissed = when(row, "atddismissedon")
    return evidence(
        row, SOURCES["tree_sidewalk_damage"], str(rid), "tree_sidewalk_damage",
        f"DOT record of sidewalk damage caused by a street tree, {day(issued)}"
        + (f"; dismissed {day(dismissed)}" if dismissed else ""),
        lat=lat, lon=lon, located_by="lot", start=issued, end=dismissed,
        address=join_address(row.get("house_num"), row.get("onstname")) or lot_address, bbl=bbl,
        url_filter={"atdid": str(rid)} if row.get("atdid") else None,
    )


def ramp_survey(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = first(row, "rampid", "cornerid")
    lat, lon = center(row, "the_geom", "location")
    if not rid or lat is None:
        return None
    corner = " and ".join(str(row[key]).title() for key in ("stname1", "stname2") if row.get(key))
    details = [
        f"ponding {row['ponding']}" if row.get("ponding") else None,
        f"detectable warning surface {row['dws_conditions']}" if row.get("dws_conditions") else None,
        f"running slope {row['ramp_running_slope_total']}" if row.get("ramp_running_slope_total") else None,
        f"cross slope {row['ramp_cross_slope']}" if row.get("ramp_cross_slope") else None,
        f"width {row['ramp_width']}" if row.get("ramp_width") else None,
        f"obstacles {row['obstacles_ramp']}" if row.get("obstacles_ramp") else None,
    ]
    return evidence(
        row, SOURCES["ramps"], str(rid), "ramp_survey",
        f"Curb ramp{f' at {corner}' if corner else ''} in DOT's ramp survey: " + (", ".join(d for d in details if d) or "no details recorded"),
        lat=lat, lon=lon, located_by="ramp", address=corner or None, url_filter={"rampid": str(rid)} if row.get("rampid") else None,
    )


def ramp_complaint(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = row.get("complaint_id")
    filed = when(row, "complaint_date")
    bbl = bbl_from_block_lot(row)
    lat, lon, lot_address = lot(bbl)
    if not rid or filed is None or lat is None:
        return None
    repaired = when(row, "temp_repair_date")
    corner = " and ".join(str(row[key]).title() for key in ("street_name1", "street_name2") if row.get(key))
    return evidence(
        row, SOURCES["ramp_complaints"], str(rid), "ramp_complaint_dot",
        f"DOT pedestrian ramp complaint on {day(filed)}{f' at {corner}' if corner else ''}"
        + (f"; temporary repair ({row.get('temp_repair_type') or 'type not recorded'}) on {day(repaired)}" if repaired else ""),
        lat=lat, lon=lon, located_by="lot", start=filed, end=repaired, address=corner or lot_address, bbl=bbl,
        url_filter={"complaint_id": str(rid)},
    )


def pothole_order(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = row.get("defnum")
    reported = when(row, "rptdate")
    lat, lon = center(row, "the_geom")
    if not rid or reported is None or lat is None:
        return None
    closed = when(row, "rptclosed")
    where = between(row.get("onprimname"), row.get("frmprimnam"), row.get("toprimname"))
    return evidence(
        row, SOURCES["pothole_orders"], str(rid), "pothole_repair",
        f"DOT pothole work order {rid}: reported {day(reported)}, closed {day(closed)}" + (f", {where}" if where else ""),
        lat=lat, lon=lon, located_by="street segment", start=reported, end=closed,
        address=join_address(row.get("housenum"), row.get("onprimname")) or None, url_filter={"defnum": str(rid)},
    )


def street_permit(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = first(row, "permitnumber", "applicationtrackingid")
    start = when(row, "issuedworkstartdate", "permitissuedate")
    lat, lon = center(row, "locationgeometry", "wkt")
    if not rid or start is None or lat is None:
        return None
    purpose = str(row.get("permitpurposecomments") or "").strip()
    where = between(row.get("onstreetname"), row.get("fromstreetname"), row.get("tostreetname"))
    end = when(row, "issuedworkenddate")
    return evidence(
        row, SOURCES["street_permits"], str(rid), "street_permit",
        f"DOT street construction permit: {row.get('permittypedesc') or 'type not recorded'}"
        + (f" ({purpose[:90]})" if purpose else "") + f", work allowed {day(start)} to {day(end)}" + (f" {where}" if where else ""),
        lat=lat, lon=lon, located_by="street segment", start=start, end=end,
        address=join_address(row.get("permithousenumber"), row.get("onstreetname")) or None,
        url_filter={"permitnumber": str(rid)} if row.get("permitnumber") else None,
    )


def street_closure(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = row.get("uniqueid")
    start = when(row, "work_start_date")
    lat, lon = center(row, "the_geom")
    if not rid or start is None or lat is None:
        return None
    end = when(row, "work_end_date")
    where = between(row.get("onstreetname"), row.get("fromstreetname"), row.get("tostreetname"))
    return evidence(
        row, SOURCES["street_closures"], str(rid), "street_closure",
        f"Street closure for construction ({row.get('purpose') or 'purpose not recorded'}), {day(start)} to {day(end)}"
        + (f" {where}" if where else ""),
        lat=lat, lon=lon, located_by="street segment", start=start, end=end, url_filter={"uniqueid": str(rid)},
    )


def dining_license(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    bbl = bbl_from(row)
    issued = when(row, "license_issue_date")
    lat, lon = center(row, "location")
    lot_lat, lot_lon, lot_address = lot(bbl)
    if lat is None:
        lat, lon = lot_lat, lot_lon
    rid = f"{bbl or 'nobbl'}:{row.get('license_type') or ''}:{row.get('license_issue_date') or ''}"
    if issued is None or lat is None:
        return None
    expires = when(row, "license_expiration_date")
    return evidence(
        row, SOURCES["dining_licenses"], rid.replace(" ", "_"), "dining_license",
        f"Dining Out NYC license ({row.get('license_type') or 'type not recorded'}): {row.get('license_status') or 'status not recorded'}, "
        f"valid {day(issued)} to {day(expires)}",
        lat=lat, lon=lon, located_by="building", start=issued, end=expires, address=lot_address, bbl=bbl,
        bin_=norm_bin(row.get("bin")), url_filter={"bbl": str(row["bbl"])} if row.get("bbl") else None,
    )


def dining_inspection(row: dict[str, Any], dataset: str, lot: LotFinder) -> Evidence | None:
    rid = row.get("restaurantinspectionid")
    inspected = when(row, "inspectedon")
    lat, lon = point(row, ("latitude", "longitude"))
    bbl = bbl_from(row)
    _, _, lot_address = lot(bbl)
    if not rid or inspected is None or lat is None:
        return None
    findings = [
        f"sidewalk seating compliant: {row['issidewaycompliant']}" if row.get("issidewaycompliant") else None,
        f"roadway seating compliant: {row['isroadwaycompliant']}" if row.get("isroadwaycompliant") else None,
        f"skipped: {row['skippedreason']}" if row.get("skippedreason") else None,
    ]
    return evidence(
        row, SOURCES["dining_inspections"], str(rid), "dining_inspection",
        f"Open Restaurants inspection on {day(inspected)}: " + ("; ".join(f for f in findings if f) or "no findings recorded"),
        lat=lat, lon=lon, located_by="building", start=inspected, address=lot_address, bbl=bbl,
        url_filter={"restaurantinspectionid": str(rid)},
    )


SOURCES: dict[str, Source] = {
    source.name: source
    for source in (
        Source("tree_points", "hn5i-inap", TREES, "Parks street tree inventory",
               "It lists trees Parks manages; trees on private property are missing, and condition is as last recorded.",
               inside(("location", "geometry")), tree_point),
        Source("tree_inspections", "4pt5-3vv4", TREES, "Parks tree inspections",
               "Trees are inspected after a complaint or on a schedule; a tree nobody reported may never have been inspected.",
               inside(("location", "geometry"), f"inspectiondate >= '{SINCE}'"), tree_inspection),
        Source("tree_work_orders", "bdjm-n7q4", TREES, "Parks tree work orders",
               "A work order shows planned or finished work; canceled orders stay in the records.",
               inside(("geometry", "location"), f"createddate >= '{SINCE}'"), tree_work_order),
        Source("facade_filings", "xubg-57si", FACADES, "Façade inspection filings (Local Law 11)",
               "Only buildings taller than six stories must file, every five years; a lower building has no filings, which says nothing about its safety.",
               lambda _: ["upper(borough) = 'BROOKLYN'", "borough = '3'", "borough = 3"], facade_filing,
               on_lots(lambda row: bbl_from_block_lot(row))),
        Source("sidewalk_violations", "6kbp-uz6m", SIDEWALK_DAMAGE, "DOT sidewalk violations",
               "DOT inspects after complaints or in planned sweeps; a dismissal means the repair was accepted or the violation withdrawn.",
               board_or_borough("cb", "bblid", "vissuedate >= '2015-01-01T00:00:00'"), sidewalk_violation,
               on_lots(lambda row: bbl_from(row, "bblid"))),
        Source("tree_sidewalk_damage", "j6v2-6uxq", SIDEWALK_DAMAGE, "DOT sidewalk damage from street trees",
               "Damage caused by a street tree is recorded separately from the owner's violations.",
               board_or_borough("cb", "bblid"), tree_sidewalk_damage, on_lots(lambda row: bbl_from(row, "bblid"))),
        Source("ramps", "ufzp-rrqu", CURB_RAMPS, "DOT pedestrian ramp survey",
               "Each ramp was surveyed once (the dataset was last updated in 2021); later repairs may be missing.",
               inside(("the_geom",)), ramp_survey),
        Source("ramp_complaints", "jagj-gttd", CURB_RAMPS, "DOT pedestrian ramp complaints",
               "Complaints made to DOT's ramp program, with any temporary repair.",
               in_district("community_district"), ramp_complaint),
        Source("pothole_orders", "x9wy-ing4", POTHOLES, "DOT pothole work orders (closed)",
               "Only closed work orders are published: a pothole still waiting for repair has no record here.",
               inside(("the_geom",), f"rptdate >= '{SINCE}'"), pothole_order),
        Source("street_permits", "tqtj-sjs8", STREET_CONSTRUCTION, "DOT street construction permits",
               "A permit shows work was allowed in its window, not that it happened; emergency work can start before its permit.",
               # Its geometry is stored as text, so the server cannot select by area.
               on_streets("onstreetname", "upper(boroughname) = 'BROOKLYN' AND issuedworkenddate >= '2024-01-01T00:00:00'"),
               street_permit, in_box("locationgeometry", "wkt")),
        Source("street_closures", "i6b5-j7bu", STREET_CONSTRUCTION, "DOT street closures for construction",
               "Planned closures; the work itself can be shorter.",
               inside(("the_geom",), "work_end_date >= '2023-01-01T00:00:00'"), street_closure),
        Source("dining_licenses", "fpeh-f7ci", OUTDOOR_DINING, "Dining Out NYC licenses",
               "Licenses under the program that began in 2024; the earlier Open Restaurants program is in a separate historical dataset.",
               lambda district: [*in_district("community_board")(district), *inside(("location",))(district)], dining_license),
        Source("dining_inspections", "4dx7-axux", OUTDOOR_DINING, "Open Restaurants inspections (2020 to 2024)",
               "Inspections from the earlier program only.",
               lambda district: [*in_district("communityboard")(district), "communityboard = '6' AND upper(borough) = 'BROOKLYN'"],
               dining_inspection),
    )
}


def sources_for(topic: str) -> list[Source]:
    return [source for source in SOURCES.values() if source.topic == topic]
