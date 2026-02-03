/**
 * MapToPrint Generate Page
 * MVP v1.7 - 2026-02-02
 * 
 * PROGRESSIVE RADIUS LOADING
 * - Fast 5km preview first
 * - Background loading of 10km, 15km, 20km
 * - Radius selector with loading states
 */

// State
let selectedCity = null;
let selectedCountry = null;
let selectedTheme = 'noir';
let selectedDistance = 5000;  // Default initial radius
let selectedSize = '30x40';
let debounceTimer = null;
let themes = [];

// Preview state
let currentPreview = null;
let previews = [];
let currentPreviewIndex = 0;
let currentJobId = null;
let variantPollingInterval = null;
let radiusPollingInterval = null;

// Radius state - tracks loading progress
let radiusStatus = {
    5000: 'pending',
    10000: 'pending',
    15000: 'locked',  // Requires signup
    20000: 'locked'   // Requires signup
};

// Feature state
let featureState = {
    parks: true,
    water: true,
    roads_drive: true,
    roads_paths: true,
    roads_cycling: true
};

// Variant state - tracks available variants
let variants = {
    drive_with_wp: null,
    drive_no_wp: null,
    all_with_wp: null,
    all_no_wp: null
};

// Loading showcase - images rotate independently on a timer
// Uses STATIC_BASE from config.js ('' for production, '/static' for local)
const LOADING_SHOWCASE = [
    { image: 'tokyo_japanese_ink_preview.webp', emoji: '🗾', label: 'Tokyo' },
    { image: 'venice_blueprint_preview.webp', emoji: '🇮🇹', label: 'Venice' },
    { image: 'san_francisco_sunset_preview.webp', emoji: '🌉', label: 'San Francisco' },
    { image: 'prague_noir_preview.webp', emoji: '🏰', label: 'Prague' },
    { image: 'dubai_midnight_blue_preview.webp', emoji: '🏙️', label: 'Dubai' },
    { image: 'singapore_neon_cyberpunk_preview.webp', emoji: '✨', label: 'Singapore' },
];

function getShowcaseImagePath(filename) {
    const base = window.STATIC_BASE || '';
    return `${base}/examples/${filename}`;
}

// Fun loading messages grouped by stage
const LOADING_MESSAGES = {
    location: [
        "Asking GPS satellites nicely...",
        "Finding your spot on Earth...",
        "Consulting ancient cartographers...",
        "Locating you in the universe...",
    ],
    streets: [
        "Downloading every street corner...",
        "Mapping out secret shortcuts...",
        "Interviewing local taxi drivers...",
        "Tracing delivery routes...",
        "Paving digital highways...",
    ],
    water: [
        "Making the rivers flow...",
        "Teaching water where to go...",
        "Consulting with local ducks...",
    ],
    parks: [
        "Planting digital trees...",
        "Finding where dogs get walked...",
        "Growing a tiny urban forest...",
    ],
    render: [
        "Mixing the perfect palette...",
        "Teaching robots to be artists...",
        "Making it poster-worthy...",
        "Adding that gallery finish...",
        "Almost frame-ready...",
    ]
};

let currentShowcaseIndex = 0;
let showcaseInterval = null;

function getRandomMessage(stage) {
    const messages = LOADING_MESSAGES[stage] || LOADING_MESSAGES.render;
    return messages[Math.floor(Math.random() * messages.length)];
}

function getCurrentShowcase() {
    return LOADING_SHOWCASE[currentShowcaseIndex];
}

function advanceShowcase() {
    currentShowcaseIndex = (currentShowcaseIndex + 1) % LOADING_SHOWCASE.length;
    updateShowcaseVisual();
}

function updateShowcaseVisual(immediate = false) {
    const showcase = getCurrentShowcase();
    const imgEl = document.getElementById('loadingStageImg');
    const emojiEl = document.getElementById('stageEmoji');
    const imagePath = getShowcaseImagePath(showcase.image);
    
    if (emojiEl) {
        if (immediate) {
            emojiEl.textContent = showcase.emoji;
            emojiEl.style.transform = 'scale(1) rotate(0deg)';
        } else {
            emojiEl.style.transform = 'scale(0) rotate(-180deg)';
            setTimeout(() => {
                emojiEl.textContent = showcase.emoji;
                emojiEl.style.transform = 'scale(1) rotate(0deg)';
            }, 200);
        }
    }
    
    if (imgEl) {
        if (immediate) {
            // Load first image immediately without animation
            imgEl.src = imagePath;
            imgEl.onload = () => imgEl.classList.add('visible');
            imgEl.onerror = () => console.error('Failed to load showcase image:', imagePath);
        } else {
            imgEl.classList.remove('visible');
            setTimeout(() => {
                imgEl.src = imagePath;
                imgEl.onload = () => imgEl.classList.add('visible');
                imgEl.onerror = () => console.error('Failed to load showcase image:', imagePath);
            }, 250);
        }
    }
}

function preloadShowcaseImages() {
    LOADING_SHOWCASE.forEach(item => {
        const img = new Image();
        img.src = getShowcaseImagePath(item.image);
    });
}

function startShowcaseRotation() {
    currentShowcaseIndex = 0;
    preloadShowcaseImages();
    updateShowcaseVisual(true);  // Load first image immediately
    // Rotate every 3 seconds
    showcaseInterval = setInterval(advanceShowcase, 3000);
}

function stopShowcaseRotation() {
    if (showcaseInterval) {
        clearInterval(showcaseInterval);
        showcaseInterval = null;
    }
}

