"""
Visualization module: generate interactive HTML maps for routes using Folium.
"""

import logging
from typing import List, Dict, Any
import networkx as nx

logger = logging.getLogger(__name__)


def generate_route_maps(
    routes_ranked: List[Dict[str, Any]],
    graph: nx.MultiDiGraph,
    output_directory: str = "."
) -> List[str]:
    """
    Generate individual interactive Folium maps for each ranked route.
    
    Creates HTML files like: route_01.html, route_02.html, etc.
    Each map shows:
    - The complete route path rendered on OpenStreetMap
    - Waypoints marked with numbered circles
    - Route statistics in a popup info box
    - Distinct colors based on rank
    
    Args:
        routes_ranked: List of route dicts from process_and_rank_routes()
        graph: NetworkX graph containing node coordinates
        output_directory: Directory to save HTML files (default: current directory)
    
    Returns:
        List of generated file paths
    
    Raises:
        ImportError: If folium is not installed
        Exception: If map generation fails
    """
    try:
        import folium
        from folium import plugins
    except ImportError:
        logger.error("folium is not installed. Install with: uv pip install folium")
        raise
    
    if not routes_ranked:
        logger.warning("No routes to visualize")
        return []
    
    generated_files = []
    
    # Define color scheme based on rank (greener = better)
    rank_colors = [
        '#2ecc71',  # Rank 1: Green (best)
        '#27ae60',  # Rank 2: Dark green
        '#3498db',  # Rank 3: Blue
        '#9b59b6',  # Rank 4: Purple
        '#e74c3c',  # Rank 5: Red
        '#e67e22',  # Rank 6: Orange
        '#f39c12',  # Rank 7: Yellow
        '#16a085',  # Rank 8: Teal
        '#c0392b',  # Rank 9: Dark red
        '#95a5a6',  # Rank 10: Gray
    ]
    
    for route_idx, route in enumerate(routes_ranked):
        try:
            rank = route['rank']
            score = route['score']
            distance_m = route['distance_m']
            distance_variance = route['distance_variance']
            waypoint_count = route['waypoint_count']
            route_nodes = route['route_nodes']
            
            # Extract coordinates from route nodes
            route_coords = []
            for node_id in route_nodes:
                if node_id not in graph.nodes:
                    continue
                node_data = graph.nodes[node_id]
                lat = node_data.get('y')
                lon = node_data.get('x')
                if lat is not None and lon is not None:
                    route_coords.append((lat, lon))
            
            if not route_coords:
                logger.warning(f"Route {rank}: No coordinates found, skipping")
                continue
            
            # Calculate map center (middle of route for better framing)
            center_lat = sum(c[0] for c in route_coords) / len(route_coords)
            center_lon = sum(c[1] for c in route_coords) / len(route_coords)
            
            # Create folium map centered on route
            route_map = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=14,
                tiles='OpenStreetMap'
            )
            
            # Get color for this rank
            color = rank_colors[rank - 1] if rank - 1 < len(rank_colors) else '#95a5a6'
            
            # Draw the route path
            folium.PolyLine(
                locations=route_coords,
                color=color,
                weight=3,
                opacity=0.8,
                popup=f"Route #{rank}"
            ).add_to(route_map)
            
            # Mark waypoints with numbered circles
            for idx, (lat, lon) in enumerate(route_coords):
                # Show marker for first, last, and every nth waypoint to avoid clutter
                if idx == 0 or idx == len(route_coords) - 1 or idx % max(1, len(route_coords) // 10) == 0:
                    folium.CircleMarker(
                        location=[lat, lon],
                        radius=6,
                        popup=f"Waypoint {idx}",
                        color=color,
                        fill=True,
                        fillColor=color,
                        fillOpacity=0.8,
                        weight=2
                    ).add_to(route_map)
            
            # Add start/end markers more prominently
            if len(route_coords) > 0:
                folium.Marker(
                    location=route_coords[0],
                    popup="Start",
                    icon=folium.Icon(color='green', icon='play')
                ).add_to(route_map)
                
                folium.Marker(
                    location=route_coords[-1],
                    popup="End",
                    icon=folium.Icon(color='red', icon='stop')
                ).add_to(route_map)
            
            # Add route statistics as control panel
            html_stats = f"""
            <div style="
                position: fixed;
                bottom: 50px; left: 50px; width: 280px; height: auto;
                background-color: white; border:2px solid grey; z-index:9999;
                font-size:14px; padding: 10px; border-radius: 5px;
                box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
            ">
                <b>Route #{rank}</b><br>
                <hr style="margin: 5px 0;">
                <b>Score:</b> {score:.1f}/100<br>
                <b>Distance:</b> {distance_m:.0f}m ({distance_variance:+.1%})<br>
                <b>Waypoints:</b> {waypoint_count}<br>
            </div>
            """
            
            route_map.get_root().html.add_child(folium.Element(html_stats))
            
            # Save map to HTML file
            output_path = f"{output_directory}/route_{rank:02d}.html"
            route_map.save(output_path)
            generated_files.append(output_path)
            
            logger.info(f"Generated map: {output_path} (Rank #{rank}, Score: {score:.1f})")
            
        except Exception as e:
            logger.error(f"Failed to generate map for route {rank}: {e}")
            continue
    
    logger.info(f"Generated {len(generated_files)} route maps")
    return generated_files
