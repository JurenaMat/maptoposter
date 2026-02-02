"""
MapToPoster Web Application
===========================
MVP v1.1 - 2026-02-02

FastAPI backend for generating map posters via web interface.

Features:
- Preview generation with separate layers for instant toggling
- Final high-res generation (300 DPI)
- Theme gallery with 17 themes
- City autocomplete via Nominatim
- Multi-preview comparison (up to 3)
"""

# IMPORTANT: Set matplotlib backend to 'Agg' BEFORE any matplotlib imports
# This is required for running matplotlib in background threads
import matplotlib
matplotlib.use('Agg')

import asyncio
import gc
import json
import os
import re
import sys
import uuid
import time
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from web.image_utils import generate_preview_from_png, r2_storage

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Add parent directory to path to import create_map_poster
sys.path.insert(0, str(Path(__file__).parent.parent))

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

import matplotlib.pyplot as plt
import osmnx as ox
from matplotlib.font_manager import FontProperties

app = FastAPI(
    title="MapToPoster",
    description="Generate beautiful map posters for any city",
    version="MVP-1.1.0",
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Serve generated posters
posters_path = Path(__file__).parent.parent / POSTERS_DIR
posters_path.mkdir(exist_ok=True)
app.mount("/posters", StaticFiles(directory=str(posters_path)), name="posters")

# Previews directory (for low-res previews)
previews_path = Path(__file__).parent / "previews"
previews_path.mkdir(exist_ok=True)
app.mount("/previews", StaticFiles(directory=str(previews_path)), name="previews")


class MapFeatures(BaseModel):
    """Feature flags for map generation."""
    roads: bool = Field(default=True, description="Include driving roads (always on)")
    paths: bool = Field(default=False, description="Include walking paths & cycleways")
    water: bool = Field(default=True, description="Include water features")
    parks: bool = Field(default=True, description="Include parks & greenery")


class PosterRequest(BaseModel):
    """Request model for poster generation."""
    city: str = Field(..., min_length=1, description="City name")
    country: str = Field(..., min_length=1, description="Country name")
    theme: str = Field(default="noir", description="Theme name")
    distance: int = Field(default=3000, ge=1000, le=20000, description="Map radius in meters")
    width: float = Field(default=12, ge=3, le=32, description="Poster width in inches")
    height: float = Field(default=16, ge=3, le=32, description="Poster height in inches")
    features: MapFeatures = Field(default_factory=MapFeatures, description="Map features to include")


class PreviewRequest(PosterRequest):
    """Request model for preview generation - inherits from PosterRequest."""
    pass


class PosterResponse(BaseModel):
    """Response model for poster generation."""
    success: bool
    message: str
    poster_url: Optional[str] = None
    preview_url: Optional[str] = None
    filename: Optional[str] = None
    coords: Optional[list] = None


# Store for active generation jobs and their progress
jobs: dict = {}

# Thread pool for running heavy generation tasks
executor = ThreadPoolExecutor(max_workers=4)

# Max distance for previews
MAX_PREVIEW_DISTANCE = 20000

# Progress steps for display
PROGRESS_STEPS = {
    1: "Finding location",
    2: "Downloading streets",
    3: "Downloading water",
    4: "Downloading parks",
    5: "Rendering map",
    6: "Saving image"
}


@app.get("/")
async def root():
    """Serve the main page."""
    return FileResponse(static_path / "index.html")


@app.get("/health")
async def health():
    """Health check endpoint for Railway."""
    return {"status": "healthy", "version": "MVP-1.1.0"}


@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str):
    """Get progress for a job (polling endpoint)."""
    if job_id not in jobs:
        return {"step": 0, "total": 6, "status": "not_found", "message": "Job not found"}
    return jobs[job_id]


@app.get("/generate")
async def generate_page():
    """Serve the generate page."""
    return FileResponse(static_path / "generate.html")


