"""
Output module: generate GPX files, Apple Maps URLs, and summary reports.
"""

import logging
from typing import List, Dict, Any, Optional
import gpxpy
import gpxpy.gpx
import networkx as nx

logger = logging.getLogger(__name__)


def export_gpx(
    route_nodes: List[int],
    graph: nx.MultiDiGraph,
    filename: str
) -> str:
    """
    Export a route to a GPX file.
    
    Args:
        route_nodes: List of node IDs forming the route
        graph: NetworkX graph containing node coordinates
        filename: Output filename (e.g., 'route_1.gpx')
    
    Returns:
        The GPX file content as a string
    
    Raises:
        ValueError: If route cannot be converted to GPX
    """
    try:
        gpx = gpxpy.gpx.GPX()
        gpx_track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(gpx_track)
        
        # Create track segment
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)
        
        # Add waypoints
        for node_id in route_nodes:
            node_data = graph.nodes[node_id]
            lat = node_data.get('y')
            lon = node_data.get('x')
            
            if lat is None or lon is None:
                logger.warning(f"Node {node_id} missing coordinates, skipping")
                continue
            
            gpx_point = gpxpy.gpx.GPXTrackPoint(latitude=lat, longitude=lon)
            gpx_segment.points.append(gpx_point)
        
        if not gpx_segment.points:
            raise ValueError("No valid waypoints to export")
        
        gpx_str = gpx.to_xml()
        logger.debug(f"Generated GPX with {len(gpx_segment.points)} points")
        
        return gpx_str
        
    except Exception as e:
        logger.error(f"Failed to export GPX: {e}")
        raise ValueError(f"Cannot export route to GPX: {e}") from e


def route_to_apple_maps_url(
    route_nodes: List[int],
    graph: nx.MultiDiGraph
) -> str:
    """
    Format an Apple Maps URL for the route waypoints.
    
    Apple Maps URL format includes waypoints as coordinates.
    Includes up to 5 waypoints for clarity (start → waypoints → end).
    
    Args:
        route_nodes: List of node IDs
        graph: NetworkX graph containing coordinates
    
    Returns:
        Apple Maps URL string
    """
    waypoints = []
    
    for node_id in route_nodes:
        node_data = graph.nodes[node_id]
        lat = node_data.get('y')
        lon = node_data.get('x')
        
        if lat is not None and lon is not None:
            waypoints.append((lat, lon))
    
    if not waypoints:
        logger.warning("No waypoints for Apple Maps URL")
        return ""
    
    # Use start point and sample intermediate waypoints to avoid URL length issues
    # Apple Maps can handle ~5-10 waypoints before the URL gets too long
    sampled_waypoints = [waypoints[0]]  # Start
    
    if len(waypoints) > 2:
        # Sample intermediate waypoints evenly
        step = max(1, (len(waypoints) - 2) // 3)  # Up to 3 intermediate waypoints
        sampled_waypoints.extend(waypoints[step:-1:step])
    
    sampled_waypoints.append(waypoints[-1])  # End
    
    # Build Apple Maps URL with waypoints
    # Format: https://maps.apple.com/?saddr=start&daddr=waypoint1&daddr=waypoint2...&mode=walking
    # mode=walking specifies walking directions
    if len(sampled_waypoints) == 1:
        url = f"https://maps.apple.com/?ll={sampled_waypoints[0][0]},{sampled_waypoints[0][1]}&mode=walking"
    else:
        url = f"https://maps.apple.com/?saddr={sampled_waypoints[0][0]},{sampled_waypoints[0][1]}"
        for wp in sampled_waypoints[1:]:
            url += f"&daddr={wp[0]},{wp[1]}"
        url += "&mode=walking"  # Walking mode
    
    logger.debug(f"Generated Apple Maps URL for {len(waypoints)} waypoints")
    return url


def format_route_stats(
    distance_m: float,
    target_distance_m: float,
    waypoint_count: int,
    score: float
) -> Dict[str, Any]:
    """
    Format route statistics for display.
    
    Args:
        distance_m: Actual route distance
        target_distance_m: Target distance
        waypoint_count: Number of waypoints
        score: Route score (0-100)
    
    Returns:
        Dictionary of formatted stats
    """
    distance_variance = (distance_m - target_distance_m) / target_distance_m
    
    return {
        'distance_m': round(distance_m, 1),
        'target_distance_m': round(target_distance_m, 1),
        'distance_variance_pct': round(distance_variance * 100, 1),
        'waypoint_count': waypoint_count,
        'score': round(score, 1)
    }


def generate_summary_report(routes_ranked: List[Dict[str, Any]]) -> str:
    """
    Generate a text summary report of all ranked routes.
    
    Args:
        routes_ranked: List of route dicts with rank, score, distance, etc.
    
    Returns:
        Formatted text report
    """
    lines = []
    lines.append("=" * 80)
    lines.append("RUNNING ROUTE GENERATOR - RESULTS")
    lines.append("=" * 80)
    lines.append("")
    
    if not routes_ranked:
        lines.append("No valid routes could be generated.")
        return "\n".join(lines)
    
    lines.append(f"Total routes generated: {len(routes_ranked)}\n")
    
    for route in routes_ranked:
        rank = route.get('rank', '?')
        score = route.get('score', 0)
        distance_m = route.get('distance_m', 0)
        distance_variance = route.get('distance_variance', 0)
        waypoint_count = route.get('waypoint_count', 0)
        apple_maps_url = route.get('apple_maps_url', '')
        
        lines.append(f"Rank #{rank}")
        lines.append(f"  Score:          {score:.1f}/100")
        lines.append(f"  Distance:       {distance_m:.0f}m ({distance_variance:+.1%})")
        lines.append(f"  Waypoints:      {waypoint_count}")
        if apple_maps_url:
            lines.append(f"  Apple Maps:     {apple_maps_url}")
        lines.append("")
    
    lines.append("=" * 80)
    lines.append(f"Top route (Rank #1): {routes_ranked[0].get('score', 0):.1f}/100")
    lines.append(f"  {routes_ranked[0].get('waypoint_count', 0)} waypoints, {routes_ranked[0].get('distance_m', 0):.0f}m")
    lines.append("=" * 80)
    
    return "\n".join(lines)
