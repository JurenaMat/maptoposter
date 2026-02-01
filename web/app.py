"""
MapToPoster Web Application
===========================
MVP v1.0 - 2026-02-01

FastAPI backend for generating map posters via web interface.

Features:
- Preview generation (low-res, fast)
- Final high-res generation (300 DPI)
- Theme gallery with 17 themes
- City autocomplete via Nominatim
- Multi-preview comparison (up to 3)
"""

import asyncio
import gc
import json
import os
import sys
import uuid
import time
from pathlib import Path
from typing import Optional
from queue import Queue
from threading import Thread
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
    version="MVP-1.0.0",
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


class PosterRequest(BaseModel):
    """Request model for poster generation."""
    city: str = Field(..., min_length=1, description="City name")
    country: str = Field(..., min_length=1, description="Country name")
    theme: str = Field(default="noir", description="Theme name")
    distance: int = Field(default=3000, ge=1000, le=20000, description="Map radius in meters")
    width: float = Field(default=12, ge=3, le=24, description="Poster width in inches")
    height: float = Field(default=16, ge=3, le=24, description="Poster height in inches")


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
executor = ThreadPoolExecutor(max_workers=2)

# Max distance for previews (to limit memory usage)
MAX_PREVIEW_DISTANCE = 3000  # 3km max for previews (faster initial load)

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
    return {"status": "healthy", "version": "MVP-1.0.0"}


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
    # Use optimized WebP previews instead of full PNGs
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