// DOM Elements
const cityInput = document.getElementById('cityInput');
const autocompleteDropdown = document.getElementById('autocompleteDropdown');
const themeGallery = document.getElementById('themeGallery');
const generateBtn = document.getElementById('generateBtn');
const step1 = document.getElementById('step1');
const step2 = document.getElementById('step2');
const loadingOverlay = document.getElementById('loadingOverlay');
const progressRing = document.getElementById('progressRing');
const progressPercent = document.getElementById('progressPercent');
const progressStatus = document.getElementById('progressStatus');
const previewCity = document.getElementById('previewCity');
const previewMeta = document.getElementById('previewMeta');
const generateFinalBtn = document.getElementById('generateFinalBtn');
const editConfigBtn = document.getElementById('editConfigBtn');
const progressModal = document.getElementById('progressModal');
const finalProgressCity = document.getElementById('finalProgressCity');
const finalProgressBar = document.getElementById('finalProgressBar');
const resultModal = document.getElementById('resultModal');
const resultModalClose = document.getElementById('resultModalClose');
const resultImage = document.getElementById('resultImage');
const resultCity = document.getElementById('resultCity');
const resultTheme = document.getElementById('resultTheme');
const downloadBtn = document.getElementById('downloadBtn');
const createAnother = document.getElementById('createAnother');

// ============================================
// Toast Notifications
// ============================================

function showToast(message, type = 'error') {
    const existingToast = document.querySelector('.toast-notification');
    if (existingToast) existingToast.remove();
    
    const icons = {
        error: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
                </svg>`,
        success: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                    <polyline points="22 4 12 14.01 9 11.01"/>
                </svg>`,
        info: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
                </svg>`
    };
    
    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <div class="toast-icon">${icons[type] || icons.info}</div>
            <div class="toast-message">${message}</div>
            <button class="toast-close" onclick="this.parentElement.parentElement.remove()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
            </button>
        </div>
    `;
    
    document.body.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('active'));
    setTimeout(() => {
        toast.classList.remove('active');
        setTimeout(() => toast.remove(), 300);
    }, 6000);
}

// ============================================
// Initialize
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    loadThemes();
    setupEventListeners();
    setupSizeGallery();
    setupRadiusSelector();
    setupFeatureToggles();
    
    const params = new URLSearchParams(window.location.search);
    if (params.get('city') && params.get('country')) {
        selectedCity = params.get('city');
        selectedCountry = params.get('country');
        cityInput.value = `${selectedCity}, ${selectedCountry}`;
    }
    if (params.get('theme')) {
        selectedTheme = params.get('theme');
    }
});

async function loadThemes() {
    try {
        const response = await fetch('/api/themes');
        themes = await response.json();
        renderThemeGallery();
    } catch (error) {
        console.error('Failed to load themes:', error);
        showToast('Failed to load themes. Please refresh the page.');
    }
}