@app.get("/api/themes")
async def get_themes():
    """Get all available themes with their details."""
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
    """Get example posters to showcase on homepage."""
    examples = [
        {"city": "San Francisco", "country": "USA", "theme": "sunset",
         "image": "/static/examples/san_francisco_sunset_thumb.webp",
         "preview": "/static/examples/san_francisco_sunset_preview.webp",
         "description": "Warm sunset tones"},
        {"city": "Tokyo", "country": "Japan", "theme": "japanese_ink",
         "image": "/static/examples/tokyo_japanese_ink_thumb.webp",
         "preview": "/static/examples/tokyo_japanese_ink_preview.webp",
         "description": "Minimalist ink wash"},
        {"city": "Venice", "country": "Italy", "theme": "blueprint",
         "image": "/static/examples/venice_blueprint_thumb.webp",
         "preview": "/static/examples/venice_blueprint_preview.webp",
         "description": "Architectural blueprint"},
        {"city": "Dubai", "country": "UAE", "theme": "midnight_blue",
         "image": "/static/examples/dubai_midnight_blue_thumb.webp",
         "preview": "/static/examples/dubai_midnight_blue_preview.webp",
         "description": "Navy & gold luxury"},
        {"city": "Singapore", "country": "Singapore", "theme": "neon_cyberpunk",
         "image": "/static/examples/singapore_neon_cyberpunk_thumb.webp",
         "preview": "/static/examples/singapore_neon_cyberpunk_preview.webp",
         "description": "Electric cyberpunk"},
        {"city": "Prague", "country": "Czech Republic", "theme": "noir",
         "image": "/static/examples/prague_noir_thumb.webp",
         "preview": "/static/examples/prague_noir_preview.webp",
         "description": "Pure gallery noir"},
    ]
    return examples


