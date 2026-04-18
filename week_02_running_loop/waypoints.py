"""
Waypoint generation module: create diverse route candidates with random waypoints.
"""

import logging
import random
from typing import List, Tuple
import networkx as nx
import osmnx as ox

logger = logging.getLogger(__name__)


def generate_route_candidates(
    graph: nx.MultiDiGraph,
    start_lat: float,
    start_lon: float,
    target_distance_m: float,
    num_routes: int = 10
) -> List[Tuple[int, List[int]]]:
    """
    Generate multiple route candidates with random waypoint distributions.
    
    Creates `num_routes` different route configurations, each with a randomly
    selected number of waypoints (2-15) sampled from the largest connected component.
    
    Args:
        graph: NetworkX MultiDiGraph of the walk network
        start_lat: Latitude of starting point
        start_lon: Longitude of starting point
        target_distance_m: Target route distance (used for context, not selection)
        num_routes: Number of route candidates to generate (default 10)
    
    Returns:
        List of tuples: [(waypoint_count, [list of node IDs]), ...]
        Each list includes the start node and random waypoints
    
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
        
        # Generate waypoints: start + random intermediate nodes from largest component
        try:
            waypoints = _generate_waypoints(component_subgraph, start_node, waypoint_count)
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


def _generate_waypoints(graph: nx.MultiDiGraph, start_node: int, waypoint_count: int) -> List[int]:
    """
    Generate a list of waypoints including the start node and random intermediate nodes.
    
    Args:
        graph: NetworkX graph
        start_node: Starting node ID
        waypoint_count: Total number of waypoints (including start)
    
    Returns:
        List of node IDs starting with start_node
    
    Raises:
        ValueError: If cannot select enough waypoints
    """
    if waypoint_count < 1:
        raise ValueError("waypoint_count must be >= 1")
    
    # Start with the beginning node
    waypoints = [start_node]
    
    if waypoint_count == 1:
        return waypoints
    
    # Select additional random nodes
    available_nodes = [n for n in graph.nodes() if n != start_node]
    
    if len(available_nodes) < waypoint_count - 1:
        raise ValueError(
            f"Not enough nodes in graph ({len(available_nodes)}) "
            f"to select {waypoint_count - 1} waypoints"
        )
    
    # Sample waypoints without replacement
    additional_waypoints = random.sample(available_nodes, waypoint_count - 1)
    waypoints.extend(additional_waypoints)
    
    return waypoints