function renderThemeGallery() {
    themeGallery.innerHTML = themes.map(theme => `
        <div class="theme-card ${theme.name === selectedTheme ? 'selected' : ''}" data-theme="${theme.name}">
            <div class="theme-preview">
                <div class="theme-preview-bg" style="background: ${theme.bg}"></div>
                <div class="theme-preview-roads">
                    <svg viewBox="0 0 100 80" preserveAspectRatio="none">
                        <path d="M0 40 Q25 35 50 40 T100 40" stroke="${theme.text}" stroke-width="3" fill="none" opacity="0.8"/>
                        <path d="M20 20 Q40 25 60 20 T100 25" stroke="${theme.text}" stroke-width="2" fill="none" opacity="0.5"/>
                        <path d="M0 60 Q30 55 60 60 T100 55" stroke="${theme.text}" stroke-width="2" fill="none" opacity="0.5"/>
                    </svg>
                </div>
            </div>
            <div class="theme-info">
                <span class="theme-name">${theme.display_name}</span>
                <span class="theme-desc">${theme.description || ''}</span>
            </div>
            <div class="theme-check">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
            </div>
        </div>
    `).join('');
    
    themeGallery.querySelectorAll('.theme-card').forEach(card => {
        card.addEventListener('click', () => {
            themeGallery.querySelectorAll('.theme-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedTheme = card.dataset.theme;
        });
    });
}

function renderThemeSwitcher() {
    const switcher = document.getElementById('themeSwitcher');
    if (!switcher) return;
    
    switcher.innerHTML = themes.map(theme => `
        <div class="theme-swatch ${theme.name === selectedTheme ? 'selected' : ''}" 
             data-theme="${theme.name}" 
             title="${theme.display_name}">
            <div class="theme-swatch-bg" style="background: ${theme.bg}"></div>
            <div class="theme-swatch-roads">
                <svg viewBox="0 0 24 24" fill="none">
                    <path d="M2 12 Q6 10 12 12 T22 12" stroke="${theme.text}" stroke-width="2" opacity="0.8"/>
                    <path d="M4 6 Q8 8 14 6" stroke="${theme.text}" stroke-width="1.5" opacity="0.5"/>
                    <path d="M2 18 Q10 16 22 18" stroke="${theme.text}" stroke-width="1.5" opacity="0.5"/>
                </svg>
            </div>
            <div class="theme-swatch-check">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
            </div>
        </div>
    `).join('');
    
    switcher.querySelectorAll('.theme-swatch').forEach(swatch => {
        swatch.addEventListener('click', () => handleThemeSwitch(swatch.dataset.theme));
    });
}

async function handleThemeSwitch(themeName) {
    if (!currentJobId || themeName === selectedTheme) return;
    
    const switcher = document.getElementById('themeSwitcher');
    
    // Update UI immediately
    switcher.querySelectorAll('.theme-swatch').forEach(s => s.classList.remove('selected'));
    switcher.querySelector(`[data-theme="${themeName}"]`)?.classList.add('selected');
    
    // Show loading overlay with theme name
    const themeInfo = themes.find(t => t.name === themeName);
    showPreviewLoading(`Painting with ${themeInfo?.display_name || themeName}...`);
    
    try {
        const response = await fetch(`/api/preview/theme/${currentJobId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: themeName })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.detail || 'Failed to switch theme');
        }
        
        selectedTheme = themeName;
        
        // Update preview image
        const previewImage = document.getElementById('previewImage');
        if (previewImage && result.preview_url) {
            previewImage.src = result.preview_url + '?t=' + Date.now();
            previewImage.onload = () => hidePreviewLoading();
    } else {
            hidePreviewLoading();
        }
        
        // Update step 1 theme gallery too
        themeGallery.querySelectorAll('.theme-card').forEach(c => {
            c.classList.toggle('selected', c.dataset.theme === themeName);
        });
        
        updatePreviewMeta();
        
    } catch (error) {
        console.error('Theme switch error:', error);
        showToast(error.message || 'Failed to switch theme', 'error');
        hidePreviewLoading();
        
        // Revert UI
        switcher.querySelectorAll('.theme-swatch').forEach(s => {
            s.classList.toggle('selected', s.dataset.theme === selectedTheme);
        });
    }
}

// ============================================
// Feature Toggles
// ============================================

function setupFeatureToggles() {
    const toggles = {
        toggleParks: 'parks',
        toggleWater: 'water',
        toggleRoadsDrive: 'roads_drive',
        toggleRoadsPaths: 'roads_paths',
        toggleRoadsCycling: 'roads_cycling'
    };
    
    for (const [elementId, featureKey] of Object.entries(toggles)) {
        const toggle = document.getElementById(elementId);
        if (toggle) {
            toggle.addEventListener('change', () => handleFeatureToggle(featureKey, toggle.checked));
        }
    }
}

let featureToggleDebounce = null;

// Fun loading messages for features
const FEATURE_LOADING_MESSAGES = {
    parks: ['🌳 Planting trees...', '🌲 Growing the forest...', '🌿 Adding some greenery...'],
    water: ['💧 Filling rivers...', '🌊 Adding the blue stuff...', '🏊 Making it swimable...'],
    roads_drive: ['🚗 Paving highways...', '🛣️ Drawing roads...', '🚙 Mapping drives...'],
    roads_paths: ['🚶 Charting footpaths...', '🛤️ Tracing trails...', '👟 Finding shortcuts...'],
    roads_cycling: ['🚴 Adding bike lanes...', '🚲 Mapping cycle routes...', '🛴 Going green...']
};

function getFeatureLoadingMessage(featureKey, adding) {
    const action = adding ? 'Adding' : 'Removing';
    const messages = FEATURE_LOADING_MESSAGES[featureKey] || ['Updating map...'];
    if (adding) {
        return messages[Math.floor(Math.random() * messages.length)];
    }
    const featureNames = {
        parks: 'parks',
        water: 'water',
        roads_drive: 'main roads',
        roads_paths: 'footpaths',
        roads_cycling: 'bike lanes'
    };
    return `${action} ${featureNames[featureKey] || 'layer'}...`;
}

async function handleFeatureToggle(featureKey, value) {
    if (!currentJobId) return;
    
    // Update local state
    featureState[featureKey] = value;
    
    // Debounce to batch multiple changes
    if (featureToggleDebounce) clearTimeout(featureToggleDebounce);
    
    featureToggleDebounce = setTimeout(async () => {
        // Show loading overlay
        showPreviewLoading(getFeatureLoadingMessage(featureKey, value));
        
        console.log('Toggling features:', featureState);
        
        try {
            const response = await fetch(`/api/preview/features/${currentJobId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(featureState)
            });
            
            const result = await response.json();
            console.log('Feature toggle response:', result);
            
            if (!response.ok) {
                throw new Error(result.detail || 'Failed to update features');
            }
            
            // Update preview image
            const previewImage = document.getElementById('previewImage');
            if (previewImage && result.preview_url) {
                previewImage.src = result.preview_url + '?t=' + Date.now();
                previewImage.onload = () => hidePreviewLoading();
            } else {
                hidePreviewLoading();
            }
            
        } catch (error) {
            console.error('Feature toggle error:', error);
            showToast(error.message || 'Failed to update features', 'error');
            hidePreviewLoading();
        }
    }, 300);
}

function resetFeatureToggles() {
    featureState = {
        parks: true,
        water: true,
        roads_drive: true,
        roads_paths: true,
        roads_cycling: true
    };
    
    const toggles = {
        toggleParks: 'parks',
        toggleWater: 'water',
        toggleRoadsDrive: 'roads_drive',
        toggleRoadsPaths: 'roads_paths',
        toggleRoadsCycling: 'roads_cycling'
    };
    
    for (const [elementId, featureKey] of Object.entries(toggles)) {
        const toggle = document.getElementById(elementId);
        if (toggle) toggle.checked = featureState[featureKey];
    }
}

// Legacy - keep for compatibility
function updateVariantStatus() {}

// ============================================
// Progressive Radius Selector (Step 2)
// ============================================

function setupRadiusSelector() {
    const radiusSelector = document.getElementById('radiusSelector');
    if (!radiusSelector) return;
    
    radiusSelector.addEventListener('click', async (e) => {
        const option = e.target.closest('.radius-option');
        if (!option) return;
        
        const radius = parseInt(option.dataset.value, 10);
        const status = option.dataset.status;
        
        // Check if locked (requires signup)
        if (status === 'locked') {
            // TODO: Implement signup modal
            showToast('Sign up to unlock larger map sizes!', 'info');
            return;
        }
        
        // Only allow clicking ready radiuses
        if (status !== 'ready') {
            if (status === 'loading') {
                showToast('This radius is still loading...', 'info');
            } else {
                showToast('This radius is not available yet', 'info');
            }
            return;
        }
        
        // Switch radius
        await switchRadius(radius);
    });
}

