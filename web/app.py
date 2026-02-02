"""
MapToPoster Web Application
===========================
MVP v1.6 - 2026-02-02

INSTANT LAYER TOGGLING with proper variants:
- Water & Parks toggle
- Simple streets vs All streets (with paths)
"""

import matplotlib
matplotlib.use('Agg')

import asyncio
import gc
import os
import re
import sys
import uuid
import time
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

os.environ['USE_PYGEOS'] = '0'

from web.image_utils import generate_preview_from_png, r2_storage

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent))

import osmnx as ox

ox.settings.use_cache = True
ox.settings.cache_folder = str(Path(__file__).parent / "cache")
Path(ox.settings.cache_folder).mkdir(exist_ok=True)
ox.settings.timeout = 30

from create_map_poster import (
    get_coordinates,
    load_theme,
    get_available_themes,
    THEMES_DIR,
    POSTERS_DIR,
    load_fonts,
    fetch_graph,
    fetch_features,
    get_edge_colors_by_type,
    get_edge_widths_by_type,
    create_gradient_fade,
    get_crop_limits,
    is_latin_script,
    FONTS,
)
import create_map_poster
import networkx as nx

# Highway types for filtering
HIGHWAY_DRIVE = {
    "motorway", "motorway_link", "trunk", "trunk_link", 
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "residential", "living_street", 
    "unclassified", "road"
}
HIGHWAY_PATHS = {
    "footway", "path", "pedestrian", "steps", "track", 
    "bridleway", "corridor", "living_street"
}
HIGHWAY_CYCLING = {
    "cycleway", "path"  # path can be used for cycling too
}


def filter_graph_by_highway_types(graph, include_types: set):
    """Filter graph edges to only include specified highway types."""
    if graph is None:
        return None
    
    # Create a copy of the graph
    filtered = graph.copy()
    
    # Find edges to remove
    edges_to_remove = []
    for u, v, key, data in filtered.edges(keys=True, data=True):
        highway = data.get('highway', 'unclassified')
        if isinstance(highway, list):
            highway_types = set(highway)
        else:
            highway_types = {highway}
        
        # Keep edge if ANY of its highway types match our include list
        if not highway_types.intersection(include_types):
            edges_to_remove.append((u, v, key))
    
    # Remove filtered edges
    filtered.remove_edges_from(edges_to_remove)
    
    # Remove isolated nodes (nodes with no edges)
    isolated = [node for node in filtered.nodes() if filtered.degree(node) == 0]
    filtered.remove_nodes_from(isolated)
    
    return filtered


def get_filtered_graph(graph_all, features: dict):
    """Get a graph filtered based on feature toggles."""
    if graph_all is None:
        return None
    
    include_types = set()
    
    # Build the set of highway types to include
    if features.get("roads_drive", True):
        include_types.update(HIGHWAY_DRIVE)
    
    if features.get("roads_paths", True):
        include_types.update(HIGHWAY_PATHS)
    
    if features.get("roads_cycling", True):
        include_types.update(HIGHWAY_CYCLING)
    
    # If all road types are enabled, just return the original graph
    if features.get("roads_drive", True) and features.get("roads_paths", True) and features.get("roads_cycling", True):
        return graph_all
    
    # If no road types are enabled, return the original graph (we need SOMETHING to render)
    # The map will still show water/parks if enabled
    if not include_types:
        return graph_all  # Return full graph, it will still be rendered but features control visibility
    
    return filter_graph_by_highway_types(graph_all, include_types)

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