def generate_layer_images(
    city, country, point, dist, output_base,
    width=12, height=16, theme=None, fonts=None, dpi=72,
    progress_callback=None
):
    """
    Generate separate layer images for frontend compositing.
    
    Returns dict with layer URLs:
    - base: roads + gradients + typography (always visible)
    - water: transparent PNG with water only
    - parks: transparent PNG with parks only
    - paths: transparent PNG with paths only (generated in background)
    """
    THEME = theme or load_theme("noir")
    create_map_poster.THEME = THEME
    
    total_steps = 6
    current_step = 0
    
    def update_progress(step_name, percent=None):
        nonlocal current_step
        current_step += 1
        if percent is None:
            percent = int((current_step / total_steps) * 100)
        if progress_callback:
            progress_callback(step_name, current_step, total_steps, percent)
        print(f"  [{current_step}/{total_steps}] {step_name}")
    
    # Step 1: Get location (already done by caller, but for progress)
    update_progress("Searching for your location", 5)
    
    # Calculate compensated distance for viewport
    compensated_dist = dist * (max(height, width) / min(height, width)) / 4
    
    # Step 2: Fetch roads (drive only for speed)
    update_progress("Loading streets", 15)
    g_drive = fetch_graph(point, compensated_dist, network_type='drive')
    if g_drive is None:
        raise RuntimeError("Failed to retrieve street network data.")
    
    # Step 3: Fetch water
    update_progress("Adding water elements", 40)
    water = fetch_features(
        point, compensated_dist,
        tags={"natural": ["water", "bay", "strait"], "waterway": "riverbank"},
        name="water"
    )
    
    # Step 4: Fetch parks
    update_progress("Adding parks and greenery", 60)
    parks = fetch_features(
        point, compensated_dist,
        tags={"leisure": "park", "landuse": "grass"},
        name="parks"
    )
    
    # Project graph once
    g_proj = ox.project_graph(g_drive)
    crop_xlim, crop_ylim = get_crop_limits(g_proj, point, None, compensated_dist)
    
    # We need a dummy figure to calculate crop limits properly
    fig_temp, ax_temp = plt.subplots(figsize=(width, height))
    crop_xlim, crop_ylim = get_crop_limits(g_proj, point, fig_temp, compensated_dist)
    plt.close(fig_temp)
    
    # Project water and parks once
    water_polys = None
    if water is not None and not water.empty:
        water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not water_polys.empty:
            try:
                water_polys = ox.projection.project_gdf(water_polys)
            except Exception:
                water_polys = water_polys.to_crs(g_proj.graph['crs'])
    
    parks_polys = None
    if parks is not None and not parks.empty:
        parks_polys = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not parks_polys.empty:
            try:
                parks_polys = ox.projection.project_gdf(parks_polys)
            except Exception:
                parks_polys = parks_polys.to_crs(g_proj.graph['crs'])
    
    # Step 5: Render all layers
    update_progress("Rendering map layers", 75)
    
    edge_colors = get_edge_colors_by_type(g_proj)
    edge_widths = get_edge_widths_by_type(g_proj)
    
    # Typography settings
    scale_factor = min(height, width) / 12.0
    active_fonts = fonts or FONTS
    
    display_city = city
    display_country = country
    
    if is_latin_script(display_city):
        spaced_city = "  ".join(list(display_city.upper()))
    else:
        spaced_city = display_city
    
    base_main = 60 * scale_factor
    city_char_count = len(display_city)
    if city_char_count > 10:
        length_factor = 10 / city_char_count
        adjusted_font_size = max(base_main * length_factor, 10 * scale_factor)
    else:
        adjusted_font_size = base_main
    
    if active_fonts:
        font_main = FontProperties(fname=active_fonts["bold"], size=adjusted_font_size)
        font_sub = FontProperties(fname=active_fonts["light"], size=22 * scale_factor)
        font_coords = FontProperties(fname=active_fonts["regular"], size=14 * scale_factor)
    else:
        font_main = FontProperties(family="monospace", weight="bold", size=adjusted_font_size)
        font_sub = FontProperties(family="monospace", size=22 * scale_factor)
        font_coords = FontProperties(family="monospace", size=14 * scale_factor)
    
    lat, lon = point
    coords_text = f"{lat:.4f}° {'N' if lat >= 0 else 'S'} / {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}"
    
    # === Generate BASE layer (roads + gradients + text) ===
    fig, ax = plt.subplots(figsize=(width, height), facecolor=THEME["bg"])
    ax.set_facecolor(THEME["bg"])
    ax.set_position((0.0, 0.0, 1.0, 1.0))
    
    ox.plot_graph(
        g_proj, ax=ax, bgcolor=THEME['bg'],
        node_size=0, edge_color=edge_colors, edge_linewidth=edge_widths,
        show=False, close=False,
    )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(crop_xlim)
    ax.set_ylim(crop_ylim)
    
    create_gradient_fade(ax, THEME['gradient_color'], location='bottom', zorder=10)
    create_gradient_fade(ax, THEME['gradient_color'], location='top', zorder=10)
    
    ax.text(0.5, 0.14, spaced_city, transform=ax.transAxes, color=THEME["text"],
            ha="center", fontproperties=font_main, zorder=11)
    ax.text(0.5, 0.10, display_country.upper(), transform=ax.transAxes, color=THEME["text"],
            ha="center", fontproperties=font_sub, zorder=11)
    ax.text(0.5, 0.07, coords_text, transform=ax.transAxes, color=THEME["text"],
            alpha=0.7, ha="center", fontproperties=font_coords, zorder=11)
    ax.plot([0.4, 0.6], [0.125, 0.125], transform=ax.transAxes, color=THEME["text"],
            linewidth=1 * scale_factor, zorder=11)
    
    base_file = f"{output_base}_base.png"
    plt.savefig(base_file, format="png", dpi=dpi, facecolor=THEME["bg"],
                bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    
    # === Generate WATER layer (transparent) ===
    water_file = f"{output_base}_water.png"
    if water_polys is not None and not water_polys.empty:
        fig, ax = plt.subplots(figsize=(width, height), facecolor='none')
        ax.set_facecolor('none')
        ax.set_position((0.0, 0.0, 1.0, 1.0))
        
        water_polys.plot(ax=ax, facecolor=THEME['water'], edgecolor='none', zorder=1)
        
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(crop_xlim)
        ax.set_ylim(crop_ylim)
        ax.axis('off')
        
        plt.savefig(water_file, format="png", dpi=dpi, transparent=True,
                    bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
    else:
        # Create empty transparent image
        fig, ax = plt.subplots(figsize=(width, height), facecolor='none')
        ax.set_facecolor('none')
        ax.axis('off')
        plt.savefig(water_file, format="png", dpi=dpi, transparent=True,
                    bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
    
    # === Generate PARKS layer (transparent) ===
    parks_file = f"{output_base}_parks.png"
    if parks_polys is not None and not parks_polys.empty:
        fig, ax = plt.subplots(figsize=(width, height), facecolor='none')
        ax.set_facecolor('none')
        ax.set_position((0.0, 0.0, 1.0, 1.0))
        
        parks_polys.plot(ax=ax, facecolor=THEME['parks'], edgecolor='none', zorder=1)
        
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(crop_xlim)
        ax.set_ylim(crop_ylim)
        ax.axis('off')
        
        plt.savefig(parks_file, format="png", dpi=dpi, transparent=True,
                    bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
    else:
        fig, ax = plt.subplots(figsize=(width, height), facecolor='none')
        ax.set_facecolor('none')
        ax.axis('off')
        plt.savefig(parks_file, format="png", dpi=dpi, transparent=True,
                    bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
    
    # Step 6: Save/finalize
    update_progress("Finishing up", 95)
    
    plt.close('all')
    gc.collect()
    
    return {
        'base_file': base_file,
        'water_file': water_file,
        'parks_file': parks_file,
        'crop_xlim': crop_xlim,
        'crop_ylim': crop_ylim,
        'g_proj_crs': g_proj.graph['crs'],
        'compensated_dist': compensated_dist,
        'point': point,
        'theme': THEME,
        'width': width,
        'height': height,
        'dpi': dpi,
    }


def generate_paths_layer(
    point, compensated_dist, crop_xlim, crop_ylim, g_proj_crs,
    output_file, theme, width, height, dpi
):
    """Generate paths layer in background (separate thread)."""
    try:
        # Fetch paths (all network includes walking/cycling paths)
        g_all = fetch_graph(point, compensated_dist, network_type='all')
        if g_all is None:
            return None
        
        g_proj = ox.project_graph(g_all)
        
        # Get only the path edges (not roads)
        path_colors = []
        path_widths = []
        for _u, _v, data in g_proj.edges(data=True):
            highway = data.get('highway', 'unclassified')
            if isinstance(highway, list):
                highway = highway[0] if highway else 'unclassified'
            
            # Only include paths/cycleways, not roads
            if highway in ['path', 'footway', 'cycleway', 'pedestrian', 'track', 'bridleway', 'steps']:
                path_colors.append(theme.get('road_residential', '#888888'))
                path_widths.append(0.3)
            else:
                path_colors.append('none')
                path_widths.append(0)
        
        # Render paths layer
        fig, ax = plt.subplots(figsize=(width, height), facecolor='none')
        ax.set_facecolor('none')
        ax.set_position((0.0, 0.0, 1.0, 1.0))
        
        ox.plot_graph(
            g_proj, ax=ax, bgcolor='none',
            node_size=0, edge_color=path_colors, edge_linewidth=path_widths,
            show=False, close=False,
        )
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(crop_xlim)
        ax.set_ylim(crop_ylim)
        ax.axis('off')
        
        plt.savefig(output_file, format="png", dpi=dpi, transparent=True,
                    bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)
        plt.close('all')
        gc.collect()
        
        return output_file
    except Exception as e:
        print(f"Error generating paths layer: {e}")
        return None


def create_poster_internal(
    city, country, point, dist, output_file, 
    width=12, height=16, theme=None, fonts=None, dpi=300, progress_callback=None,
    features=None
):
    """
    Internal poster generation with progress callbacks.
    Used for final high-res generation.
    """
    THEME = theme or load_theme("noir")
    create_map_poster.THEME = THEME
    
    if features is None:
        features = {'roads': True, 'paths': False, 'water': True, 'parks': True}
    
    total_steps = 6
    current_step = 0
    
    def update_progress(step_name):
        nonlocal current_step
        current_step += 1
        percent = int((current_step / total_steps) * 100)
        if progress_callback:
            progress_callback(step_name, current_step, total_steps, percent)
        print(f"  [{current_step}/{total_steps}] {step_name}")
    
    update_progress("Searching for your location")
    
    compensated_dist = dist * (max(height, width) / min(height, width)) / 4
    
    network_type = 'all' if features.get('paths') else 'drive'
    update_progress("Loading streets" + (" & paths" if features.get('paths') else ""))
    
    g = fetch_graph(point, compensated_dist, network_type=network_type)
    if g is None:
        raise RuntimeError("Failed to retrieve street network data.")
    
    water = None
    parks = None
    
    if features.get('water'):
        update_progress("Adding water elements")
        water = fetch_features(
            point, compensated_dist,
            tags={"natural": ["water", "bay", "strait"], "waterway": "riverbank"},
            name="water"
        )
    else:
        update_progress("Skipping water")
    
    if features.get('parks'):
        update_progress("Adding parks and greenery")
        parks = fetch_features(
            point, compensated_dist,
            tags={"leisure": "park", "landuse": "grass"},
            name="parks"
        )
    else:
        update_progress("Skipping parks")
    
    update_progress("Putting it all together")
    
    fig, ax = plt.subplots(figsize=(width, height), facecolor=THEME["bg"])
    ax.set_facecolor(THEME["bg"])
    ax.set_position((0.0, 0.0, 1.0, 1.0))
    
    g_proj = ox.project_graph(g)
    
    if water is not None and not water.empty:
        water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not water_polys.empty:
            try:
                water_polys = ox.projection.project_gdf(water_polys)
            except Exception:
                water_polys = water_polys.to_crs(g_proj.graph['crs'])
            water_polys.plot(ax=ax, facecolor=THEME['water'], edgecolor='none', zorder=0.5)
    
    if parks is not None and not parks.empty:
        parks_polys = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not parks_polys.empty:
            try:
                parks_polys = ox.projection.project_gdf(parks_polys)
            except Exception:
                parks_polys = parks_polys.to_crs(g_proj.graph['crs'])
            parks_polys.plot(ax=ax, facecolor=THEME['parks'], edgecolor='none', zorder=0.8)
    
    edge_colors = get_edge_colors_by_type(g_proj)
    edge_widths = get_edge_widths_by_type(g_proj)
    crop_xlim, crop_ylim = get_crop_limits(g_proj, point, fig, compensated_dist)
    
    ox.plot_graph(
        g_proj, ax=ax, bgcolor=THEME['bg'],
        node_size=0, edge_color=edge_colors, edge_linewidth=edge_widths,
        show=False, close=False,
    )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(crop_xlim)
    ax.set_ylim(crop_ylim)
    
    create_gradient_fade(ax, THEME['gradient_color'], location='bottom', zorder=10)
    create_gradient_fade(ax, THEME['gradient_color'], location='top', zorder=10)
    
    scale_factor = min(height, width) / 12.0
    active_fonts = fonts or FONTS
    
    display_city = city
    display_country = country
    
    if is_latin_script(display_city):
        spaced_city = "  ".join(list(display_city.upper()))
    else:
        spaced_city = display_city
    
    base_main = 60 * scale_factor
    city_char_count = len(display_city)
    if city_char_count > 10:
        length_factor = 10 / city_char_count
        adjusted_font_size = max(base_main * length_factor, 10 * scale_factor)
    else:
        adjusted_font_size = base_main
    
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
    ax.text(0.5, 0.10, display_country.upper(), transform=ax.transAxes, color=THEME["text"],
            ha="center", fontproperties=font_sub, zorder=11)
    
    lat, lon = point
    coords_text = f"{lat:.4f}° {'N' if lat >= 0 else 'S'} / {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}"
    ax.text(0.5, 0.07, coords_text, transform=ax.transAxes, color=THEME["text"],
            alpha=0.7, ha="center", fontproperties=font_coords, zorder=11)
    
    ax.plot([0.4, 0.6], [0.125, 0.125], transform=ax.transAxes, color=THEME["text"],
            linewidth=1 * scale_factor, zorder=11)
    
    update_progress("Finishing up")
    plt.savefig(output_file, format="png", dpi=dpi, facecolor=THEME["bg"],
                bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    plt.close('all')
    
    del g, g_proj
    gc.collect()
    
    return True


@app.post("/api/preview/start")
async def start_preview(request: PreviewRequest):
    """
    Start a preview generation with separate layers for instant UI toggling.
    
    Returns layer URLs:
    - base: roads + gradients + typography
    - water: transparent water layer
    - parks: transparent parks layer
    - paths: transparent paths layer (loaded in background)
    """
    print(f"✓ Preview request: {request.city}, {request.country}")
    
    available_themes = get_available_themes()
    if request.theme not in available_themes:
        raise HTTPException(status_code=400, detail=f"Theme '{request.theme}' not found")
    
    job_id = uuid.uuid4().hex[:8]
    city_slug = re.sub(r'[\\/:*?"<>|,\s]', '_', request.city.lower())
    output_base = str(previews_path / f"preview_{city_slug}_{request.theme}_{job_id}")
    
    jobs[job_id] = {
        "step": 0,
        "total": 6,
        "status": "starting",
        "message": "Starting...",
        "layers": None,
        "error": None
    }
    
    async def run_generation():
        try:
            jobs[job_id].update({"step": 1, "message": "Finding location", "status": "running"})
            
            try:
                coords = get_coordinates(request.city, request.country)
            except ValueError as e:
                jobs[job_id].update({"status": "error", "error": str(e)})
                return
            
            theme = load_theme(request.theme)
            fonts = load_fonts()
            
            preview_width = request.width / 2
            preview_height = request.height / 2
            preview_distance = min(request.distance, MAX_PREVIEW_DISTANCE)
            
            def progress_callback(step_name, step_num, total, percent=0):
                jobs[job_id].update({
                    "step": step_num,
                    "total": total,
                    "message": step_name,
                    "status": "running",
                    "percent": percent
                })
            
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor,
                lambda: generate_layer_images(
                    city=request.city,
                    country=request.country,
                    point=coords,
                    dist=preview_distance,
                    output_base=output_base,
                    width=preview_width,
                    height=preview_height,
                    theme=theme,
                    fonts=fonts,
                    dpi=72,
                    progress_callback=progress_callback,
                )
            )
            
            # Get filenames from paths
            base_filename = Path(result['base_file']).name
            water_filename = Path(result['water_file']).name
            parks_filename = Path(result['parks_file']).name
            
            layers = {
                "base": f"/previews/{base_filename}",
                "water": f"/previews/{water_filename}",
                "parks": f"/previews/{parks_filename}",
                "paths": None  # Will be generated in background
            }
            
            jobs[job_id].update({
                "step": 6,
                "total": 6,
                "status": "complete",
                "message": "Done!",
                "percent": 100,
                "layers": layers,
                "coords": list(coords),
                "settings": {
                    "city": request.city,
                    "country": request.country,
                    "theme": request.theme,
                    "distance": preview_distance,
                    "width": request.width,
                    "height": request.height,
                }
            })
            
            # Start paths generation in background
            paths_file = f"{output_base}_paths.png"
            asyncio.create_task(generate_paths_background(
                job_id, coords, result['compensated_dist'],
                result['crop_xlim'], result['crop_ylim'], result['g_proj_crs'],
                paths_file, theme, preview_width, preview_height, 72
            ))
            
            gc.collect()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            jobs[job_id].update({"status": "error", "error": str(e)})
    
    asyncio.create_task(run_generation())
    
    return {"job_id": job_id, "status": "started"}


async def generate_paths_background(job_id, point, compensated_dist, crop_xlim, crop_ylim, g_proj_crs, output_file, theme, width, height, dpi):
    """Generate paths layer in background and update job when done."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            lambda: generate_paths_layer(
                point, compensated_dist, crop_xlim, crop_ylim, g_proj_crs,
                output_file, theme, width, height, dpi
            )
        )
        
        if result and job_id in jobs:
            paths_filename = Path(output_file).name
            if jobs[job_id].get("layers"):
                jobs[job_id]["layers"]["paths"] = f"/previews/{paths_filename}"
                print(f"  Paths layer ready for job {job_id}")
    except Exception as e:
        print(f"Error generating paths in background: {e}")


@app.get("/api/layers/{job_id}")
async def get_layers(job_id: str):
    """Get current layer URLs for a job (for polling paths availability)."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return {
        "layers": job.get("layers"),
        "status": job.get("status"),
        "settings": job.get("settings"),
    }


@app.post("/api/generate/start")
async def start_final_generation(request: PosterRequest):
    """Start final high-resolution poster generation (non-blocking)."""
    job_id = uuid.uuid4().hex[:8]
    
    print(f"✓ Final generation request: {request.city}, {request.country} [job: {job_id}]")
    
    available_themes = get_available_themes()
    if request.theme not in available_themes:
        raise HTTPException(status_code=400, detail=f"Theme '{request.theme}' not found")
    
    city_slug = re.sub(r'[\\/:*?"<>|]', '-', request.city.lower().replace(" ", "_").replace(",", ""))
    filename = f"{city_slug}_{request.theme}_{job_id}.png"
    
    jobs[job_id] = {
        "step": 0,
        "total": 6,
        "status": "starting",
        "message": "Starting...",
        "poster_url": None,
        "filename": filename,
        "error": None
    }
    
    async def run_generation():
        try:
            jobs[job_id].update({"step": 1, "message": "Finding location", "status": "running"})
            
            try:
                coords = get_coordinates(request.city, request.country)
            except ValueError as e:
                jobs[job_id].update({"status": "error", "error": str(e)})
                return
            
            theme = load_theme(request.theme)
            fonts = load_fonts()
            
            output_path = posters_path / filename
            
            def progress_callback(step_name, step_num, total, percent=0):
                jobs[job_id].update({
                    "step": step_num,
                    "total": total,
                    "message": step_name,
                    "status": "running",
                    "percent": percent
                })
            
            features_dict = {
                'roads': True,
                'paths': request.features.paths if request.features else False,
                'water': request.features.water if request.features else True,
                'parks': request.features.parks if request.features else True,
            }
            print(f"  Final features: {features_dict}")
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                executor,
                lambda: create_poster_internal(
                    city=request.city,
                    country=request.country,
                    point=coords,
                    dist=request.distance,
                    output_file=str(output_path),
                    width=request.width,
                    height=request.height,
                    theme=theme,
                    fonts=fonts,
                    dpi=150,
                    progress_callback=progress_callback,
                    features=features_dict,
                )
            )
            
            gc.collect()
            
            jobs[job_id].update({
                "step": 6,
                "total": 6,
                "status": "complete",
                "message": "Done!",
                "percent": 100,
                "poster_url": f"/posters/{filename}",
                "filename": filename,
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            jobs[job_id].update({"status": "error", "error": str(e)})
    
    asyncio.create_task(run_generation())
    
    return {"job_id": job_id, "status": "started"}


@app.get("/api/geocode")
async def geocode(q: str):
    """Geocode a search query to get city suggestions."""
    from geopy.geocoders import Nominatim
    
    geolocator = Nominatim(user_agent="maptoposter", timeout=10)
    
    try:
        # Search for locations
        locations = geolocator.geocode(q, exactly_one=False, limit=5, addressdetails=True)
        
        if not locations:
            return []
        
        results = []
        seen = set()
        
        for loc in locations:
            addr = loc.raw.get('address', {})
            
            # Try to get city name
            city = (addr.get('city') or addr.get('town') or 
                   addr.get('village') or addr.get('municipality') or
                   addr.get('hamlet') or q.split(',')[0].strip())
            
            country = addr.get('country', '')
            
            # Deduplicate
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
