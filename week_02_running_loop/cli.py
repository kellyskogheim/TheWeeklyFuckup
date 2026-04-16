"""
CLI argument parser for the running route generator.

Handles parsing and validation of command-line arguments.
"""

import argparse
import sys
from typing import Tuple


def parse_args() -> Tuple[str, float, str] | None:
    """
    Parse command-line arguments for route generation.
    
    Expected usage:
        python main.py '123 Main St, City' 5 miles
        python main.py '123 Main St, City' 8 km
    
    Returns:
        Tuple of (address, distance_value, distance_unit) if CLI args present
        None if no CLI args (indicating API mode should be used)
    
    Raises:
        SystemExit: On invalid arguments
    """
    # Check if we have CLI args (excluding the script name)
    if len(sys.argv) == 1:
        # No arguments provided - signal API mode
        return None
    
    parser = argparse.ArgumentParser(
        description="Generate optimal running routes using OSMnX and NetworkX",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "123 Main St, New York" 5 miles
  python main.py "Eiffel Tower, Paris" 3 km
  
Run without arguments to start the API server instead.
        """
    )
    
    parser.add_argument(
        "address",
        type=str,
        help="Address or location name (e.g., '123 Main St, City' or 'Central Park, NYC')"
    )
    
    parser.add_argument(
        "distance",
        type=float,
        help="Distance value (numeric, e.g., 5 or 8.5)"
    )
    
    parser.add_argument(
        "unit",
        type=str,
        choices=["miles", "km", "kilometers"],
        help="Distance unit: 'miles', 'km', or 'kilometers'"
    )
    
    args = parser.parse_args()
    
    # Validate distance is positive
    if args.distance <= 0:
        parser.error("Distance must be a positive value")
    
    # Normalize unit name
    unit = "km" if args.unit in ("km", "kilometers") else "miles"
    
    return (args.address, args.distance, unit)


def distance_to_meters(distance: float, unit: str) -> float:
    """
    Convert distance to meters.
    
    Args:
        distance: Numeric distance value
        unit: Distance unit ('miles' or 'km')
    
    Returns:
        Distance in meters
    
    Raises:
        ValueError: If unit is invalid
    """
    if unit == "miles":
        # 1 mile = 1609.34 meters
        return distance * 1609.34
    elif unit == "km":
        # 1 km = 1000 meters
        return distance * 1000.0
    else:
        raise ValueError(f"Unknown unit: {unit}")
