from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree
from zipfile import ZipFile

from energy_logic import haversine_distance_m


LEGACY_VALIDATION_COLUMNS = (
    "PointID",
    "T",
    "Stop",
    "Latitude",
    "Longitude",
    "Alpha",
    "Total_Distance",
    "Distance",
)
SPREADSHEET_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "package": "http://schemas.openxmlformats.org/package/2006/relationships",
}
WORKBOOK_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def discover_legacy_validation_files(search_root: Path) -> List[Dict[str, str]]:
    references: List[Dict[str, str]] = []

    for workbook_path in sorted(search_root.rglob("BD_Ligne*.xlsx")):
        try:
            sheet_name = read_first_sheet_name(workbook_path)
        except Exception:
            sheet_name = workbook_path.stem

        references.append(
            {
                "name": workbook_path.stem,
                "sheet_name": sheet_name,
                "path": str(workbook_path),
            }
        )

    return references


def read_first_sheet_name(workbook_path: Path) -> str:
    with ZipFile(workbook_path) as workbook_zip:
        workbook_root = ElementTree.fromstring(workbook_zip.read("xl/workbook.xml"))
        first_sheet = workbook_root.find("main:sheets/main:sheet", SPREADSHEET_NS)
        if first_sheet is None:
            return workbook_path.stem
        return first_sheet.attrib.get("name", workbook_path.stem)


def column_reference_to_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha())
    value = 0
    for character in letters:
        value = value * 26 + (ord(character.upper()) - 64)
    return max(value - 1, 0)


def coerce_excel_value(value: str) -> Any:
    if value in ("", None):
        return ""
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return value
    if numeric_value.is_integer():
        return int(numeric_value)
    return numeric_value


def read_first_sheet_rows(workbook_path: Path) -> tuple[str, List[List[Any]]]:
    with ZipFile(workbook_path) as workbook_zip:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in workbook_zip.namelist():
            shared_root = ElementTree.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
            for string_item in shared_root.findall("main:si", SPREADSHEET_NS):
                text_parts = [node.text or "" for node in string_item.findall(".//main:t", SPREADSHEET_NS)]
                shared_strings.append("".join(text_parts))

        workbook_root = ElementTree.fromstring(workbook_zip.read("xl/workbook.xml"))
        rels_root = ElementTree.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            relation.attrib["Id"]: relation.attrib["Target"]
            for relation in rels_root.findall("package:Relationship", SPREADSHEET_NS)
        }

        first_sheet = workbook_root.find("main:sheets/main:sheet", SPREADSHEET_NS)
        if first_sheet is None:
            return workbook_path.stem, []

        sheet_name = first_sheet.attrib.get("name", workbook_path.stem)
        relationship_id = first_sheet.attrib.get(WORKBOOK_REL_NS, "")
        target = rel_map.get(relationship_id, "")
        worksheet_path = target if target.startswith("xl/") else f"xl/{target}"

        worksheet_root = ElementTree.fromstring(workbook_zip.read(worksheet_path))
        rows: List[List[Any]] = []

        for row in worksheet_root.findall("main:sheetData/main:row", SPREADSHEET_NS):
            indexed_values: Dict[int, Any] = {}

            for cell in row.findall("main:c", SPREADSHEET_NS):
                cell_reference = cell.attrib.get("r", "")
                column_index = column_reference_to_index(cell_reference)
                cell_type = cell.attrib.get("t")
                raw_value = ""

                if cell_type == "inlineStr":
                    text_node = cell.find(".//main:t", SPREADSHEET_NS)
                    raw_value = "" if text_node is None else text_node.text or ""
                else:
                    value_node = cell.find("main:v", SPREADSHEET_NS)
                    raw_value = "" if value_node is None else value_node.text or ""
                    if cell_type == "s" and raw_value != "":
                        raw_value = shared_strings[int(raw_value)]

                indexed_values[column_index] = coerce_excel_value(raw_value)

            if not indexed_values:
                continue

            max_index = max(indexed_values)
            rows.append([indexed_values.get(index, "") for index in range(max_index + 1)])

        return sheet_name, rows


