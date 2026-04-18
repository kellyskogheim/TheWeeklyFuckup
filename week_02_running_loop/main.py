"""
Running route generator CLI - generates optimal routes from an address and distance.

Usage:
  python main.py "address" distance unit
  
Example:
  python main.py "Central Park, NYC" 5 miles
  python main.py "Eiffel Tower, Paris" 3 km
"""

import sys
import logging
from cli import parse_args, distance_to_meters

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cli_mode():
    """
    CLI mode: orchestrate end-to-end route generation from command line.
    """
    logger.info("Starting CLI mode")
    
    # Parse CLI arguments
    cli_result = parse_args()
    if cli_result is None:
        logger.error("No CLI arguments provided. Use: python main.py 'address' distance unit")
        sys.exit(1)
    
    address, distance_value, unit = cli_result
    distance_m = distance_to_meters(distance_value, unit)
    
    logger.info(f"Generating routes for: {address}, {distance_value} {unit} ({distance_m:.1f}m)")
    
    # Import modules for orchestration
    try:
        from geocode import address_to_coords
        from network import download_walk_network
        from waypoints import generate_route_candidates
        from routing import process_and_rank_routes
        from output import generate_summary_report
        from visualization import generate_route_maps
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        sys.exit(1)
    
    # Phase 2: Geocoding & Network Download
    try:
        lat, lon = address_to_coords(address)
        logger.info(f"Geocoded address to: {lat:.6f}, {lon:.6f}")
    except Exception as e:
        logger.error(f"Geocoding failed: {e}")
        sys.exit(1)
    
    try:
        graph = download_walk_network(lat, lon, distance_m)
        logger.info(f"Downloaded walk network: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    except Exception as e:
        logger.error(f"Network download failed: {e}")
        sys.exit(1)
    
    # Phase 3: Waypoint Generation
    try:
        route_candidates = generate_route_candidates(graph, lat, lon, distance_m, num_routes=10)
        logger.info(f"Generated {len(route_candidates)} route candidates")
    except Exception as e:
        logger.error(f"Waypoint generation failed: {e}")
        sys.exit(1)
    
    # Phase 4: Routing & Scoring
    try:
        routes_ranked = process_and_rank_routes(graph, route_candidates, distance_m, start_lat=lat, start_lon=lon)
        logger.info(f"Ranked {len(routes_ranked)} routes by score")
    except Exception as e:
        logger.error(f"Route processing failed: {e}")
        sys.exit(1)
    
    # Phase 5: Output
    try:
        report = generate_summary_report(routes_ranked)
        print("\n" + report)
        logger.info("Route generation complete")
    except Exception as e:
        logger.error(f"Output generation failed: {e}")
        sys.exit(1)
    
    # Phase 6: Visualization
    try:
        generated_maps = generate_route_maps(routes_ranked, graph)
        if generated_maps:
            print(f"\n📍 Generated {len(generated_maps)} interactive maps:")
            for map_file in generated_maps:
                print(f"   {map_file}")
            logger.info(f"Generated {len(generated_maps)} route visualizations")
    except Exception as e:
        logger.error(f"Map generation failed: {e}")
        # Don't exit - visualization is optional


def main():
    """
    Main entry point for CLI route generation.
    """
    cli_mode()


if __name__ == "__main__":
    main()