app = FastAPI(title="MapToPoster", version="MVP-1.6.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

posters_path = Path(__file__).parent.parent / POSTERS_DIR
posters_path.mkdir(exist_ok=True)
app.mount("/posters", StaticFiles(directory=str(posters_path)), name="posters")

previews_path = Path(__file__).parent / "previews"
previews_path.mkdir(exist_ok=True)
app.mount("/previews", StaticFiles(directory=str(previews_path)), name="previews")


# ============================================
# Memory Cleanup
# ============================================

async def cleanup_old_jobs():
    """Remove expired jobs and their associated data."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            current_time = time.time()
            expired_jobs = []
            
            for job_id, job_data in list(jobs.items()):
                created_at = job_data.get("created_at", current_time)
                if current_time - created_at > JOB_EXPIRY_SECONDS:
                    expired_jobs.append(job_id)
            
            for job_id in expired_jobs:
                # Clear large data (graphs, etc.)
                if job_id in jobs:
                    job = jobs[job_id]
                    for radius_data in job.get("radiuses", {}).values():
                        radius_data["graph_drive"] = None
                        radius_data["graph_all"] = None
                        radius_data["water"] = None
                        radius_data["parks"] = None
                    del jobs[job_id]
                    print(f"  [cleanup] Removed expired job: {job_id}")
                
                if job_id in cancelled_jobs:
                    cancelled_jobs.discard(job_id)
            
            if expired_jobs:
                gc.collect()
                print(f"  [cleanup] Cleaned up {len(expired_jobs)} expired jobs")
                
        except Exception as e:
            print(f"  [cleanup] Error during cleanup: {e}")


@app.on_event("startup")
async def startup_event():
    """Start background cleanup task on server startup."""
    asyncio.create_task(cleanup_old_jobs())
    print("✓ Job cleanup task started")


class MapFeatures(BaseModel):
    water: bool = Field(default=True)
    parks: bool = Field(default=True)
    roads_drive: bool = Field(default=True)
    roads_paths: bool = Field(default=True)
    roads_cycling: bool = Field(default=True)
    # Legacy fields for backwards compatibility
    roads: bool = Field(default=True)
    paths: bool = Field(default=False)


class PosterRequest(BaseModel):
    city: str = Field(..., min_length=1)
    country: str = Field(..., min_length=1)
    theme: str = Field(default="noir")
    distance: int = Field(default=3000, ge=1000, le=20000)
    width: float = Field(default=12, ge=3, le=32)
    height: float = Field(default=16, ge=3, le=32)
    features: MapFeatures = Field(default_factory=MapFeatures)


class PreviewRequest(PosterRequest):
    pass


jobs: dict = {}
cancelled_jobs: set = set()
executor = ThreadPoolExecutor(max_workers=8)
MAX_PREVIEW_DISTANCE = 20000

# Progressive loading radiuses (in meters)
AVAILABLE_RADIUSES = [5000, 10000]  # Free tier
LOCKED_RADIUSES = [15000, 20000]    # Requires signup (future)
ALL_RADIUSES = AVAILABLE_RADIUSES + LOCKED_RADIUSES
INITIAL_RADIUS = 10000  # Default: 10km with all roads

# Memory cleanup settings
JOB_EXPIRY_SECONDS = 1800  # 30 minutes
CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes


def fetch_graph_fast(point, dist, network_type='drive'):
    """Fetch graph with optimizations for speed."""
    try:
        g = ox.graph_from_point(
            point, dist=dist, dist_type='bbox',
            network_type=network_type, truncate_by_edge=True, simplify=True
        )
        return g
    except Exception as e:
        print(f"Graph fetch error: {e}")
        return None


def fetch_water_fast(point, dist):
    if dist > 15000:
        return None
    try:
        return fetch_features(
            point, dist,
            tags={"natural": ["water", "bay"], "waterway": "riverbank"},
            name="water"
        )
    except Exception:
        return None


def fetch_parks_fast(point, dist):
    if dist > 15000:
        return None
    try:
        return fetch_features(
            point, dist,
            tags={"leisure": "park", "landuse": "grass"},
            name="parks"
        )
    except Exception:
        return None


@app.get("/")
async def root():
    return FileResponse(static_path / "index.html")


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "MVP-1.6.0"}


@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str):
    if job_id not in jobs:
        return {"status": "not_found"}
    
    job = jobs[job_id]
    
    # Return only JSON-serializable fields (exclude graph objects, GeoDataFrames)
    return {
        "status": job.get("status"),
        "step": job.get("step"),
        "total": job.get("total"),
        "message": job.get("message"),
        "percent": job.get("percent"),
        "preview_url": job.get("preview_url"),
        "poster_url": job.get("poster_url"),  # For final generation
        "filename": job.get("filename"),       # For final generation
        "error": job.get("error"),
        "current_radius": job.get("current_radius"),
        "settings": job.get("settings"),
        "variants": job.get("variants"),
        "coords": job.get("coords"),
    }


@app.post("/api/cancel/{job_id}")
async def cancel_job(job_id: str):
    if job_id in jobs:
        cancelled_jobs.add(job_id)
        jobs[job_id]["status"] = "cancelled"
        jobs[job_id]["message"] = "Cancelled"
        return {"status": "cancelled"}
    return {"status": "not_found"}


@app.get("/generate")
async def generate_page():
    return FileResponse(static_path / "generate.html")


@app.get("/api/themes")
async def get_themes():
    themes = []
    for theme_name in get_available_themes():
        theme_data = load_theme(theme_name)
        themes.append({
            "name": theme_name,
            "display_name": theme_data.get("name", theme_name),
            "description": theme_data.get("description", ""),
            "bg": theme_data.get("bg", "#ffffff"),
            "text": theme_data.get("text", "#000000"),
        })
    return themes


@app.get("/api/examples")
async def get_examples():
    return [
        {"city": "San Francisco", "country": "USA", "theme": "sunset",
         "description": "Warm oranges and pinks - golden hour aesthetic",
         "image": "/static/examples/san_francisco_sunset_thumb.webp",
         "preview": "/static/examples/san_francisco_sunset_preview.webp"},
        {"city": "Tokyo", "country": "Japan", "theme": "japanese_ink",
         "description": "Traditional ink wash - minimalist with subtle red accent",
         "image": "/static/examples/tokyo_japanese_ink_thumb.webp",
         "preview": "/static/examples/tokyo_japanese_ink_preview.webp"},
        {"city": "Venice", "country": "Italy", "theme": "blueprint",
         "description": "Classic architectural blueprint - technical drawing aesthetic",
         "image": "/static/examples/venice_blueprint_thumb.webp",
         "preview": "/static/examples/venice_blueprint_preview.webp"},
        {"city": "Dubai", "country": "UAE", "theme": "midnight_blue",
         "description": "Deep navy with gold roads - luxury atlas aesthetic",
         "image": "/static/examples/dubai_midnight_blue_thumb.webp",
         "preview": "/static/examples/dubai_midnight_blue_preview.webp"},
        {"city": "Singapore", "country": "Singapore", "theme": "neon_cyberpunk",
         "description": "Electric pink and cyan - bold night city vibes",
         "image": "/static/examples/singapore_neon_cyberpunk_thumb.webp",
         "preview": "/static/examples/singapore_neon_cyberpunk_preview.webp"},
        {"city": "Prague", "country": "Czech Republic", "theme": "noir",
         "description": "Pure black with white roads - modern gallery aesthetic",
         "image": "/static/examples/prague_noir_thumb.webp",
         "preview": "/static/examples/prague_noir_preview.webp"},
    ]


def render_full_poster(
    city, country, graph, water, parks, point, width, height, theme, fonts, 
    output_file, compensated_dist, include_water_parks=True
):
    """Render complete poster with text."""
    THEME = theme
    create_map_poster.THEME = THEME
    
    fig, ax = plt.subplots(figsize=(width, height), facecolor=THEME["bg"])
    ax.set_facecolor(THEME["bg"])
    ax.set_position((0.0, 0.0, 1.0, 1.0))
    
    # Handle case where graph might be None or empty
    if graph is None or len(graph.edges()) == 0:
        # Just render background with water/parks if available
        g_proj = None
    else:
        g_proj = ox.project_graph(graph)
    
    # Plot water (if enabled)
    if include_water_parks and water is not None and not water.empty:
        water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not water_polys.empty:
            try:
                water_polys = ox.projection.project_gdf(water_polys)
            except:
                try:
                    if g_proj is not None:
                        water_polys = water_polys.to_crs(g_proj.graph['crs'])
                except:
                    pass
            try:
                water_polys.plot(ax=ax, facecolor=THEME['water'], edgecolor='none', zorder=0.5)
            except:
                pass
    
    # Plot parks (if enabled)
    if include_water_parks and parks is not None and not parks.empty:
        parks_polys = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not parks_polys.empty:
            try:
                parks_polys = ox.projection.project_gdf(parks_polys)
            except:
                try:
                    if g_proj is not None:
                        parks_polys = parks_polys.to_crs(g_proj.graph['crs'])
                except:
                    pass
            try:
                parks_polys.plot(ax=ax, facecolor=THEME['parks'], edgecolor='none', zorder=0.8)
            except:
                pass
    
    # Plot roads (if we have a graph)
    if g_proj is not None:
        edge_colors = get_edge_colors_by_type(g_proj)
        edge_widths = get_edge_widths_by_type(g_proj)
        
        # Use the actual compensated_dist for crop!
        crop_xlim, crop_ylim = get_crop_limits(g_proj, point, fig, compensated_dist)
        
        ox.plot_graph(
            g_proj, ax=ax, bgcolor=THEME['bg'],
            node_size=0, edge_color=edge_colors, edge_linewidth=edge_widths,
            show=False, close=False,
        )
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(crop_xlim)
        ax.set_ylim(crop_ylim)
    else:
        # No roads to plot, just set up basic axes
        ax.set_aspect("equal", adjustable="box")
        ax.axis('off')
    
    create_gradient_fade(ax, THEME['gradient_color'], location='bottom', zorder=10)
    create_gradient_fade(ax, THEME['gradient_color'], location='top', zorder=10)
    
    # Typography
    scale_factor = min(height, width) / 12.0
    active_fonts = fonts or FONTS
    
    if is_latin_script(city):
        spaced_city = "  ".join(list(city.upper()))
    else:
        spaced_city = city
    
    base_main = 60 * scale_factor
    adjusted_font_size = max(base_main * (10 / len(city)), 10 * scale_factor) if len(city) > 10 else base_main
    
    if active_fonts:
        font_main = FontProperties(fname=active_fonts["bold"], size=adjusted_font_size)
        font_sub = FontProperties(fname=active_fonts["light"], size=22 * scale_factor)
        font_coords = FontProperties(fname=active_fonts["regular"], size=14 * scale_factor)
    else:
        font_main = FontProperties(family="monospace", weight="bold", size=adjusted_font_size)
        font_sub = FontProperties(family="monospace", size=22 * scale_factor)
        font_coords = FontProperties(family="monospace", size=14 * scale_factor)
    
    ax.text(0.5, 0.14, spaced_city, transform=ax.transAxes, color=THEME["text"],
            ha="center", fontproperties=font_main, zorder=11)
    ax.text(0.5, 0.10, country.upper(), transform=ax.transAxes, color=THEME["text"],
            ha="center", fontproperties=font_sub, zorder=11)
    
    lat, lon = point
    coords_text = f"{lat:.4f}° {'N' if lat >= 0 else 'S'} / {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}"
    ax.text(0.5, 0.07, coords_text, transform=ax.transAxes, color=THEME["text"],
            alpha=0.7, ha="center", fontproperties=font_coords, zorder=11)
    
    ax.plot([0.4, 0.6], [0.125, 0.125], transform=ax.transAxes, color=THEME["text"],
            linewidth=1 * scale_factor, zorder=11)
    
    plt.savefig(output_file, format="png", dpi=72, facecolor=THEME["bg"],
                bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    plt.close('all')
    gc.collect()
    
    return True


@app.post("/api/preview/start")
async def start_preview(request: PreviewRequest):
    """Generate preview with progressive radius loading.
    
    Flow:
    1. Fetch 5km data first (fast) -> show preview immediately
    2. Background fetch 10km, 15km, 20km data
    3. Radiuses "unlock" as data becomes available
    """
    print(f"\n{'='*50}")
    print(f"✓ Preview: {request.city}, {request.country} (Progressive Loading)")
    print(f"{'='*50}")
    
    available_themes = get_available_themes()
    if request.theme not in available_themes:
        raise HTTPException(status_code=400, detail=f"Theme '{request.theme}' not found")
    
    job_id = uuid.uuid4().hex[:8]
    city_slug = re.sub(r'[\\/:*?"<>|,\s]', '_', request.city.lower())
    base_name = f"preview_{city_slug}_{request.theme}_{job_id}"
    
    # New job structure with per-radius data storage
    jobs[job_id] = {
        "status": "starting",
        "step": 0,
        "total": 4,
        "message": "Finding your location...",
        "percent": 0,
        "preview_url": None,
        "variants": {},
        "error": None,
        "created_at": time.time(),  # For cleanup
        # Progressive loading state
        "coords": None,
        "base_name": base_name,
        "theme_name": request.theme,
        "radiuses": {
            # Available radiuses (free tier)
            5000: {"status": "pending", "graph_drive": None, "graph_all": None, "water": None, "parks": None, "preview_url": None},
            10000: {"status": "pending", "graph_drive": None, "graph_all": None, "water": None, "parks": None, "preview_url": None},
            # Locked radiuses (require signup - future feature)
            15000: {"status": "locked", "graph_drive": None, "graph_all": None, "water": None, "parks": None, "preview_url": None},
            20000: {"status": "locked", "graph_drive": None, "graph_all": None, "water": None, "parks": None, "preview_url": None},
        },
        "current_radius": INITIAL_RADIUS,
        # Current feature toggles
        "features": {
            "parks": True,
            "water": True,
            "roads_drive": True,
            "roads_paths": True,
            "roads_cycling": True,
        },
        "settings": {
            "city": request.city,
            "country": request.country,
            "theme": request.theme,
            "width": request.width,
            "height": request.height,
        }
    }
    
    async def run_progressive_generation():
        start_time = time.time()
        
        try:
            jobs[job_id].update({
                "status": "running",
                "step": 1,
                "message": "Finding your location...",
                "percent": 5
            })
            
            try:
                coords = get_coordinates(request.city, request.country)
                jobs[job_id]["coords"] = list(coords)
                print(f"  [{job_id}] Location: {coords} ({time.time()-start_time:.1f}s)")
            except ValueError as e:
                jobs[job_id].update({"status": "error", "error": str(e)})
                return
            
            theme = load_theme(request.theme)
            fonts = load_fonts()
            
            preview_width = request.width / 1.5
            preview_height = request.height / 1.5
            aspect_ratio = max(preview_height, preview_width) / min(preview_height, preview_width)
            
            loop = asyncio.get_event_loop()
            
            # ============================================
            # Phase 1: Load 10km preview (default)
            # ============================================
            initial_radius = INITIAL_RADIUS  # 10km
            compensated_dist = initial_radius * aspect_ratio / 4
            
            jobs[job_id]["radiuses"][initial_radius]["status"] = "loading"
            
            jobs[job_id].update({
                "step": 2,
                "message": "Downloading street data...",
                "percent": 15
            })
            
            print(f"  [{job_id}] Fetching {initial_radius//1000}km streets (all roads)...")
            
            # Fetch all network (includes drive, paths, cycling)
            all_task = loop.run_in_executor(executor, fetch_graph_fast, coords, compensated_dist, 'all')
            
            street_start = time.time()
            while not all_task.done():
                if job_id in cancelled_jobs:
                    return
                await asyncio.sleep(0.5)
                elapsed = time.time() - street_start
                progress = min(40, 15 + (elapsed / 30) * 25)
                jobs[job_id].update({
                    "percent": int(progress),
                    "message": f"Loading streets... ({elapsed:.0f}s)"
                })
            
            g_all = await all_task
            print(f"  [{job_id}] {initial_radius//1000}km streets done ({time.time()-start_time:.1f}s)")
            
            if g_all is None:
                jobs[job_id].update({"status": "error", "error": "Failed to load street data"})
                return
            
            # Fetch water and parks
            jobs[job_id].update({
                "step": 3,
                "message": "Adding water & parks...",
                "percent": 45
            })
            
            print(f"  [{job_id}] Fetching water & parks...")
            water_task = loop.run_in_executor(executor, fetch_water_fast, coords, compensated_dist)
            parks_task = loop.run_in_executor(executor, fetch_parks_fast, coords, compensated_dist)
            
            features_start = time.time()
            while not (water_task.done() and parks_task.done()):
                if job_id in cancelled_jobs:
                    return
                await asyncio.sleep(0.3)
                elapsed = time.time() - features_start
                progress = min(70, 45 + (elapsed / 10) * 25)
                jobs[job_id].update({"percent": int(progress)})
            
            water = await water_task
            parks = await parks_task
            print(f"  [{job_id}] Water & parks done ({time.time()-start_time:.1f}s)")
            
            # Store 10km data
            jobs[job_id]["radiuses"][initial_radius].update({
                "graph_all": g_all,
                "water": water,
                "parks": parks,
                "compensated_dist": compensated_dist,
            })
            
            # Render 10km preview
            jobs[job_id].update({
                "step": 4,
                "message": "Composing your map...",
                "percent": 75
            })
            
            main_file = f"{base_name}_{initial_radius//1000}km.png"
            main_path = str(previews_path / main_file)
            
            print(f"  [{job_id}] Rendering {initial_radius//1000}km preview...")
            render_task = loop.run_in_executor(
                executor,
                render_full_poster,
                request.city, request.country, g_all, water, parks,
                coords, preview_width, preview_height, theme, fonts,
                main_path, compensated_dist, True
            )
            
            render_start = time.time()
            while not render_task.done():
                if job_id in cancelled_jobs:
                    return
                await asyncio.sleep(0.2)
                elapsed = time.time() - render_start
                progress = min(95, 75 + (elapsed / 5) * 20)
                jobs[job_id].update({"percent": int(progress)})
            
            await render_task
            
            total_time = time.time() - start_time
            print(f"  [{job_id}] ✓ {initial_radius//1000}km preview done in {total_time:.1f}s")
            
            # Mark 10km as ready
            jobs[job_id]["radiuses"][initial_radius].update({
                "status": "ready",
                "preview_url": f"/previews/{main_file}",
            })
            
            # Complete initial preview
            jobs[job_id].update({
                "status": "complete",
                "step": 4,
                "total": 4,
                "message": "Done!",
                "percent": 100,
                "preview_url": f"/previews/{main_file}",
                "current_radius": initial_radius,
                "variants": {},
                "settings": {
                    "city": request.city,
                    "country": request.country,
                    "theme": request.theme,
                    "distance": initial_radius,
                    "width": request.width,
                    "height": request.height,
                }
            })
            
            # ============================================
            # Phase 2: Background fetch 5km (smaller radius)
            # ============================================
            asyncio.create_task(fetch_other_radiuses_background(
                job_id, coords, aspect_ratio, preview_width, preview_height,
                theme, fonts, request.city, request.country
            ))
            
            gc.collect()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            jobs[job_id].update({"status": "error", "error": str(e)})
    
    asyncio.create_task(run_progressive_generation())
    return {"job_id": job_id, "status": "started"}


async def fetch_other_radiuses_background(
    job_id, coords, aspect_ratio, preview_width, preview_height,
    theme, fonts, city, country
):
    """Fetch 5km data in background after 10km is shown.
    
    Note: 15km and 20km are locked (require signup - future feature).
    """
    try:
        loop = asyncio.get_event_loop()
        base_name = jobs[job_id]["base_name"]
        
        # Only fetch 5km (10km already loaded, 15km/20km locked)
        for radius in [5000]:
            if job_id not in jobs or job_id in cancelled_jobs:
                return
            
            compensated_dist = radius * aspect_ratio / 4
            
            jobs[job_id]["radiuses"][radius]["status"] = "loading"
            print(f"  [{job_id}] Background: fetching {radius/1000:.0f}km data...")
            
            # Fetch all streets
            g_all = await loop.run_in_executor(
                executor, fetch_graph_fast, coords, compensated_dist, 'all'
            )
            
            if g_all is None:
                jobs[job_id]["radiuses"][radius]["status"] = "error"
                print(f"  [{job_id}] Failed to fetch {radius/1000:.0f}km streets")
                continue
            
            # Fetch water and parks
            water = await loop.run_in_executor(executor, fetch_water_fast, coords, compensated_dist)
            parks = await loop.run_in_executor(executor, fetch_parks_fast, coords, compensated_dist)
            
            # Store data
            jobs[job_id]["radiuses"][radius].update({
                "graph_all": g_all,
                "water": water,
                "parks": parks,
                "compensated_dist": compensated_dist,
            })
            
            # Render preview for this radius
            preview_file = f"{base_name}_{radius//1000}km.png"
            preview_path = str(previews_path / preview_file)
            
            await loop.run_in_executor(
                executor,
                render_full_poster,
                city, country, g_all, water, parks,
                coords, preview_width, preview_height, theme, fonts,
                preview_path, compensated_dist, True
            )
            
            # Mark as ready
            jobs[job_id]["radiuses"][radius].update({
                "status": "ready",
                "preview_url": f"/previews/{preview_file}",
            })
            
            print(f"  [{job_id}] ✓ {radius/1000:.0f}km ready!")
        
        print(f"  [{job_id}] ✓ All available radiuses ready!")
        
    except Exception as e:
        print(f"  [{job_id}] Background radius fetch error: {e}")
        import traceback
        traceback.print_exc()


async def render_variants_background(
    job_id, base_name, city, country,
    g_drive, water, parks, point,
    width, height, theme, fonts, compensated_dist
):
    """Render variant images in background for instant toggling."""
    try:
        loop = asyncio.get_event_loop()
        
        # Variant 1: Drive streets without water/parks
        no_wp_file = f"{base_name}_no_wp.png"
        no_wp_path = str(previews_path / no_wp_file)
        print(f"  [{job_id}] Rendering drive_no_wp variant...")
        await loop.run_in_executor(
            executor,
            render_full_poster,
            city, country, g_drive, water, parks,
            point, width, height, theme, fonts,
            no_wp_path, compensated_dist, False  # include_water_parks=False
        )
        if job_id in jobs:
            jobs[job_id]["variants"]["drive_no_wp"] = f"/previews/{no_wp_file}"
        print(f"  [{job_id}] ✓ drive_no_wp ready")
        
        # Fetch all streets (with paths) in background
        print(f"  [{job_id}] Fetching all streets (with paths)...")
        g_all = await loop.run_in_executor(
            executor, fetch_graph_fast, point, compensated_dist, 'all'
        )
        
        if g_all is not None:
            # Variant 2: All streets with water/parks
            all_wp_file = f"{base_name}_all_wp.png"
            all_wp_path = str(previews_path / all_wp_file)
            print(f"  [{job_id}] Rendering all_with_wp variant...")
            await loop.run_in_executor(
                executor,
                render_full_poster,
                city, country, g_all, water, parks,
                point, width, height, theme, fonts,
                all_wp_path, compensated_dist, True
            )
            if job_id in jobs:
                jobs[job_id]["variants"]["all_with_wp"] = f"/previews/{all_wp_file}"
            print(f"  [{job_id}] ✓ all_with_wp ready")
            
            # Variant 3: All streets without water/parks
            all_no_wp_file = f"{base_name}_all_no_wp.png"
            all_no_wp_path = str(previews_path / all_no_wp_file)
            print(f"  [{job_id}] Rendering all_no_wp variant...")
            await loop.run_in_executor(
                executor,
                render_full_poster,
                city, country, g_all, water, parks,
                point, width, height, theme, fonts,
                all_no_wp_path, compensated_dist, False
            )
            if job_id in jobs:
                jobs[job_id]["variants"]["all_no_wp"] = f"/previews/{all_no_wp_file}"
            print(f"  [{job_id}] ✓ all_no_wp ready")
        
        print(f"  [{job_id}] ✓ All variants ready!")
        
    except Exception as e:
        print(f"  [{job_id}] Variant render error: {e}")


@app.get("/api/variants/{job_id}")
async def get_variants(job_id: str):
    """Get available variants for a job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"variants": jobs[job_id].get("variants", {})}


