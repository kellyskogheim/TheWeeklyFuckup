"""
Running route generator - dual-mode CLI and REST API.

Modes:
  - CLI: python main.py "address" distance unit
  - API: python main.py (no args)
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
    
    # Import modules for orchestration (will be created in later phases)
    try:
        from geocode import address_to_coords
        from network import download_walk_network
        from waypoints import generate_route_candidates
        from routing import process_and_rank_routes
        from output import generate_summary_report
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
        routes_ranked = process_and_rank_routes(graph, route_candidates, distance_m)
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


def api_mode():
    """
    API mode: start FastAPI server for REST API.
    """
    logger.info("Starting API mode")
    
    try:
        from api import app
        import uvicorn
    except ImportError as e:
        logger.error(f"Failed to import API modules: {e}")
        sys.exit(1)
    
    logger.info("FastAPI server starting on http://localhost:8000")
    logger.info("API docs available at http://localhost:8000/docs")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)


def main():
    """
    Main entry point: detect mode and run accordingly.
    """
    if len(sys.argv) > 1:
        # CLI mode: arguments provided
        cli_mode()
    else:
        # API mode: no arguments
        api_mode()


if __name__ == "__main__":
    main()
