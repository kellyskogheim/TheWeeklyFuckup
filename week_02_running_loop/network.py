"""
Network download module: fetch and process walk-friendly networks from OSM.
"""

import logging
from typing import Any
import osmnx as ox
import networkx as nx

logger = logging.getLogger(__name__)

# Highway types that are good for walking
WALKABLE_WAYS = {'footway', 'path', 'pedestrian', 'residential', 'living_street', 'unclassified', 'track', 'cycleway'}

# Highway types to exclude
EXCLUDE_WAYS = {'motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'construction'}


def download_walk_network(lat: float, lon: float, distance_m: float) -> nx.MultiDiGraph:
    """
    Download and filter a street network for walking routes.
    
    Downloads all streets within the specified distance, then filters to keep
    walkable ways and edge metadata for feature-based routing.
    
    Args:
        lat: Latitude of starting point
        lon: Longitude of starting point
        distance_m: Search radius in meters
    
    Returns:
        NetworkX MultiDiGraph with edge attributes (highway type, leisure, natural, man_made, length)
    
    Raises:
        Exception: If network download fails
    """
    try:
        logger.debug(f"Downloading street network around ({lat:.6f}, {lon:.6f}) within {distance_m:.0f}m")
        
        # Download the network for walking
        # Use simplify=True to reduce node count, truncate_by_edge to get exact radius
        graph = ox.graph_from_point(
            (lat, lon),
            dist=distance_m,
            network_type='walk',
            simplify=True,
            retain_all=False,
            truncate_by_edge=True
        )
        
        logger.debug(f"Downloaded raw network with {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges")
        
        # Filter and annotate edges
        _filter_and_annotate_graph(graph)
        
        logger.debug(f"After filtering: {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges")
        
        return graph
        
    except Exception as e:
        logger.error(f"Failed to download walk network: {e}")
        raise


def _filter_and_annotate_graph(graph: nx.MultiDiGraph) -> None:
    """
    Filter graph in place to remove non-walkable ways and add feature metadata to edges.
    
    Args:
        graph: NetworkX MultiDiGraph to modify in place
    """
    edges_to_remove = []
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        highway_type = data.get('highway', 'unknown')
        
        # Handle multiple highway types (lists)
        if isinstance(highway_type, list):
            highway_type = highway_type[0]
        
        # Mark non-walkable ways for removal
        if highway_type in EXCLUDE_WAYS:
            edges_to_remove.append((u, v, key))
            continue
        
        # Add length attribute if not present
        if 'length' not in data:
            data['length'] = 50.0  # Default segment length in meters
        
        # Extract useful tags for feature-based weighting
        data['leisure'] = data.get('leisure', None)
        data['natural'] = data.get('natural', None)
        data['waterway'] = data.get('waterway', None)
        data['tourism'] = data.get('tourism', None)
        data['man_made'] = data.get('man_made', None)
    
    # Remove marked edges
    for u, v, key in edges_to_remove:
        graph.remove_edge(u, v, key)
    
    logger.debug(f"Removed {len(edges_to_remove)} non-walkable edges")