def create_poster_internal(
    city, country, point, dist, output_file, 
    width=12, height=16, theme=None, fonts=None, dpi=300, progress_callback=None
):
    """
    Internal poster generation with progress callbacks.
    
    Args:
        progress_callback: Function to call with (step_name, step_number, total_steps)
    """
    THEME = theme or load_theme("noir")
    create_map_poster.THEME = THEME
    
    def update_progress(step_name, step_num, total=6):
        if progress_callback:
            progress_callback(step_name, step_num, total)
        print(f"  [{step_num}/{total}] {step_name}")
    
    update_progress("Looking up location", 1)
    
    # Calculate compensated distance for viewport
    compensated_dist = dist * (max(height, width) / min(height, width)) / 4
    
    update_progress("Downloading street network", 2)
    g = fetch_graph(point, compensated_dist)
    if g is None:
        raise RuntimeError("Failed to retrieve street network data.")
    
    update_progress("Downloading water features", 3)
    water = fetch_features(
        point, compensated_dist,
        tags={"natural": ["water", "bay", "strait"], "waterway": "riverbank"},
        name="water"
    )
    
    update_progress("Downloading parks", 4)
    parks = fetch_features(
        point, compensated_dist,
        tags={"leisure": "park", "landuse": "grass"},
        name="parks"
    )
    
    update_progress("Rendering map", 5)
    
    # Setup plot
    fig, ax = plt.subplots(figsize=(width, height), facecolor=THEME["bg"])
    ax.set_facecolor(THEME["bg"])
    ax.set_position((0.0, 0.0, 1.0, 1.0))
    
    # Project graph
    g_proj = ox.project_graph(g)
    
    # Plot water
    if water is not None and not water.empty:
        water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not water_polys.empty:
            try:
                water_polys = ox.projection.project_gdf(water_polys)
            except Exception:
                water_polys = water_polys.to_crs(g_proj.graph['crs'])
            water_polys.plot(ax=ax, facecolor=THEME['water'], edgecolor='none', zorder=0.5)
    
    # Plot parks
    if parks is not None and not parks.empty:
        parks_polys = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not parks_polys.empty:
            try:
                parks_polys = ox.projection.project_gdf(parks_polys)
            except Exception:
                parks_polys = parks_polys.to_crs(g_proj.graph['crs'])
            parks_polys.plot(ax=ax, facecolor=THEME['parks'], edgecolor='none', zorder=0.8)
    
    # Plot roads
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
    
    # Gradients
    create_gradient_fade(ax, THEME['gradient_color'], location='bottom', zorder=10)
    create_gradient_fade(ax, THEME['gradient_color'], location='top', zorder=10)
    
    # Typography
    scale_factor = min(height, width) / 12.0
    active_fonts = fonts or FONTS
    
    display_city = city
    display_country = country
    
    if is_latin_script(display_city):
        spaced_city = "  ".join(list(display_city.upper()))
    else:
        spaced_city = display_city
    
    # Adjust font size for long names
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
        font_attr = FontProperties(fname=active_fonts["light"], size=8 * scale_factor)
    else:
        font_main = FontProperties(family="monospace", weight="bold", size=adjusted_font_size)
        font_sub = FontProperties(family="monospace", size=22 * scale_factor)
        font_coords = FontProperties(family="monospace", size=14 * scale_factor)
        font_attr = FontProperties(family="monospace", size=8 * scale_factor)
    
    # City name
    ax.text(0.5, 0.14, spaced_city, transform=ax.transAxes, color=THEME["text"],
            ha="center", fontproperties=font_main, zorder=11)
    
    # Country
    ax.text(0.5, 0.10, display_country.upper(), transform=ax.transAxes, color=THEME["text"],
            ha="center", fontproperties=font_sub, zorder=11)
    
    # Coordinates
    lat, lon = point
    coords_text = f"{lat:.4f}° {'N' if lat >= 0 else 'S'} / {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}"
    ax.text(0.5, 0.07, coords_text, transform=ax.transAxes, color=THEME["text"],
            alpha=0.7, ha="center", fontproperties=font_coords, zorder=11)
    
    # Line
    ax.plot([0.4, 0.6], [0.125, 0.125], transform=ax.transAxes, color=THEME["text"],
            linewidth=1 * scale_factor, zorder=11)
    
    # Attribution
    ax.text(0.98, 0.02, "© OpenStreetMap contributors", transform=ax.transAxes,
            color=THEME["text"], alpha=0.5, ha="right", va="bottom",
            fontproperties=font_attr, zorder=11)
    
    update_progress("Saving image", 6)
    plt.savefig(output_file, format="png", dpi=dpi, facecolor=THEME["bg"],
                bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    plt.close('all')  # Ensure all figures are closed
    
    # Clear references to help garbage collection
    del g, g_proj, water, parks, edge_colors, edge_widths
    gc.collect()
    
    return True


@app.post("/api/preview/start")
async def start_preview(request: PreviewRequest):
    """Start a preview generation and return job_id for progress tracking."""
    print(f"✓ Preview request: {request.city}, {request.country}")
    
    # Validate theme
    available_themes = get_available_themes()
    if request.theme not in available_themes:
        raise HTTPException(status_code=400, detail=f"Theme '{request.theme}' not found")
    
    # Create job
    job_id = uuid.uuid4().hex[:8]
    city_slug = request.city.lower().replace(" ", "_").replace(",", "")
    filename = f"preview_{city_slug}_{request.theme}_{job_id}.png"
    
    jobs[job_id] = {
        "step": 0,
        "total": 6,
        "status": "starting",
        "message": "Starting...",
        "preview_url": None,
        "error": None
    }
    
    # Start generation in background
    async def run_generation():
        try:
            # Step 1: Get coordinates
            jobs[job_id].update({"step": 1, "message": "Finding location", "status": "running"})
            
            try:
                coords = get_coordinates(request.city, request.country)
            except ValueError as e:
                jobs[job_id].update({"status": "error", "error": str(e)})
                return
            
            # Load theme and fonts
            theme = load_theme(request.theme)
            fonts = load_fonts()
            
            output_path = previews_path / filename
            preview_width = request.width / 2
            preview_height = request.height / 2
            preview_distance = min(request.distance, MAX_PREVIEW_DISTANCE)
            
            # Progress callback
            def progress_callback(step_name, step_num, total):
                jobs[job_id].update({
                    "step": step_num,
                    "total": total,
                    "message": step_name,
                    "status": "running"
                })
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                executor,
                lambda: create_poster_internal(
                    city=request.city,
                    country=request.country,
                    point=coords,
                    dist=preview_distance,
                    output_file=str(output_path),
                    width=preview_width,
                    height=preview_height,
                    theme=theme,
                    fonts=fonts,
                    dpi=72,
                    progress_callback=progress_callback,
                )
            )
            
            gc.collect()
            
            jobs[job_id].update({
                "step": 6,
                "status": "complete",
                "message": "Done!",
                "preview_url": f"/previews/{filename}",
                "coords": list(coords)
            })
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            jobs[job_id].update({"status": "error", "error": str(e)})
    
    # Fire and forget
    asyncio.create_task(run_generation())
    
    return {"job_id": job_id, "status": "started"}


