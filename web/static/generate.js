/**
 * MapToPoster Generate Page
 * MVP v1.6 - 2026-02-02
 * 
 * INSTANT VARIANT SWITCHING
 * - Water & Parks toggle
 * - Simple vs All Streets radio
 * - Variants render in background, switch instantly
 */

// State
let selectedCity = null;
let selectedCountry = null;
let selectedTheme = 'noir';
let selectedDistance = 5000;
let selectedSize = '50x70';
let debounceTimer = null;
let themes = [];

// Preview state
let currentPreview = null;
let previews = [];
let currentPreviewIndex = 0;
let currentJobId = null;
let variantPollingInterval = null;

// Variant state - tracks available variants
let variants = {
    drive_with_wp: null,
    drive_no_wp: null,
    all_with_wp: null,
    all_no_wp: null
};

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
    setupRadiusGallery();
    setupSizeGallery();
    setupVariantToggles();
    
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

// ============================================
// Variant Toggles - Water&Parks + StreetType
// ============================================

function setupVariantToggles() {
    const waterParksToggle = document.getElementById('toggleWaterParks');
    const streetRadios = document.querySelectorAll('input[name="streetType"]');
    
    if (waterParksToggle) {
        waterParksToggle.addEventListener('change', updateCurrentVariant);
    }
    
    streetRadios.forEach(radio => {
        radio.addEventListener('change', updateCurrentVariant);
    });
}

function updateCurrentVariant() {
    const waterParksToggle = document.getElementById('toggleWaterParks');
    const streetType = document.querySelector('input[name="streetType"]:checked')?.value || 'simple';
    
    const withWaterParks = waterParksToggle?.checked ?? true;
    
    // Determine which variant to show
    let variantKey;
    if (streetType === 'simple') {
        variantKey = withWaterParks ? 'drive_with_wp' : 'drive_no_wp';
    } else {
        variantKey = withWaterParks ? 'all_with_wp' : 'all_no_wp';
    }
    
    const variantUrl = variants[variantKey];
    const previewImage = document.getElementById('previewImage');
    
    if (variantUrl && previewImage) {
        previewImage.classList.add('loading');
        previewImage.src = variantUrl + '?t=' + Date.now();
        previewImage.onload = () => previewImage.classList.remove('loading');
    } else if (!variantUrl && previewImage) {
        // Variant not ready yet, show message
        const statusEl = document.getElementById('allStreetsStatus');
        if (streetType === 'all' && statusEl) {
            statusEl.textContent = 'Loading...';
        }
    }
}

function updateVariantStatus() {
    const allStreetsStatus = document.getElementById('allStreetsStatus');
    const allStreetsRadio = document.querySelector('input[name="streetType"][value="all"]');
    
    const allReady = variants.all_with_wp && variants.all_no_wp;
    
    if (allStreetsStatus) {
        allStreetsStatus.textContent = allReady ? 'Paths & cycleways' : 'Loading...';
    }
    
    if (allStreetsRadio) {
        allStreetsRadio.disabled = !allReady;
    }
}

// ============================================
// Radius & Size Galleries
// ============================================

function setupRadiusGallery() {
    const radiusGallery = document.getElementById('radiusGallery');
    if (!radiusGallery) return;
    
    radiusGallery.addEventListener('click', (e) => {
        const option = e.target.closest('.radius-image-option');
        if (!option) return;
        
        radiusGallery.querySelectorAll('.radius-image-option').forEach(o => o.classList.remove('selected'));
        option.classList.add('selected');
        selectedDistance = parseInt(option.dataset.value, 10);
    });
    
    const defaultOption = radiusGallery.querySelector('[data-value="5000"]');
    if (defaultOption) defaultOption.classList.add('selected');
}

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
    
    const defaultOption = sizeGallery.querySelector('[data-value="50x70"]');
    if (defaultOption) defaultOption.classList.add('selected');
}

