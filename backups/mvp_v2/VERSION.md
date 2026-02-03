# MapToPrint MVP v2.0

**Date:** 2026-02-03  
**Status:** Production Ready ✓

## What's New in V2

### Deployment Fixes
- ✅ Fixed frontend directory not included in Railway builds
- ✅ Added explicit routes for static files at root level (/styles.css, /app.js, etc.)
- ✅ Better error handling for missing frontend files

### Configuration
- ✅ Added `nixpacks.toml` for Railway builder configuration
- ✅ Created `DEPLOYMENT_NOTES.md` with Railway/Cloudflare Pages setup
- ✅ Removed unused Docker/Heroku files

### Features (inherited from V1)
- ✅ Generate map posters for any city worldwide
- ✅ 17 unique themes with distinct aesthetics
- ✅ Configurable map radius (5-20km)
- ✅ Multiple poster sizes
- ✅ Progressive radius loading (5km, 10km)
- ✅ Layer toggling (water, parks, road types)
- ✅ Theme switching with cached data
- ✅ High-resolution poster generation

## Architecture
- **Backend:** Railway (Python FastAPI)
- **Frontend:** Cloudflare Pages (static HTML/CSS/JS)
- **Domain:** maptoprint.com
- **Map Data:** OpenStreetMap via OSMnx
- **Geocoding:** Nominatim API

## Files
```
├── create_map_poster.py    # CLI tool for poster generation
├── font_management.py      # Font loading utilities
├── start.py               # Server startup script
├── railway.toml           # Railway deployment config
├── nixpacks.toml          # Nixpacks builder config
├── web/
│   ├── app.py             # FastAPI backend (API + static serving)
│   └── image_utils.py     # Image processing utilities
└── frontend/
    ├── index.html         # Homepage
    ├── generate.html      # Generate page
    ├── styles.css         # Shared styles
    ├── generate.css       # Generate page styles
    ├── app.js             # Homepage JS
    ├── generate.js        # Generate page logic
    └── config.js          # API configuration
```

## To Run Locally
```bash
cd /path/to/maptoprint
uv run uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000
