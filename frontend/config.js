/**
 * MapToPoster Configuration
 * API URL is set based on environment
 */

// In production, this will be set to Cloud Run URL
// For local development, use empty string (same origin)
const API_BASE = window.MAPTOPOSTER_API_URL || '';

// Export for use in other scripts
window.API_BASE = API_BASE;