@app.get("/api/radiuses/{job_id}")
async def get_radiuses(job_id: str):
    """Get status of all radiuses for progressive loading."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    radiuses_status = {}
    
    for radius, data in job.get("radiuses", {}).items():
        radiuses_status[str(radius)] = {
            "status": data.get("status", "pending"),
            "preview_url": data.get("preview_url"),
        }
    
    return {
        "radiuses": radiuses_status,
        "current_radius": job.get("current_radius", INITIAL_RADIUS),
    }


class RadiusSwitchRequest(BaseModel):
    radius: int = Field(..., ge=1000, le=20000)


@app.post("/api/preview/radius/{job_id}")
async def switch_radius(job_id: str, request: RadiusSwitchRequest):
    """Switch to a different radius preview."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    radius = request.radius
    
    # Check if this radius exists
    if radius not in job.get("radiuses", {}):
        raise HTTPException(status_code=400, detail=f"Radius {radius}m not available")
    
    radius_data = job["radiuses"][radius]
    
    # Check if locked (requires signup)
    if radius_data.get("status") == "locked":
        raise HTTPException(status_code=403, detail=f"Radius {radius}m requires signup")
    
    if radius_data.get("status") != "ready":
        raise HTTPException(status_code=400, detail=f"Radius {radius}m is still loading")
    
    preview_url = radius_data.get("preview_url")
    if not preview_url:
        raise HTTPException(status_code=400, detail=f"No preview available for {radius}m")
    
    # Update current radius and settings
    job["current_radius"] = radius
    job["preview_url"] = preview_url
    job["settings"]["distance"] = radius
    
    return {
        "preview_url": preview_url,
        "radius": radius,
        "status": "ready"
    }


