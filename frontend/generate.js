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
let debounceTimer = null;
let themes = [];
let previews = []; // Store generated previews
let currentPreviewIndex = 0;
const MAX_PREVIEWS = 3;

// DOM Elements
const cityInput = document.getElementById('cityInput');
const autocompleteDropdown = document.getElementById('autocompleteDropdown');
const themeGallery = document.getElementById('themeGallery');
const distanceSelect = document.getElementById('distanceSelect');
const sizeSelect = document.getElementById('sizeSelect');
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
// Initialize
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    loadThemes();
    setupEventListeners();
    setupRadiusGallery();
    
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
        const response = await fetch((window.API_BASE || '') + '/api/themes');
        themes = await response.json();
        renderThemeGallery();
    } catch (error) {
        console.error('Failed to load themes:', error);
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
        });
    });
}

// Setup radius gallery click handlers
function setupRadiusGallery() {
    const radiusGallery = document.getElementById('radiusGallery');
    const distanceInput = document.getElementById('distanceSelect');
    
    if (!radiusGallery) return;
    
    radiusGallery.querySelectorAll('.radius-option').forEach(option => {
        option.addEventListener('click', () => {
            radiusGallery.querySelectorAll('.radius-option').forEach(o => o.classList.remove('selected'));
            option.classList.add('selected');
            distanceInput.value = option.dataset.value;
        });
    });
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
        const response = await fetch((window.API_BASE || '') + `/api/geocode?q=${encodeURIComponent(query)}`);
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
            alert('Please select a city from the suggestions');
            cityInput.focus();
            return;
        }
    }
    
    // Check limit
    if (previews.length >= MAX_PREVIEWS) {
        alert(`Maximum ${MAX_PREVIEWS} previews reached. Remove one to generate a new one.`);
        return;
    }
    
    // Get settings - convert cm to inches for backend
    const sizeValue = sizeSelect.value;
    const [widthCm, heightCm] = sizeValue.split('x').map(Number);
    const width = cmToInches(widthCm);
    const height = cmToInches(heightCm);
    
    const settings = {
        city: selectedCity,
        country: selectedCountry,
        theme: selectedTheme,
        distance: parseInt(distanceSelect.value),
        width: width,
        height: height
    };
    
    // Show loading
    showLoading();
    generateBtn.classList.add('loading');
    generateBtn.disabled = true;
    updateProgress(0, 6, 'Starting...');
    
    try {
        // Start the job
        const startResponse = await fetch((window.API_BASE || '') + '/api/preview/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const startResult = await startResponse.json();
        
        if (!startResponse.ok) {
            const errorDetail = startResult.detail;
            const errorMsg = Array.isArray(errorDetail) 
                ? errorDetail.map(e => e.msg || e.message || JSON.stringify(e)).join(', ')
                : (errorDetail || 'Failed to start preview');
            throw new Error(errorMsg);
        }
        
        const jobId = startResult.job_id;
        
        // Poll for progress
        let complete = false;
        while (!complete) {
            await new Promise(r => setTimeout(r, 200));
            
            const progressResponse = await fetch((window.API_BASE || '') + `/api/progress/${jobId}`);
            const progress = await progressResponse.json();
            
            updateProgress(progress.step, progress.total, progress.message);
            
            if (progress.status === 'complete') {
                complete = true;
                
                // Add to previews (prepend API base for cross-origin images)
                const apiBase = window.API_BASE || '';
                const preview = {
                    id: jobId,
                    url: apiBase + progress.preview_url,
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
        const errorMsg = error.message || (typeof error === 'object' ? JSON.stringify(error) : String(error));
        alert(`Error: ${errorMsg}`);
        hideLoading();
    } finally {
        generateBtn.classList.remove('loading');
        generateBtn.disabled = false;
    }
}

function showLoading() {
    loadingOverlay.classList.add('active');
    updateProgress(0, 6, 'Starting...');
}

function hideLoading() {
    loadingOverlay.classList.remove('active');
}

function updateProgress(step, total, message) {
    const percent = (step / total) * 100;
    const circumference = 2 * Math.PI * 45;
    const offset = circumference - (percent / 100) * circumference;
    
    progressRing.style.strokeDashoffset = offset;
    progressPercent.textContent = `${step}/${total}`;
    progressText.textContent = `${step}/${total}`;
    progressStatus.textContent = message || `Step ${step} of ${total}`;
}

// ============================================
// Preview Display
// ============================================

function showPreview(preview) {
    const settings = preview.settings;
    const themeName = themes.find(t => t.name === settings.theme)?.display_name || settings.theme;
    
    previewImage.src = preview.url + '?t=' + preview.timestamp;
    previewCity.textContent = `${settings.city}, ${settings.country}`;
    previewMeta.textContent = `${themeName} • ${settings.distance / 1000}km • ${settings.width}×${settings.height}"`;
    
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
    
    showFinalProgress(settings);
    simulateFinalProgress();
    
    try {
        const response = await fetch((window.API_BASE || '') + '/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.detail || 'Generation failed');
        }
        
        completeFinalProgress();
        await new Promise(r => setTimeout(r, 500));
        
        closeFinalProgress();
        showResult(result, settings);
        updateStepIndicators(3);
        
    } catch (error) {
        console.error('Generation error:', error);
        closeFinalProgress();
        alert(`Error: ${error.message}`);
    }
}

// ============================================
// Final Progress Modal
// ============================================

let finalProgressInterval = null;

function showFinalProgress(settings) {
    finalProgressCity.textContent = `${settings.city}, ${settings.country}`;
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

function simulateFinalProgress() {
    let currentStep = 0;
    const steps = document.querySelectorAll('#progressModal .progress-step');
    const totalSteps = steps.length;
    const stepDurations = [500, 3000, 2000, 2000, 5000, 2000];
    
    function advanceStep() {
        if (currentStep > 0 && currentStep <= totalSteps) {
            const prevStep = steps[currentStep - 1];
            prevStep.classList.remove('active');
            prevStep.classList.add('complete');
            prevStep.querySelector('.step-status').textContent = 'Done';
        }
        
        if (currentStep < totalSteps) {
            const step = steps[currentStep];
            step.classList.add('active');
            step.querySelector('.step-status').textContent = 'In progress...';
            
            const progress = ((currentStep + 0.5) / totalSteps) * 100;
            finalProgressBar.style.width = `${progress}%`;
            
            currentStep++;
            const duration = stepDurations[currentStep - 1] || 2000;
            finalProgressInterval = setTimeout(advanceStep, duration);
        }
    }
    
    advanceStep();
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
    const apiBase = window.API_BASE || '';
    const posterUrl = apiBase + result.poster_url;
    
    resultImage.src = posterUrl + '?t=' + Date.now();
    resultCity.textContent = settings.city;
    resultTheme.textContent = `${themeName} • ${settings.width}×${settings.height}"`;
    downloadBtn.href = posterUrl;
    downloadBtn.download = result.filename;
    
    resultModal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeResultModal() {
    resultModal.classList.remove('active');
    document.body.style.overflow = '';
}
