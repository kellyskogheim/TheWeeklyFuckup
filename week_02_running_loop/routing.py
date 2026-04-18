"""
Routing module: calculate routes with custom weights and score them.
"""

import logging
from typing import List, Tuple, Dict, Any
import networkx as nx

logger = logging.getLogger(__name__)

# Feature-based weight multipliers (lower = more desirable)
WEIGHT_PRIMARY_ROAD = 2.0  # Penalize main roads
WEIGHT_TRUNK_ROAD = 1.5    # Penalize trunk roads
WEIGHT_PARK = 0.5          # Reward parks
WEIGHT_WATER = 0.7         # Reward water features
WEIGHT_FOREST = 0.6        # Reward forests
WEIGHT_MOUNTAIN = 0.7      # Reward mountains
WEIGHT_SCULPTURE = 0.7     # Reward art/sculptures
WEIGHT_BRIDGE = 0.8        # Reward bridges

# Distance tolerance bounds
DISTANCE_LOWER_TOLERANCE = -0.10  # −10% OK
DISTANCE_UPPER_TOLERANCE = 0.20   # +20% max

# Waypoint preference range
WAYPOINT_PREFERRED_MIN = 4
WAYPOINT_PREFERRED_MAX = 12


def weight_function(u: int, v: int, d: Dict[str, Any], graph: nx.MultiDiGraph) -> float:
    """
    Calculate custom edge weight based on edge features.
    
    Weight multiplies the edge length to encourage/discourage certain paths:
    - Lower weight = more desirable
    - Primary/trunk roads penalized (×2.0, ×1.5)
    - Parks, water, forests, mountains, art, bridges rewarded (×0.5-0.8)
    
    Args:
        u: Source node
        v: Target node
        d: Edge data dictionary
        graph: NetworkX graph (for context)
    
    Returns:
        Weighted distance in meters (edge length × weight multiplier)
    """
    # Base edge length
    edge_length = d.get('length', 50.0)
    
    # Start with multiplier of 1.0
    multiplier = 1.0
    
    # Penalize main roads
    highway_type = d.get('highway', '')
    if isinstance(highway_type, list):
        highway_type = highway_type[0]
    
    if highway_type == 'primary':
        multiplier *= WEIGHT_PRIMARY_ROAD
    elif highway_type == 'trunk':
        multiplier *= WEIGHT_TRUNK_ROAD
    
    # Reward scenic/pleasant features
    if d.get('leisure') == 'park':
        multiplier *= WEIGHT_PARK
    
    if d.get('waterway'):
        multiplier *= WEIGHT_WATER
    
    if d.get('natural') == 'forest':
        multiplier *= WEIGHT_FOREST
    elif d.get('natural') == 'peak':
        multiplier *= WEIGHT_MOUNTAIN
    
    if d.get('tourism') == 'artwork':
        multiplier *= WEIGHT_SCULPTURE
    
    if d.get('man_made') == 'bridge':
        multiplier *= WEIGHT_BRIDGE
    
    return edge_length * multiplier


def build_route(
    graph: nx.MultiDiGraph,
    waypoints: List[int],
    target_distance_m: float
) -> Tuple[List[int], float]:
    """
    Build a complete route by chaining waypoints using shortest paths.
    
    Connects waypoints in order: start → w1 → w2 → ... → start
    Uses custom weight function to prefer scenic routes.
    
    Args:
        graph: NetworkX graph
        waypoints: List of node IDs representing waypoints
        target_distance_m: Target distance (for context only)
    
    Returns:
        Tuple of (route_nodes, total_distance_m)
        route_nodes is the complete sequence of nodes forming the route
    
    Raises:
        ValueError: If route cannot be computed
    """
    if len(waypoints) < 2:
        raise ValueError("Need at least 2 waypoints to build a route")
    
    route_nodes = []
    total_distance = 0.0
    
    # Connect each pair of consecutive waypoints (including wraparound to start)
    waypoint_pairs = []
    for i in range(len(waypoints)):
        current = waypoints[i]
        next_wp = waypoints[(i + 1) % len(waypoints)]  # Wrap around to start
        waypoint_pairs.append((current, next_wp))
    
    try:
        for start_wp, end_wp in waypoint_pairs:
            # Find shortest path between waypoints using custom weights
            path = nx.shortest_path(
                graph,
                start_wp,
                end_wp,
                weight=lambda u, v, d: weight_function(u, v, d, graph)
            )
            
            # Add to route (avoiding duplicate nodes at connections)
            if route_nodes:
                path = path[1:]  # Skip first node (already in route)
            
            route_nodes.extend(path)
            
            # Sum distances
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                # Get edge data (handle MultiDiGraph which may have multiple edges)
                edge_data = graph[u][v]
                if isinstance(edge_data, dict):
                    # Single edge
                    segment_length = edge_data.get('length', 50.0)
                else:
                    # Multiple edges (MultiDiGraph) - use first
                    segment_length = edge_data[0].get('length', 50.0)
                
                total_distance += segment_length
        
        logger.debug(f"Built route with {len(route_nodes)} nodes, total distance: {total_distance:.1f}m")
        return (route_nodes, total_distance)
        
    except nx.NetworkXNoPath as e:
        logger.error(f"Cannot connect waypoints {start_wp} → {end_wp}: no path")
        raise ValueError(f"Cannot build continuous route: waypoints disconnected") from e
    except Exception as e:
        logger.error(f"Error building route: {e}")
        raise


