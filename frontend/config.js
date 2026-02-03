/**
 * MapToPrint Configuration
 * API URL and static paths set based on environment
 */

// Production API URL - Railway backend
// For local development, set window.MAPTOPRINT_API_URL = '' before loading this script
const API_BASE = window.MAPTOPRINT_API_URL !== undefined 
    ? window.MAPTOPRINT_API_URL 
    : 'https://api.maptoprint.com';

// Static asset base path
// Production (Cloudflare Pages): '' (files at root)
// Local (FastAPI): '/static' (files mounted at /static)
const STATIC_BASE = window.MAPTOPRINT_STATIC_BASE !== undefined
    ? window.MAPTOPRINT_STATIC_BASE
    : '';

// Export for use in other scripts
window.API_BASE = API_BASE;
window.STATIC_BASE = STATIC_BASE;
