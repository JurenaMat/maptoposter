/**
 * MapToPoster Generate Page
 * MVP v1.0 - 2026-02-01
 * 
 * Clean flow: Configure → Preview → Download
 * 
 * Features:
 * - Visual theme gallery
 * - City autocomplete
 * - Progress ring animation
 * - Multi-preview comparison (up to 3)
 * - High-res generation with step progress
 */

// State
let selectedCity = null;
let selectedCountry = null;
let selectedTheme = 'noir';
let selectedDistance = 5000; // Track distance in state
let selectedSize = '50x70';  // Track size in state
let debounceTimer = null;
let themes = [];
let previews = []; // Store generated previews
let currentPreviewIndex = 0;
const MAX_PREVIEWS = 3;

// DOM Elements
const cityInput = document.getElementById('cityInput');
const autocompleteDropdown = document.getElementById('autocompleteDropdown');
const themeGallery = document.getElementById('themeGallery');
const generateBtn = document.getElementById('generateBtn');
const progressText = document.getElementById('progressText');

const step1 = document.getElementById('step1');
const step2 = document.getElementById('step2');
const loadingOverlay = document.getElementById('loadingOverlay');
const progressRing = document.getElementById('progressRing');
const progressPercent = document.getElementById('progressPercent');
const progressStatus = document.getElementById('progressStatus');

const previewImage = document.getElementById('previewImage');
const previewCity = document.getElementById('previewCity');
const previewMeta = document.getElementById('previewMeta');
const generateFinalBtn = document.getElementById('generateFinalBtn');
const editConfigBtn = document.getElementById('editConfigBtn');
const previousPreviews = document.getElementById('previousPreviews');
const previewsMiniGrid = document.getElementById('previewsMiniGrid');

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
    // Remove any existing toast
    const existingToast = document.querySelector('.toast-notification');
    if (existingToast) {
        existingToast.remove();
    }
    
    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    toast.innerHTML = `
        <div class="toast-content">
            <div class="toast-icon">
                ${type === 'error' ? `
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M12 8v4M12 16h.01"/>
                    </svg>
                ` : `
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                        <polyline points="22 4 12 14.01 9 11.01"/>
                    </svg>
                `}
            </div>
            <div class="toast-message">${message}</div>
            <button class="toast-close" onclick="this.parentElement.parentElement.remove()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
            </button>
        </div>
    `;
    
    document.body.appendChild(toast);
    
    // Animate in
    requestAnimationFrame(() => {
        toast.classList.add('active');
    });
    
    // Auto-remove after 6 seconds
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
    
    // Check URL params
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
                        <path d="M30 10 L35 70" stroke="${theme.text}" stroke-width="1.5" fill="none" opacity="0.4"/>
                        <path d="M70 5 L65 75" stroke="${theme.text}" stroke-width="1.5" fill="none" opacity="0.4"/>
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
    
    // Add click handlers
    themeGallery.querySelectorAll('.theme-card').forEach(card => {
        card.addEventListener('click', () => {
            themeGallery.querySelectorAll('.theme-card').forEach(c => c.classList.remove('selected'));
            card.classList.add('selected');
            selectedTheme = card.dataset.theme;
            console.log('Theme selected:', selectedTheme);
        });
    });
}

// Setup radius gallery click handlers
function setupRadiusGallery() {
    const radiusGallery = document.getElementById('radiusGallery');
    if (!radiusGallery) return;
    
    // Use event delegation for more reliable handling
    radiusGallery.addEventListener('click', (e) => {
        const option = e.target.closest('.radius-image-option');
        if (!option) return;
        
        // Update visual selection
        radiusGallery.querySelectorAll('.radius-image-option').forEach(o => o.classList.remove('selected'));
        option.classList.add('selected');
        
        // Update state
        selectedDistance = parseInt(option.dataset.value);
        console.log('Distance selected:', selectedDistance);
    });
    
    // Set initial value from currently selected option
    const selectedOption = radiusGallery.querySelector('.radius-image-option.selected');
    if (selectedOption) {
        selectedDistance = parseInt(selectedOption.dataset.value);
    }
}

// Get current distance from DOM (fallback)
function getCurrentDistance() {
    const radiusGallery = document.getElementById('radiusGallery');
    if (!radiusGallery) return selectedDistance;
    
    const selected = radiusGallery.querySelector('.radius-image-option.selected');
    if (selected) {
        return parseInt(selected.dataset.value);
    }
    return selectedDistance;
}