def load_legacy_validation_profile(workbook_path: Path) -> Dict[str, Any]:
    sheet_name, raw_rows = read_first_sheet_rows(workbook_path)
    points: List[Dict[str, Any]] = []

    for row in raw_rows:
        normalized_row = list(row[: len(LEGACY_VALIDATION_COLUMNS)])
        while len(normalized_row) < len(LEGACY_VALIDATION_COLUMNS):
            normalized_row.append("")

        point = dict(zip(LEGACY_VALIDATION_COLUMNS, normalized_row))
        if point["Latitude"] == "" or point["Longitude"] == "":
            continue

        point["PointID"] = str(point["PointID"])
        point["Stop"] = int(point["Stop"] or 0)
        point["Latitude"] = float(point["Latitude"])
        point["Longitude"] = float(point["Longitude"])
        point["Alpha"] = float(point["Alpha"] or 0.0)
        point["Total_Distance"] = float(point["Total_Distance"] or 0.0)
        point["Distance"] = float(point["Distance"] or 0.0)
        point["T"] = float(point["T"] or 0.0)
        points.append(point)

    non_zero_distances = [point["Distance"] for point in points if point["Distance"] > 0]
    total_distance_m = max((point["Total_Distance"] for point in points), default=0.0)

    return {
        "path": str(workbook_path),
        "sheet_name": sheet_name,
        "points": points,
        "point_count": len(points),
        "stop_count": sum(1 for point in points if point["Stop"] == 0),
        "total_distance_m": total_distance_m,
        "total_distance_km": total_distance_m / 1000.0,
        "mean_step_distance_m": mean(non_zero_distances) if non_zero_distances else 0.0,
        "mean_abs_alpha_rad": mean(abs(point["Alpha"]) for point in points) if points else 0.0,
        "start_point": points[0] if points else None,
        "end_point": points[-1] if points else None,
    }


def build_current_profile_summary(
    raw_segments: List[Dict[str, Any]],
    results: Dict[str, Any],
) -> Dict[str, Any]:
    current_points: List[Dict[str, Any]] = []

    for segment in raw_segments:
        geo_points = segment.get("geo_points", [])
        for point_index, point in enumerate(geo_points):
            if (
                current_points
                and point_index == 0
                and current_points[-1]["lat"] == point.get("lat")
                and current_points[-1]["lon"] == point.get("lon")
            ):
                continue
            current_points.append(point)

    step_distances = []
    for index in range(len(current_points) - 1):
        step_distances.append(
            haversine_distance_m(
                current_points[index]["lat"],
                current_points[index]["lon"],
                current_points[index + 1]["lat"],
                current_points[index + 1]["lon"],
            )
        )

    weighted_abs_slopes = [
        segment["abs_slope_rad"] * segment["distance_m"]
        for segment in results["segments"]
    ]
    total_distance_m = results["total_distance_km"] * 1000.0

    return {
        "point_count": len(current_points),
        "stop_count": len(raw_segments) + 1 if raw_segments else 0,
        "total_distance_m": total_distance_m,
        "total_distance_km": results["total_distance_km"],
        "mean_step_distance_m": mean(step_distances) if step_distances else 0.0,
        "mean_abs_alpha_rad": (
            sum(weighted_abs_slopes) / total_distance_m if total_distance_m > 0 else 0.0
        ),
        "start_point": current_points[0] if current_points else None,
        "end_point": current_points[-1] if current_points else None,
    }


def compare_trip_with_legacy_reference(
    raw_segments: List[Dict[str, Any]],
    results: Dict[str, Any],
    validation_path: str,
) -> Dict[str, Any]:
    legacy_profile = load_legacy_validation_profile(Path(validation_path))
    current_profile = build_current_profile_summary(raw_segments, results)

    legacy_distance_m = legacy_profile["total_distance_m"]
    current_distance_m = current_profile["total_distance_m"]
    distance_gap_m = current_distance_m - legacy_distance_m

    start_gap_m = None
    if current_profile["start_point"] and legacy_profile["start_point"]:
        start_gap_m = haversine_distance_m(
            current_profile["start_point"]["lat"],
            current_profile["start_point"]["lon"],
            legacy_profile["start_point"]["Latitude"],
            legacy_profile["start_point"]["Longitude"],
        )

    end_gap_m = None
    if current_profile["end_point"] and legacy_profile["end_point"]:
        end_gap_m = haversine_distance_m(
            current_profile["end_point"]["lat"],
            current_profile["end_point"]["lon"],
            legacy_profile["end_point"]["Latitude"],
            legacy_profile["end_point"]["Longitude"],
        )

    return {
        "reference_name": Path(validation_path).stem,
        "reference_path": validation_path,
        "sheet_name": legacy_profile["sheet_name"],
        "legacy": legacy_profile,
        "current": current_profile,
        "distance_gap_m": distance_gap_m,
        "distance_gap_km": distance_gap_m / 1000.0,
        "distance_gap_pct": (
            (distance_gap_m / legacy_distance_m) * 100.0 if legacy_distance_m > 0 else 0.0
        ),
        "point_gap": current_profile["point_count"] - legacy_profile["point_count"],
        "stop_gap": current_profile["stop_count"] - legacy_profile["stop_count"],
        "mean_step_gap_m": current_profile["mean_step_distance_m"] - legacy_profile["mean_step_distance_m"],
        "mean_abs_alpha_gap_rad": (
            current_profile["mean_abs_alpha_rad"] - legacy_profile["mean_abs_alpha_rad"]
        ),
        "start_gap_m": start_gap_m,
        "end_gap_m": end_gap_m,
    }
