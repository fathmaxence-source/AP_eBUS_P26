from __future__ import annotations

import csv
import html
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from project_paths import EXPORTS_DIR


BUS_FIELD_LABELS = [
    ("mass_kg", "Masse du bus", "kg"),
    ("g", "Gravité", "m/s²"),
    ("air_density", "Densité de l’air", "kg/m³"),
    ("rolling_coeff", "Coefficient de roulement", ""),
    ("frontal_area_m2", "Surface frontale", "m²"),
    ("drag_coeff", "Coefficient de traînée", ""),
    ("aux_power_kw", "Puissance auxiliaire", "kW"),
]

SEGMENT_PREFERRED_FIELDS = [
    "name",
    "distance_m",
    "time_s",
    "speed_m_s",
    "speed_km_h",
    "slope_rad",
    "acceleration_m_s2",
    "turn_points_count",
    "sharp_turn_count",
    "mean_turn_angle_deg",
    "max_turn_angle_deg",
    "turn_penalty_kw",
    "total_power_kw",
    "energy_kwh",
]

SCENARIO_PREFERRED_FIELDS = [
    "name",
    "is_reference",
    "total_energy_kwh",
    "specific_consumption_kwh_km",
    "delta_energy_kwh",
    "delta_energy_pct",
]


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    slug = re.sub(r"[^A-Za-z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "analyse"


def _get_trip_summaries(gtfs_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    trip_summaries = gtfs_data.get("trip_summaries")
    if trip_summaries:
        return list(trip_summaries)

    trip = gtfs_data.get("trip", {})
    stop_names = gtfs_data.get("stop_names", [])
    return [
        {
            "trip_id": trip.get("trip_id", ""),
            "headsign": trip.get("trip_headsign", ""),
            "direction_id": trip.get("direction_id", ""),
            "stop_names": stop_names,
            "segment_count": max(len(stop_names) - 1, 0),
        }
    ]


def _get_reference_distance_km(results: Dict[str, Any]) -> float:
    return float(results.get("reference_total_distance_km", results.get("total_distance_km", 0.0)))


def _get_reference_energy_kwh(results: Dict[str, Any]) -> float:
    return float(results.get("reference_total_energy_kwh", results.get("total_energy_kwh", 0.0)))


def _get_reference_turn_energy_kwh(results: Dict[str, Any]) -> float:
    return float(results.get("reference_total_turn_energy_kwh", results.get("total_turn_energy_kwh", 0.0)))


def _get_reference_turn_points(results: Dict[str, Any]) -> int:
    return int(results.get("reference_total_turn_points", results.get("total_turn_points", 0)))


def _get_reference_sharp_turns(results: Dict[str, Any]) -> int:
    return int(results.get("reference_total_sharp_turns", results.get("total_sharp_turns", 0)))


def _analysis_unit_label(results: Dict[str, Any]) -> str:
    return str(results.get("analysis_unit_label", "trajet sélectionné"))


def _analysis_count_label(results: Dict[str, Any]) -> str:
    if _analysis_unit_label(results) == "aller-retour":
        return "Nombre d’allers-retours"
    return "Nombre de répétitions du trajet"


def _ordered_fields(rows: List[Dict[str, Any]], preferred: List[str]) -> List[str]:
    seen = set()
    fields: List[str] = []
    for field_name in preferred:
        for row in rows:
            if field_name in row and field_name not in seen:
                seen.add(field_name)
                fields.append(field_name)
                break
    extra_fields = sorted(
        {
            field_name
            for row in rows
            for field_name in row.keys()
            if field_name not in seen
        }
    )
    fields.extend(extra_fields)
    return fields


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def _write_csv(rows: List[Dict[str, Any]], output_path: Path, preferred_fields: List[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return

    fieldnames = _ordered_fields(rows, preferred_fields)
    with output_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def build_default_report_name(gtfs_data: Dict[str, Any], results: Dict[str, Any]) -> str:
    route_short = gtfs_data.get("route", {}).get("route_short_name") or gtfs_data.get("trip", {}).get("route_id") or "ligne"
    route_name = gtfs_data.get("route_name") or ""
    unit_slug = _slugify(_analysis_unit_label(results))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"rapport_{_slugify(route_short)}_{_slugify(route_name) or 'trajet'}_{unit_slug}_{stamp}.html"


def resolve_report_output_path(
    gtfs_data: Dict[str, Any],
    results: Dict[str, Any],
    requested_output: str | Path | None = None,
    export_root: str | Path | None = None,
) -> Path:
    if requested_output is None:
        root = Path(export_root) if export_root is not None else EXPORTS_DIR / "rapports"
        root.mkdir(parents=True, exist_ok=True)
        return root / build_default_report_name(gtfs_data, results)

    output_path = Path(requested_output)
    if output_path.exists() and output_path.is_dir():
        output_path = output_path / build_default_report_name(gtfs_data, results)
    elif output_path.suffix.lower() != ".html":
        if output_path.exists() or output_path.suffix:
            output_path = output_path.with_suffix(".html")
        else:
            output_path = output_path / build_default_report_name(gtfs_data, results)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _render_metric_cards(results: Dict[str, Any]) -> str:
    metrics = [
        ("Distance cumulée", f"{results['total_distance_km']:.3f} km"),
        ("Énergie cumulée", f"{results['total_energy_kwh']:.4f} kWh"),
        ("Consommation spécifique", f"{results['specific_consumption_kwh_km']:.4f} kWh/km"),
        (_analysis_count_label(results), str(results.get("analysis_unit_count", 1))),
        ("Nombre de bus", str(results.get("bus_count", 1))),
        ("Virages détectés (réf.)", str(_get_reference_turn_points(results))),
    ]
    return "".join(
        (
            '<div class="metric-card">'
            f"<span>{html.escape(label)}</span>"
            f"<strong>{html.escape(value)}</strong>"
            "</div>"
        )
        for label, value in metrics
    )


def _render_trip_summaries(gtfs_data: Dict[str, Any]) -> str:
    items = []
    for summary in _get_trip_summaries(gtfs_data):
        direction = summary.get("headsign") or summary.get("direction_id") or "N/A"
        stops = " → ".join(summary.get("stop_names", []))
        items.append(
            "<div class=\"trip-block\">"
            f"<h4>{html.escape(summary.get('trip_id', 'Trip'))}</h4>"
            f"<p><strong>Direction :</strong> {html.escape(direction)}</p>"
            f"<p><strong>Segments :</strong> {summary.get('segment_count', 0)}</p>"
            f"<p><strong>Arrêts :</strong> {html.escape(stops)}</p>"
            "</div>"
        )
    return "".join(items)


def _render_bus_table(results: Dict[str, Any]) -> str:
    bus_values = results.get("bus_parameters", {})
    rows = []
    mode = "Valeurs par défaut" if results.get("bus_parameters_mode") == "default" else "Paramètres personnalisés"
    rows.append(
        "<tr><th>Mode</th><td colspan=\"2\">"
        f"{html.escape(mode)}</td></tr>"
    )
    for field_name, label, unit in BUS_FIELD_LABELS:
        raw_value = bus_values.get(field_name, "")
        if isinstance(raw_value, float):
            if field_name == "mass_kg":
                value = f"{raw_value:.1f}"
            elif field_name in {"g", "air_density", "drag_coeff"}:
                value = f"{raw_value:.3f}"
            elif field_name == "rolling_coeff":
                value = f"{raw_value:.4f}"
            else:
                value = f"{raw_value:.2f}"
        else:
            value = str(raw_value)
        rows.append(
            "<tr>"
            f"<th>{html.escape(label)}</th>"
            f"<td>{html.escape(value)}</td>"
            f"<td>{html.escape(unit)}</td>"
            "</tr>"
        )
    return "".join(rows)


def _render_key_value_table(items: Iterable[tuple[str, str]]) -> str:
    rows = []
    for label, value in items:
        rows.append(
            "<tr>"
            f"<th>{html.escape(label)}</th>"
            f"<td>{html.escape(value)}</td>"
            "</tr>"
        )
    return "".join(rows)


def _render_scenarios(results: Dict[str, Any]) -> str:
    comparisons = results.get("scenario_comparisons", [])
    if not comparisons:
        return "<p>Aucun scénario comparé.</p>"

    rows = []
    for scenario in comparisons:
        delta_text = (
            "Référence"
            if scenario.get("is_reference")
            else f"{scenario.get('delta_energy_kwh', 0.0):+.4f} kWh ({scenario.get('delta_energy_pct', 0.0):+.1f} %)"
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(scenario.get('name', '')))}</td>"
            f"<td>{scenario.get('total_energy_kwh', 0.0):.4f}</td>"
            f"<td>{scenario.get('specific_consumption_kwh_km', 0.0):.4f}</td>"
            f"<td>{html.escape(delta_text)}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Scénario</th><th>Énergie (kWh)</th><th>Consommation (kWh/km)</th><th>Écart</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_segments(results: Dict[str, Any]) -> str:
    rows = []
    for segment in results.get("segments", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(segment.get('name', '')))}</td>"
            f"<td>{segment.get('distance_m', 0.0):.1f}</td>"
            f"<td>{segment.get('time_s', 0.0):.1f}</td>"
            f"<td>{segment.get('speed_km_h', 0.0):.2f}</td>"
            f"<td>{segment.get('slope_rad', 0.0):.5f}</td>"
            f"<td>{segment.get('acceleration_m_s2', 0.0):.4f}</td>"
            f"<td>{segment.get('sharp_turn_count', 0)}</td>"
            f"<td>{segment.get('turn_penalty_kw', 0.0):.2f}</td>"
            f"<td>{segment.get('total_power_kw', 0.0):.2f}</td>"
            f"<td>{segment.get('energy_kwh', 0.0):.4f}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr>"
        "<th>Segment</th><th>Distance (m)</th><th>Temps (s)</th><th>Vitesse (km/h)</th>"
        "<th>Pente (rad)</th><th>Accélération (m/s²)</th><th>Virages marqués</th>"
        "<th>Pénalité virages (kW)</th><th>Puissance (kW)</th><th>Énergie (kWh)</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_validation(results: Dict[str, Any]) -> str:
    validation = results.get("historical_validation")
    if not validation:
        return "<p>Aucune validation historique sélectionnée.</p>"

    items = [
        ("Référence", validation.get("reference_name", "")),
        ("Feuille", validation.get("sheet_name", "")),
        ("Distance actuelle", f"{validation['current']['total_distance_km']:.3f} km"),
        ("Distance historique", f"{validation['legacy']['total_distance_km']:.3f} km"),
        ("Écart de distance", f"{validation.get('distance_gap_km', 0.0):+.3f} km ({validation.get('distance_gap_pct', 0.0):+.1f} %)"),
        ("Points actuels / historiques", f"{validation['current']['point_count']} / {validation['legacy']['point_count']}"),
        ("Arrêts actuels / historiques", f"{validation['current']['stop_count']} / {validation['legacy']['stop_count']}"),
        ("Écart de pas moyen", f"{validation.get('mean_step_gap_m', 0.0):+.1f} m"),
        ("Écart de pente absolue moyenne", f"{validation.get('mean_abs_alpha_gap_rad', 0.0):+.5f} rad"),
    ]
    if validation.get("start_gap_m") is not None:
        items.append(("Écart du point de départ", f"{validation['start_gap_m']:.1f} m"))
    if validation.get("end_gap_m") is not None:
        items.append(("Écart du point d’arrivée", f"{validation['end_gap_m']:.1f} m"))
    return "<table><tbody>" + _render_key_value_table(items) + "</tbody></table>"


def _render_report_html(gtfs_data: Dict[str, Any], results: Dict[str, Any], bundle_paths: Dict[str, Path]) -> str:
    route_short = gtfs_data.get("route", {}).get("route_short_name", "N/A")
    route_name = gtfs_data.get("route_name") or "N/A"
    network_name = Path(str(gtfs_data.get("gtfs_dir", ""))).name or str(gtfs_data.get("gtfs_dir", "N/A"))
    validation_name = (
        results.get("historical_validation", {}).get("reference_name")
        if results.get("historical_validation")
        else "Aucune"
    )
    bounds = gtfs_data.get("gtfs_bounds")
    bounds_label = "Non déterminée"
    if bounds:
        bounds_label = (
            f"lat {bounds['min_lat']:.4f}-{bounds['max_lat']:.4f} | "
            f"lon {bounds['min_lon']:.4f}-{bounds['max_lon']:.4f}"
        )

    overview_items = [
        ("Date de génération", datetime.now().strftime("%d/%m/%Y %H:%M:%S")),
        ("Mode de données", str(gtfs_data.get("data_mode", "local"))),
        ("Réseau GTFS", network_name),
        ("Ligne", route_short or "N/A"),
        ("Nom de route", route_name),
        ("Route GTFS", gtfs_data.get("trip", {}).get("route_id", "")),
        (
            "Source altimétrique",
            str(
                gtfs_data.get(
                    "altimetry_label",
                    "Oui" if gtfs_data.get("altimetry_enabled") else "Non",
                )
            ),
        ),
        ("Emprise GTFS", bounds_label),
        ("Unité de référence", _analysis_unit_label(results)),
        (_analysis_count_label(results), str(results.get("analysis_unit_count", 1))),
        ("Nombre de bus", str(results.get("bus_count", 1))),
        ("Distance du trajet de référence", f"{_get_reference_distance_km(results):.3f} km"),
        ("Énergie du trajet de référence", f"{_get_reference_energy_kwh(results):.4f} kWh"),
        ("Virages détectés (référence)", str(_get_reference_turn_points(results))),
        ("Virages marqués (référence)", str(_get_reference_sharp_turns(results))),
        ("Surcoût des virages (référence)", f"{_get_reference_turn_energy_kwh(results):.4f} kWh"),
        ("Angle maximal détecté", f"{results.get('max_turn_angle_deg', 0.0):.1f}°"),
        ("Validation historique", validation_name),
        ("Export segments CSV", bundle_paths["segments_csv"].name),
        ("Export scénarios CSV", bundle_paths["scenarios_csv"].name),
    ]

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rapport d'analyse énergétique - {html.escape(route_short or route_name)}</title>
  <style>
    :root {{
      --night: #0f2234;
      --ink: #17324d;
      --steel: #5f7892;
      --mist: #eef4f8;
      --sand: #f5efe6;
      --line: #d7e2ea;
      --white: #ffffff;
      --teal: #117a8b;
      --success: #2d6a4f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--sand);
      color: var(--ink);
      font-family: "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    .page {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 24px;
    }}
    .hero {{
      background: var(--night);
      color: var(--white);
      border-radius: 18px;
      padding: 28px 32px;
      margin-bottom: 18px;
    }}
    .hero p {{ color: #dbe7f0; max-width: 860px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .metric-card {{
      background: var(--white);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px 16px;
    }}
    .metric-card span {{
      display: block;
      font-size: 0.9rem;
      color: var(--steel);
      margin-bottom: 6px;
    }}
    .metric-card strong {{
      font-size: 1.2rem;
      color: var(--ink);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 14px;
    }}
    .card {{
      background: var(--white);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 18px 20px;
      overflow: hidden;
    }}
    .card h2 {{
      margin: 0 0 10px 0;
      font-size: 1.1rem;
    }}
    .card h3 {{
      margin: 0 0 8px 0;
      font-size: 1rem;
    }}
    .trip-block {{
      padding: 12px 0;
      border-top: 1px solid var(--line);
    }}
    .trip-block:first-child {{ border-top: none; padding-top: 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.94rem;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: var(--mist);
      font-weight: 600;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
    .full {{
      margin-bottom: 14px;
    }}
    .note {{
      color: var(--steel);
      font-size: 0.92rem;
    }}
    .footer {{
      margin-top: 18px;
      color: var(--steel);
      font-size: 0.9rem;
    }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .page {{ padding: 16px; }}
      .hero {{ padding: 22px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>Rapport d'analyse énergétique</h1>
      <p>
        Synthèse générée automatiquement pour la ligne <strong>{html.escape(route_short or "N/A")}</strong>
        ({html.escape(route_name)}). Ce document résume les hypothèses, les paramètres du bus,
        le bilan énergétique, les scénarios comparés et le détail segmentaire.
      </p>
    </section>

    <section class="metrics">
      {_render_metric_cards(results)}
    </section>

    <section class="grid">
      <article class="card">
        <h2>Contexte de l'analyse</h2>
        <table><tbody>{_render_key_value_table(overview_items)}</tbody></table>
      </article>
      <article class="card">
        <h2>Trajets GTFS retenus</h2>
        {_render_trip_summaries(gtfs_data)}
      </article>
    </section>

    <section class="grid">
      <article class="card">
        <h2>Paramètres du bus</h2>
        <table><tbody>{_render_bus_table(results)}</tbody></table>
      </article>
      <article class="card">
        <h2>Validation historique</h2>
        {_render_validation(results)}
      </article>
    </section>

    <section class="card full">
      <h2>Scénarios comparés</h2>
      <p class="note">
        Les scénarios permettent d’isoler l’influence du relief et des pénalités de virage sur le bilan énergétique.
      </p>
      <div class="table-wrap">
        {_render_scenarios(results)}
      </div>
    </section>

    <section class="card full">
      <h2>Détail segmentaire</h2>
      <p class="note">
        Le tableau ci-dessous correspond au trajet de référence analysé. Les fichiers CSV associés sont écrits à côté de ce rapport.
      </p>
      <div class="table-wrap">
        {_render_segments(results)}
      </div>
    </section>

    <section class="footer">
      <p>
        Rapport généré automatiquement par l’outil d’aide à la décision. Les exports tabulaires associés sont :
        <strong>{html.escape(bundle_paths["segments_csv"].name)}</strong> et
        <strong>{html.escape(bundle_paths["scenarios_csv"].name)}</strong>.
      </p>
    </section>
  </div>
</body>
</html>
"""


def export_analysis_report_bundle(
    gtfs_data: Dict[str, Any],
    results: Dict[str, Any],
    requested_output: str | Path | None = None,
    export_root: str | Path | None = None,
) -> Dict[str, Path]:
    html_path = resolve_report_output_path(
        gtfs_data=gtfs_data,
        results=results,
        requested_output=requested_output,
        export_root=export_root,
    )
    segments_csv = html_path.with_name(f"{html_path.stem}_segments.csv")
    scenarios_csv = html_path.with_name(f"{html_path.stem}_scenarios.csv")

    bundle_paths = {
        "html": html_path,
        "segments_csv": segments_csv,
        "scenarios_csv": scenarios_csv,
    }

    _write_csv(list(results.get("segments", [])), segments_csv, SEGMENT_PREFERRED_FIELDS)
    _write_csv(
        list(results.get("scenario_comparisons", [])),
        scenarios_csv,
        SCENARIO_PREFERRED_FIELDS,
    )

    html_path.write_text(
        _render_report_html(gtfs_data, results, bundle_paths),
        encoding="utf-8",
    )
    return bundle_paths