// Setup size gallery click handlers
function setupSizeGallery() {
    const sizeGallery = document.getElementById('sizeGallery');
    if (!sizeGallery) return;
    
    // Use event delegation for more reliable handling
    sizeGallery.addEventListener('click', (e) => {
        const option = e.target.closest('.size-option');
        if (!option) return;
        
        // Update visual selection
        sizeGallery.querySelectorAll('.size-option').forEach(o => o.classList.remove('selected'));
        option.classList.add('selected');
        
        // Update state
        selectedSize = option.dataset.value;
        console.log('Size selected:', selectedSize);
    });
    
    // Set initial value from currently selected option
    const selectedOption = sizeGallery.querySelector('.size-option.selected');
    if (selectedOption) {
        selectedSize = selectedOption.dataset.value;
    }
}

// Get current size from DOM (fallback)
function getCurrentSize() {
    const sizeGallery = document.getElementById('sizeGallery');
    if (!sizeGallery) return selectedSize;
    
    const selected = sizeGallery.querySelector('.size-option.selected');
    if (selected) {
        return selected.dataset.value;
    }
    return selectedSize;
}

// Convert cm to inches for backend
function cmToInches(cm) {
    return cm / 2.54;
}

function setupEventListeners() {
    // City autocomplete
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
    
    // Generate button
    generateBtn.addEventListener('click', handleGenerate);
    
    // Preview actions
    generateFinalBtn.addEventListener('click', handleGenerateFinal);
    editConfigBtn.addEventListener('click', goToStep1);
    
    // Result modal
    resultModalClose.addEventListener('click', closeResultModal);
    document.querySelector('#resultModal .modal-backdrop')?.addEventListener('click', closeResultModal);
    createAnother.addEventListener('click', () => {
        closeResultModal();
        resetAll();
    });
    
    // Preview zoom
    const previewWrapper = document.getElementById('previewWrapper');
    if (previewWrapper) {
        previewWrapper.addEventListener('click', openZoomModal);
    }
    
    // Zoom modal
    const zoomModalClose = document.getElementById('zoomModalClose');
    const zoomModal = document.getElementById('zoomModal');
    if (zoomModalClose) {
        zoomModalClose.addEventListener('click', closeZoomModal);
    }
    if (zoomModal) {
        zoomModal.querySelector('.modal-backdrop')?.addEventListener('click', closeZoomModal);
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
        if (step < activeStep) {
            indicator.classList.add('complete');
        } else if (step === activeStep) {
            indicator.classList.add('active');
        }
    });
}

function resetAll() {
    cityInput.value = '';
    selectedCity = null;
    selectedCountry = null;
    selectedTheme = 'noir';
    selectedDistance = 5000;
    selectedSize = '50x70';
    previews = [];
    currentPreviewIndex = 0;
    renderThemeGallery();
    goToStep1();
}

// ============================================
// Preview Generation
// ============================================

