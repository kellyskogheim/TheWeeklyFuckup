# Plan: Route Generator with OSMnX, NetworkX & FastAPI

## TL;DR
Build a simple web app with REST API that takes an address and distance via an HTML form, downloads the walk network via OSMnX, generates 10 routes with random waypoint counts (2–15), uses shortest_path with custom weights that penalize primary roads and reward parks/water/forests/monuments/bridges, ranks routes by distance tolerance (±20%/−10%) and waypoint preference (4–12), and returns Apple Maps URLs + route stats + GPX files for all ranked routes.

## Steps

### Phase 1: Setup & Dependency Management (blocks phase 2)
1. Update pyproject.toml to add dependencies:
   - `gpxpy>=1.6.0` (GPX export)
   - `fastapi>=0.109.0` + `uvicorn>=0.27.0` (REST API server)
   - `pydantic>=2.5.0` (request/response validation)
2. Update main.py to start FastAPI server on `localhost:8000` (will be expanded in Phase 6)

### Phase 2: Geocoding & Network Download (depends on phase 1; parallel with phase 3)
4. Create `geocode.py` module:
   - Function `address_to_coords(address_str)` → uses OSMnX's `geocode()` to convert address to (lat, lon)
   - Handle geocoding errors (invalid address) with user-friendly messages
5. Create `network.py` module:
   - Function `download_walk_network(lat, lon, distance_m)` → uses OSMnX to download "footway" & "path" ways
   - Filter for walkable ways (exclude motorways, trunk roads, etc.)
   - Return NetworkX MultiDiGraph with full edge metadata (highway type, leisure, natural, man_made tags, distance)

### Phase 3: Waypoint Generation & Route Synthesis (parallel with phase 2)
6. Create `waypoints.py` module:
   - Function `generate_route_candidates(graph, start_lat, start_lon, target_distance_m, num_routes=10)` →
     - For each of 10 routes, randomly select `waypoint_count` from range [2, 15]
     - For each count, randomly sample that many nodes from graph with distributed spacing
     - Return list of 10 route configs: `[(waypoint_count, waypoints_list), ...]`

### Phase 4: Routing with Custom Weights & Distance-Aware Scoring (depends on phase 3)
7. Create `routing.py` module:
   - Function `weight_function(u, v, d, graph)` → custom edge weight multiplier:
     - **Base**: edge length in meters
     - **Penalize**: primary roads (×2.0), trunk roads (×1.5)
     - **Reward**: parks (×0.5), water proximity (×0.7 if waterway tag), forests (×0.6 if `natural=forest`), mountains (×0.7 if `natural=peak`), sculptures (×0.7 if `tourism=artwork`), bridges (×0.8 if `man_made=bridge`)
   - Function `build_route(graph, waypoints, target_distance_m)` →
     - Use `networkx.shortest_path()` with custom weight function to chain waypoints (start → w1 → w2 → ... → start)
     - Return (route_nodes, total_distance_m)
   - Function `score_route(total_distance_m, waypoint_count, target_distance_m)` →
     - **Distance score**: penalize routes outside tolerance bounds (−10% OK, +20% max); bonus for closest to target
     - **Waypoint score**: reward counts in [4, 12]; penalize < 4 or > 12
     - Return composite score (0–100)
   - Function `process_and_rank_routes(routes_with_distances, target_distance_m)` → score all 10 routes, return sorted list (highest → lowest score)

### Phase 5: Output Generation (depends on phase 4)
8. Create `output.py` module:
   - Function `route_to_apple_maps_url(waypoints)` → format Apple Maps URL with waypoint parameters
   - Function `export_gpx(route_nodes, graph, filename)` → convert node sequence to GPX file using `gpxpy`
   - Function `format_route_stats(distance_m, target_distance_m, waypoint_count, score)` → return stats dict with distance variance %, score, waypoint count
   - Function `generate_summary_report(routes_ranked_with_scores)` → return text/JSON listing all 10 routes ranked by score

