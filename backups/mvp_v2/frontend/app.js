/**
 * MapToPrint Homepage
 * Background showcase, gallery with preview modal
 */

const gallery = document.getElementById('gallery');
const showcaseTrack = document.getElementById('showcaseTrack');
const previewModal = document.getElementById('previewModal');
const previewModalImage = document.getElementById('previewModalImage');
const previewModalCity = document.getElementById('previewModalCity');
const previewModalDesc = document.getElementById('previewModalDesc');
const previewModalCta = document.getElementById('previewModalCta');
const previewModalClose = document.getElementById('previewModalClose');

let examples = [];

document.addEventListener('DOMContentLoaded', () => {
    loadExamples();
    setupModalListeners();
});

async function loadExamples() {
    try {
        const response = await fetch('/api/examples');
        examples = await response.json();
        
        // Setup background showcase
        setupShowcase(examples);
        
        // Render gallery
        renderGallery(examples);
        
    } catch (error) {
        console.error('Failed to load examples:', error);
    }
}

function setupShowcase(items) {
    if (!showcaseTrack || items.length === 0) return;
    
    // Triple the items for seamless infinite scroll
    const allItems = [...items, ...items, ...items];
    
    showcaseTrack.innerHTML = allItems.map((example, index) => `
        <div class="showcase-item" data-index="${index % items.length}">
            <img src="${example.image}" alt="${example.city}" loading="eager">
        </div>
    `).join('');
    
    // Add click handlers for preview
    showcaseTrack.querySelectorAll('.showcase-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.stopPropagation();
            const idx = parseInt(item.dataset.index);
            openPreview(examples[idx]);
        });
    });
}

function renderGallery(items) {
    if (!gallery) return;
    
    gallery.innerHTML = items.map((example, index) => `
        <div class="gallery-item" data-index="${index}">
            <div class="gallery-item-placeholder"></div>
            <img 
                src="${example.image}" 
                alt="${example.city} map poster" 
                loading="lazy"
                decoding="async"
                fetchpriority="low"
                onload="this.parentElement.classList.add('loaded')"
            >
            <div class="gallery-item-overlay">
                <div class="gallery-item-city">${example.city}</div>
                <div class="gallery-item-theme">${example.description}</div>
            </div>
        </div>
    `).join('');
    
    // Click to preview
    gallery.querySelectorAll('.gallery-item').forEach(item => {
        item.addEventListener('click', () => {
            const idx = parseInt(item.dataset.index);
            openPreview(examples[idx]);
        });
    });
}

function openPreview(example) {
    if (!previewModal || !example) return;
    
    // Use the larger preview image if available
    previewModalImage.src = example.preview || example.image;
    previewModalCity.textContent = `${example.city}, ${example.country}`;
    previewModalDesc.textContent = example.description;
    previewModalCta.href = `/generate?city=${encodeURIComponent(example.city)}&country=${encodeURIComponent(example.country)}&theme=${encodeURIComponent(example.theme)}`;
    
    previewModal.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closePreview() {
    previewModal.classList.remove('active');
    document.body.style.overflow = '';
}

function setupModalListeners() {
    if (!previewModal) return;
    
    previewModalClose?.addEventListener('click', closePreview);
    
    previewModal.querySelector('.preview-modal-backdrop')?.addEventListener('click', closePreview);
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && previewModal.classList.contains('active')) {
            closePreview();
        }
    });
}