async function handleGenerate() {
    // Validate city
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
    
    // Check limit
    if (previews.length >= MAX_PREVIEWS) {
        showToast(`Maximum ${MAX_PREVIEWS} previews reached. Remove one to generate a new one.`);
        return;
    }
    
    // Get settings - read from DOM to ensure latest values
    const currentDistance = getCurrentDistance();
    const currentSize = getCurrentSize();
    const [widthCm, heightCm] = currentSize.split('x').map(Number);
    const width = cmToInches(widthCm);
    const height = cmToInches(heightCm);
    
    // Get currently selected theme from DOM
    const selectedThemeCard = themeGallery.querySelector('.theme-card.selected');
    const currentTheme = selectedThemeCard ? selectedThemeCard.dataset.theme : selectedTheme;
    
    const settings = {
        city: selectedCity,
        country: selectedCountry,
        theme: currentTheme,
        distance: currentDistance,
        width: width,
        height: height
    };
    
    console.log('Generating with settings:', settings);
    console.log('Distance from DOM:', currentDistance, 'Size from DOM:', currentSize, 'Theme:', currentTheme);
    
    // Show loading
    showLoading();
    generateBtn.classList.add('loading');
    generateBtn.disabled = true;
    updateProgress(0, 6, 'Starting...');
    
    try {
        // Start the job
        const startResponse = await fetch('/api/preview/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const startResult = await startResponse.json();
        
        if (!startResponse.ok) {
            const errorDetail = startResult.detail;
            let errorMsg;
            if (Array.isArray(errorDetail)) {
                errorMsg = errorDetail.map(e => e.msg || e.message || JSON.stringify(e)).join(', ');
            } else if (typeof errorDetail === 'object') {
                errorMsg = errorDetail.msg || errorDetail.message || JSON.stringify(errorDetail);
            } else {
                errorMsg = errorDetail || 'Failed to start preview';
            }
            throw new Error(errorMsg);
        }
        
        const jobId = startResult.job_id;
        
        // Poll for progress
        let complete = false;
        while (!complete) {
            await new Promise(r => setTimeout(r, 200));
            
            const progressResponse = await fetch(`/api/progress/${jobId}`);
            const progress = await progressResponse.json();
            
            updateProgress(progress.step, progress.total, progress.message, progress.percent);
            
            if (progress.status === 'complete') {
                complete = true;
                
                // Add to previews
                const preview = {
                    id: jobId,
                    url: progress.preview_url,
                    settings: settings,
                    timestamp: Date.now()
                };
                previews.push(preview);
                currentPreviewIndex = previews.length - 1;
                
                // Show preview
                hideLoading();
                showPreview(preview);
                goToStep2();
                
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

// Progress animation
let progressInterval = null;
let displayPercent = 0;
let targetPercent = 0;
let currentStep = 0;
let currentMessage = 'Starting...';
let isCatchingUp = false; // True when transitioning between steps

// Step config: min% where step starts, max% it can reach
const STEP_CONFIG = {
    1: { min: 0, max: 7 },     // Location
    2: { min: 8, max: 51 },    // Streets (longest)
    3: { min: 52, max: 71 },   // Water
    4: { min: 72, max: 87 },   // Parks
    5: { min: 88, max: 95 },   // Render
    6: { min: 96, max: 99 }    // Save
};

function showLoading() {
    loadingOverlay.classList.add('active');
    displayPercent = 0;
    targetPercent = 0;
    currentStep = 0;
    isCatchingUp = false;
    renderProgress(0, 'Starting...');
    
    if (progressInterval) clearInterval(progressInterval);
    progressInterval = setInterval(tickProgress, 80);
}

function hideLoading() {
    loadingOverlay.classList.remove('active');
    if (progressInterval) {
        clearInterval(progressInterval);
        progressInterval = null;
    }
}

function tickProgress() {
    if (displayPercent >= 100) return;
    
    if (isCatchingUp) {
        // Fast mode: catching up to new step's minimum
        const config = STEP_CONFIG[currentStep] || { min: 0, max: 100 };
        if (displayPercent < config.min) {
            // Move fast: 3-5% per tick
            displayPercent = Math.min(config.min, displayPercent + 4);
        } else {
            // Caught up, switch to slow mode
            isCatchingUp = false;
        }
    } else {
        // Slow mode: creeping within current step
        const config = STEP_CONFIG[currentStep] || { min: 0, max: 100 };
        if (displayPercent < config.max) {
            // Move slow: 0.3% per tick (~4% per second)
            displayPercent = Math.min(config.max, displayPercent + 0.3);
        }
        // If at max, just wait for next step
    }
    
    renderProgress(displayPercent, currentMessage);
}

function updateProgress(step, total, message, percent = null) {
    currentMessage = message;
    
    // Complete - jump to 100%
    if (percent === 100) {
        displayPercent = 100;
        targetPercent = 100;
        renderProgress(100, message);
        return;
    }
    
    // Step changed - trigger catch-up mode
    if (step !== currentStep) {
        currentStep = step;
        const config = STEP_CONFIG[step] || { min: 0, max: 100 };
        
        if (displayPercent < config.min) {
            // Behind the new step's start - catch up fast
            isCatchingUp = true;
        }
        // Target is this step's max
        targetPercent = config.max;
    }
}

function renderProgress(percent, message) {
    const circumference = 2 * Math.PI * 45;
    const offset = circumference - (percent / 100) * circumference;
    
    progressRing.style.strokeDashoffset = offset;
    progressPercent.textContent = `${Math.round(percent)}%`;
    if (progressText) progressText.textContent = `${Math.round(percent)}%`;
    progressStatus.textContent = message || `Processing...`;
}

// ============================================
// Preview Display
// ============================================

function showPreview(preview) {
    const settings = preview.settings;
    const themeName = themes.find(t => t.name === settings.theme)?.display_name || settings.theme;
    const sizeLabel = `${Math.round(settings.width * 2.54)}×${Math.round(settings.height * 2.54)}cm`;
    
    previewImage.src = preview.url + '?t=' + preview.timestamp;
    previewCity.textContent = `${settings.city}, ${settings.country}`;
    previewMeta.textContent = `${themeName} • ${settings.distance / 1000}km • ${sizeLabel}`;
    
    renderMiniPreviews();
}

function renderMiniPreviews() {
    if (previews.length <= 1) {
        previousPreviews.style.display = 'none';
        return;
    }
    
    previousPreviews.style.display = 'block';
    
    previewsMiniGrid.innerHTML = previews.map((p, index) => `
        <div class="mini-preview ${index === currentPreviewIndex ? 'active' : ''}" data-index="${index}">
            <img src="${p.url}?t=${p.timestamp}" alt="Preview ${index + 1}">
            <div class="mini-preview-remove" onclick="event.stopPropagation(); removePreview(${index})">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
            </div>
        </div>
    `).join('');
    
    // Click to switch
    previewsMiniGrid.querySelectorAll('.mini-preview').forEach((el, index) => {
        el.addEventListener('click', () => {
            currentPreviewIndex = index;
            showPreview(previews[index]);
        });
    });
}

function removePreview(index) {
    previews.splice(index, 1);
    
    if (previews.length === 0) {
        goToStep1();
        return;
    }
    
    if (currentPreviewIndex >= previews.length) {
        currentPreviewIndex = previews.length - 1;
    }
    
    showPreview(previews[currentPreviewIndex]);
}

// Make globally available
window.removePreview = removePreview;

// ============================================
// Final Generation
// ============================================

async function handleGenerateFinal() {
    const preview = previews[currentPreviewIndex];
    if (!preview) return;
    
    const settings = preview.settings;
    
    showFinalProgress(settings, preview.url);
    
    try {
        // Start the async job
        const startResponse = await fetch('/api/generate/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const responseText = await startResponse.text();
        let startResult;
        try {
            startResult = JSON.parse(responseText);
        } catch (e) {
            // Response wasn't JSON - likely an internal server error
            throw new Error(`Server error: ${responseText.substring(0, 100)}`);
        }
        
        if (!startResponse.ok) {
            throw new Error(startResult.detail || 'Failed to start generation');
        }
        
        const jobId = startResult.job_id;
        
        // Poll for progress (same as preview)
        let complete = false;
        while (!complete) {
            await new Promise(r => setTimeout(r, 300));
            
            const progressResponse = await fetch(`/api/progress/${jobId}`);
            const progress = await progressResponse.json();
            
            // Update the step progress UI
            updateFinalProgress(progress.step, progress.total || 6, progress.message);
            
            if (progress.status === 'complete') {
                complete = true;
                
                completeFinalProgress();
                await new Promise(r => setTimeout(r, 500));
                
                closeFinalProgress();
                showResult({
                    poster_url: progress.poster_url,
                    filename: progress.filename || `poster_${jobId}.png`
                }, settings);
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

let finalProgressInterval = null;

function showFinalProgress(settings, previewUrl) {
    // Set preview image
    const previewImg = document.getElementById('finalProgressPreview');
    if (previewImg && previewUrl) {
        previewImg.src = previewUrl;
    }
    
    // Set location and meta info
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
    if (finalProgressInterval) {
        clearTimeout(finalProgressInterval);
        finalProgressInterval = null;
    }
}

function updateFinalProgress(stepNum, totalSteps, message) {
    const steps = document.querySelectorAll('#progressModal .progress-step');
    
    // Update progress bar
    const progress = (stepNum / totalSteps) * 100;
    finalProgressBar.style.width = `${progress}%`;
    
    // Update step indicators
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
    if (finalProgressInterval) {
        clearTimeout(finalProgressInterval);
        finalProgressInterval = null;
    }
    
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
    
    if (!zoomModal || !zoomImage || !previewImage.src) return;
    
    // Reset zoom
    currentZoom = 1;
    zoomImage.src = previewImage.src;
    zoomImage.style.transform = `scale(${currentZoom})`;
    
    zoomModal.classList.add('active');
    document.body.style.overflow = 'hidden';
    
    // Setup button handlers
    document.getElementById('zoomIn').onclick = () => {
        currentZoom = Math.min(3, currentZoom * 1.3);
        zoomImage.style.transform = `scale(${currentZoom})`;
    };
    
    document.getElementById('zoomOut').onclick = () => {
        currentZoom = Math.max(0.5, currentZoom / 1.3);
        zoomImage.style.transform = `scale(${currentZoom})`;
    };
    
    // Keyboard shortcuts
    document.onkeydown = (e) => {
        if (!zoomModal.classList.contains('active')) return;
        if (e.key === 'Escape') {
            closeZoomModal();
        }
    };
}

function closeZoomModal() {
    const zoomModal = document.getElementById('zoomModal');
    
    if (zoomModal) {
        zoomModal.classList.remove('active');
    }
    document.body.style.overflow = '';
    document.onkeydown = null;
}
