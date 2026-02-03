/**
 * MapToPrint Configuration
 * API URL is set based on environment
 */

// Auto-detect environment: use local API on localhost, production API otherwise
const isLocalDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
const API_BASE = window.MAPTOPRINT_API_URL !== undefined 
    ? window.MAPTOPRINT_API_URL 
    : isLocalDev 
        ? ''  // Local dev: same-origin API
        : 'https://api.maptoprint.com';

// Export for use in other scripts
window.API_BASE = API_BASE;
