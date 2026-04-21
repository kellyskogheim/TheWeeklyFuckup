"""
Waypoint generation module: create distance-constrained route candidates.
"""

import logging
import random
import math
from typing import List, Tuple, Optional
import networkx as nx
import osmnx as ox

logger = logging.getLogger(__name__)


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate great-circle distance between two points in meters.
    
    Args:
        lat1, lon1: First point (latitude, longitude)
        lat2, lon2: Second point (latitude, longitude)
    
    Returns:
        Distance in meters
    """
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    
    return R * c


def generate_route_candidates(
    graph: nx.MultiDiGraph,
    start_lat: float,
    start_lon: float,
    target_distance_m: float,
    num_routes: int = 10
) -> List[Tuple[int, List[int]]]:
    """
    Generate multiple route candidates with distance-constrained waypoints.
    
    Creates `num_routes` different route configurations with randomly selected
    waypoint counts (2-15), where waypoints are selected to respect distance budgets:
    - First waypoint: within target_distance_m / 2 of start
    - Subsequent waypoints: within remaining distance budget
    
    Args:
        graph: NetworkX MultiDiGraph of the walk network
        start_lat: Latitude of starting point
        start_lon: Longitude of starting point
        target_distance_m: Target route distance for constraining waypoint selection
        num_routes: Number of route candidates to generate (default 10)
    
    Returns:
        List of tuples: [(waypoint_count, [list of node IDs]), ...]
        Each list includes the start node and distance-constrained waypoints
    
    Raises:
        ValueError: If graph has too few nodes for waypoint selection
    """
    # Get the largest connected component to ensure waypoints are reachable
    largest_cc = max(nx.weakly_connected_components(graph), key=len)
    logger.debug(f"Using largest connected component with {len(largest_cc)} nodes")
    
    if len(largest_cc) < 3:
        raise ValueError(f"Largest connected component has too few nodes ({len(largest_cc)}) for route generation")
    
    # Find closest node to start point within the largest component
    component_subgraph = graph.subgraph(largest_cc)
    start_node = ox.nearest_nodes(component_subgraph, start_lon, start_lat)
    logger.debug(f"Start node: {start_node}")
    
    candidates = []
    
    for route_idx in range(num_routes):
        # Randomly select waypoint count for this route (2-15)
        waypoint_count = random.randint(2, 15)
        
        # Generate distance-constrained waypoints
        try:
            waypoints = _generate_waypoints(
                component_subgraph, 
                start_node, 
                waypoint_count,
                target_distance_m
            )
            candidates.append((waypoint_count, waypoints))
            logger.debug(f"Route {route_idx + 1}: {waypoint_count} waypoints selected")
        except ValueError as e:
            logger.warning(f"Failed to generate waypoints for route {route_idx + 1}: {e}")
            # Fallback: create degenerate route with just start and one other node
            other_nodes = [n for n in largest_cc if n != start_node]
            if other_nodes:
                waypoints = [start_node, random.choice(other_nodes)]
                candidates.append((2, waypoints))
    
    logger.info(f"Generated {len(candidates)} route candidates")
    return candidates


def _calculate_shortest_path_distance(
    graph: nx.MultiDiGraph,
    start_node: int,
    end_node: int
) -> Optional[float]:
    """
    Calculate shortest path distance between two nodes using physical edge lengths.
    
    Args:
        graph: NetworkX graph
        start_node: Starting node ID
        end_node: Ending node ID
    
    Returns:
        Shortest path distance in meters, or None if no path exists
    """
    try:
        path = nx.shortest_path(graph, start_node, end_node, weight='length')
        total_distance = 0.0
        
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edge_data = graph[u][v]
            if isinstance(edge_data, dict):
                segment_length = edge_data.get('length', 50.0)
            else:
                segment_length = edge_data[0].get('length', 50.0)
            total_distance += segment_length
        
        return total_distance
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def _find_nodes_within_distance(
    graph: nx.MultiDiGraph,
    start_node: int,
    max_distance_m: float,
    sample_size: int = 300
) -> List[int]:
    """
    Find candidate nodes within a distance budget from start_node.
    
    Uses geographic distance (haversine) as a quick filter, then validates with
    actual network shortest paths for candidates that pass the geographic filter.
    
    Args:
        graph: NetworkX graph with node coordinates
        start_node: Starting node ID
        max_distance_m: Maximum distance in meters
        sample_size: Number of candidate nodes to sample and check
    
    Returns:
        List of node IDs within the distance budget
    """
    if start_node not in graph:
        return []
    
    # Get start node coordinates
    start_data = graph.nodes[start_node]
    start_lat = start_data.get('y')
    start_lon = start_data.get('x')
    
    if start_lat is None or start_lon is None:
        logger.warning(f"Start node {start_node} missing coordinates")
        return []
    
    available_nodes = [n for n in graph.nodes() if n != start_node]
    sample_size = min(sample_size, len(available_nodes))
    
    if sample_size == 0:
        return []
    
    # Sample candidate nodes
    candidates_to_check = random.sample(available_nodes, sample_size)
    
    # Filter by geographic distance (haversine) - use 1.5x multiplier since network paths are longer
    geo_budget = max_distance_m * 1.5
    geographically_close = []
    
    for candidate in candidates_to_check:
        candidate_data = graph.nodes[candidate]
        cand_lat = candidate_data.get('y')
        cand_lon = candidate_data.get('x')
        
        if cand_lat is None or cand_lon is None:
            continue
        
        geo_dist = _haversine_distance(start_lat, start_lon, cand_lat, cand_lon)
        if geo_dist <= geo_budget:
            geographically_close.append(candidate)
    
    logger.debug(
        f"Geo filter: {len(geographically_close)}/{sample_size} candidates within "
        f"{geo_budget:.0f}m (network budget: {max_distance_m:.0f}m)"
    )
    
    if not geographically_close:
        # Fallback: return closest geographically if none pass budget
        if available_nodes:
            return [min(available_nodes, key=lambda n: _haversine_distance(
                start_lat, start_lon,
                graph.nodes[n].get('y', 0),
                graph.nodes[n].get('x', 0)
            ))]
        return []
    
    # Verify network distances for geographically close nodes
    valid_nodes = []
    for candidate in geographically_close:
        distance = _calculate_shortest_path_distance(graph, start_node, candidate)
        if distance is not None and distance <= max_distance_m:
            valid_nodes.append(candidate)
    
    logger.debug(f"Network filter: {len(valid_nodes)} nodes reachable within {max_distance_m:.0f}m")
    return valid_nodes


def _generate_waypoints(
    graph: nx.MultiDiGraph,
    start_node: int,
    waypoint_count: int,
    target_distance_m: float
) -> List[int]:
    """
    Generate distance-constrained waypoints.
    
    Selection strategy:
    1. First waypoint: within target_distance_m / 2 from start
    2. Subsequent waypoints: within (remaining_budget - estimated_return_distance)
       where remaining_budget = target_distance_m - sum(prior_segment_distances)
    
    If waypoint selection fails due to tight constraints, the function relaxes the
    budget by using historical path data to estimate more realistic segment distances.
    
    Args:
        graph: NetworkX graph
        start_node: Starting node ID
        waypoint_count: Total number of waypoints (including start)
        target_distance_m: Target total route distance in meters
    
    Returns:
        List of node IDs starting with start_node
    
    Raises:
        ValueError: If cannot select enough waypoints within constraints
    """
    if waypoint_count < 1:
        raise ValueError("waypoint_count must be >= 1")
    
    waypoints = [start_node]
    
    if waypoint_count == 1:
        return waypoints
    
    current_node = start_node
    accumulated_distance = 0.0
    path_distances = []  # Track segment distances for better estimation
    
    # For each additional waypoint to select
    for wp_index in range(1, waypoint_count):
        remaining_waypoints = waypoint_count - wp_index
        
        # Calculate budget for this segment
        if wp_index == 1:
            # First waypoint: constrain to half the target distance
            segment_budget = target_distance_m / 2.0
        else:
            # Subsequent waypoints: budget is remaining distance divided by remaining segments
            # Use historical average path distance to estimate segments
            avg_segment = sum(path_distances) / len(path_distances) if path_distances else (target_distance_m / waypoint_count)
            
            # Reserve distance for return to start (estimate based on history)
            return_distance_estimate = avg_segment * 1.2
            remaining_budget = target_distance_m - accumulated_distance - return_distance_estimate
            
            # Distribute remaining budget across remaining waypoints
            segment_budget = remaining_budget / remaining_waypoints if remaining_waypoints > 0 else remaining_budget
        
        # Use minimum segment budget, but allow going over if necessary
        minimum_budget = target_distance_m * 0.15  # At least 15% of target per segment
        segment_budget = max(segment_budget, minimum_budget)
        
        logger.debug(
            f"Waypoint {wp_index}/{waypoint_count}: "
            f"accumulated={accumulated_distance:.0f}m, budget={segment_budget:.0f}m"
        )
        
        # Find candidate nodes within the segment budget
        candidate_nodes = _find_nodes_within_distance(
            graph,
            current_node,
            segment_budget,
            sample_size=500
        )
        
        # Filter out already-selected waypoints
        candidate_nodes = [n for n in candidate_nodes if n not in waypoints]
        
        if not candidate_nodes:
            # If no candidates found, try with a relaxed budget (2x)
            logger.debug(f"  No candidates found with budget {segment_budget:.0f}m, trying relaxed budget...")
            segment_budget *= 2.0
            candidate_nodes = _find_nodes_within_distance(
                graph,
                current_node,
                segment_budget,
                sample_size=500
            )
            candidate_nodes = [n for n in candidate_nodes if n not in waypoints]
        
        if not candidate_nodes:
            raise ValueError(
                f"Cannot find waypoint {wp_index}: no nodes within {segment_budget:.0f}m "
                f"of {current_node} (accumulated distance: {accumulated_distance:.0f}m)"
            )
        
        # Select a random node from candidates
        next_waypoint = random.choice(candidate_nodes)
        segment_distance = _calculate_shortest_path_distance(graph, current_node, next_waypoint)
        
        if segment_distance is None:
            raise ValueError(f"Selected waypoint {next_waypoint} is not reachable from {current_node}")
        
        waypoints.append(next_waypoint)
        path_distances.append(segment_distance)
        accumulated_distance += segment_distance
        current_node = next_waypoint
        
        logger.debug(f"  Selected waypoint {next_waypoint}, segment distance: {segment_distance:.0f}m")
    
    logger.debug(
        f"Generated {len(waypoints)} waypoints with accumulated path distance: {accumulated_distance:.0f}m "
        f"(target: {target_distance_m:.0f}m)"
    )
    return waypoints
