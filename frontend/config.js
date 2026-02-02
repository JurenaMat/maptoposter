/**
 * MapToPoster Configuration
 * API URL is set based on environment
 */

// Production API URL - Railway backend
// For local development, set window.MAPTOPOSTER_API_URL = '' before loading this script
const API_BASE = window.MAPTOPOSTER_API_URL !== undefined 
    ? window.MAPTOPOSTER_API_URL 
    : 'https://api.maptoprint.com';

// Export for use in other scripts
window.API_BASE = API_BASE;