async function switchRadius(radius) {
    if (!currentJobId) return;
    
    // Show loading overlay
    showPreviewLoading(`Resizing to ${radius / 1000}km view...`);
    
    try {
        const response = await fetch(`/api/preview/radius/${currentJobId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ radius })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.detail || 'Failed to switch radius');
        }
        
        // Update UI
        selectedDistance = radius;
        
        // Update selection in radius selector
        const selector = document.getElementById('radiusSelector');
        selector.querySelectorAll('.radius-option').forEach(opt => {
            opt.classList.remove('selected');
            if (parseInt(opt.dataset.value, 10) === radius) {
                opt.classList.add('selected');
            }
        });
        
        // Update preview image
        const previewImage = document.getElementById('previewImage');
        if (previewImage && result.preview_url) {
            previewImage.src = result.preview_url + '?t=' + Date.now();
            previewImage.onload = () => hidePreviewLoading();
        } else {
            hidePreviewLoading();
        }
        
        // Update meta text
        updatePreviewMeta();
        
    } catch (error) {
        console.error('Radius switch error:', error);
        showToast(error.message || 'Failed to switch radius', 'error');
        hidePreviewLoading();
    }
}

function updateRadiusSelectorUI(radiusData) {
    const selector = document.getElementById('radiusSelector');
    if (!selector) return;
    
    for (const [radiusStr, data] of Object.entries(radiusData)) {
        const radius = parseInt(radiusStr, 10);
        const option = selector.querySelector(`[data-value="${radius}"]`);
        if (!option) continue;
        
        const status = data.status;
        const statusEl = option.querySelector('.radius-option-status');
        
        // Update data attribute for CSS
        option.dataset.status = status;
        
        // Update status text
        if (statusEl) {
            switch (status) {
                case 'ready':
                    statusEl.textContent = 'Ready';
                    break;
                case 'loading':
                    statusEl.textContent = 'Loading...';
                    break;
                case 'pending':
                    statusEl.textContent = 'Locked';
                    break;
                case 'error':
                    statusEl.textContent = 'Failed';
                    break;
            }
        }
        
        // Update classes
        option.classList.remove('loading', 'locked');
        if (status === 'loading') {
            option.classList.add('loading');
        } else if (status === 'pending') {
            option.classList.add('locked');
        }
        
        // Store in state
        radiusStatus[radius] = status;
    }
}

function updatePreviewMeta() {
    const previewMeta = document.getElementById('previewMeta');
    if (!previewMeta || !currentPreview) return;
    
    const settings = currentPreview.settings;
    const themeName = themes.find(t => t.name === settings.theme)?.display_name || settings.theme;
    const sizeLabel = `${Math.round(settings.width * 2.54)}×${Math.round(settings.height * 2.54)}cm`;
    
    previewMeta.textContent = `${themeName} • ${selectedDistance / 1000}km • ${sizeLabel}`;
}

// ============================================
// Size Gallery
// ============================================

function setupSizeGallery() {
    const sizeGallery = document.getElementById('sizeGallery');
    if (!sizeGallery) return;
    
    sizeGallery.addEventListener('click', (e) => {
        const option = e.target.closest('.size-option');
        if (!option) return;
        
        sizeGallery.querySelectorAll('.size-option').forEach(o => o.classList.remove('selected'));
        option.classList.add('selected');
        selectedSize = option.dataset.value;
    });
    
    const defaultOption = sizeGallery.querySelector('[data-value="30x40"]');
    if (defaultOption) defaultOption.classList.add('selected');
}

function getCurrentDistance() {
    // With progressive loading, always start with 5km
    return selectedDistance;
}

function getCurrentSize() {
    const selected = document.querySelector('#sizeGallery .size-option.selected');
    return selected ? selected.dataset.value : selectedSize;
}

function cmToInches(cm) {
    return cm / 2.54;
}

// ============================================
// Event Listeners
// ============================================

function setupEventListeners() {
    cityInput.addEventListener('input', handleCityInput);
    cityInput.addEventListener('focus', () => {
        if (autocompleteDropdown.children.length > 0) {
            autocompleteDropdown.classList.add('active');
        }
    });
    
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.autocomplete-wrapper')) {
            autocompleteDropdown.classList.remove('active');
        }
    });
    
    generateBtn.addEventListener('click', handleGenerate);
    generateFinalBtn.addEventListener('click', handleGenerateFinal);
    editConfigBtn.addEventListener('click', goToStep1);
    
    resultModalClose.addEventListener('click', closeResultModal);
    document.querySelector('#resultModal .modal-backdrop')?.addEventListener('click', closeResultModal);
    createAnother.addEventListener('click', () => {
        closeResultModal();
        resetAll();
    });
    
    const previewWrapper = document.getElementById('previewWrapper');
    if (previewWrapper) {
        previewWrapper.addEventListener('click', openZoomModal);
    }
    
    const zoomModalClose = document.getElementById('zoomModalClose');
    const zoomModal = document.getElementById('zoomModal');
    if (zoomModalClose) zoomModalClose.addEventListener('click', closeZoomModal);
    if (zoomModal) zoomModal.querySelector('.modal-backdrop')?.addEventListener('click', closeZoomModal);
    
    const cancelBtn = document.getElementById('cancelBtn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', handleCancel);
    }
}

async function handleCancel() {
    if (currentJobId) {
        try {
            await fetch(`/api/cancel/${currentJobId}`, { method: 'POST' });
            showToast('Generation cancelled', 'info');
        } catch (e) {
            console.error('Cancel error:', e);
        }
        hideLoading();
        generateBtn.classList.remove('loading');
        generateBtn.disabled = false;
        currentJobId = null;
    }
}

// ============================================
// City Autocomplete
// ============================================

function handleCityInput(e) {
    const query = e.target.value.trim();
    if (debounceTimer) clearTimeout(debounceTimer);
    selectedCity = null;
    selectedCountry = null;
    
    if (query.length < 2) {
        autocompleteDropdown.classList.remove('active');
        autocompleteDropdown.innerHTML = '';
        return;
    }
    
    debounceTimer = setTimeout(() => fetchCitySuggestions(query), 300);
}

async function fetchCitySuggestions(query) {
    try {
        const response = await fetch(`/api/geocode?q=${encodeURIComponent(query)}`);
        const results = await response.json();
        
        if (results.length === 0) {
            autocompleteDropdown.classList.remove('active');
            return;
        }
        
        autocompleteDropdown.innerHTML = results.map((result, index) => `
            <div class="autocomplete-item" data-index="${index}">
                <div class="autocomplete-item-city">${result.city}</div>
                <div class="autocomplete-item-country">${result.country}</div>
            </div>
        `).join('');
        
        autocompleteDropdown.querySelectorAll('.autocomplete-item').forEach((item, index) => {
            item.addEventListener('click', () => {
                const r = results[index];
                selectedCity = r.city;
                selectedCountry = r.country;
                cityInput.value = `${r.city}, ${r.country}`;
                autocompleteDropdown.classList.remove('active');
            });
        });
        
        autocompleteDropdown.classList.add('active');
    } catch (error) {
        console.error('Autocomplete error:', error);
    }
}

// ============================================
// Navigation
// ============================================

function goToStep1() {
    step1.dataset.active = 'true';
    step2.dataset.active = 'false';
    updateStepIndicators(1);
    stopVariantPolling();
    stopRadiusPolling();
}

function goToStep2() {
    step1.dataset.active = 'false';
    step2.dataset.active = 'true';
    updateStepIndicators(2);
}

function updateStepIndicators(activeStep) {
    document.querySelectorAll('.step-indicator').forEach((indicator, index) => {
        const step = index + 1;
        indicator.classList.remove('active', 'complete');
        if (step < activeStep) indicator.classList.add('complete');
        else if (step === activeStep) indicator.classList.add('active');
    });
}

function resetAll() {
    cityInput.value = '';
    selectedCity = null;
    selectedCountry = null;
    selectedTheme = 'noir';
    selectedDistance = 10000;  // Default 10km
    selectedSize = '30x40';
    currentPreview = null;
    previews = [];
    currentPreviewIndex = 0;
    currentJobId = null;
    variants = {};
    radiusStatus = { 5000: 'pending', 10000: 'pending', 15000: 'locked', 20000: 'locked' };
    featureState = { parks: true, water: true, roads_drive: true, roads_paths: true, roads_cycling: true };
    stopVariantPolling();
    stopRadiusPolling();
    renderThemeGallery();
    goToStep1();
}

// ============================================
// Preview Generation
// ============================================

async function handleGenerate() {
    if (!selectedCity || !selectedCountry) {
        const parts = cityInput.value.split(',').map(s => s.trim());
        if (parts.length >= 2) {
            selectedCity = parts[0];
            selectedCountry = parts.slice(1).join(', ');
        } else {
            showToast('Please select a location from the suggestions');
            cityInput.focus();
            return;
        }
    }
    
    const currentSize = getCurrentSize();
    const [widthCm, heightCm] = currentSize.split('x').map(Number);
    const width = cmToInches(widthCm);
    const height = cmToInches(heightCm);
    
    const selectedThemeCard = themeGallery.querySelector('.theme-card.selected');
    const currentTheme = selectedThemeCard ? selectedThemeCard.dataset.theme : selectedTheme;
    
    // Start with 10km (default) with all features
    const settings = {
        city: selectedCity,
        country: selectedCountry,
        theme: currentTheme,
        distance: 10000,  // Default 10km
        width: width,
        height: height,
        features: { water: true, parks: true, paths: true }
    };
    
    console.log('Generating preview:', settings);
    
    // Reset states
    selectedDistance = 10000;  // Default 10km
    variants = {};
    radiusStatus = { 5000: 'pending', 10000: 'pending', 15000: 'locked', 20000: 'locked' };
    resetRadiusSelectorUI();
    resetFeatureToggles();
    
    showLoading();
    generateBtn.classList.add('loading');
    generateBtn.disabled = true;
    
    try {
        const startResponse = await fetch('/api/preview/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const startResult = await startResponse.json();
        
        if (!startResponse.ok) {
            throw new Error(startResult.detail || 'Failed to start preview');
        }
        
        const jobId = startResult.job_id;
        currentJobId = jobId;
        
        startProgressAnimation();
        
        let complete = false;
        while (!complete) {
            await new Promise(r => setTimeout(r, 250));
            
            const progressResponse = await fetch(`/api/progress/${jobId}`);
            const progress = await progressResponse.json();
            
            if (progress.status === 'cancelled') {
                return;
            }
            
            setTargetProgress(progress.percent, progress.message);
            
            if (progress.status === 'complete') {
                complete = true;
                // Keep currentJobId for radius polling!
                
                // Store variants
                if (progress.variants) {
                    variants = progress.variants;
                }
                
                const previewUrl = progress.preview_url;
                
                currentPreview = {
                    id: jobId,
                    previewUrl: previewUrl,
                    variants: progress.variants,
                    settings: progress.settings || settings,
                    timestamp: Date.now()
                };
                
                previews.push(currentPreview);
                currentPreviewIndex = previews.length - 1;
                
                setTargetProgress(100, 'Done!');
                await new Promise(r => setTimeout(r, 300));
                
                hideLoading();
                showPreview(currentPreview);
                goToStep2();
                
                // Start polling for radius availability (progressive loading)
                startRadiusPolling(jobId);
                
            } else if (progress.status === 'error') {
                throw new Error(progress.error || 'Preview generation failed');
            }
        }
        
    } catch (error) {
        console.error('Preview error:', error);
        showToast(error.message || 'An unexpected error occurred');
        hideLoading();
    } finally {
        generateBtn.classList.remove('loading');
        generateBtn.disabled = false;
    }
}

function resetRadiusSelectorUI() {
    const selector = document.getElementById('radiusSelector');
    if (!selector) return;
    
    selector.querySelectorAll('.radius-option').forEach((opt) => {
        const radius = parseInt(opt.dataset.value, 10);
        opt.classList.remove('selected', 'loading', 'locked');
        
        const statusEl = opt.querySelector('.radius-option-status');
        
        if (radius === 10000) {
            // 10km is default, loading first
            opt.classList.add('selected');
            opt.dataset.status = 'loading';
            if (statusEl) statusEl.textContent = 'Loading...';
        } else if (radius === 5000) {
            // 5km loads in background
            opt.dataset.status = 'pending';
            if (statusEl) statusEl.textContent = 'Loading...';
        } else {
            // 15km and 20km are locked
            opt.classList.add('locked');
            opt.dataset.status = 'locked';
            if (statusEl) statusEl.textContent = 'Sign up';
        }
    });
}

function showPreview(preview) {
    const settings = preview.settings;
    const themeName = themes.find(t => t.name === settings.theme)?.display_name || settings.theme;
    const sizeLabel = `${Math.round(settings.width * 2.54)}×${Math.round(settings.height * 2.54)}cm`;
    
    previewCity.textContent = `${settings.city}, ${settings.country}`;
    previewMeta.textContent = `${themeName} • ${selectedDistance / 1000}km • ${sizeLabel}`;
    
    // Set preview image
    const previewImage = document.getElementById('previewImage');
    if (previewImage) {
        previewImage.src = preview.previewUrl + '?t=' + Date.now();
    }
    
    // Update variants from preview
    if (preview.variants) {
        variants = { ...variants, ...preview.variants };
    }
    
    // Render theme switcher in sidebar
    renderThemeSwitcher();
    
    renderPreviewsGrid();
}

function renderPreviewsGrid() {
    const grid = document.querySelector('.previews-mini-grid');
    if (!grid || previews.length <= 1) {
        const container = document.querySelector('.previous-previews');
        if (container) container.style.display = 'none';
        return;
    }
    
    const container = document.querySelector('.previous-previews');
    if (container) container.style.display = 'block';
    
    grid.innerHTML = previews.map((p, i) => `
        <div class="mini-preview ${i === currentPreviewIndex ? 'active' : ''}" data-index="${i}">
            <img src="${p.previewUrl}" alt="Preview ${i + 1}">
            <span class="mini-preview-label">v${i + 1}</span>
        </div>
    `).join('');
    
    grid.querySelectorAll('.mini-preview').forEach(el => {
        el.addEventListener('click', () => {
            const idx = parseInt(el.dataset.index);
            currentPreviewIndex = idx;
            currentPreview = previews[idx];
            showPreview(currentPreview);
            
            // Restart variant polling for this preview
            if (currentPreview.id) {
                startVariantPolling(currentPreview.id);
            }
        });
    });
}

// ============================================
// Radius Polling (Progressive Loading)
// ============================================

function startRadiusPolling(jobId) {
    stopRadiusPolling();
    
    // Mark 10km as ready immediately (it was just completed)
    updateRadiusSelectorUI({ 
        '10000': { status: 'ready' },
        '5000': { status: 'loading' },
        '15000': { status: 'locked' },
        '20000': { status: 'locked' }
    });
    
    radiusPollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/radiuses/${jobId}`);
            const data = await response.json();
            
            if (data.radiuses) {
                updateRadiusSelectorUI(data.radiuses);
                
                // Check if all available radiuses are ready (5km and 10km)
                const availableReady = 
                    data.radiuses['5000']?.status === 'ready' && 
                    data.radiuses['10000']?.status === 'ready';
                
                if (availableReady) {
                    showToast('All map sizes ready!', 'success');
                    stopRadiusPolling();
                }
            }
        } catch (error) {
            console.error('Radius polling error:', error);
        }
    }, 2000);
}

