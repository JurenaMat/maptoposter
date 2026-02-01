#!/usr/bin/env python3
"""
Generate radius preview images for the Map Radius selector.
Uses ONE city (New York) with different radiuses to show the difference in scope.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set matplotlib backend BEFORE any matplotlib imports
import matplotlib
matplotlib.use('Agg')

import create_map_poster
from create_map_poster import (
    get_coordinates,
    load_theme,
    load_fonts,
    fetch_graph,
    fetch_features,
    get_edge_colors_by_type,
    get_edge_widths_by_type,
    create_gradient_fade,
    get_crop_limits,
)
import matplotlib.pyplot as plt
import osmnx as ox
from PIL import Image
import gc


def generate_radius_preview(city, country, radius_m, output_path, theme_name="noir"):
    """Generate a small preview image for a given radius."""
    print(f"Generating {radius_m/1000}km radius preview for {city}...")
    
    # Get coordinates
    coords = get_coordinates(city, country)
    theme = load_theme(theme_name)
    
    # Set the global THEME variable for functions that use it
    create_map_poster.THEME = theme
    
    # Small poster dimensions for preview
    width = 4
    height = 5.33
    dpi = 72
    
    compensated_dist = radius_m * (max(height, width) / min(height, width)) / 4
    
    print(f"  Downloading street network...")
    g = fetch_graph(coords, compensated_dist)
    if g is None:
        print(f"  ERROR: Failed to get street network")
        return False
    
    print(f"  Downloading water features...")
    water = fetch_features(
        coords, compensated_dist,
        tags={"natural": ["water", "bay", "strait"], "waterway": "riverbank"},
        name="water"
    )
    
    print(f"  Downloading parks...")
    parks = fetch_features(
        coords, compensated_dist,
        tags={"leisure": "park", "landuse": "grass"},
        name="parks"
    )
    
    print(f"  Rendering...")
    fig, ax = plt.subplots(figsize=(width, height), facecolor=theme["bg"])
    ax.set_facecolor(theme["bg"])
    ax.set_position((0.0, 0.0, 1.0, 1.0))
    
    g_proj = ox.project_graph(g)
    
    # Plot water
    if water is not None and not water.empty:
        water_polys = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not water_polys.empty:
            try:
                water_polys = ox.projection.project_gdf(water_polys)
            except Exception:
                water_polys = water_polys.to_crs(g_proj.graph['crs'])
            water_polys.plot(ax=ax, facecolor=theme['water'], edgecolor='none', zorder=0.5)
    
    # Plot parks
    if parks is not None and not parks.empty:
        parks_polys = parks[parks.geometry.type.isin(["Polygon", "MultiPolygon"])]
        if not parks_polys.empty:
            try:
                parks_polys = ox.projection.project_gdf(parks_polys)
            except Exception:
                parks_polys = parks_polys.to_crs(g_proj.graph['crs'])
            parks_polys.plot(ax=ax, facecolor=theme['parks'], edgecolor='none', zorder=0.8)
    
    # Plot roads
    edge_colors = get_edge_colors_by_type(g_proj)
    edge_widths = get_edge_widths_by_type(g_proj)
    crop_xlim, crop_ylim = get_crop_limits(g_proj, coords, fig, compensated_dist)
    
    ox.plot_graph(
        g_proj, ax=ax, bgcolor=theme['bg'],
        node_size=0, edge_color=edge_colors, edge_linewidth=edge_widths,
        show=False, close=False,
    )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(crop_xlim)
    ax.set_ylim(crop_ylim)
    
    # Gradients
    create_gradient_fade(ax, theme['gradient_color'], location='bottom', zorder=10)
    create_gradient_fade(ax, theme['gradient_color'], location='top', zorder=10)
    
    # Remove axes
    ax.axis('off')
    
    # Save as PNG first
    png_path = output_path.with_suffix('.png')
    plt.savefig(png_path, format="png", dpi=dpi, facecolor=theme["bg"],
                bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    plt.close('all')
    
    # Convert to WebP
    print(f"  Converting to WebP...")
    with Image.open(png_path) as img:
        img.save(output_path, "WEBP", quality=85)
    png_path.unlink()  # Remove PNG
    
    # Cleanup
    del g, g_proj, water, parks
    gc.collect()
    
    print(f"  ✓ Saved: {output_path}")
    return True


def main():
    output_dir = Path("web/static/examples")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use New York (Manhattan) as the reference city
    city = "Manhattan"
    country = "United States"
    
    radiuses = [
        (3000, "radius_3km.webp"),
        (5000, "radius_5km.webp"),
        (10000, "radius_10km.webp"),
        (15000, "radius_15km.webp"),
        (20000, "radius_20km.webp"),
    ]
    
    print(f"\n{'='*50}")
    print(f"Generating radius preview images for {city}, {country}")
    print(f"{'='*50}\n")
    
    for radius_m, filename in radiuses:
        output_path = output_dir / filename
        try:
            generate_radius_preview(city, country, radius_m, output_path)
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n✓ Done! Preview images saved to {output_dir}")


if __name__ == "__main__":
    main()
