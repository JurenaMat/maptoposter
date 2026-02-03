# MapToPrint Deployment Notes

## Architecture
- **Backend**: Railway (Python FastAPI) - serves API and static files
- **Frontend**: Cloudflare Pages (static HTML/CSS/JS) - serves the main website
- **Domain**: maptoprint.com
- **Repository**: github.com/JurenaMat/maptoposter

## Railway Deployment
- Uses **nixpacks** builder (not Docker)
- Start command: `python start.py`
- Health check: `/health`
- The `frontend/` directory MUST be included in the build for the root route to work
- Railway automatically deploys on git push to main branch

## Important Files
- `web/app.py` - Main FastAPI application
- `frontend/` - Static frontend files (served by Railway backend for root route)
- `nixpacks.toml` - Nixpacks build configuration (CRITICAL for Railway)
- `railway.toml` - Railway deployment configuration
- `requirements.txt` - Python dependencies

## nixpacks.toml Requirements
The `nixpacks.toml` file MUST:
1. **NOT specify Python in nixPkgs** - this breaks pip! Let nixpacks auto-detect from requirements.txt
2. **Use aptPkgs for geo libraries**: `libgdal-dev`, `libgeos-dev`, `libproj-dev`, `gdal-bin`
3. **Create directories**: `web/previews`, `posters`, `cache` (relative paths, NOT /app/...)

## Pre-Deployment Checklist
Before pushing to main:
1. Run `uv run pytest tests/test_deployment.py -v` - all tests must pass
2. Run `uv run python -c "from web.app import app; print('OK')"` - app must import
3. Verify `frontend/index.html` exists
4. Check `nixpacks.toml` has correct system packages

## Common Build Failures
1. **"pip: command not found"**: Do NOT specify python in nixPkgs! Let nixpacks auto-detect.
2. **Missing geo libraries**: Use `aptPkgs` (not nixPkgs) for libgdal-dev, libgeos-dev, libproj-dev
3. **Wrong directory paths**: Use relative paths (not `/app/...`) in nixpacks.toml
4. **Missing frontend**: Ensure `frontend/` is committed and not in `.gitignore`
5. **Import errors**: Run app import test locally before pushing

## Deployment Process
1. Run local tests: `uv run pytest tests/test_deployment.py -v`
2. Push changes to git (main branch)
3. Railway automatically detects changes and rebuilds
4. Check Railway logs for build/deployment status
5. Verify deployment at maptoprint.com

## Testing Commands
```bash
# API tests (fast)
uv run pytest tests/test_deployment.py -v

# E2E tests (requires server)
PORT=8000 uv run python start.py &
uv run pytest tests/e2e/test_full_flow.py -v --base-url http://localhost:8000
```