function stopRadiusPolling() {
    if (radiusPollingInterval) {
        clearInterval(radiusPollingInterval);
        radiusPollingInterval = null;
    }
}

// ============================================
// Variant Polling (kept for water/parks toggle)
// ============================================

function startVariantPolling(jobId) {
    stopVariantPolling();
    
    variantPollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/variants/${jobId}`);
            const data = await response.json();
            
            if (data.variants) {
                let updated = false;
                
                // Update variants that weren't previously available
                for (const key of Object.keys(data.variants)) {
                    if (data.variants[key] && !variants[key]) {
                        variants[key] = data.variants[key];
                        updated = true;
                    }
                }
                
                if (updated) {
                    updateVariantStatus();
                    
                    // Check if all variants are ready
                    const allReady = variants.drive_with_wp && variants.drive_no_wp && 
                                     variants.all_with_wp && variants.all_no_wp;
                    
                    if (allReady) {
                        showToast('All variants ready! Toggle instantly.', 'success');
                        stopVariantPolling();
                    }
                }
            }
        } catch (error) {
            console.error('Variant polling error:', error);
        }
    }, 2000);
}

function stopVariantPolling() {
    if (variantPollingInterval) {
        clearInterval(variantPollingInterval);
        variantPollingInterval = null;
    }
}

// ============================================
// Progress Animation
// ============================================

let progressAnimationFrame = null;
let currentProgress = 0;
let targetProgress = 0;
let currentMessage = 'Starting...';
let lastUpdateTime = Date.now();

function startProgressAnimation() {
    currentProgress = 0;
    targetProgress = 0;
    lastUpdateTime = Date.now();
    animateProgress();
}

function setTargetProgress(percent, message) {
    if (percent > targetProgress) {
        targetProgress = percent;
        lastUpdateTime = Date.now();
    }
    if (message) currentMessage = message;
}

function animateProgress() {
    const now = Date.now();
    const timeSinceUpdate = now - lastUpdateTime;
    const creepAmount = Math.min(0.5, timeSinceUpdate / 1000 * 0.3);
    
    if (currentProgress < targetProgress) {
        const diff = targetProgress - currentProgress;
        const speed = Math.max(0.5, diff * 0.15);
        currentProgress = Math.min(targetProgress, currentProgress + speed);
    } else if (currentProgress < 95 && targetProgress < 100) {
        currentProgress = Math.min(currentProgress + creepAmount * 0.1, targetProgress + 10);
    }
    
    currentProgress = Math.min(99, Math.max(0, currentProgress));
    
    renderProgress(currentProgress, currentMessage);
    
    if (currentProgress < 99 || targetProgress < 100) {
        progressAnimationFrame = requestAnimationFrame(animateProgress);
    }
}

function showLoading() {
    loadingOverlay.classList.add('active');
    currentProgress = 0;
    targetProgress = 0;
    currentLoadingStage = 'location';
    renderProgress(0, 'Starting...');
    updateFunMessage('location');
    startFunMessageRotation();
    startShowcaseRotation();
}

function hideLoading() {
    loadingOverlay.classList.remove('active');
    stopFunMessageRotation();
    stopShowcaseRotation();
    if (progressAnimationFrame) {
        cancelAnimationFrame(progressAnimationFrame);
        progressAnimationFrame = null;
    }
}

// Preview loading overlay (for theme/feature changes)
function showPreviewLoading(text = 'Applying changes...') {
    const overlay = document.getElementById('previewLoadingOverlay');
    const textEl = document.getElementById('previewLoadingText');
    const previewImage = document.getElementById('previewImage');
    
    if (overlay) overlay.classList.add('active');
    if (textEl) textEl.textContent = text;
    if (previewImage) previewImage.classList.add('loading');
}

function hidePreviewLoading() {
    const overlay = document.getElementById('previewLoadingOverlay');
    const previewImage = document.getElementById('previewImage');
    
    if (overlay) overlay.classList.remove('active');
    if (previewImage) previewImage.classList.remove('loading');
}

let currentLoadingStage = 'location';
let funMessageInterval = null;

function renderProgress(percent, message) {
    const circumference = 2 * Math.PI * 45;
    const offset = circumference - (percent / 100) * circumference;
    
    if (progressRing) progressRing.style.strokeDashoffset = offset;
    if (progressPercent) progressPercent.textContent = `${Math.round(percent)}%`;
    if (progressStatus) progressStatus.textContent = message || 'Processing...';
    
    // Determine stage based on message
    let stage = 'render';
    if (message?.toLowerCase().includes('location') || message?.toLowerCase().includes('finding')) {
        stage = 'location';
    } else if (message?.toLowerCase().includes('street') || message?.toLowerCase().includes('road')) {
        stage = 'streets';
    } else if (message?.toLowerCase().includes('water')) {
        stage = 'water';
    } else if (message?.toLowerCase().includes('park')) {
        stage = 'parks';
    } else if (message?.toLowerCase().includes('compos') || message?.toLowerCase().includes('render')) {
        stage = 'render';
    }
    
    // Update fun message when stage changes
    if (stage !== currentLoadingStage) {
        currentLoadingStage = stage;
        updateFunMessage(stage);
    }
}

function updateFunMessage(stage) {
    const funEl = document.getElementById('progressFun');
    if (funEl) {
        funEl.style.opacity = '0';
        setTimeout(() => {
            funEl.textContent = getRandomMessage(stage);
            funEl.style.opacity = '1';
        }, 200);
    }
}


function startFunMessageRotation() {
    // Rotate fun messages every 3 seconds
    funMessageInterval = setInterval(() => {
        updateFunMessage(currentLoadingStage);
    }, 3500);
}

function stopFunMessageRotation() {
    if (funMessageInterval) {
        clearInterval(funMessageInterval);
        funMessageInterval = null;
    }
}

// ============================================
// Final Generation
// ============================================

async function handleGenerateFinal() {
    if (!currentPreview) return;
    
    const settings = currentPreview.settings;
    
    // Use the current feature state from toggles
    const finalSettings = {
        ...settings,
        distance: selectedDistance,  // Use current radius selection
        features: {
            water: featureState.water,
            parks: featureState.parks,
            roads_drive: featureState.roads_drive,
            roads_paths: featureState.roads_paths,
            roads_cycling: featureState.roads_cycling
        }
    };
    
    console.log('Generating final with settings:', finalSettings);
    console.log('Feature state:', featureState);
    
    showFinalProgress(finalSettings);
    
    try {
        const startResponse = await fetch('/api/generate/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(finalSettings)
        });
        
        const startResult = await startResponse.json();
        
        if (!startResponse.ok) {
            throw new Error(startResult.detail || 'Failed to start generation');
        }
        
        const jobId = startResult.job_id;
        
        let complete = false;
        while (!complete) {
            await new Promise(r => setTimeout(r, 300));
            
            const progressResponse = await fetch(`/api/progress/${jobId}`);
            const progress = await progressResponse.json();
            
            updateFinalProgress(progress.step, progress.total || 4, progress.message);
            
            if (progress.status === 'complete') {
                complete = true;
                completeFinalProgress();
                await new Promise(r => setTimeout(r, 500));
                closeFinalProgress();
                showResult({
                    poster_url: progress.poster_url,
                    filename: progress.filename || `poster_${jobId}.png`
                }, finalSettings);
                updateStepIndicators(3);
                showToast('High-resolution poster ready!', 'success');
                
            } else if (progress.status === 'error') {
                throw new Error(progress.error || 'Generation failed');
            }
        }
        
    } catch (error) {
        console.error('Generation error:', error);
        closeFinalProgress();
        showToast(error.message || 'Generation failed', 'error');
    }
}

// ============================================
// Final Progress Modal
// ============================================

function showFinalProgress(settings) {
    finalProgressCity.textContent = `${settings.city}, ${settings.country}`;
    
    const metaEl = document.getElementById('finalProgressMeta');
    if (metaEl) {
        const themeName = themes.find(t => t.name === settings.theme)?.display_name || settings.theme;
        const sizeLabel = `${Math.round(settings.width * 2.54)}×${Math.round(settings.height * 2.54)}cm`;
        metaEl.textContent = `${themeName} • ${settings.distance / 1000}km • ${sizeLabel}`;
    }
    
    // Show the current preview image
    const previewImg = document.getElementById('finalProgressPreview');
    if (previewImg && currentPreview?.previewUrl) {
        // Use the current preview image from the preview panel
        const currentPreviewImg = document.getElementById('previewImage');
        if (currentPreviewImg?.src) {
            previewImg.src = currentPreviewImg.src;
        } else {
            previewImg.src = currentPreview.previewUrl + '?t=' + Date.now();
        }
    }
    
    finalProgressBar.style.width = '0%';
    
    document.querySelectorAll('#progressModal .progress-step').forEach(step => {
        step.classList.remove('active', 'complete');
        step.querySelector('.step-status').textContent = 'Pending';
    });
    
    progressModal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeFinalProgress() {
    progressModal.classList.remove('active');
    document.body.style.overflow = '';
}

function updateFinalProgress(stepNum, totalSteps, message) {
    const steps = document.querySelectorAll('#progressModal .progress-step');
    const progress = (stepNum / totalSteps) * 100;
    finalProgressBar.style.width = `${progress}%`;
    
    steps.forEach((step, index) => {
        const stepValue = index + 1;
        if (stepValue < stepNum) {
            step.classList.remove('active');
            step.classList.add('complete');
            step.querySelector('.step-status').textContent = 'Done';
        } else if (stepValue === stepNum) {
            step.classList.add('active');
            step.classList.remove('complete');
            step.querySelector('.step-status').textContent = message || 'In progress...';
        } else {
            step.classList.remove('active', 'complete');
            step.querySelector('.step-status').textContent = 'Pending';
        }
    });
}

function completeFinalProgress() {
    document.querySelectorAll('#progressModal .progress-step').forEach(step => {
        step.classList.remove('active');
        step.classList.add('complete');
        step.querySelector('.step-status').textContent = 'Done';
    });
    finalProgressBar.style.width = '100%';
}

// ============================================
// Result Modal
// ============================================

function showResult(result, settings) {
    const themeName = themes.find(t => t.name === settings.theme)?.display_name || settings.theme;
    const sizeLabel = `${Math.round(settings.width * 2.54)}×${Math.round(settings.height * 2.54)}cm`;
    
    resultImage.src = result.poster_url + '?t=' + Date.now();
    resultCity.textContent = settings.city;
    resultTheme.textContent = `${themeName} • ${sizeLabel}`;
    downloadBtn.href = result.poster_url;
    downloadBtn.download = result.filename;
    
    resultModal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeResultModal() {
    resultModal.classList.remove('active');
    document.body.style.overflow = '';
}

// ============================================
// Preview Zoom Modal
// ============================================

let currentZoom = 1;

function openZoomModal() {
    const zoomModal = document.getElementById('zoomModal');
    const zoomImage = document.getElementById('zoomImage');
    const previewImage = document.getElementById('previewImage');
    
    if (!zoomModal || !zoomImage || !previewImage?.src) return;
    
    currentZoom = 1;
    zoomImage.src = previewImage.src;
    zoomImage.style.transform = `scale(${currentZoom})`;
    
    zoomModal.classList.add('active');
    document.body.style.overflow = 'hidden';
    
    document.getElementById('zoomIn').onclick = () => {
        currentZoom = Math.min(3, currentZoom * 1.3);
        zoomImage.style.transform = `scale(${currentZoom})`;
    };
    
    document.getElementById('zoomOut').onclick = () => {
        currentZoom = Math.max(0.5, currentZoom / 1.3);
        zoomImage.style.transform = `scale(${currentZoom})`;
    };
    
    document.onkeydown = (e) => {
        if (!zoomModal.classList.contains('active')) return;
        if (e.key === 'Escape') closeZoomModal();
    };
}

function closeZoomModal() {
    const zoomModal = document.getElementById('zoomModal');
    if (zoomModal) zoomModal.classList.remove('active');
    document.body.style.overflow = '';
    document.onkeydown = null;
}
