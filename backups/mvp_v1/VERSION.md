# MapToPrint MVP v1.0

**Date:** 2026-02-01  
**Status:** MVP Complete ✓

## Features

### Core Functionality
- ✅ Generate map posters for any city worldwide
- ✅ 17 unique themes with distinct aesthetics
- ✅ Configurable map radius (5-20km)
- ✅ Multiple poster sizes (8×10" to 18×24")
- ✅ High-resolution output (300 DPI)

### Web Interface
- ✅ Homepage with example gallery
- ✅ Dedicated `/generate` page
- ✅ Visual theme gallery picker
- ✅ City autocomplete via Nominatim
- ✅ Fast preview generation (~10s at 100 DPI)
- ✅ Progress indicator with percentage
- ✅ Compare up to 3 preview versions
- ✅ Step-by-step progress for final generation
- ✅ Download high-res PNG

### Architecture
- **Backend:** FastAPI + Python
- **Frontend:** Vanilla JS + CSS (no framework)
- **Map Data:** OpenStreetMap via OSMnx
- **Geocoding:** Nominatim API

## Files
```
web/
├── app.py              # FastAPI backend
├── static/
│   ├── index.html      # Homepage
│   ├── app.js          # Homepage JS
│   ├── styles.css      # Shared styles
│   ├── generate.html   # Generate page
│   ├── generate.css    # Generate page styles
│   └── generate.js     # Generate page logic
└── previews/           # Low-res previews (auto-generated)
```

## To Run
```bash
source $HOME/.local/bin/env
cd /path/to/maptoprint
uv run uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000