function getCurrentDistance() {
    const selected = document.querySelector('#radiusGallery .radius-image-option.selected');
    return selected ? parseInt(selected.dataset.value, 10) : selectedDistance;
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
    selectedDistance = 5000;
    selectedSize = '50x70';
    currentPreview = null;
    previews = [];
    currentPreviewIndex = 0;
    variants = { drive_with_wp: null, drive_no_wp: null, all_with_wp: null, all_no_wp: null };
    stopVariantPolling();
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
    
    const currentDistance = getCurrentDistance();
    const currentSize = getCurrentSize();
    const [widthCm, heightCm] = currentSize.split('x').map(Number);
    const width = cmToInches(widthCm);
    const height = cmToInches(heightCm);
    
    const selectedThemeCard = themeGallery.querySelector('.theme-card.selected');
    const currentTheme = selectedThemeCard ? selectedThemeCard.dataset.theme : selectedTheme;
    
    const settings = {
        city: selectedCity,
        country: selectedCountry,
        theme: currentTheme,
        distance: currentDistance,
        width: width,
        height: height,
        features: { water: true, parks: true, paths: false }
    };
    
    console.log('Generating with settings:', settings);
    
    // Reset variants
    variants = { drive_with_wp: null, drive_no_wp: null, all_with_wp: null, all_no_wp: null };
    updateVariantStatus();
    
    // Reset toggles
    const waterParksToggle = document.getElementById('toggleWaterParks');
    const simpleRadio = document.querySelector('input[name="streetType"][value="simple"]');
    if (waterParksToggle) waterParksToggle.checked = true;
    if (simpleRadio) simpleRadio.checked = true;
    
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
                currentJobId = null;
                
                // Store variants
                if (progress.variants) {
                    variants = progress.variants;
                }
                
                // Main preview URL is drive_with_wp
                const previewUrl = progress.preview_url || variants.drive_with_wp;
                
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
                
                // Start polling for variant availability
                startVariantPolling(jobId);
                
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

function showPreview(preview) {
    const settings = preview.settings;
    const themeName = themes.find(t => t.name === settings.theme)?.display_name || settings.theme;
    const sizeLabel = `${Math.round(settings.width * 2.54)}×${Math.round(settings.height * 2.54)}cm`;
    
    previewCity.textContent = `${settings.city}, ${settings.country}`;
    previewMeta.textContent = `${themeName} • ${settings.distance / 1000}km • ${sizeLabel}`;
    
    // Set preview image
    const previewImage = document.getElementById('previewImage');
    if (previewImage) {
        previewImage.src = preview.previewUrl + '?t=' + Date.now();
    }
    
    // Update variants from preview
    if (preview.variants) {
        variants = { ...variants, ...preview.variants };
    }
    
    updateVariantStatus();
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
// Variant Polling
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
    renderProgress(0, 'Starting...');
}

function hideLoading() {
    loadingOverlay.classList.remove('active');
    if (progressAnimationFrame) {
        cancelAnimationFrame(progressAnimationFrame);
        progressAnimationFrame = null;
    }
}

function renderProgress(percent, message) {
    const circumference = 2 * Math.PI * 45;
    const offset = circumference - (percent / 100) * circumference;
    
    if (progressRing) progressRing.style.strokeDashoffset = offset;
    if (progressPercent) progressPercent.textContent = `${Math.round(percent)}%`;
    if (progressStatus) progressStatus.textContent = message || 'Processing...';
}

// ============================================
// Final Generation
// ============================================

async function handleGenerateFinal() {
    if (!currentPreview) return;
    
    const settings = currentPreview.settings;
    
    // Get toggle states
    const waterParksToggle = document.getElementById('toggleWaterParks');
    const streetType = document.querySelector('input[name="streetType"]:checked')?.value || 'simple';
    
    const withWaterParks = waterParksToggle?.checked ?? true;
    const withPaths = streetType === 'all';
    
    const finalSettings = {
        ...settings,
        features: {
            roads: true,
            water: withWaterParks,
            parks: withWaterParks,
            paths: withPaths
        }
    };
    
    console.log('Generating final with settings:', finalSettings);
    
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
