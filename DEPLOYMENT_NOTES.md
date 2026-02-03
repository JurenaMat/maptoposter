# MapToPrint Deployment Notes

## Architecture
- **Backend**: Railway (Python FastAPI) - serves API and static files
- **Frontend**: Cloudflare Pages (static HTML/CSS/JS) - serves the main website
- **Domain**: maptoprint.com

## Railway Deployment
- Uses **nixpacks** builder (not Docker)
- Start command: `python start.py`
- Health check: `/health`
- The `frontend/` directory MUST be included in the build for the root route to work
- Railway automatically deploys on git push to main branch

## Important Files
- `web/app.py` - Main FastAPI application
- `frontend/` - Static frontend files (served by Railway backend for root route)
- `.dockerignore` - Only affects Docker builds, NOT Railway (Railway uses nixpacks)
- `railway.toml` - Railway configuration

## Common Issues
1. **500 Error on root route**: Frontend directory not included in build
   - Solution: Ensure `frontend/` is not in `.gitignore` or any ignore files
   - Check that `frontend/index.html` exists in the repository

2. **Static files not loading**: Check that `frontend/` directory is mounted correctly in `web/app.py`

## Deployment Process
1. Push changes to git (main branch)
2. Railway automatically detects changes and rebuilds
3. Check Railway logs for build/deployment status
4. Verify deployment at maptoprint.com
