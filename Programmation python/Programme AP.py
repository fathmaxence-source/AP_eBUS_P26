from analysis_runner import run_analysis
from gtfs_services import discover_gtfs_feeds, load_gtfs_feed
from project_paths import get_gtfs_search_root
from reporting_services import export_analysis_report_bundle
from unified_gui import launch_unified_gui
from ui_helpers import (
    parse_arguments,
    print_results_console,
    resolve_gtfs_directory,
    should_launch_gui,
    validate_selection_args,
)


def main() -> None:
    arguments = parse_arguments()
    launched_from_gui = should_launch_gui(arguments)

    if arguments.list_networks:
        feeds = discover_gtfs_feeds(
            get_gtfs_search_root(arguments.data_mode),
            data_mode=arguments.data_mode,
        )
        if not feeds:
            raise FileNotFoundError("Aucun réseau GTFS détecté dans le dossier courant.")
        print("=" * 80)
        print("RESEAUX GTFS DISPONIBLES")
        print("=" * 80)
        for feed in feeds:
            if arguments.data_mode == "online" and feed.get("covered_area"):
                print(f"- {feed['agency_name']} | zone: {feed['covered_area']}")
            else:
                print(f"- {feed['agency_name']} | dossier: {feed['name']}")
        raise SystemExit(0)

    if arguments.list_lines:
        gtfs_dir = resolve_gtfs_directory(arguments)
        feed = load_gtfs_feed(gtfs_dir)
        print("=" * 80)
        print("LIGNES GTFS DISPONIBLES")
        print("=" * 80)
        for route in feed["routes"]:
            short_name = route.get("route_short_name", "")
            long_name = route.get("route_long_name", "")
            print(f"- route_id={route['route_id']} | ligne={short_name} | nom={long_name}")
        raise SystemExit(0)

    if launched_from_gui:
        launch_unified_gui(arguments)
        return

    arguments.gtfs_path = resolve_gtfs_directory(arguments)
    validate_selection_args(arguments)
    gtfs_data, results = run_analysis(arguments)
    print_results_console(gtfs_data, results)
    if arguments.export_report:
        bundle_paths = export_analysis_report_bundle(
            gtfs_data=gtfs_data,
            results=results,
            requested_output=arguments.report_output,
        )
        print()
        print("=" * 80)
        print("RAPPORT GENERE")
        print("=" * 80)
        print(f"HTML                : {bundle_paths['html']}")
        print(f"CSV segments        : {bundle_paths['segments_csv']}")
        print(f"CSV scenarios       : {bundle_paths['scenarios_csv']}")


if __name__ == "__main__":
    main()
