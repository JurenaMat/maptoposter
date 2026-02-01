#!/usr/bin/env python3
"""
Generate optimized WebP previews from existing poster PNGs.
Run this once to create the example images.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from web.image_utils import generate_preview_from_png

# Poster mappings
POSTERS = [
    ("san_francisco_sunset_20260118_144726.png", "san_francisco_sunset"),
    ("tokyo_japanese_ink_20260118_142446.png", "tokyo_japanese_ink"),
    ("venice_blueprint_20260118_140505.png", "venice_blueprint"),
    ("dubai_midnight_blue_20260118_140807.png", "dubai_midnight_blue"),
    ("singapore_neon_cyberpunk_20260118_153328.png", "singapore_neon_cyberpunk"),
    ("prague_noir_20260201_123817.png", "prague_noir"),
]

def main():
    posters_dir = Path(__file__).parent.parent / "posters"
    examples_dir = Path(__file__).parent.parent / "web" / "static" / "examples"
    examples_dir.mkdir(exist_ok=True)
    
    print(f"Generating previews from {posters_dir}")
    print(f"Output directory: {examples_dir}")
    print()
    
    for png_name, base_name in POSTERS:
        png_path = posters_dir / png_name
        
        if not png_path.exists():
            print(f"⚠ Skipping {png_name} - not found")
            continue
        
        print(f"Processing {png_name}...")
        
        try:
            # Generate preview and thumb
            result = generate_preview_from_png(str(png_path), examples_dir)
            
            # Rename to standard names
            preview_src = Path(result['preview'])
            thumb_src = Path(result['thumb'])
            
            preview_dst = examples_dir / f"{base_name}_preview.webp"
            thumb_dst = examples_dir / f"{base_name}_thumb.webp"
            
            preview_src.rename(preview_dst)
            thumb_src.rename(thumb_dst)
            
            # Get file sizes
            preview_size = preview_dst.stat().st_size / 1024
            thumb_size = thumb_dst.stat().st_size / 1024
            original_size = png_path.stat().st_size / 1024
            
            print(f"  ✓ Original: {original_size:.0f}KB")
            print(f"  ✓ Preview:  {preview_size:.0f}KB ({preview_dst.name})")
            print(f"  ✓ Thumb:    {thumb_size:.0f}KB ({thumb_dst.name})")
            print(f"  ✓ Blur:     {len(result['blur_placeholder'])} bytes base64")
            print()
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            print()
    
    print("Done! Preview files generated in web/static/examples/")


if __name__ == "__main__":
    main()