class ThemeSwitchRequest(BaseModel):
    theme: str


@app.post("/api/preview/theme/{job_id}")
async def switch_theme(job_id: str, request: ThemeSwitchRequest):
    """Switch theme and re-render preview with cached data."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    current_radius = job.get("current_radius", INITIAL_RADIUS)
    radius_data = job["radiuses"].get(current_radius, {})
    
    # Check if we have cached data
    if radius_data.get("status") != "ready" or radius_data.get("graph_all") is None:
        raise HTTPException(status_code=400, detail="Preview data not ready")
    
    # Validate theme
    available_themes = get_available_themes()
    if request.theme not in available_themes:
        raise HTTPException(status_code=400, detail=f"Theme '{request.theme}' not found")
    
    theme = load_theme(request.theme)
    fonts = load_fonts()
    
    coords = tuple(job["coords"])
    settings = job["settings"]
    preview_width = settings["width"] / 1.5
    preview_height = settings["height"] / 1.5
    
    # Generate new filename with theme
    base_name = job["base_name"].rsplit('_', 1)[0]  # Remove old theme suffix
    new_file = f"{base_name}_{request.theme}_{current_radius//1000}km.png"
    new_path = str(previews_path / new_file)
    
    loop = asyncio.get_event_loop()
    
    # Re-render with new theme using cached data
    features = job.get("features", {})
    include_wp = features.get("parks", True) or features.get("water", True)
    
    await loop.run_in_executor(
        executor,
        render_full_poster,
        settings["city"], settings["country"],
        radius_data["graph_all"],
        radius_data["water"] if features.get("water", True) else None,
        radius_data["parks"] if features.get("parks", True) else None,
        coords, preview_width, preview_height, theme, fonts,
        new_path, radius_data["compensated_dist"], include_wp
    )
    
    # Update job state
    job["theme_name"] = request.theme
    job["settings"]["theme"] = request.theme
    job["preview_url"] = f"/previews/{new_file}"
    radius_data["preview_url"] = f"/previews/{new_file}"
    
    return {
        "preview_url": f"/previews/{new_file}",
        "theme": request.theme,
        "status": "ready"
    }


class FeatureToggleRequest(BaseModel):
    parks: Optional[bool] = None
    water: Optional[bool] = None
    roads_drive: Optional[bool] = None
    roads_paths: Optional[bool] = None
    roads_cycling: Optional[bool] = None


@app.post("/api/preview/features/{job_id}")
async def toggle_features(job_id: str, request: FeatureToggleRequest):
    """Toggle map features and re-render preview.
    
    Note: Currently parks and water are toggled together (water & greenery).
    Road types (drive, paths, cycling) require different graph data.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    current_radius = job.get("current_radius", INITIAL_RADIUS)
    radius_data = job["radiuses"].get(current_radius, {})
    
    if radius_data.get("status") != "ready" or radius_data.get("graph_all") is None:
        raise HTTPException(status_code=400, detail="Preview data not ready")
    
    # Update features
    features = job.get("features", {})
    if request.parks is not None:
        features["parks"] = request.parks
    if request.water is not None:
        features["water"] = request.water
    if request.roads_drive is not None:
        features["roads_drive"] = request.roads_drive
    if request.roads_paths is not None:
        features["roads_paths"] = request.roads_paths
    if request.roads_cycling is not None:
        features["roads_cycling"] = request.roads_cycling
    
    job["features"] = features
    
    theme = load_theme(job["theme_name"])
    fonts = load_fonts()
    
    coords = tuple(job["coords"])
    settings = job["settings"]
    preview_width = settings["width"] / 1.5
    preview_height = settings["height"] / 1.5
    
    # Generate filename with feature hash
    import hashlib
    feature_hash = hashlib.md5(str(features).encode()).hexdigest()[:6]
    new_file = f"{job['base_name']}_{current_radius//1000}km_{feature_hash}.png"
    new_path = str(previews_path / new_file)
    
    loop = asyncio.get_event_loop()
    
    include_wp = features.get("parks", True) or features.get("water", True)
    
    # Filter graph based on road type toggles
    filtered_graph = get_filtered_graph(radius_data["graph_all"], features)
    
    print(f"  [features] roads_drive={features.get('roads_drive', True)}, "
          f"roads_paths={features.get('roads_paths', True)}, "
          f"roads_cycling={features.get('roads_cycling', True)}, "
          f"water={features.get('water', True)}, parks={features.get('parks', True)}")
    
    await loop.run_in_executor(
        executor,
        render_full_poster,
        settings["city"], settings["country"],
        filtered_graph,
        radius_data["water"] if features.get("water", True) else None,
        radius_data["parks"] if features.get("parks", True) else None,
        coords, preview_width, preview_height, theme, fonts,
        new_path, radius_data["compensated_dist"], include_wp
    )
    
    job["preview_url"] = f"/previews/{new_file}"
    radius_data["preview_url"] = f"/previews/{new_file}"
    
    print(f"  [features] Preview updated: {new_file}")
    
    return {
        "preview_url": f"/previews/{new_file}",
        "features": features,
        "status": "ready"
    }