@app.post("/api/preview")
async def generate_preview_sync(request: PreviewRequest):
    """Synchronous preview (backwards compatible) - starts job and waits for completion."""
    # Start the job
    result = await start_preview(request)
    job_id = result["job_id"]
    
    # Poll until complete
    while True:
        job = jobs.get(job_id, {})
        if job.get("status") in ["complete", "error"]:
            break
        await asyncio.sleep(0.1)
    
    if job.get("status") == "error":
        raise HTTPException(status_code=500, detail=job.get("error", "Preview failed"))
    
    return {
        "success": True,
        "preview_url": job["preview_url"],
        "coords": job.get("coords", []),
        "preview_id": job_id,
    }


@app.post("/api/generate")
async def generate_final(request: PosterRequest):
    """Generate final high-resolution poster."""
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"status": "pending", "progress": 0, "step": "Starting"}
    
    print(f"✓ Final generation request: {request.city}, {request.country} [job: {job_id}]")
    
    try:
        available_themes = get_available_themes()
        if request.theme not in available_themes:
            raise HTTPException(status_code=400, detail=f"Theme '{request.theme}' not found")
        
        try:
            coords = get_coordinates(request.city, request.country)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        theme = load_theme(request.theme)
        fonts = load_fonts()
        
        city_slug = request.city.lower().replace(" ", "_").replace(",", "")
        filename = f"{city_slug}_{request.theme}_{job_id}.png"
        output_path = posters_path / filename
        
        def progress_callback(step_name, step_num, total):
            jobs[job_id] = {
                "status": "processing",
                "progress": int((step_num / total) * 100),
                "step": step_name
            }
        
        # Limit distance to 8km for high-res to stay within memory limits
        final_distance = min(request.distance, 8000)
        
        # Run in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            executor,
            lambda: create_poster_internal(
                city=request.city,
                country=request.country,
                point=coords,
                dist=final_distance,
                output_file=str(output_path),
                width=request.width,
                height=request.height,
                theme=theme,
                fonts=fonts,
                dpi=200,  # Reduced from 300 to save memory
                progress_callback=progress_callback,
            )
        )
        
        # Force garbage collection
        gc.collect()
        
        jobs[job_id] = {"status": "complete", "progress": 100, "step": "Done"}
        
        return PosterResponse(
            success=True,
            message=f"Poster generated for {request.city}",
            poster_url=f"/posters/{filename}",
            filename=filename,
            coords=list(coords),
        )
        
    except HTTPException:
        jobs[job_id] = {"status": "error", "progress": 0, "step": "Failed"}
        raise
    except Exception as e:
        jobs[job_id] = {"status": "error", "progress": 0, "step": str(e)}
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str):
    """Get progress for a generation job."""
    if job_id in jobs:
        return jobs[job_id]
    return {"status": "unknown", "progress": 0, "step": "Job not found"}


@app.get("/api/geocode")
async def geocode_city(q: str):
    """Geocode a city name using Nominatim (for autocomplete)."""
    import requests
    
    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": q,
                "format": "json",
                "addressdetails": 1,
                "limit": 5,
                "featuretype": "city",
            },
            headers={"User-Agent": "MapToPoster/1.0"},
            timeout=10,
        )
        response.raise_for_status()
        
        results = []
        for item in response.json():
            address = item.get("address", {})
            city = (
                address.get("city") or 
                address.get("town") or 
                address.get("village") or 
                address.get("municipality") or
                item.get("name", "")
            )
            country = address.get("country", "")
            
            if city and country:
                results.append({
                    "city": city,
                    "country": country,
                    "display": f"{city}, {country}",
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                })
        
        return results
        
    except Exception:
        return []


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
