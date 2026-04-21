# Running Route Generator

A Python CLI tool that generates optimal running routes from a given address and target distance. Uses OpenStreetMap data and network analysis to create walkable/runnable routes and visualizes them on interactive maps.

## Features

- **Intelligent Route Generation**: Creates multiple candidate routes based on the street network topology
- **Distance-Aware**: Generates routes matching your specified distance (in miles or kilometers)
- **Interactive Visualizations**: Creates HTML maps showing each route with distance markers
- **Caching**: Caches API responses to avoid redundant network calls
- **Route Ranking**: Scores routes based on various metrics to rank quality
- **Comprehensive Reporting**: Generates summary reports with route statistics

## Installation

### Requirements
- Python 3.14 or later

### Setup

1. Clone the repository
2. Install dependencies using uv (recommended) or pip:

```bash
# Using uv (faster)
uv sync

# Or using pip
pip install -e .
```

## Usage

### CLI Mode

Generate a running route from the command line:

```bash
python main.py "address" distance unit
```

**Examples:**
```bash
python main.py "Central Park, NYC" 5 miles
python main.py "Eiffel Tower, Paris" 3 km
python main.py "123 Main St, Boston" 10 km
```

## Output

The tool generates:
- **HTML route maps** (route_01.html, route_02.html, etc.) - interactive visualizations of each candidate route
- **Summary report** (output.txt) - statistics and details about generated routes
- **Cache files** (cache/) - cached geocoding and network data to speed up future runs

## Project Structure

```
├── main.py              # Entry point and orchestration
├── cli.py               # Command-line argument parsing
├── geocode.py           # Address-to-coordinates conversion
├── network.py           # OpenStreetMap network download
├── waypoints.py         # Route candidate generation
├── routing.py           # Route processing and ranking
├── output.py            # Report generation
├── visualization.py     # Map and HTML generation
├── pyproject.toml       # Project configuration
└── cache/               # Cached API responses
```

## Dependencies

- **folium** - Interactive map generation
- **gpxpy** - GPX format handling
- **networkx** - Graph/network algorithms
- **osmnx** - OpenStreetMap network data
- **requests** - HTTP requests
- **scikit-learn** - Machine learning utilities
- **shapely** - Geometric operations

## Development

Run tests:
```bash
pytest
```

Format and lint code:
```bash
ruff check --fix
```
