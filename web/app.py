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


class MapFeatures(BaseModel):
    roads: bool = Field(default=True)
    paths: bool = Field(default=False)
    water: bool = Field(default=True)
    parks: bool = Field(default=True)


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
    return jobs[job_id]


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
         "image": "/static/examples/san_francisco_sunset_thumb.webp",
         "preview": "/static/examples/san_francisco_sunset_preview.webp"},
        {"city": "Tokyo", "country": "Japan", "theme": "japanese_ink",
         "image": "/static/examples/tokyo_japanese_ink_thumb.webp",
         "preview": "/static/examples/tokyo_japanese_ink_preview.webp"},
        {"city": "Venice", "country": "Italy", "theme": "blueprint",
         "image": "/static/examples/venice_blueprint_thumb.webp",
         "preview": "/static/examples/venice_blueprint_preview.webp"},
        {"city": "Dubai", "country": "UAE", "theme": "midnight_blue",
         "image": "/static/examples/dubai_midnight_blue_thumb.webp",
         "preview": "/static/examples/dubai_midnight_blue_preview.webp"},
        {"city": "Singapore", "country": "Singapore", "theme": "neon_cyberpunk",
         "image": "/static/examples/singapore_neon_cyberpunk_thumb.webp",
         "preview": "/static/examples/singapore_neon_cyberpunk_preview.webp"},
        {"city": "Prague", "country": "Czech Republic", "theme": "noir",
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
    
    g_proj = ox.project_graph(graph)
    
    # Plot water (if enabled)
    if include_water_parks and water is not None and not water.empty:
        water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not water_polys.empty:
            try:
                water_polys = ox.projection.project_gdf(water_polys)
            except:
                try:
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
                    parks_polys = parks_polys.to_crs(g_proj.graph['crs'])
                except:
                    pass
            try:
                parks_polys.plot(ax=ax, facecolor=THEME['parks'], edgecolor='none', zorder=0.8)
            except:
                pass
    
    # Plot roads
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
    """Generate preview with multiple variants for instant toggling."""
    print(f"\n{'='*50}")
    print(f"✓ Preview: {request.city}, {request.country} @ {request.distance}m")
    print(f"{'='*50}")
    
    available_themes = get_available_themes()
    if request.theme not in available_themes:
        raise HTTPException(status_code=400, detail=f"Theme '{request.theme}' not found")
    
    job_id = uuid.uuid4().hex[:8]
    city_slug = re.sub(r'[\\/:*?"<>|,\s]', '_', request.city.lower())
    base_name = f"preview_{city_slug}_{request.theme}_{job_id}"
    
    jobs[job_id] = {
        "status": "starting",
        "step": 0,
        "total": 4,
        "message": "Finding your location...",
        "percent": 0,
        "preview_url": None,
        "variants": {},
        "error": None
    }
    
    async def run_generation():
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
                print(f"  [{job_id}] Location: {coords} ({time.time()-start_time:.1f}s)")
            except ValueError as e:
                jobs[job_id].update({"status": "error", "error": str(e)})
                return
            
            theme = load_theme(request.theme)
            fonts = load_fonts()
            
            preview_width = request.width / 1.5
            preview_height = request.height / 1.5
            preview_distance = min(request.distance, MAX_PREVIEW_DISTANCE)
            
            # Calculate compensated distance - THIS IS KEY FOR RADIUS!
            aspect_ratio = max(preview_height, preview_width) / min(preview_height, preview_width)
            compensated_dist = preview_distance * aspect_ratio / 4
            
            print(f"  [{job_id}] Distance: {preview_distance}m, Compensated: {compensated_dist:.0f}m")
            
            loop = asyncio.get_event_loop()
            
            # Step 2: Fetch drive streets
            jobs[job_id].update({
                "step": 2,
                "message": "Downloading street data...",
                "percent": 15
            })
            
            print(f"  [{job_id}] Fetching streets (drive)...")
            street_task = loop.run_in_executor(
                executor, fetch_graph_fast, coords, compensated_dist, 'drive'
            )
            
            street_start = time.time()
            while not street_task.done():
                if job_id in cancelled_jobs:
                    return
                await asyncio.sleep(0.5)
                elapsed = time.time() - street_start
                progress = min(40, 15 + (elapsed / 30) * 25)
                jobs[job_id].update({
                    "percent": int(progress),
                    "message": f"Loading streets... ({elapsed:.0f}s)"
                })
            
            g_drive = await street_task
            print(f"  [{job_id}] Streets (drive) done ({time.time()-start_time:.1f}s)")
            
            if g_drive is None:
                jobs[job_id].update({"status": "error", "error": "Failed to load street data"})
                return
            
            # Step 3: Fetch water and parks
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
            
            # Step 4: Render main variant (drive + water + parks)
            jobs[job_id].update({
                "step": 4,
                "message": "Composing your map...",
                "percent": 75
            })
            
            main_file = f"{base_name}.png"
            main_path = str(previews_path / main_file)
            
            print(f"  [{job_id}] Rendering main variant...")
            render_task = loop.run_in_executor(
                executor,
                render_full_poster,
                request.city, request.country, g_drive, water, parks,
                coords, preview_width, preview_height, theme, fonts,
                main_path, compensated_dist, True  # include_water_parks=True
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
            print(f"  [{job_id}] ✓ Main variant done in {total_time:.1f}s")
            
            # Complete! Main preview ready
            jobs[job_id].update({
                "status": "complete",
                "step": 4,
                "total": 4,
                "message": "Done!",
                "percent": 100,
                "preview_url": f"/previews/{main_file}",
                "variants": {
                    "drive_with_wp": f"/previews/{main_file}",
                    "drive_no_wp": None,
                    "all_with_wp": None,
                    "all_no_wp": None
                },
                "coords": list(coords),
                "compensated_dist": compensated_dist,
                "settings": {
                    "city": request.city,
                    "country": request.country,
                    "theme": request.theme,
                    "distance": preview_distance,
                    "width": request.width,
                    "height": request.height,
                }
            })
            
            # Render other variants in background
            asyncio.create_task(render_variants_background(
                job_id, base_name, request.city, request.country,
                g_drive, water, parks, coords,
                preview_width, preview_height, theme, fonts,
                compensated_dist
            ))
            
            gc.collect()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            jobs[job_id].update({"status": "error", "error": str(e)})
    
    asyncio.create_task(run_generation())
    return {"job_id": job_id, "status": "started"}


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


@app.post("/api/generate/start")
async def start_final_generation(request: PosterRequest):
    """Start final high-resolution poster generation."""
    job_id = uuid.uuid4().hex[:8]
    
    print(f"\n✓ Final: {request.city}, {request.country} [job: {job_id}]")
    print(f"  Features: water={request.features.water}, parks={request.features.parks}, paths={request.features.paths}")
    
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
            
            # Use 'all' network type if paths requested
            network_type = 'all' if request.features.paths else 'drive'
            
            aspect_ratio = max(request.height, request.width) / min(request.height, request.width)
            compensated_dist = request.distance * aspect_ratio / 4
            
            loop = asyncio.get_event_loop()
            
            jobs[job_id].update({
                "step": 2,
                "message": "Loading streets...",
                "percent": 15
            })
            
            g = await loop.run_in_executor(
                executor, fetch_graph_fast, coords, compensated_dist, network_type
            )
            
            if g is None:
                jobs[job_id].update({"status": "error", "error": "Failed to load street data"})
                return
            
            jobs[job_id].update({
                "step": 3,
                "message": "Adding features...",
                "percent": 45
            })
            
            # Only fetch water/parks if enabled
            water = None
            parks = None
            include_wp = request.features.water or request.features.parks
            if include_wp:
                water = await loop.run_in_executor(executor, fetch_water_fast, coords, compensated_dist)
                parks = await loop.run_in_executor(executor, fetch_parks_fast, coords, compensated_dist)
            
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
