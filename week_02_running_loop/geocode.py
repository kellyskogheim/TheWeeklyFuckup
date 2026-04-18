"""
Geocoding module: convert addresses to latitude/longitude coordinates.
"""

import logging
from typing import Tuple
import osmnx as ox

logger = logging.getLogger(__name__)


def address_to_coords(address_str: str) -> Tuple[float, float]:
    """
    Convert an address string to latitude and longitude coordinates.
    
    Args:
        address_str: Address or location name (e.g., '123 Main St, NYC' or 'Central Park, NYC')
    
    Returns:
        Tuple of (latitude, longitude)
    
    Raises:
        ValueError: If address cannot be geocoded
    """
    try:
        logger.debug(f"Geocoding address: {address_str}")
        lat, lon = ox.geocode(address_str)
        logger.debug(f"Successfully geocoded to: ({lat:.6f}, {lon:.6f})")
        return (lat, lon)
    except Exception as e:
        logger.error(f"Failed to geocode address '{address_str}': {e}")
        raise ValueError(f"Could not find location: {address_str}") from e