### Phase 6: API Layer (depends on phases 4–5)
9. Create `api.py` module with FastAPI:
   - Define `RouteRequest` Pydantic model: `address: str, distance_value: float, distance_unit: str`
   - Define `RouteResult` model: `url: str, stats: dict, gpx_data: str (embedded), score: float, rank: int`
   - Define `RouteResponse` model: `routes: List[RouteResult]` (all 10 ranked)
   - Endpoint: `POST /generate-routes` → call orchestration, return JSON response with GPX files embedded or as downloadable links
   - Endpoint: `GET /health` → simple liveness check

### Phase 7: Main Script - Simple Server Startup (depends on api.py)
10. Update main.py to simply start the FastAPI server:
    - Import FastAPI app from `api.py`
    - Start uvicorn server on `localhost:8000`
    - Log server URL for user convenience

## Relevant files
- pyproject.toml — add gpxpy, fastapi, uvicorn, pydantic
- main.py — simple server startup
- New: `geocode.py` — address → lat/lon conversion
- New: `network.py` — OSMnX network download & filtering for walkable ways
- New: `waypoints.py` — probabilistic waypoint selection across 10 routes
- New: `routing.py` — custom weight function with multi-feature rewards, route scoring & ranking
- New: `output.py` — Apple Maps URL formatting, GPX export, stats formatting
- New: `api.py` — FastAPI server with web interface and `/generate-routes` endpoint

## Verification
1. **Unit tests** (pytest): Test each module in isolation
   - `test_geocode.py` — address conversion (mock OSMnX)
   - `test_routing.py` — weight function logic, scoring algorithm (check distance tolerance bounds & waypoint preference)
   - `test_output.py` — URL formatting, GPX validity
   - `test_waypoints.py` — ensure 10 routes generated with waypoint counts in [2, 15]
2. **Integration test (web interface)**: Start server with `python main.py`, then:
   - Open http://localhost:8000 in browser
   - Submit form with address (e.g., "Central Park, NYC") and distance (e.g., "5 miles")
   - Verify 10 routes returned with scores & rankings
   - Verify top-ranked route has waypoint count in [4, 12] range
   - Verify distance variance is within ±20%/−10% tolerance
   - Download and verify GPX file validity
3. **Manual test**: Open Apple Maps URL from top-ranked route in browser, verify waypoints appear on map

## Decisions
- **Web app first**: Single interface via browser, no separate CLI
- **10 random variants** (waypoint_counts randomly in [2, 15]) — provides variety, user sees multiple options
- **Distance tolerance**: ±20%/−10% accepted range (−10% under is better than exceeded); bonus score for closest to target
- **Waypoint preference**: reward [4, 12] range; penalize < 4 (too sparse) or > 12 (too dense)
- **Feature rewards**: parks (×0.5), water (×0.7), forests (×0.6), mountains (×0.7), sculptures (×0.7), bridges (×0.8)
- **API-only architecture**: All orchestration in `/generate-routes` endpoint
- **Apple Maps URLs**: lat/lon coordinates only (simpler, no reverse geocoding delay)
- **All 10 routes returned**: user can compare all options via web UI

## Further Considerations
1. **Distance unit in web form**: The form will let users choose unit (miles/km) via dropdown or radio buttons, then convert to meters in the API endpoint.
2. **Tag-based feature detection** — water, mountains, forests, sculptures, bridges are detected via OSM tags. For complex geometry queries (e.g., ways near water), consider caching results to avoid repeated OSM API calls in future iterations.
3. **API response format for GPX** — FastAPI can embed GPX as text in JSON or serve as file downloads. Decision: embed as text in JSON response for simplicity; web UI can offer download button that saves GPX to user's computer.
4. **Scoring algorithm fine-tuning** — current weights (distance tolerance, waypoint preference) are fixed. If results feel imbalanced, consider making weights configurable via form inputs or config file.