@app.post("/api/generate/start")
async def start_final_generation(request: PosterRequest):
    """Start final high-resolution poster generation."""
    job_id = uuid.uuid4().hex[:8]
    
    # Convert features to dict for filtering
    features_dict = {
        "water": request.features.water,
        "parks": request.features.parks,
        "roads_drive": request.features.roads_drive,
        "roads_paths": request.features.roads_paths,
        "roads_cycling": request.features.roads_cycling,
    }
    
    print(f"\n✓ Final: {request.city}, {request.country} [job: {job_id}]")
    print(f"  Features: {features_dict}")
    
    available_themes = get_available_themes()
    if request.theme not in available_themes:
        raise HTTPException(status_code=400, detail=f"Theme '{request.theme}' not found")
    
    city_slug = re.sub(r'[\\/:*?"<>|]', '-', request.city.lower().replace(" ", "_").replace(",", ""))
    filename = f"{city_slug}_{request.theme}_{job_id}.png"
    
    jobs[job_id] = {
        "status": "starting",
        "step": 0,
        "total": 4,
        "message": "Starting...",
        "percent": 0,
        "poster_url": None,
        "filename": filename,
        "error": None
    }
    
    async def run_generation():
        start_time = time.time()
        
        try:
            jobs[job_id].update({
                "status": "running",
                "step": 1,
                "message": "Finding location...",
                "percent": 5
            })
            
            try:
                coords = get_coordinates(request.city, request.country)
            except ValueError as e:
                jobs[job_id].update({"status": "error", "error": str(e)})
                return
            
            theme = load_theme(request.theme)
            fonts = load_fonts()
            output_path = posters_path / filename
            
            # Always fetch 'all' network type, then filter based on toggles
            network_type = 'all'
            
            aspect_ratio = max(request.height, request.width) / min(request.height, request.width)
            compensated_dist = request.distance * aspect_ratio / 4
            
            loop = asyncio.get_event_loop()
            
            jobs[job_id].update({
                "step": 2,
                "message": "Loading streets...",
                "percent": 15
            })
            
            g_all = await loop.run_in_executor(
                executor, fetch_graph_fast, coords, compensated_dist, network_type
            )
            
            if g_all is None:
                jobs[job_id].update({"status": "error", "error": "Failed to load street data"})
                return
            
            # Filter graph based on road type toggles
            g = get_filtered_graph(g_all, features_dict)
            
            jobs[job_id].update({
                "step": 3,
                "message": "Adding features...",
                "percent": 45
            })
            
            # Fetch water/parks based on individual toggles
            water = None
            parks = None
            if request.features.water:
                water = await loop.run_in_executor(executor, fetch_water_fast, coords, compensated_dist)
            if request.features.parks:
                parks = await loop.run_in_executor(executor, fetch_parks_fast, coords, compensated_dist)
            
            include_wp = request.features.water or request.features.parks
            
            jobs[job_id].update({
                "step": 4,
                "message": "Rendering...",
                "percent": 75
            })
            
            await loop.run_in_executor(
                executor,
                render_full_poster,
                request.city, request.country, g, water, parks,
                coords, request.width, request.height, theme, fonts,
                str(output_path), compensated_dist, include_wp
            )
            
            gc.collect()
            
            total_time = time.time() - start_time
            print(f"  [{job_id}] ✓ Final complete in {total_time:.1f}s")
            
            jobs[job_id].update({
                "status": "complete",
                "step": 4,
                "total": 4,
                "message": "Done!",
                "percent": 100,
                "poster_url": f"/posters/{filename}",
                "filename": filename
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            jobs[job_id].update({"status": "error", "error": str(e)})
    
    asyncio.create_task(run_generation())
    return {"job_id": job_id, "status": "started"}


@app.post("/api/generate")
async def generate_poster_sync(request: PosterRequest):
    """Synchronous poster generation - returns when complete."""
    print(f"\n✓ Generate (sync): {request.city}, {request.country}")
    print(f"  Features: water={request.features.water}, parks={request.features.parks}, paths={request.features.paths}")
    
    available_themes = get_available_themes()
    if request.theme not in available_themes:
        raise HTTPException(status_code=400, detail=f"Theme '{request.theme}' not found")
    
    try:
        coords = get_coordinates(request.city, request.country)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    theme = load_theme(request.theme)
    fonts = load_fonts()
    
    city_slug = re.sub(r'[\\/:*?"<>|]', '-', request.city.lower().replace(" ", "_").replace(",", ""))
    job_id = uuid.uuid4().hex[:8]
    filename = f"{city_slug}_{request.theme}_{job_id}.png"
    output_path = posters_path / filename
    
    # Use 'all' network type if paths requested
    network_type = 'all' if request.features.paths else 'drive'
    
    aspect_ratio = max(request.height, request.width) / min(request.height, request.width)
    compensated_dist = request.distance * aspect_ratio / 4
    
    loop = asyncio.get_event_loop()
    
    # Fetch streets
    g = await loop.run_in_executor(
        executor, fetch_graph_fast, coords, compensated_dist, network_type
    )
    
    if g is None:
        raise HTTPException(status_code=500, detail="Failed to load street data")
    
    # Fetch water/parks if enabled
    water = None
    parks = None
    include_wp = request.features.water or request.features.parks
    if include_wp:
        water = await loop.run_in_executor(executor, fetch_water_fast, coords, compensated_dist)
        parks = await loop.run_in_executor(executor, fetch_parks_fast, coords, compensated_dist)
    
    # Render poster
    await loop.run_in_executor(
        executor,
        render_full_poster,
        request.city, request.country, g, water, parks,
        coords, request.width, request.height, theme, fonts,
        str(output_path), compensated_dist, include_wp
    )
    
    gc.collect()
    
    print(f"  ✓ Generated: {filename}")
    
    return {
        "poster_url": f"/posters/{filename}",
        "filename": filename
    }


@app.get("/api/geocode")
async def geocode(q: str):
    from geopy.geocoders import Nominatim
    
    geolocator = Nominatim(user_agent="maptoposter", timeout=10)
    
    try:
        locations = geolocator.geocode(q, exactly_one=False, limit=5, addressdetails=True)
        
        if not locations:
            return []
        
        results = []
        seen = set()
        
        for loc in locations:
            addr = loc.raw.get('address', {})
            city = (addr.get('city') or addr.get('town') or 
                   addr.get('village') or addr.get('municipality') or
                   addr.get('hamlet') or q.split(',')[0].strip())
            country = addr.get('country', '')
            
            key = f"{city.lower()}_{country.lower()}"
            if key in seen:
                continue
            seen.add(key)
            
            results.append({
                "city": city,
                "country": country,
                "lat": loc.latitude,
                "lon": loc.longitude,
            })
        
        return results
        
    except Exception as e:
        print(f"Geocoding error: {e}")
        return []