def score_route(
    total_distance_m: float,
    waypoint_count: int,
    target_distance_m: float
) -> float:
    """
    Score a route based on distance tolerance and waypoint preference.
    
    Scoring components:
    - Distance: penalize routes outside tolerance bounds (−10% to +20%);
      bonus for closest to target
    - Waypoint preference: reward [4, 12]; penalize < 4 or > 12
    
    Returns:
        Composite score 0–100 (higher is better)
    
    Args:
        total_distance_m: Actual route distance in meters
        waypoint_count: Number of waypoints in route
        target_distance_m: Target distance in meters
    
    Returns:
        Score from 0–100 (higher is better)
    """
    score = 100.0
    
    # Distance tolerance scoring
    distance_variance = (total_distance_m - target_distance_m) / target_distance_m
    
    if distance_variance < DISTANCE_LOWER_TOLERANCE:
        # Route too short: penalize
        penalty = abs(distance_variance) * 50
        score -= penalty
        logger.debug(f"Distance too short ({distance_variance:.1%}): -{penalty:.1f}")
    
    elif distance_variance > DISTANCE_UPPER_TOLERANCE:
        # Route too long: penalize heavily
        penalty = (distance_variance - DISTANCE_UPPER_TOLERANCE) * 100
        score -= penalty
        logger.debug(f"Distance too long ({distance_variance:.1%}): -{penalty:.1f}")
    
    else:
        # Within tolerance: bonus for being closer to target
        # Bonus at 0% distance
        closeness_bonus = (DISTANCE_UPPER_TOLERANCE - abs(distance_variance)) / DISTANCE_UPPER_TOLERANCE * 20
        score += closeness_bonus
        logger.debug(f"Distance within tolerance ({distance_variance:.1%}): +{closeness_bonus:.1f}")
    
    # Waypoint preference scoring
    if waypoint_count < WAYPOINT_PREFERRED_MIN:
        # Too few: penalize
        deficit = WAYPOINT_PREFERRED_MIN - waypoint_count
        penalty = deficit * 10
        score -= penalty
        logger.debug(f"Too few waypoints ({waypoint_count}): -{penalty:.1f}")
    
    elif waypoint_count > WAYPOINT_PREFERRED_MAX:
        # Too many: penalize
        excess = waypoint_count - WAYPOINT_PREFERRED_MAX
        penalty = excess * 10
        score -= penalty
        logger.debug(f"Too many waypoints ({waypoint_count}): -{penalty:.1f}")
    
    else:
        # Preferred range: bonus (linearly scaled, max bonus at middle of range)
        mid_point = (WAYPOINT_PREFERRED_MIN + WAYPOINT_PREFERRED_MAX) / 2
        deviation = abs(waypoint_count - mid_point)
        max_deviation = (WAYPOINT_PREFERRED_MAX - WAYPOINT_PREFERRED_MIN) / 2
        waypoint_bonus = (1 - deviation / max_deviation) * 15
        score += waypoint_bonus
        logger.debug(f"Waypoint count in preferred range ({waypoint_count}): +{waypoint_bonus:.1f}")
    
    # Clamp score to 0-100
    score = max(0.0, min(100.0, score))
    
    return score


def process_and_rank_routes(
    graph: nx.MultiDiGraph,
    route_candidates: List[Tuple[int, List[int]]],
    target_distance_m: float
) -> List[Dict[str, Any]]:
    """
    Build and score all route candidates, returning ranked list.
    
    Args:
        graph: NetworkX graph
        route_candidates: List of (waypoint_count, waypoints) tuples
        target_distance_m: Target distance for scoring
    
    Returns:
        List of route dicts sorted by score (highest first):
        [
            {
                'rank': int,
                'score': float,
                'waypoint_count': int,
                'route_nodes': [int, ...],
                'distance_m': float,
                'distance_variance': float
            },
            ...
        ]
    """
    routes_with_scores = []
    
    for waypoint_count, waypoints in route_candidates:
        try:
            # Build the complete route
            route_nodes, total_distance = build_route(graph, waypoints, target_distance_m)
            
            # Score the route
            score = score_route(total_distance, waypoint_count, target_distance_m)
            distance_variance = (total_distance - target_distance_m) / target_distance_m
            
            # Generate Apple Maps URL for the route
            from output import route_to_apple_maps_url
            apple_maps_url = route_to_apple_maps_url(route_nodes, graph)
            
            routes_with_scores.append({
                'waypoint_count': waypoint_count,
                'route_nodes': route_nodes,
                'distance_m': total_distance,
                'distance_variance': distance_variance,
                'score': score,
                'apple_maps_url': apple_maps_url
            })
            
            logger.debug(
                f"Route: {waypoint_count} waypoints, "
                f"{total_distance:.0f}m ({distance_variance:+.1%}), score: {score:.1f}"
            )
            
        except Exception as e:
            logger.warning(f"Failed to build route with {waypoint_count} waypoints: {e}")
            # Skip this route candidate
            continue
    
    # Rank by score (highest first)
    routes_with_scores.sort(key=lambda r: r['score'], reverse=True)
    
    # Add rank field
    for rank, route in enumerate(routes_with_scores, 1):
        route['rank'] = rank
    
    logger.info(f"Ranked {len(routes_with_scores)} valid routes")
    return routes_with_scores
