import argparse
from pathlib import Path

from gtfs_core import (
    build_trip_segments,
    default_search_root,
    discover_gtfs_feeds,
    export_payload_json,
    export_segments_csv,
    format_bounds,
    load_gtfs_feed,
    preview_trip_selection,
    select_gtfs_feed,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Outil GTFS autonome pour le groupe modélisation : découverte des réseaux, "
            "sélection d'une ligne, aperçu des trajets et export des segments."
        )
    )
    parser.add_argument("--data-mode", choices=("local", "online"), default="local")
    parser.add_argument("--search-root", type=str, default=str(default_search_root()))
    parser.add_argument("--gtfs-path", type=str, default=None)
    parser.add_argument("--network", type=str, default=None)
    parser.add_argument("--list-networks", action="store_true")
    parser.add_argument("--list-lines", action="store_true")
    parser.add_argument("--line", type=str, default=None)
    parser.add_argument("--route-id", type=str, default=None)
    parser.add_argument("--trip-id", type=str, default=None)
    parser.add_argument("--direction-id", type=str, default=None)
    parser.add_argument("--max-segments", type=int, default=None)
    parser.add_argument("--show-stops", action="store_true")
    parser.add_argument("--export-json", type=str, default=None)
    parser.add_argument("--export-csv", type=str, default=None)
    return parser.parse_args()


def print_networks(feeds: list[dict], data_mode: str) -> None:
    print("=" * 90)
    print("RÉSEAUX GTFS DISPONIBLES")
    print("=" * 90)
    for feed in feeds:
        if data_mode == "online" and feed.get("covered_area"):
            print(f"- {feed['agency_name']} | zone={feed['covered_area']}")
        else:
            print(f"- {feed['agency_name']} | dossier={feed['name']}")


def print_lines(feed: dict) -> None:
    print("=" * 90)
    print("LIGNES GTFS DISPONIBLES")
    print("=" * 90)
    for route in feed["routes"]:
        short_name = route.get("route_short_name", "")
        long_name = route.get("route_long_name", "")
        print(f"- route_id={route['route_id']} | ligne={short_name} | nom={long_name}")


def print_preview(preview: dict, payload: dict, show_stops: bool) -> None:
    route = payload["route"]
    print("=" * 90)
    print("APERÇU DU TRAJET RETENU")
    print("=" * 90)
    print(f"Route ID                 : {preview['route_id']}")
    print(f"Ligne                    : {route.get('route_short_name', '')}")
    print(f"Nom long                 : {route.get('route_long_name', '')}")
    print(f"Nombre de trajets GTFS   : {preview['trip_count']}")
    print(f"Nombre total de segments : {preview['segment_count']}")
    print(f"Segments retenus         : {payload['segment_count']}")
    print(f"Nombre d'arrêts          : {preview['stop_count']}")
    print(f"Emprise géographique     : {format_bounds(payload.get('bounds'))}")
    print()

    for summary in payload["trip_summaries"]:
        headsign = summary.get("headsign") or summary.get("direction_id") or "N/A"
        print(f"- trip_id={summary['trip_id']} | direction={headsign} | segments={summary['segment_count']}")
        if show_stops:
            print("  " + " -> ".join(summary.get("stop_names", [])))


def main() -> None:
    args = parse_arguments()
    search_root = Path(args.search_root).resolve()

    if args.list_networks:
        feeds = discover_gtfs_feeds(search_root, data_mode=args.data_mode)
        print_networks(feeds, args.data_mode)
        return

    gtfs_dir = select_gtfs_feed(
        search_root=search_root,
        gtfs_path=args.gtfs_path,
        network_name=args.network,
        data_mode=args.data_mode,
    )
    feed = load_gtfs_feed(gtfs_dir)

    if args.list_lines:
        print_lines(feed)
        return

    if not any([args.line, args.route_id, args.trip_id]):
        raise ValueError("Aucune ligne n'a été sélectionnée. Utilisez --line, --route-id ou --trip-id.")

    preview = preview_trip_selection(
        feed=feed,
        trip_id=args.trip_id,
        route_id=args.route_id,
        line_selector=args.line,
        direction_id=args.direction_id,
    )
    payload = build_trip_segments(
        feed=feed,
        trip_id=args.trip_id,
        route_id=args.route_id,
        line_selector=args.line,
        direction_id=args.direction_id,
        max_segments=args.max_segments,
    )

    print_preview(preview, payload, args.show_stops)

    if args.export_json:
        export_payload_json(Path(args.export_json), payload)
        print()
        print(f"JSON généré : {Path(args.export_json).resolve()}")

    if args.export_csv:
        export_segments_csv(Path(args.export_csv), payload["segments"])
        print(f"CSV généré  : {Path(args.export_csv).resolve()}")


if __name__ == "__main__":
    main()
